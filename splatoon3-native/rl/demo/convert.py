"""Native per-present recording -> private BC shards + explicit reconstruction error.

No optimizer or training. Default sync observes imported native state without
integrating physics; unknown channels carry masks and require --allow-approximate.
The old hybrid integrator is explicit diagnostic-only, separate from free audit.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import torch
from rl.gpu.contract import Config, MOVE_DIRECTIONS, camera_levels
from rl.gpu.env import (
    ParallelEnv,
    YAW,
    PITCH,
    HEADING,
    HP,
    INK,
    GAUGE,
    SQUID,
    SUB,
    GROUND,
    RESPAWN,
    ARM,
)
from rl.demo.capture import safe_out, write


def wrap(x):
    return math.atan2(math.sin(x), math.cos(x))


def quantize(action, cfg, camera, previous):
    xy = np.asarray(action["sticks"][:2])
    moves = np.asarray(MOVE_DIRECTIONS)
    move = int(np.square(moves - xy).sum(1).argmin())
    levels_camera = camera_levels(cfg)
    turn = cfg.gyro_max_radians_per_frame + cfg.stick_plus5_radians_per_frame
    native = np.asarray([*action["sticks"][2:], *action["gyro"]], float)
    from .camera_model import predict

    delta = predict(native, camera)
    indices = [
        int(np.abs(np.asarray(levels_camera) * turn - v).argmin()) for v in delta
    ]
    b = action["buttons"]
    levels = [move, *indices, b[0], b[1], b[4], b[2], b[3]]
    command = levels.copy()
    for head in (3, 4):
        command[head] = (
            0 if levels[head] == previous[head] else 1 if levels[head] else 2
        )
    err = dict(
        move_l2=float(np.linalg.norm(moves[move] - xy)),
        camera_radians_per_frame=(
            np.asarray(levels_camera)[indices] * turn - delta
        ).tolist(),
        camera_clipped=(abs(delta) > turn).tolist(),
        unrepresented_Y=bool(b[5]),
        unrepresented_X=bool(action.get("observer_buttons", [0])[0]),
    )
    return levels, command, err


def camera_windows(inputs, barriers):
    # Native sample times, not ACK times. Discard intervals containing spawn/death.
    X = []
    Y = []
    roles = [{}, {}]
    for row in barriers:
        for n in range(2):
            p = f"player_{n}"
            i = row["infos"][p]
            v = i.get("own_view", {})
            if (
                i.get("position_valid")
                and i.get("alive")
                and i["position"][1] < 20
                and v.get("valid")
            ):
                f = i["position_sample_frame"] - barriers[0]["infos"][p]["frame"]
                roles[n].setdefault(f, [v["yaw"], v["pitch"]])
    for n, samples in enumerate(roles):
        for f, g in zip(sorted(samples), sorted(samples)[1:]):
            if not 0 <= f < g <= len(inputs) or g - f > 8:
                continue
            acts = [inputs[k]["actions"][f"player_{n}"] for k in range(f, g)]
            x = np.asarray([[*a["sticks"][2:], *a["gyro"]] for a in acts])
            # Constant windows suppress native smoothing/edge lag from crude linear fit.
            if np.ptp(x, axis=0).max() > 1e-5:
                continue
            dy = [wrap(samples[g][0] - samples[f][0]), samples[g][1] - samples[f][1]]
            X.append(x.mean(0))
            Y.append(np.asarray(dy) / (g - f))
    if len(X) < 10:
        raise ValueError("not enough native camera calibration windows")
    return np.asarray(X), np.asarray(Y)


def fit_camera(inputs, barriers):
    X, Y = camera_windows(inputs, barriers)
    coef = np.linalg.lstsq(X, Y, rcond=None)[0].T
    residual = Y - X @ coef.T
    return dict(
        matrix=coef.tolist(),
        input_columns=[
            "rx",
            "ry",
            "gyro_x_turns_s",
            "gyro_y_turns_s",
            "gyro_z_turns_s",
        ],
        output_columns=["delta_yaw_rad_per_frame", "delta_pitch_rad_per_frame"],
        samples=len(X),
        rank=int(np.linalg.matrix_rank(X)),
        rmse_radians_per_frame=np.sqrt(np.mean(residual**2, axis=0)).tolist(),
        scope="Linear steady-input diagnostic fitted on this scripted corpus, not a held-out dynamic response calibration",
    )


def evaluate_camera(camera, inputs, barriers):
    X, Y = camera_windows(inputs, barriers)
    residual = Y - X @ np.asarray(camera["matrix"]).T
    return dict(
        samples=len(X),
        rank=int(np.linalg.matrix_rank(X)),
        rmse_radians_per_frame=np.sqrt(np.mean(residual**2, axis=0)).tolist(),
        scope="Fixed external matrix on this held-out corpus; no coefficient refitting. Constant-input windows only, not arbitrary dynamic/physical gyro calibration.",
    )


def anchored(env, row, origins):
    ages = []
    valid = []
    for n in range(2):
        p = f"player_{n}"
        i = row["infos"][p]
        s = env.state[0, n]
        v = i.get("own_view", {})
        age = i["frame"] - i.get("position_sample_frame", i["frame"])
        ages.append(age)
        good = bool(
            i.get("position_valid")
            and v.get("valid")
            and i.get("hp_valid")
            and i.get("ink_valid")
            and age <= 8
        )
        valid.append(good)
        if not good:
            continue
        s[:3] = torch.as_tensor(i["position"], device=env.device)
        s[YAW] = v["yaw"]
        s[PITCH] = v["pitch"]
        s[HEADING] = i.get("heading", v["yaw"])
        s[HP] = i["hp"]
        s[INK] = i["ink"]
        s[GAUGE] = i.get("special", 0)
        m = i.get("referee_motion", {})
        s[SQUID] = int(m.get("form_squid") == 1)
        s[SUB] = int(m.get("form_squid") == 1 and m.get("ground_contact") == 0)
        s[GROUND] = int(m.get("ground_contact") != 5)
        s[RESPAWN] = 0 if i.get("alive") else max(1, float(s[RESPAWN]))
        s[ARM] = -1 if i.get("alive") else -2
    return valid, ages


def stats(v):
    v = np.asarray(v, float)
    return (
        dict(
            n=int(v.size),
            mean=float(v.mean()),
            p95=float(np.percentile(v, 95)),
            max=float(v.max()),
        )
        if v.size
        else dict(n=0)
    )


def legacy_convert(a):
    torch.set_num_threads(a.cpu_threads)
    source = Path(a.recording).resolve()
    out = safe_out(a.out)
    if out.exists():
        raise ValueError("fresh output directory required")
    if not a.allow_approximate:
        raise ValueError(
            "native dense ink/projectile reconstruction incomplete; explicit --allow-approximate required, no silent BC-ready claim"
        )
    inputs = [json.loads(x) for x in (source / "inputs-per-present.jsonl").open()]
    rows = [json.loads(x) for x in (source / "native-barriers.jsonl").open()]
    result = json.loads((source / "result.json").read_text())
    if result["weapons"] != [8000, 50]:
        raise ValueError(
            "current GPU pair supports stamper vs .52 only; keep policy-opponent corpus archived, do not relabel a Stamper as .52"
        )
    if not rows or len(rows) != len(inputs) + 1:
        raise ValueError("missing barrier coverage")
    for f, r in enumerate(inputs):
        if r["frame_interval"] != [f, f + 1] or rows[f]["frame"] != f:
            raise ValueError("recording gaps/overlaps")
    camera = (
        json.loads(Path(a.camera).read_text()) if a.camera else fit_camera(inputs, rows)
    )
    conf = json.loads(Path(a.calibration).read_text())
    cfg = Config(
        **conf.get("config", conf), decision_frames=1, loadout_mode="primary_only"
    )
    if result["loadout_mode"] != "primary_only":
        raise ValueError(
            "full equipment conversion is not BC-qualified; .52 sub/special still unimplemented"
        )
    out.mkdir(parents=True, mode=0o700)
    write(out / "camera-response.json", camera)
    env = ParallelEnv(a.data, cfg, device=a.device)
    free = ParallelEnv(a.data, cfg, device=a.device)
    # Replay needs public observations only at exported BC boundaries. Keep
    # the exact environment physics/step; suppress unused per-frame ray work.
    observe = env._observation
    env._observation = lambda *args: None
    free._observation = lambda *args: None
    origins = rows[0]["infos"]
    first = next(
        (
            f
            for f, r in enumerate(rows)
            if all(
                i.get("position_valid")
                and i.get("alive")
                and i["position"][1] < 20
                and i.get("own_view", {}).get("valid")
                and i.get("referee_motion", {}).get("ground_contact") == 0
                for i in r["infos"].values()
            )
        ),
        None,
    )
    if first is None:
        raise ValueError(
            "no common grounded initialization; cannot replace native spawner flight with invented GPU states"
        )
    anchored(env, rows[first], origins)
    anchored(free, rows[first], origins)
    env.steps[:] = first
    free.steps[:] = first
    prev = [0, 4, 4, 0, 0, 0, 0, 0]
    shard = []
    errors = []
    role_errors = [[], []]
    position = [[], []]
    hp = [[], []]
    ink = [[], []]
    seen = [set(), set()]
    ages_all = []
    unrepresented = 0
    labels = 0

    def flush():
        nonlocal shard
        if not shard:
            return
        index = len(list(out.glob("bc-*.npz")))
        arrays = {k: np.stack([r[k] for r in shard]) for k in shard[0]}
        np.savez_compressed(out / f"bc-{index:05d}.npz", **arrays)
        shard = []

    stop = min(len(inputs), a.max_frames or len(inputs))
    for f in range(first, stop):
        if any(
            i["phase"] != 1 or (i.get("time_valid") and i.get("remaining_time", 1) <= 0)
            for i in rows[f]["infos"].values()
        ):
            break
        # Only the past/current native packet is anchored; no future state enters obs.
        valid, ages = anchored(env, rows[f], origins)
        ages_all.extend(ages)
        actions = []
        commands = []
        q = []
        for n in range(2):
            lv, cmd, err = quantize(
                inputs[f]["actions"][f"player_{n}"],
                cfg,
                camera,
                prev if n == 0 else [0, 4, 4, 0, 0, 0, 0, 0],
            )
            actions.append(lv)
            commands.append(cmd)
            q.append(err)
        if f % a.stride == 0:
            obs = observe(env.state, env.shots, env.paint, env.steps)
            # Toggle label is relative to the last exported physical level, not last frame.
            lv, cmd, err = quantize(inputs[f]["actions"]["player_0"], cfg, camera, prev)
            record = {k: v[0, 0].detach().cpu().numpy() for k, v in obs.items()}
            record.update(
                previous_physical_actions=np.asarray(prev, np.int64),
                frame=np.array(f, np.int64),
                actions=np.asarray(cmd, np.int64),
                physical_actions=np.asarray(lv, np.int64),
                state_valid=np.asarray(valid[0]),
                source_age_frames=np.asarray(ages[0], np.int16),
                dense_paint_native_valid=np.asarray(False),
                projectiles_native_valid=np.asarray(False),
            )
            # Translate the allowed level mask to the actual toggle command mask.
            from rl.gpu.stage1.controller import command_mask

            record["action_mask"] = (
                command_mask(
                    obs["action_mask"][0, 0],
                    torch.as_tensor(prev, device=env.device),
                    "toggle",
                )
                .cpu()
                .numpy()
            )
            shard.append(record)
            prev = lv
            labels += 1
            if len(shard) >= a.shard_size:
                flush()
        errors.extend(q)
        for n in range(2):
            role_errors[n].append(q[n])
        unrepresented += int(q[0]["unrepresented_Y"])
        tensor = torch.as_tensor([actions], device=env.device)
        env.step(tensor)
        free.step(tensor)
        # Compare each native field at its source sample frame, not the ACK frame.
        # Retain free snapshots until delayed native samples arrive.
        if f == first:
            snapshots = {}
        snapshots[f + 1] = free.state[0].detach().cpu().numpy().copy()
        for n in range(2):
            i = rows[f + 1]["infos"][f"player_{n}"]
            sample = (
                i.get("position_sample_frame", -1) - origins[f"player_{n}"]["frame"]
            )
            if (
                sample in snapshots
                and sample not in seen[n]
                and i.get("position_valid")
            ):
                seen[n].add(sample)
                s = snapshots[sample][n]
                position[n].append(float(np.linalg.norm(s[:3] - i["position"])))
                if i.get("hp_valid"):
                    hp[n].append(abs(float(s[HP]) - i["hp"]))
                if i.get("ink_valid"):
                    ink[n].append(abs(float(s[INK]) - i["ink"]))
        snapshots = {k: v for k, v in snapshots.items() if k >= f - 120}
        if f % 600 == 0:
            print(json.dumps(dict(frame=f, labels=labels)), flush=True)
    flush()
    native_turf = result.get("turf_ratio_by_role", {}).get("player_0")
    free_turf = [
        float((free.paint == i).sum().item() / free.paint_count) for i in range(2)
    ]
    turf_error = (
        [100 * (x - y) for x, y in zip(free_turf, native_turf)] if native_turf else None
    )
    report = dict(
        final_native_turf_ratio=native_turf,
        free_rollout_turf_ratio=free_turf,
        turf_error_percentage_points=turf_error,
        schema="inklab.rl.demo.bc.v1",
        ready_for_training=False,
        training_started=False,
        source=result["source"],
        first_ground_frame=first,
        last_frame=f + 1,
        decision_stride=a.stride,
        samples=labels,
        button_semantics="toggle for ZR/ZL; physical holds retained",
        camera_response=camera,
        quantization_scope="Stamper only, physical input -> levels; camera linear surrogate fitted from native sample windows",
        quantization=dict(
            move_l2=stats([e["move_l2"] for e in role_errors[0]]),
            camera_abs_deg_per_frame=stats(
                [
                    abs(x) * 180 / math.pi
                    for e in role_errors[0]
                    for x in e["camera_radians_per_frame"]
                ]
            ),
            camera_clipped_fraction=float(
                np.mean([any(e["camera_clipped"]) for e in role_errors[0]])
            ),
            unrepresented_Y_frames=unrepresented,
        ),
        open_loop_native_error={
            str(n): dict(
                position_units=stats(position[n]),
                hp_fraction=stats(hp[n]),
                ink_fraction=stats(ink[n]),
            )
            for n in range(2)
        },
        source_state_age_frames=stats(ages_all),
        native_dense_paint_available=False,
        projectile_reconstruction="simulated, no qualified native correspondence",
        observation_schedule="Full public observation at each exported BC boundary only; unchanged environment.step physics at every native frame; unused free-rollout observations omitted",
        observations="BC: current/past native position/view/HP/ink anchor + simulator dynamics/paint/projectiles; public ray/entity visibility masking only. Separate free rollout never corrected after initialization.",
        limitations=[
            "Native dense paint unavailable: minimap and ray ink are approximate, not BC-qualified.",
            "Native projectile/weapon internal state not fully imported.",
            "Original spawner flight omitted explicitly.",
            "Quantization and geometry/dynamic mismatch accumulate; do not treat as native parity.",
        ],
        source_sha256={
            name: hashlib.sha256((source / name).read_bytes()).hexdigest()
            for name in [
                "inputs-per-present.jsonl",
                "native-barriers.jsonl",
                "result.json",
            ]
        },
    )
    write(out / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def convert(a):
    if getattr(a, "observation_mode", "sync") == "hybrid":
        return legacy_convert(a)
    from .bc_sync import convert_synced

    return convert_synced(a)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--recording", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--data", default="work/rl-stage0/data-v5")
    p.add_argument(
        "--calibration", default="work/rl-stage0/native-camera-calibration-v1.json"
    )
    p.add_argument("--camera")
    p.add_argument("--allow-approximate", action="store_true")
    p.add_argument("--device", default="cpu")
    p.add_argument("--cpu-threads", type=int, default=1)
    p.add_argument("--stride", type=int, default=2)
    p.add_argument(
        "--sample-offset",
        type=int,
        help="sync-only: fixed sampling phase; default aligns periodic native ink",
    )
    p.add_argument("--shard-size", type=int, default=256)
    p.add_argument("--max-frames", type=int)
    p.add_argument("--observation-mode", choices=["sync", "hybrid"], default="sync")
    convert(p.parse_args())
