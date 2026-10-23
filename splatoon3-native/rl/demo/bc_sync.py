"""Native-state-only BC export; derived sensor gaps fail readiness explicitly."""

import hashlib, json, math, time
from pathlib import Path
import numpy as np
import torch
from rl.gpu.contract import Config
from rl.gpu.env import ParallelEnv
from rl.demo.capture import safe_out, write
from rl.demo.state_sync import NativeRebuilder, read_jsonl


def convert_synced(a):
    from .convert import quantize, fit_camera, stats
    from rl.gpu.stage1.controller import command_mask

    torch.set_num_threads(a.cpu_threads)
    source = Path(a.recording).resolve()
    out = safe_out(a.out)
    if out.exists():
        raise ValueError("fresh output directory required")
    result = json.loads((source / "result.json").read_text())
    rows = read_jsonl(source / "native-barriers.jsonl")
    inputs = read_jsonl(source / "inputs-per-present.jsonl")
    if result["weapons"] != [8000, 50] or result["loadout_mode"] != "primary_only":
        raise ValueError(
            "BC pair must be primary-only stamper vs .52; never relabel policy weapons"
        )
    if len(rows) != len(inputs) + 1 or any(
        x["frame_interval"] != [f, f + 1] or rows[f]["frame"] != f
        for f, x in enumerate(inputs)
    ):
        raise ValueError("recording gaps/overlaps")
    # Qualifying full truth must precede allowing unmasked training export.
    if not a.allow_approximate:
        raise ValueError(
            "native paint/weapon/projectile completeness not qualified; explicit --allow-approximate required"
        )
    camera = (
        json.loads(Path(a.camera).read_text()) if a.camera else fit_camera(inputs, rows)
    )
    conf = json.loads(Path(a.calibration).read_text())
    cfg = Config(
        **(
            conf.get("config", conf)
            | dict(decision_frames=1, loadout_mode="primary_only")
        )
    )
    from dataclasses import replace
    from rl.gpu.contract import camera_levels

    cfg = replace(
        cfg, camera_codebook=camera.get("recommended_codebook", cfg.camera_codebook)
    )
    out.mkdir(parents=True, mode=0o700)
    write(out / "camera-response.json", camera)
    env = ParallelEnv(a.data, cfg, device=a.device)
    rebuilder = NativeRebuilder(env, source, rows[0]["infos"])
    offset = sampling_phase(
        a.stride, rebuilder.ink.index.rows, getattr(a, "sample_offset", None)
    )
    batch_size = 32
    batch = ParallelEnv(a.data, cfg, device=a.device, n_envs=batch_size)
    pending = []
    shard = []
    all_quality = []
    errors = []
    skipped = 0
    seen = [set(), set()]
    labels = 0
    wall = time.monotonic()
    prev = [0, 4, 4, 0, 0, 0, 0, 0]
    first = None

    def flush_shard():
        nonlocal shard
        if shard:
            np.savez_compressed(
                out / f"bc-{len(list(out.glob('bc-*.npz'))):05d}.npz",
                **{k: np.stack([r[k] for r in shard]) for k in shard[0]},
            )
            shard = []

    def observe_batch():
        nonlocal pending, shard, labels
        if not pending:
            return
        count = len(pending)
        padded = pending + [pending[-1]] * (batch_size - count)
        state = torch.cat([x["state"] for x in padded])
        frames = torch.as_tensor([x["frame"] for x in padded], device=env.device)
        cam = (
            tuple(torch.cat([x["camera"][i] for x in padded]) for i in range(4))
            if all(x["camera"] is not None for x in padded)
            else None
        )
        obs = batch._observe(
            state,
            torch.cat([x["shots"] for x in padded]),
            batch.paint,
            frames,
            camera_override=cam,
        )
        for j, x in enumerate(pending):
            q = x["quality"]
            i = x["info"]
            single = {k: v[j : j + 1] for k, v in obs.items()}
            single_camera = (
                tuple(v[j : j + 1] for v in cam) if cam is not None else None
            )
            cutoff = i["frame"] - rows[0]["infos"]["player_0"]["frame"] - 1
            ink_valid, minimap_valid = rebuilder.ink.overlay(
                single, single_camera, cutoff
            )
            record = {k: v[j, 0].detach().cpu().numpy() for k, v in obs.items()}
            if i.get("time_valid"):
                record["hud"][6] = i["remaining_time"]
            hud_valid = np.array(
                [
                    i.get("ink_valid", False),
                    i.get("special_valid", False),
                    i.get("referee_motion", {}).get("form_squid", -1) >= 0,
                    i.get("referee_motion", {}).get("ground_contact", -1) >= 0,
                    q["weapon_native_valid"][0],
                    True,
                    i.get("time_valid", False),
                    False,
                    False,
                    i.get("hp_valid", False),
                ],
                dtype=bool,
            )
            record.update(
                previous_physical_actions=np.array(x["previous"], np.int64),
                frame=np.array(x["frame"], np.int64),
                actions=np.array(x["command"], np.int64),
                physical_actions=np.array(x["physical"], np.int64),
                state_valid=np.array(q["state_valid"][0]),
                source_age_frames=np.array(q["source_age_frames"][0], np.int16),
                native_camera_valid=np.array(cam is not None),
                hud_valid=hud_valid,
                screen_channel_valid=np.broadcast_to(
                    np.array([True, True, False, True]), (18, 32, 4)
                ).copy(),
                minimap_valid=minimap_valid[0].cpu().numpy(),
                dense_paint_native_valid=np.array(False),
                projectiles_native_valid=np.array(q["projectiles_native_valid"]),
                weapon_native_valid=np.array(q["weapon_native_valid"][0]),
                weapon_stage_id=np.array(
                    q.get("weapon_details", [{}])[0].get("weapon_stage_id", -1),
                    np.int16,
                ),
                weapon_animation_remaining_frames=np.array(
                    q.get("weapon_details", [{}])[0].get(
                        "animation_deadline_remaining_frames", -1
                    ),
                    np.float32,
                ),
                action_labels_trainable=np.array(
                    result.get("action_labels_trainable", True)
                    and not result.get("direct_aim", False)
                ),
                entities_complete=np.array(False),
                entity_velocity_native_valid=np.array(False),
                position_import_error_u=np.array(
                    max(q["position_import_residual"], default=0)
                ),
                observation_mode=np.array(1, np.uint8),
            )
            record["screen_channel_valid"][..., 2] = ink_valid[0].cpu().numpy()
            record["action_mask"] = (
                command_mask(
                    obs["action_mask"][j, 0],
                    torch.as_tensor(x["previous"], device=env.device),
                    "toggle",
                )
                .cpu()
                .numpy()
            )
            shard.append(record)
            labels += 1
            if len(shard) >= a.shard_size:
                flush_shard()
        pending = []

    stop = min(len(inputs), a.max_frames or len(inputs))
    export_stop = stop
    for f in range(stop):
        row = rows[f]
        if any(
            i.get("time_valid") and i.get("remaining_time", 1) <= 0
            for i in row["infos"].values()
        ):
            export_stop = f
            break
        if any(i["phase"] != 1 for i in row["infos"].values()):
            if first is not None:
                export_stop = f
                break
            continue
        quality, cam = rebuilder.sync(row)
        if not all(quality["state_valid"]):
            skipped += 1
            continue
        if first is None:
            first = f
        # Repeated packets remain available in the corpus but not duplicated as
        # independent position measurements in aggregate source coverage.
        for n in range(2):
            seen[n].add(row["infos"][f"player_{n}"]["position_sample_frame"])
        lv, cmd, err = quantize(inputs[f]["actions"]["player_0"], cfg, camera, prev)
        errors.append(err)
        if f % a.stride != offset:
            continue
        pending.append(
            dict(
                state=env.state.clone(),
                shots=env.shots.clone(),
                camera=cam,
                quality=quality,
                frame=f,
                info=row["infos"]["player_0"],
                previous=prev.copy(),
                physical=lv,
                command=cmd,
            )
        )
        prev = lv
        all_quality.append(quality)
        if len(pending) >= batch_size:
            observe_batch()
        if f % 600 == 0:
            print(json.dumps(dict(frame=f, labels=labels)), flush=True)
    observe_batch()
    flush_shard()
    gates = dict(
        complete_native_match=bool(result["complete"] and not result["errors"]),
        causal_state_available=bool(
            all_quality and all(all(x["state_valid"]) for x in all_quality)
        ),
        state_physics_free=True,
        native_dense_paint=False,
        native_weapon_stage=bool(
            all_quality and all(all(x["weapon_native_valid"]) for x in all_quality)
        ),
        native_projectile_active_set=False,
        camera_axes_calibration_rank5=camera.get("rank", 0) == 5,
        accepted_stage0_geometry_contract=True,
        causal_native_camera_available=bool(
            all_quality and all(all(q["camera_native_valid"]) for q in all_quality)
        ),
        script_not_human=result["source"] != "human_USB",
        no_direct_aim_action_labels=not result.get("direct_aim", False),
    )
    # Script is useful pipeline QA but not a human skill demonstration.
    ready = all(v for k, v in gates.items() if k != "script_not_human")
    report = dict(
        schema="inklab.rl.demo.bc.v2",
        observation_mode="native_state_sync_only",
        ready_for_training=ready,
        training_started=False,
        source=result["source"],
        samples=labels,
        decision_stride=a.stride,
        sample_offset=offset,
        camera_codebook=cfg.camera_codebook,
        camera_levels=list(camera_levels(cfg)),
        first_state_frame=first,
        last_frame_exclusive=export_stop,
        source_frames=len(inputs),
        invalid_packet_frames_skipped=skipped,
        native_source_samples=[len(x) for x in seen],
        physics_steps_for_bc=0,
        position_import_error_units=stats(
            [x for q in all_quality for x in q["position_import_residual"]]
        ),
        source_state_age_frames=stats(
            [x for q in all_quality for x in q["source_age_frames"]]
        ),
        native_camera_available_fraction=float(
            np.mean([all(q["camera_native_valid"]) for q in all_quality])
        )
        if all_quality
        else 0,
        readiness_gates=gates,
        blocked_gates=[k for k, v in gates.items() if not v],
        quantization=dict(
            move_l2=stats([e["move_l2"] for e in errors]),
            camera_abs_deg_per_frame=stats(
                [
                    abs(x) * 180 / math.pi
                    for e in errors
                    for x in e["camera_radians_per_frame"]
                ]
            ),
            camera_clipped_fraction=float(
                np.mean([any(e["camera_clipped"]) for e in errors])
            )
            if errors
            else None,
        ),
        camera_response=camera,
        free_rollout="separate dynamics audit; never used to build BC observations",
        unknown_contract="Validity masks must be honored; false paint/projectile/weapon fields are placeholders, not neutral/idle/empty truth.",
        camera_contract="Native eye/at direction when all batch cameras causal+valid; fallback batches have native_camera_valid=false. FOV remains stage0 assumption.",
        wall_seconds=time.monotonic() - wall,
        source_sha256={
            f: hashlib.sha256((source / f).read_bytes()).hexdigest()
            for f in [
                "result.json",
                "inputs-per-present.jsonl",
                "native-barriers.jsonl",
                "cameras.jsonl",
                "native-state.jsonl",
                "native-weapon.jsonl",
                "native-projectiles.jsonl",
                "native-ink.json",
            ]
            if (source / f).exists()
        },
    )
    write(out / "report.json", report)
    print(json.dumps(report, indent=2))
    return report


def sampling_phase(stride, snapshots, override=None):
    if stride < 1 or (override is not None and not 0 <= override < stride):
        raise ValueError("sample offset must be in [0,stride)")
    if override is not None:
        return override
    # Atlas frame f is available for observation f+1. Avoid an even period
    # silently missing every snapshot when the default decision stride is 2.
    # This chooses a fixed phase, never holds paint or uses future image values.
    counts = np.zeros(stride, dtype=int)
    for row in snapshots:
        if row["frame"] >= 0:
            counts[(row["frame"] + 1) % stride] += 1
    return int(counts.argmax())
