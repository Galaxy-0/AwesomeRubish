"""Recording-only .52 sparring partner; receives filtered policy JSON, no truth.

Knobs are human-like design choices, not measurements of human skill. One action
is held until the next decision. Only native controller input is emitted.
"""

from dataclasses import asdict, dataclass
import math
import random
import numpy as np
from arena.lib.skills import Skills, aim_at, neutral, own_state, wrap


@dataclass(frozen=True)
class Parameters:
    reaction_frames: int
    reaction_jitter: int
    memory_frames: int
    aim_tau: float
    yaw_degrees_s: float
    error_degrees: float
    error_distance: float
    error_lateral: float
    lead_fraction: float
    strafe_speed: float
    strafe_period: tuple[int, int]
    comfort: tuple[float, float]
    fire_cone_degrees: float
    retreat_hp: float
    low_ink: float
    jump_chance: float
    paint_duty: float
    cover: bool = False
    half_fov_degrees: float = 43.0
    sense_range: float = 35.0
    fire_range: float = 13.4
    gun_pitch_bias: float = 0.0870194305
    gun_pitch_scale: float = 1.27970519
    burst_frames: int = 24
    settle_frames: int = 18


# 60 native frames/s; delays ~350/250/170ms plus uniform jitter and decision cadence.
LEVELS = {
    "easy": Parameters(
        21,
        4,
        60,
        0.45,
        90,
        7.5,
        1.8,
        0.22,
        0.0,
        0.65,
        (66, 120),
        (7.0, 10.0),
        22,
        0.30,
        0.22,
        0.03,
        0.48,
        burst_frames=6,
        settle_frames=42,
    ),
    "medium": Parameters(
        15,
        3,
        108,
        0.30,
        140,
        4.0,
        1.2,
        0.13,
        0.0,
        0.80,
        (42, 84),
        (8.0, 11.0),
        16,
        0.42,
        0.24,
        0.05,
        0.62,
    ),
    "hard": Parameters(
        10,
        2,
        150,
        0.20,
        200,
        2.0,
        0.8,
        0.08,
        0.35,
        0.95,
        (30, 66),
        (8.5, 11.5),
        12,
        0.48,
        0.26,
        0.07,
        0.70,
        True,
        burst_frames=45,
        settle_frames=9,
    ),
}


def clip(x, lo, hi):
    return max(lo, min(hi, x))


def world_stick(vector, yaw, strength):
    dx, dz = vector
    length = math.hypot(dx, dz)
    if length < 1e-6:
        return [0.0, 0.0]
    # Same camera-relative convention as arena Skills.move_to.
    return [
        strength * (-dx * math.cos(yaw) + dz * math.sin(yaw)) / length,
        strength * (dx * math.sin(yaw) + dz * math.cos(yaw)) / length,
    ]


