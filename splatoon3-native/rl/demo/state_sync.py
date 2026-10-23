"""Causal native-state import for observations; never advance simulator physics.

Unknown dense paint/weapon/projectile fields are explicit masks, not fake truth.
Native sidecars are joined strictly before the ACK frame, never from the future.
"""

import bisect
import json
from pathlib import Path
import numpy as np
import torch
from rl.gpu.env import (
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
    CHARGE,
    COOL,
)


class CausalIndex:
    def __init__(self, rows):
        self.rows = sorted(rows, key=lambda x: x["frame"])
        self.frames = [x["frame"] for x in self.rows]

    def latest(self, frame, max_age=4):
        at = bisect.bisect_right(self.frames, frame) - 1
        if at < 0 or frame - self.frames[at] > max_age:
            return None
        return self.rows[at]


def read_jsonl(path):
    with Path(path).open() as stream:
        return [json.loads(line) for line in stream]


class NativeRebuilder:
    def __init__(self, env, source, origins):
        self.env = env
        self.origins = origins
        self.previous = {}
        self.last_velocity = {}
        self.camera = []
        path = Path(source) / "cameras.jsonl"
        rows = read_jsonl(path) if path.is_file() else []
        self.camera = [
            CausalIndex([r for r in rows if r["player"] == n]) for n in range(2)
        ]
        self.native = []
        path = Path(source) / "native-state.jsonl"
        rows = read_jsonl(path) if path.is_file() else []
        self.native = [
            CausalIndex([r for r in rows if r["player"] == n]) for n in range(2)
        ]
        path = Path(source) / "native-projectiles.jsonl"
        self.projectiles = CausalIndex(read_jsonl(path) if path.is_file() else [])
        from .native_ink import NativeInk

        self.ink = NativeInk(source, env.geo)
        self.ink.horizontal = env.cfg.camera_horizontal_fov_degrees
        self.ink.vertical = env.cfg.camera_vertical_fov_degrees

    def sync(self, row):
        e = self.env
        s = e.state
        s.zero_()
        e.shots.zero_()
        e.paint.fill_(-1)
        e.steps.fill_(row["frame"])
        valid = []
        ages = []
        camera = []
        fwd = []
        rights = []
        ups = []
        camera_valid = []
        phase_valid = []
        weapon_details = []
        residual = []
        for n in range(2):
            p = f"player_{n}"
            i = row["infos"][p]
            v = i.get("own_view", {})
            age = i["frame"] - i.get("position_sample_frame", i["frame"])
            ages.append(age)
            good = bool(
                i.get("position_valid")
                and v.get("valid")
                and i.get("hp_valid")
                and i.get("ink_valid")
                and 0 <= age <= 4
            )
            valid.append(good)
            if good:
                s[0, n, :3] = torch.as_tensor(i["position"], device=e.device)
                for key, field in [("yaw", YAW), ("pitch", PITCH)]:
                    s[0, n, field] = v[key]
                s[0, n, HEADING] = i.get("heading", v["yaw"])
                s[0, n, HP] = i["hp"]
                s[0, n, INK] = i["ink"]
                s[0, n, GAUGE] = i.get("special", 0)
                m = i.get("referee_motion", {})
                sq = m.get("form_squid")
                contact = m.get("ground_contact")
                s[0, n, SQUID] = int(sq == 1)
                s[0, n, SUB] = int(sq == 1 and contact == 0)
                s[0, n, GROUND] = int(contact in (0, 4))
                s[0, n, RESPAWN] = 0 if i.get("alive") else 1
                sf = i["position_sample_frame"]
                old = self.previous.get(p)
                if old and sf > old[0]:
                    self.last_velocity[p] = (np.array(i["position"]) - old[1]) / (
                        sf - old[0]
                    )
                if p in self.last_velocity:
                    s[0, n, 3:6] = torch.as_tensor(
                        self.last_velocity[p], device=e.device
                    )
                if not old or sf > old[0]:
                    self.previous[p] = (sf, np.array(i["position"]))
                residual.append(
                    float(
                        torch.linalg.vector_norm(
                            s[0, n, :3]
                            - torch.as_tensor(i["position"], device=e.device)
                        )
                    )
                )
            # Sidecar events from native frame f are emitted before ACK(f+1).
            relative = i["frame"] - self.origins[p]["frame"]
            cutoff = relative - 1
            c = self.camera[n].latest(cutoff, 4)
            cg = False
            if c:
                eye = np.asarray(c["eye"])
                at = np.asarray(c["at"])
                d = at - eye
                norm = np.linalg.norm(d)
                cg = bool(np.isfinite([eye, at]).all() and norm > 0.1 and norm < 100)
            camera_valid.append(cg)
            if cg:
                d = d / norm
                r = np.cross([0, 1, 0], d)
                r /= max(np.linalg.norm(r), 1e-8)
                u = np.cross(d, r)
                camera.append(eye)
                fwd.append(d)
                rights.append(r)
                ups.append(u)
                s[0, n, YAW] = c["yaw"]
                s[0, n, PITCH] = c["pitch"]
            else:
                camera.append([0, 0, 0])
                fwd.append([0, 0, 1])
                rights.append([1, 0, 0])
                ups.append([0, 1, 0])
            native = self.native[n].latest(cutoff, 4)
            wv = bool(native and native.get("weapon_phase_qualified"))
            phase_valid.append(wv)
            weapon_details.append(
                {
                    k: native.get(k)
                    for k in [
                        "weapon_stage_id",
                        "charge_native_frames",
                        "animation_deadline_remaining_frames",
                        "cooldown_lock_qualified",
                    ]
                }
                if wv
                else {}
            )
            if wv:
                s[0, n, CHARGE] = native["charge_frames"]
                s[0, n, COOL] = native["cooldown_frames"]
        override = (
            tuple(
                torch.as_tensor(np.asarray([x]), device=e.device, dtype=torch.float32)
                for x in [camera, fwd, rights, ups]
            )
            if all(camera_valid)
            else None
        )
        # Local native world0 primary bullets only. A past tick may NOT be
        # carried forward: it may already have hit/released in the missing tick.
        cutoff = (
            row["infos"]["player_0"]["frame"] - self.origins["player_0"]["frame"] - 1
        )
        projectile = self.projectiles.latest(cutoff, 0)
        pq = bool(
            projectile
            and projectile.get("primary_projectile_set_qualified")
            and projectile.get("observer") == 0
        )
        if pq:
            slots = [0, 0]
            for bullet in projectile["projectiles"]:
                owner = bullet["owner"]
                slot = slots[owner]
                slots[owner] += 1
                if slot >= 8:
                    pq = False
                    e.shots.zero_()
                    break
                q = e.shots[0, owner, slot]
                q[:3] = torch.as_tensor(bullet["position"], device=e.device)
                q[3:6] = torch.as_tensor(bullet["velocity"], device=e.device)
                q[6] = bullet["age_frames"]
                q[8] = bullet["damage"]
                q[9] = bullet["kind"]
                q[10] = 1
        quality = dict(
            state_valid=valid,
            source_age_frames=ages,
            camera_native_valid=camera_valid,
            weapon_native_valid=phase_valid,
            weapon_details=weapon_details,
            dense_paint_native_valid=False,
            projectiles_native_valid=pq,
            projectile_observer_valid=[pq, False],
            position_import_residual=residual,
            physics_steps=0,
            entity_velocity_native_valid=False,
        )
        return quality, override

    def observe(self, row):
        q, cam = self.sync(row)
        e = self.env
        obs = e._observe(e.state, e.shots, e.paint, e.steps, camera_override=cam)
        # Timer is a native HUD field, not elapsed ACK count (Ready!/Go! differs).
        for n in range(2):
            i = row["infos"][f"player_{n}"]
            if i.get("time_valid"):
                obs["hud"][0, n, 6] = i["remaining_time"]
        # Values remain representable by the existing network. False validity
        # masks, not neutral-color placeholders, determine whether usable.
        q["camera_override_used"] = cam is not None
        q["screen_color_valid"] = False
        q["minimap_valid"] = False
        q["entity_projectiles_complete"] = False
        cutoff = (
            row["infos"]["player_0"]["frame"] - self.origins["player_0"]["frame"] - 1
        )
        screen_valid, minimap_valid = self.ink.overlay(obs, cam, cutoff)
        q["screen_ink_valid_mask"] = screen_valid
        q["minimap_valid_mask"] = minimap_valid
        q["screen_color_valid"] = bool(screen_valid[0].any())
        q["minimap_valid"] = bool(minimap_valid[0].any())
        return obs, q