class Opponent52:
    def __init__(self, level, atlas, mesh=None, seed=0):
        if level not in (*LEVELS, "turret"):
            raise ValueError("unknown .52 level")
        self.level, self.p = level, LEVELS.get(level)
        self.atlas, self.mesh = atlas, mesh
        self.rng = random.Random(seed)
        self.skills = Skills(atlas)
        self.points = np.asarray(atlas.points, float)
        self.last_frame = None
        self.target_id = None
        self.last_seen = None
        self.seen_frame = -10000
        self.sample_frame = None
        self.velocity = np.zeros(3)
        self.reaction_at = 0
        self.acquired_at = 0
        self.was_visible = False
        self.recovering = False
        self.recover_at = 0
        self.strafe = 1
        self.next_strafe = 0
        self.next_jump = 0
        self.patrol_index = 0
        self.patrol = None
        self.cover = None
        self.cover_until = 0
        self.debug = {}
        self.teleports = 0
        self.previous_position = None

    def parameters(self):
        return asdict(self.p) if self.p else dict(legacy=True, reaction_frames=0)

    def _perceive(self, obs, own):
        p = self.p
        candidates = []
        for enemy in obs.get("enemies", []):
            # Never inspect hidden position/heading/last_seen fields. Memory is
            # our own copy of a previously visible synchronized sample only.
            if not enemy.get("visible") or enemy["public"].get("alive") is False:
                continue
            position = enemy.get("position")
            sample = enemy.get("sample_frame")
            if (
                position is None
                or sample is None
                or not 0 <= obs["frame"] - sample <= 8
            ):
                continue
            dx, dz = position[0] - own["position"][0], position[2] - own["position"][2]
            angle = wrap(math.atan2(dx, dz) - own["view_yaw"])
            if math.hypot(dx, dz) <= p.sense_range and abs(angle) <= math.radians(
                p.half_fov_degrees
            ):
                candidates.append((math.hypot(dx, dz), enemy))
        return min(candidates, key=lambda x: x[0])[1] if candidates else None

    def _look(self, own, point, dt, noise=0.0, pitch_noise=0.0):
        p = self.p
        pos = own["position"]
        dx, dz = point[0] - pos[0], point[2] - pos[2]
        error = wrap(math.atan2(dx, dz) - own["view_yaw"])
        desired = clip(
            math.atan2(point[1] - pos[1] - 1.1, max(0.05, math.hypot(dx, dz))),
            -0.8,
            0.8,
        )
        # Mean native shooter elevation transfer, measured in D3-R. This
        # compensates muzzle bias through ordinary gyro input, never direct aim.
        desired = (desired - p.gun_pitch_bias) / p.gun_pitch_scale + pitch_noise
        action = neutral()
        # Independently measured native +5 gyro yaw gain ~.25rad/frame per
        # injected turn/s. Rate cap + first order follow prevent snap aiming.
        rate = clip(
            (error + noise) / p.aim_tau,
            -math.radians(p.yaw_degrees_s),
            math.radians(p.yaw_degrees_s),
        )
        action["gyro"][2] = rate / 60 / 0.25
        action["gyro"][0] = clip((own["view_pitch"] - desired) * 0.32, -0.12, 0.12)
        return action, error

    def _safe_move(self, own, vector, strength):
        if self.mesh is not None:
            length = max(0.001, math.hypot(*vector))
            a = np.array(own["position"]) + [0, 0.7, 0]
            b = a + np.array([vector[0] / length * 0.8, 0, vector[1] / length * 0.8])
            if not self.mesh.clear(a, b):
                return [0.0, 0.0]
            floor = self.mesh.floor(
                b[0], b[2], top=own["position"][1] + 2, bottom=own["position"][1] - 4
            )
            if floor is None or floor < own["position"][1] - 1.4:
                return [0.0, 0.0]
        sticks = world_stick(vector, own["view_yaw"], strength)
        dominant = max(map(abs, sticks))
        norm = math.hypot(*sticks)
        if 0.01 < dominant < 0.60:
            scale = min(0.65 / dominant, 0.95 / norm)
            sticks = [x * scale for x in sticks]
        return sticks

    def _cover_goal(self, own, threat, frame):
        if self.mesh is None or not self.p.cover:
            return None
        if self.cover is not None and frame < self.cover_until:
            return self.cover
        pos = np.asarray(own["position"])
        ds = np.linalg.norm(self.points[:, [0, 2]] - pos[[0, 2]], axis=1)
        idx = np.flatnonzero(
            (ds > 1.5) & (ds < 6) & (abs(self.points[:, 1] - pos[1]) < 0.8)
        )
        for i in sorted(idx, key=lambda i: ds[i])[:16]:
            q = self.points[i]
            if not self.mesh.clear(
                np.asarray(threat) + [0, 1.1, 0], q + [0, 1.1, 0]
            ) and self.mesh.clear(pos + [0, 0.7, 0], q + [0, 0.7, 0]):
                self.cover, self.cover_until = q.tolist(), frame + 60
                return self.cover
        self.cover, self.cover_until = None, frame + 30
        return None

    def _patrol(self, obs, own):
        pos = np.asarray(own["position"])
        if self.patrol is None or math.dist(pos, self.patrol) < 2 or self.skills.failed:
            center = np.asarray(self.atlas.objective())
            if math.dist(pos[[0, 2]], center[[0, 2]]) > 22:
                self.patrol = center.tolist()
            else:
                # Public terrain-only route; no inferred hidden enemy position.
                angles = (0.0, math.pi / 2, math.pi, -math.pi / 2)
                angle = angles[self.patrol_index % 4]
                q = center + [10 * math.sin(angle), 0, 10 * math.cos(angle)]
                self.patrol = list(self.atlas.points[self.atlas.nearest(q)])
                self.patrol_index += 1
            self.skills = Skills(self.atlas)
        move = self.skills.move_to(obs, self.patrol).action
        sx, sy = move["sticks"][:2]
        # Spray a few units ahead along the path while advancing, not just when
        # an enemy happens to enter range. Keep navigation jump recovery input.
        yaw = own["view_yaw"]
        dx, dz = (
            -sx * math.cos(yaw) + sy * math.sin(yaw),
            sx * math.sin(yaw) + sy * math.cos(yaw),
        )
        norm = max(0.001, math.hypot(dx, dz))
        target = pos + np.array([dx / norm * 5, -0.3, dz / norm * 5])
        action, _ = self._look(own, target, 6)
        action["sticks"][:2] = move["sticks"][:2]
        action["buttons"][4] = move["buttons"][4]
        action["buttons"][0] = int(obs["frame"] % 90 < int(90 * self.p.paint_duty))
        self.debug["mode"] = "paint_advance"
        return action

    def act(self, obs):
        frame = obs["frame"]
        own = own_state(obs)
        if own is None or own.get("view_yaw") is None or own.get("view_pitch") is None:
            self.debug = dict(frame=frame, mode="unavailable", visible=False)
            if obs["own"]["public"].get("alive") is False:
                self.last_seen, self.was_visible = None, False
            return neutral()
        if self.level == "turret":
            visible = [
                e for e in obs.get("enemies", []) if e.get("position") is not None
            ]
            if visible:
                target = list(visible[0]["position"])
                target[1] += 1
                action = aim_at(obs, target).action
                action["buttons"][0] = int(math.dist(target, own["position"]) <= 14)
            else:
                action = self.skills.move_to(obs, self.atlas.objective()).action
            self.debug = dict(frame=frame, mode="turret", visible=bool(visible))
            return action
        p = self.p
        dt = max(1, frame - self.last_frame) if self.last_frame is not None else 6
        self.last_frame = frame
        pos = np.asarray(own["position"])
        if (
            self.previous_position is not None
            and math.dist(pos, self.previous_position) > 20
        ):
            self.last_seen, self.was_visible, self.recovering = None, False, False
            self.skills = Skills(self.atlas)
            self.patrol = None
            self.teleports += 1
        self.previous_position = pos.copy()
        enemy = self._perceive(obs, own)
        visible = enemy is not None
        if visible:
            point = np.asarray(enemy["position"], float)
            identity = enemy["public"]["player_id"]
            if (
                self.last_seen is not None
                and identity == self.target_id
                and enemy["sample_frame"] != self.sample_frame
            ):
                delta = max(1, enemy["sample_frame"] - self.sample_frame)
                estimate = (point - self.last_seen) * 60 / delta
                if np.linalg.norm(estimate) < 30:
                    self.velocity = 0.6 * self.velocity + 0.4 * estimate
            if not self.was_visible and (
                frame - self.seen_frame > 12 or identity != self.target_id
            ):
                self.reaction_at = (
                    frame
                    + p.reaction_frames
                    + self.rng.randint(-p.reaction_jitter, p.reaction_jitter)
                )
                self.acquired_at = frame
                self.velocity = np.zeros(3)
            self.last_seen = point.copy()
            self.seen_frame = frame
            self.sample_frame = enemy["sample_frame"]
            self.target_id = identity
        self.was_visible = visible
        if frame - self.seen_frame > p.memory_frames:
            self.last_seen = None
            self.velocity = np.zeros(3)
        self.debug = dict(
            frame=frame,
            mode="search",
            visible=visible,
            last_seen_age=frame - self.seen_frame
            if self.last_seen is not None
            else None,
            reaction_at=self.reaction_at,
            acquired_at=self.acquired_at,
            fire=False,
        )
        hp, ink = own.get("hp"), own.get("ink")
        if (hp is not None and hp < p.retreat_hp) or (
            ink is not None and ink < p.low_ink
        ):
            if not self.recovering:
                self.recover_at = frame
            self.recovering = True
        if (
            self.recovering
            and (hp is None or hp >= 0.90)
            and (ink is None or ink >= 0.80)
        ):
            self.recovering = False
        if self.recovering:
            action = neutral()
            self.debug["mode"] = "recover"
            if self.last_seen is not None:
                goal = self._cover_goal(own, self.last_seen, frame)
                direction = (
                    (np.asarray(goal) - pos)
                    if goal is not None
                    else pos - self.last_seen
                )
                if frame - self.recover_at < 54 or goal is not None:
                    action["sticks"][:2] = self._safe_move(
                        own, (direction[0], direction[2]), 0.7
                    )
            # If not in painted ground, briefly paint feet between swim attempts.
            paint = (
                own.get("submerged") is not True
                and frame % 120 < 24
                and (ink is None or ink > 0.06)
            )
            action["buttons"][1] = int(not paint)
            if paint:
                look, _ = self._look(own, pos + [0, -1, 3], dt)
                action["gyro"] = look["gyro"]
                action["buttons"][0] = 1
            return action
        if self.last_seen is None:
            return self._patrol(obs, own)
        target = self.last_seen.copy() + [0, 1.0, 0]
        distance = float(np.linalg.norm(target - pos))
        delta = self.last_seen - pos
        lateral = abs(self.velocity[0] * delta[2] - self.velocity[2] * delta[0]) / max(
            0.1, math.hypot(delta[0], delta[2])
        )
        sigma = math.radians(
            p.error_degrees
            + p.error_distance * distance / 12
            + p.error_lateral * lateral
        )
        if visible:
            target += self.velocity * (distance / (3.06 * 60)) * p.lead_fraction
        action, yaw_error = self._look(
            own, target, dt, self.rng.gauss(0, sigma), self.rng.gauss(0, sigma * 0.55)
        )
        if visible:
            if frame >= self.next_strafe:
                self.strafe = self.rng.choice((-1, 1))
                self.next_strafe = frame + self.rng.randint(*p.strafe_period)
            d = max(0.001, math.hypot(delta[0], delta[2]))
            ux, uz = delta[0] / d, delta[2] / d
            radial = (
                -0.7
                if distance < p.comfort[0]
                else 0.65
                if distance > p.comfort[1]
                else 0
            )
            vector = (radial * ux + self.strafe * uz, radial * uz - self.strafe * ux)
            action["sticks"][:2] = self._safe_move(own, vector, p.strafe_speed)
            if frame >= self.next_jump:
                action["buttons"][4] = int(self.rng.random() < p.jump_chance)
                self.next_jump = frame + 60
            fire = (
                frame >= self.reaction_at
                and distance <= p.fire_range
                and abs(yaw_error) < math.radians(p.fire_cone_degrees)
                and (frame - self.reaction_at) % (p.burst_frames + p.settle_frames)
                < p.burst_frames
            )
            action["buttons"][0] = int(fire)
            self.debug.update(
                mode="engage",
                fire=fire,
                distance=distance,
                aim_sigma_degrees=math.degrees(sigma),
                reaction_elapsed_frames=frame - self.acquired_at,
            )
        else:
            # Only stored, time-stamped position is chased; no firing at memory.
            goal = list(self.atlas.points[self.atlas.nearest(self.last_seen)])
            move = self.skills.move_to(obs, goal).action
            action["sticks"][:2] = move["sticks"][:2]
            action["buttons"][4] = move["buttons"][4]
            self.debug["mode"] = "memory_search"
        if p.cover and visible and hp is not None and hp < 0.72:
            goal = self._cover_goal(own, self.last_seen, frame)
            if goal is not None:
                q = np.asarray(goal) - pos
                action["sticks"][:2] = self._safe_move(own, (q[0], q[2]), 0.65)
                self.debug["mode"] = "cover"
        return action


class SaberFixture:
    """Public-observation-only active player for smoke tests; not a policy edit."""

    def __init__(self, atlas):
        self.skills = Skills(atlas)
        self.landing_until = 180
        self.refilling = False

    def act(self, obs):
        raw = obs["own"]
        if raw.get("position") is not None and raw["position"][1] > 20:
            self.landing_until = obs["frame"] + 120
            self.skills = Skills(self.skills.atlas)
            a = neutral()
            a["buttons"][0] = int(obs["frame"] % 30 == 0)
            return a
        own = own_state(obs)
        if own is None:
            if obs["own"]["public"].get("alive") is False:
                self.skills = Skills(self.skills.atlas)
            return neutral()
        if own["position"][1] > 20:
            self.landing_until = obs["frame"] + 120
        if obs["frame"] < self.landing_until:
            self.skills = Skills(self.skills.atlas)
            a = neutral()
            a["buttons"][0] = int(obs["frame"] % 30 == 0)
            return a
        ink = own.get("ink")
        if ink is not None and ink < 0.15:
            self.refilling = True
        if ink is not None and ink > 0.75:
            self.refilling = False
        if self.refilling:
            a = self.skills.move_to(obs, self.skills.atlas.objective()).action
            a["buttons"][1] = int(obs["frame"] % 180 < 120)
            return a
        visible = [
            e
            for e in obs["enemies"]
            if e.get("visible") and e.get("position") is not None
        ]
        if not visible:
            a = self.skills.move_to(obs, self.skills.atlas.objective()).action
            a["buttons"][0] = int(obs["frame"] % 48 < 6)
            # Scan when at the centre instead of staring forever at an empty point.
            if math.dist(own["position"], self.skills.atlas.objective()) < 3:
                a["sticks"][2] = 0.3
            return a
        target = np.asarray(visible[0]["position"]) + [0, 1.0, 0]
        distance = math.dist(target, own["position"])
        cycle = obs["frame"] % 90
        a = aim_at(
            obs, target, eye_height=1.0 if cycle >= 60 else 2.2, pitch_scale=0.9446
        ).action
        if distance > 15:
            q = target - np.asarray(own["position"])
            a["sticks"][:2] = world_stick((q[0], q[2]), own["view_yaw"], 0.65)
        a["buttons"][0] = int(
            distance < 23 and cycle < 23 or distance < 19 and 60 <= cycle < 64
        )
        return a
