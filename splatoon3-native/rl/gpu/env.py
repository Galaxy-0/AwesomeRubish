"""Batched fixed60 approximation. GPU tensors only on the reset/step hot path.

All movement/terrain/weapon approximations are explicit in the acceptance report.
This module never imports a native session or runs a training algorithm.
"""

import json, math
from pathlib import Path
import torch
from .contract import Config, MOVE_DIRECTIONS, CAMERA_LEVELS, ACTION_SIZES
from .geometry import Geometry, basis
from .collision import capsule_first, segment_distance

# Float state layout; positions/velocities never leave this private referee state.
(
    X,
    Y,
    Z,
    VX,
    VY,
    VZ,
    YAW,
    PITCH,
    HEADING,
    HP,
    INK,
    GAUGE,
    SQUID,
    SUB,
    GROUND,
    CHARGE,
    COOL,
    RECOVER,
    EMERGE,
    HURT,
    RESPAWN,
    PROTECTED,
    PHASE,
    AGE,
    AX,
    AY,
    AZ,
    SX,
    SY,
    SZ,
    PREV_ZR,
    PREV_ZL,
    PREV_B,
    PREV_R,
    PREV_RS,
    DELAY,
    FULL,
    CONTACT,
    CONTACT_HIT,
    CREDIT,
    ARM,
    RETURN_AGE,
    RESERVED,
    FX,
    FY,
    FZ,
    FLIGHT_AGE,
    FLIGHT_DURATION,
) = range(48)
STATE_SIZE = 48
EVENT_SIZE = 6  # received,down,attack,hook,return-frame,weapon-caused-down
# Projectile layout x,y,z,vx,vy,vz,age,lifetime,damage,kind,alive,radius.
PX, PY, PZ, PVX, PVY, PVZ, PA, PL, PD, PK, ACTIVE, PR, RX, RY, RZ, UX, UY, UZ, MASK = (
    range(19)
)


class ParallelEnv:
    possible_agents = ("stamper", "52")
    metadata = {
        "name": "inklab_gpu_stage0_v1",
        "render_modes": [],
        "is_parallelizable": True,
    }

    def __init__(
        self,
        data,
        config: Config,
        *,
        n_envs=1,
        device="cpu",
        compile=False,
        fast_rays=False,
    ):
        config.validate()
        self.cfg = config
        self.device = torch.empty(0, device=device).device
        self.n = n_envs
        self.geo = Geometry(data, self.device, fast_rays=fast_rays)
        self.params = json.loads((Path(data) / "parameters.json").read_text())
        self.saber = self.params["saber"]["tables"]["WeaponSaberNormal"]
        self.sw = self.saber["spl__WeaponSaberParam"]["SwingParam"]
        self.ch = self.saber["spl__WeaponSaberParam"]["ChargeParam"]
        self.gun = self.params["gun"]["parameter_values"]
        self.zip = self.params["zipcaster"]["normalized"]
        self.flight = self.params["flight"]
        self.flight_progress = torch.tensor(self.flight["progress"], device=self.device)
        self.bomb = self.params["advanced"]
        self.gun_steps = torch.tensor(
            [3.06, 3.06, 2.28, 1.8]
            + [0.4] * 4
            + [0.2] * 4
            + [0.1375] * 4
            + [0.1375] * 4
            + [0.12] * 15,
            device=self.device,
        )
        self.motion = self.params["motion"]
        self.moves = torch.tensor(
            MOVE_DIRECTIONS, device=self.device, dtype=torch.float32
        )
        self.turns = torch.tensor(CAMERA_LEVELS, device=self.device)
        self.roles = torch.arange(2, device=self.device)[None, :]
        self.button_enabled = torch.ones(
            (1, 2, 8), dtype=torch.bool, device=self.device
        )
        self.button_enabled[:, 1, 6:] = (
            False  # .52 sub/special not implemented in stage0
        )
        if config.loadout_mode == "primary_only":
            self.button_enabled[:, :, 6:] = False
        self.action_mask = torch.zeros(
            (1, 2, 8, 17), dtype=torch.bool, device=self.device
        )
        for i, size in enumerate(ACTION_SIZES):
            self.action_mask[:, :, i, :size] = True
        self.action_mask[:, :, 6:, 1] = self.button_enabled[:, :, 6:]

        self.env_ids = torch.arange(n_envs, device=self.device)
        self.agent_mask = (self.roles == 0).expand(n_envs, 2)
        self.steps = torch.zeros(n_envs, device=self.device, dtype=torch.int64)
        self.state = torch.zeros((n_envs, 2, STATE_SIZE), device=self.device)
        self.shots = torch.zeros((n_envs, 2, 8, 19), device=self.device)
        self.paint = torch.full(
            (n_envs, len(self.geo.points) + 1),
            -1,
            device=self.device,
            dtype=torch.int8,  # only -1/unpainted,0,1; preserve integer semantics
        )
        self.seed_tensor = torch.zeros(
            (n_envs, 2), device=self.device, dtype=torch.int64
        )
        self.anneal = torch.ones((), device=self.device)
        self.dead = torch.zeros(n_envs, device=self.device, dtype=torch.bool)
        self.paint_count = int(self.geo.paintable.sum().item())
        self.offsets = torch.tensor(
            [(x, 0, z) for x in range(-4, 5) for z in range(-4, 5)],
            device=self.device,
            dtype=torch.float32,
        )
        # Constants are allocated before CUDA capture; no host-to-device copies in step.
        self.constants = [
            torch.tensor(v, device=self.device)
            for v in [
                [0.0, 0.4, 0.0],
                [0.0, 1.3, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 2.2, 0.0],
                [0.0, 0.7, 0.0],
                [0.0, 0.24, 0.0],
                [0.0, 0.825, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.35, 0.0],
                [0.35, 1.3 - 0.35 + 0.35, 0.35],
                [0.0, self.cfg.camera_target_height, 0.0],
            ]
        ]
        self._advance = self._frame
        self._observation = self._observe
        if compile:
            self._advance = torch.compile(self._frame, fullgraph=True, mode="default")
            self._observation = torch.compile(
                self._observe, fullgraph=True, mode="default"
            )
        self.reset()

    def reset(self, seed=None, options=None):
        # Full reset and explicit per-environment mask; no auto-reset destroys terminal obs.
        mask = (
            torch.ones(self.n, device=self.device, dtype=torch.bool)
            if options is None
            else options["mask"].to(self.device, dtype=torch.bool)
        )
        s = torch.zeros_like(self.state)
        s[..., :3] = self.geo.spawn
        s[..., YAW] = torch.tensor([math.pi, 0.0], device=self.device)
        s[..., HEADING] = s[..., YAW]
        s[..., HP] = 1
        s[..., INK] = 1
        s[..., GROUND] = 1
        s[..., HURT] = 10000
        self.state = torch.where(mask[:, None, None], s, self.state)
        self.shots = torch.where(mask[:, None, None, None], 0.0, self.shots)
        self.paint = torch.where(mask[:, None], -1, self.paint)
        self.steps = torch.where(mask, 0, self.steps)
        self.dead &= ~mask
        self.seed_value = 0 if seed is None else int(seed)
        self.seed_tensor = torch.where(mask[:, None], self.seed_value, self.seed_tensor)
        self.generator = torch.Generator(device=self.device).manual_seed(
            0 if seed is None else seed
        )
        obs = self._observation(self.state, self.shots, self.paint, self.steps)
        return obs, {
            "frame": self.steps,
            "model_is_approximation": torch.ones_like(self.dead),
        }

    def set_auxiliary_scale(self, value):
        if not 0 <= value <= 1:
            raise ValueError("auxiliary scale must be in [0,1]")
        self.anneal.fill_(value)

    def random_actions(self):
        # Uses one GPU generator, no per-environment Python dispatch.
        a = torch.randint(
            0, 2, (self.n, 2, 8), generator=self.generator, device=self.device
        )
        a[..., 0] = torch.randint(
            0, 17, (self.n, 2), generator=self.generator, device=self.device
        )
        a[..., 1:3] = torch.randint(
            0, 9, (self.n, 2, 2), generator=self.generator, device=self.device
        )
        return torch.where(self.button_enabled, a, 0)

    def step(self, actions):
        if (
            actions.shape != (self.n, 2, 8)
            or actions.device != self.device
            or actions.dtype != torch.int64
        ):
            raise ValueError("actions must be int64 [n_envs,2,8] on environment device")
        actions = torch.where(self.button_enabled, actions, 0)
        reward = torch.zeros((self.n, 2), device=self.device)
        events = torch.zeros((self.n, 2, EVENT_SIZE), device=self.device)
        for _ in range(self.cfg.decision_frames):
            self.state, self.shots, self.paint, r, event = self._advance(
                self.state, self.shots, self.paint, actions, self.steps, self.anneal
            )
            active = ~self.dead
            reward += r * active[:, None]
            events += event * active[:, None, None]
            self.steps += active.long()
            ended = active & (self.steps >= self.cfg.duration_frames)
            counts = torch.stack([(self.paint == i).sum(-1) for i in range(2)], -1)
            win = torch.sign((counts[:, 0] - counts[:, 1]).float()) * 0.5
            reward += torch.stack([win, -win], -1) * ended[:, None]
            self.dead |= ended
        obs = self._observation(self.state, self.shots, self.paint, self.steps)
        termination = self.dead[:, None].expand(-1, 2)
        truncation = torch.zeros_like(termination)
        return (
            obs,
            reward,
            termination,
            truncation,
            {
                "frame": self.steps,
                "events": events,
                "aux_scale": self.anneal.expand(self.n),
                "turf_counts": counts,
            },
        )

    def _paint_disks(self, paint, position, enabled, radius, owner):
        # Same 1u navigation scoring domain as S1, with layered support retained.
        floor, base = self.geo.support(position, top_offset=0.0)
        near = (base >= 0) & ((position[..., 1] - floor) <= 3.1)
        projected = position.clone()
        projected[..., 1] = floor
        p = projected[..., None, :] + self.offsets
        cell = self.geo.cell(p)
        sample = self.geo.points[cell.clamp_min(0)]
        distance = (
            torch.stack([sample[..., 0], sample[..., 2]], -1)
            - torch.stack([projected[..., 0], projected[..., 2]], -1)[..., None, :]
        ).norm(dim=-1)
        valid = (
            (cell >= 0) & (enabled & near)[..., None] & (distance <= radius[..., None])
        )
        valid &= self.geo.paintable[cell.clamp_min(0)]
        valid &= self.geo.clear(
            projected[..., None, :] + self.constants[0],
            p + self.constants[0],
            4,
            wall_only=True,
        )
        cell = torch.where(valid, cell, len(self.geo.points))
        flat = cell.flatten(1)
        old = paint.gather(1, flat)
        new = torch.where(valid.flatten(1), owner, old)
        # Duplicate indices all write the same owner. Two owners are resolved in order.
        paint = paint.scatter(1, flat, new)
        return paint

    def _frame(self, s, shots, paint, a, frame, anneal):
        t = s.clone()
        q = shots.clone()
        old_paint = paint
        live = s[..., HP] > 0
        stamper = self.agent_mask
        zr, zl, jump, rr, rs = [a[..., i] > 0 for i in range(3, 8)]
        bjump = jump & (s[..., PREV_B] == 0)
        rspress = rs & (s[..., PREV_RS] == 0)
        phase = s[..., PHASE]
        sp = phase > 0
        attached = phase == 4
        returning = phase == 5
        can = live & (phase != 1) & (phase != 3) & ~attached & ~returning
        turn_max = (
            self.cfg.gyro_max_radians_per_frame + self.cfg.stick_plus5_radians_per_frame
        )
        yaw = s[..., YAW] + self.turns[a[..., 1].clamp(0, 8)] * turn_max
        yaw = torch.atan2(torch.sin(yaw), torch.cos(yaw))
        pitch = (s[..., PITCH] + self.turns[a[..., 2].clamp(0, 8)] * turn_max).clamp(
            -1.1, 1.1
        )
        t[..., YAW] = torch.where(live, yaw, s[..., YAW])
        t[..., PITCH] = torch.where(live, pitch, s[..., PITCH])
        t[..., HEADING] = t[..., YAW]
        fwd, right, up = basis(t[..., YAW], t[..., PITCH])
        horizontal = torch.stack(
            [torch.sin(yaw), torch.zeros_like(yaw), torch.cos(yaw)], -1
        )
        color = self.geo.color(paint, s[..., :3])
        ground = s[..., GROUND] > 0
        submerged = zl & ground & (color == self.roles) & live
        t[..., SQUID] = zl.float()
        t[..., SUB] = submerged.float()
        emerge = torch.where(
            (s[..., SUB] > 0) & ~zl, 5.0, (s[..., EMERGE] - 1).clamp_min(0)
        )
        t[..., EMERGE] = emerge
        cooldown = (s[..., COOL] - 1).clamp_min(0)
        t[..., COOL] = cooldown
        t[..., RECOVER] = (s[..., RECOVER] - 1).clamp_min(0)
        t[..., HURT] = s[..., HURT] + 1
        charge = torch.where(
            stamper & zr & ~zl & can & (cooldown == 0) & (emerge == 0),
            s[..., CHARGE] + 1,
            torch.where(zr, s[..., CHARGE], 0.0),
        )
        charge = torch.where(zl, 0.0, charge)
        t[..., CHARGE] = charge
        release = (
            stamper & ~zr & (s[..., PREV_ZR] > 0) & (s[..., CHARGE] > 0) & can & ~zl
        )
        full = release & (s[..., CHARGE] >= 21)
        cost = torch.where(full, self.ch["InkConsumeFullCharge"], self.sw["InkConsume"])
        shoot = release & ((s[..., INK] >= cost) | sp)
        gunshot = (
            ~stamper
            & zr
            & can
            & ~zl
            & (cooldown == 0)
            & (s[..., INK] >= self.gun["ink_per_shot"])
        )
        shot = shoot | gunshot
        t[..., FULL] = torch.where(shoot, full.float(), s[..., FULL])
        t[..., DELAY] = torch.where(
            shoot,
            torch.where(
                full,
                float(self.sw["ChargeSwingShotBulletFrame"]),
                float(self.sw["WeakSwingShotBulletFrame"]),
            ),
            (s[..., DELAY] - 1).clamp_min(0),
        )
        t[..., CONTACT] = torch.where(
            shoot, torch.where(full, 6.0, 9.0), (s[..., CONTACT] - 1).clamp_min(0)
        )
        t[..., CONTACT_HIT] = torch.where(shoot, 0.0, s[..., CONTACT_HIT])
        t[..., COOL] = torch.where(
            shoot, torch.where(full, 36.0, 29.0), torch.where(gunshot, 9.0, cooldown)
        )
        t[..., INK] = (
            s[..., INK]
            - torch.where(shoot & ~sp, cost, 0.0)
            - gunshot * self.gun["ink_per_shot"]
        )
        t[..., RECOVER] = torch.where(shot, 40.0, t[..., RECOVER])
        # Zipcaster: native resource rates, with explicitly approximate stage motion.
        activate = (
            rspress
            & stamper
            & live
            & ~sp
            & (s[..., GAUGE] >= 0.999)
            & (self.cfg.loadout_mode != "primary_only")
        )
        phase = torch.where(activate, 1.0, phase)
        age = torch.where(activate, 0.0, s[..., AGE] + 1)
        t[..., SX : SZ + 1] = torch.where(
            activate[..., None], s[..., :3], s[..., SX : SZ + 1]
        )
        phase = torch.where((phase == 1) & (age >= 31), 2.0, phase)
        detach = attached & bjump
        phase = torch.where(detach, 2.0, phase)
        hook_release = stamper & sp & can & ~rr & (s[..., PREV_R] > 0)
        dist, code, normal = self.geo.ray(
            s[..., :3] + self.constants[1], fwd, 35.0, 1.0
        )
        hook = hook_release & ((code & 4) > 0) & ((code & 3) == 2)
        normal = torch.where((normal * fwd).sum(-1, keepdim=True) > 0, -normal, normal)
        anchor = s[..., :3] + self.constants[1] + fwd * dist[..., None] + normal * 0.8
        t[..., AX : AZ + 1] = torch.where(hook[..., None], anchor, s[..., AX : AZ + 1])
        flight_length = (anchor - s[..., :3]).norm(dim=-1)
        duration = (
            (
                self.flight["coefficients"][0]
                + self.flight["coefficients"][1] * flight_length
            )
            .ceil()
            .clamp_min(18)
        )
        t[..., FX : FZ + 1] = torch.where(
            hook[..., None], s[..., :3], s[..., FX : FZ + 1]
        )
        t[..., FLIGHT_DURATION] = torch.where(hook, duration, s[..., FLIGHT_DURATION])
        t[..., FLIGHT_AGE] = torch.where(hook, 0.0, s[..., FLIGHT_AGE] + 1)
        phase = torch.where(hook, 3.0, phase)
        gauge = s[..., GAUGE] - torch.where(
            sp & ~returning & (s[..., AGE] >= 11), self.zip["natural_per_present"], 0.0
        )
        reserved = s[..., RESERVED]
        charging = (
            stamper
            & zr
            & sp
            & can
            & ~zl
            & (cooldown == 0)
            & (charge <= 21)
            & (charge > s[..., CHARGE])
        )
        reserve_cost = charging * self.zip["per_full"] / 21
        gauge -= hook * self.zip["per_hook"] + reserve_cost
        gauge -= torch.where(
            shoot & sp,
            (
                torch.where(full, self.zip["per_full"], self.zip["per_light"])
                - reserved
            ).clamp_min(0),
            0.0,
        )
        t[..., RESERVED] = torch.where(zl | shoot | ~sp, 0.0, reserved + reserve_cost)
        exhausted = sp & ~returning & (gauge <= 0)
        phase = torch.where(exhausted, 5.0, phase)
        return_age = torch.where(exhausted, 0.0, s[..., RETURN_AGE] + 1)
        finish_return = (phase == 5) & (return_age >= 99)
        phase = torch.where(finish_return, 0.0, phase)
        t[..., GAUGE] = gauge.clamp(0, 1)
        t[..., AGE] = age
        t[..., PHASE] = phase
        t[..., RETURN_AGE] = return_age
        # S1 six movement modes and radial human response.
        move = self.moves[a[..., 0].clamp(0, 16)]
        mag = move.norm(dim=-1).clamp_max(1)
        mode = torch.where(
            ~ground,
            5,
            torch.where(
                zl,
                torch.where(submerged, 3, 4),
                torch.where(charge >= 5, 1, torch.where(cooldown > 0, 2, 0)),
            ),
        )
        names = ["human", "charge", "recovery", "squid_own", "squid_dry", "air"]
        speed = torch.zeros_like(yaw)
        acc = speed.clone()
        brake = speed.clone()
        dx = speed.clone()
        dz = speed.clone()
        for i, name in enumerate(names):
            model = self.motion["modes"][name]
            select = mode == i
            if model.get("response_space", "axis") == "radial":
                response = (mag - model["deadzone"]).clamp_min(0) / (
                    1 - model["deadzone"]
                )
                response = response.pow(model["exponent"]) / mag.clamp_min(1e-6)
                local = move * response[..., None]
            else:
                local = move.sign() * (
                    (move.abs() - model["deadzone"]).clamp_min(0)
                    / (1 - model["deadzone"])
                ).pow(model["exponent"])
            local = local / local.norm(dim=-1, keepdim=True).clamp_min(1)
            dx = torch.where(select, local[..., 0], dx)
            dz = torch.where(select, local[..., 1], dz)
            speed = torch.where(select, model["speed"], speed)
            acc = torch.where(select, model["acceleration"], acc)
            brake = torch.where(select, model["braking"], brake)
        speed = torch.where(~stamper & zr, self.gun["shot_move_speed"], speed)
        target = (
            torch.stack(
                [
                    -dx * torch.cos(yaw) + dz * torch.sin(yaw),
                    dx * torch.sin(yaw) + dz * torch.cos(yaw),
                ],
                -1,
            )
            * speed[..., None]
        )
        current = torch.stack([s[..., VX], s[..., VZ]], -1)
        rate = torch.where(target.norm(dim=-1) < current.norm(dim=-1), brake, acc)
        velocity = current + (target - current).clamp(-rate[..., None], rate[..., None])
        enemy = (color >= 0) & (color != self.roles) & ground
        velocity = torch.where(
            enemy[..., None], velocity.clamp(-0.024, 0.024), velocity
        )
        velocity = torch.where(can[..., None], velocity, 0.0)
        p = s[..., :3].clone()
        vy = torch.where(
            (bjump & ground & can) | detach,
            torch.where(detach, 0.205, self.motion["jump"]["jump_speed"]),
            s[..., VY],
        )
        ground = ground & ~(bjump & can) & ~detach & ~(phase >= 3)
        for axis, slot in [(0, 0), (2, 1)]:
            candidate = p.clone()
            candidate[..., axis] += velocity[..., slot]
            floor, cell = self.geo.support(candidate)
            code, _ = self.geo.lookup(candidate + self.constants[2])
            allowed = (code & 3) != 2
            # A raised1u support column can overwrite a thin wall voxel. It
            # is an obstacle, not a hole to walk into and fall underneath.
            column_y, column_ids, column_valid = self.geo.column(candidate)
            raised = (
                (column_ids >= 0)
                & (column_y > p[..., 1, None] + 0.205)
                & (column_y < p[..., 1, None] + 1.65)
            ).any(-1) & column_valid
            allowed &= ~(ground & raised)
            p[..., axis] = torch.where(allowed, candidate[..., axis], p[..., axis])
            p[..., 1] = torch.where(
                ground & (cell >= 0) & (floor >= p[..., 1] - 0.3), floor, p[..., 1]
            )
        floor, cell = self.geo.support(p)
        ground = ground & (cell >= 0) & ((p[..., 1] - floor) <= 0.3)
        vy = torch.where(ground, 0.0, vy - self.motion["jump"]["gravity"])
        next_y = p[..., 1] + vy
        landing = ~ground & (vy <= 0) & (cell >= 0) & (next_y <= floor)
        p[..., 1] = torch.where(landing, floor, torch.where(ground, p[..., 1], next_y))
        ground |= landing
        delta = t[..., AX : AZ + 1] - t[..., FX : FZ + 1]
        length = delta.norm(dim=-1)
        windup = (
            self.flight["windup_coefficients"][0]
            + self.flight["windup_coefficients"][1] * length
        ).clamp_min(0)
        windup = torch.minimum(windup, (t[..., FLIGHT_DURATION] - 1).clamp_min(0))
        progress = (
            (t[..., FLIGHT_AGE] + 1 - windup)
            / (t[..., FLIGHT_DURATION] - windup).clamp_min(1)
        ).clamp(0, 1) * 64
        index = progress.long().clamp(0, 63)
        fraction = progress - index
        progress = (
            self.flight_progress[index] * (1 - fraction)
            + self.flight_progress[index + 1] * fraction
        )
        flying = phase == 3
        arrive = flying & (t[..., FLIGHT_AGE] + 1 >= t[..., FLIGHT_DURATION])
        p = torch.where(
            flying[..., None], t[..., FX : FZ + 1] + delta * progress[..., None], p
        )
        p = torch.where((phase == 4)[..., None], s[..., :3], p)
        phase = torch.where(arrive, 4.0, phase)
        p = torch.where(
            (phase == 5)[..., None],
            s[..., :3]
            + (t[..., SX : SZ + 1] - s[..., :3])
            / (99 - return_age).clamp_min(1)[..., None],
            p,
        )
        p = torch.where(finish_return[..., None], t[..., SX : SZ + 1], p)
        t[..., :3] = torch.where(live[..., None], p, s[..., :3])
        t[..., VX] = velocity[..., 0]
        t[..., VZ] = velocity[..., 1]
        t[..., VY] = vy
        t[..., GROUND] = (ground & ~((phase >= 3) & (phase <= 5))).float()
        t[..., PHASE] = phase
        # Emission occurs after native-derived delay; independent fixed slot ring.
        emit = (s[..., DELAY] == 1) & stamper & live & (phase != 5) | gunshot
        t[..., DELAY] = torch.where(phase == 5, 0.0, t[..., DELAY])
        t[..., CONTACT] = torch.where(phase == 5, 0.0, t[..., CONTACT])
        t[..., CHARGE] = torch.where(phase == 5, 0.0, t[..., CHARGE])
        bomb_throw = (
            (self.cfg.loadout_mode != "primary_only")
            & stamper
            & live
            & can
            & ~sp
            & ~zl
            & ~rr
            & (s[..., PREV_R] > 0)
            & (t[..., INK] >= 0.45)
            & ~emit
        )
        emit |= bomb_throw
        t[..., INK] -= bomb_throw * 0.45
        t[..., RECOVER] = torch.where(bomb_throw, 60.0, t[..., RECOVER])
        full_emit = (s[..., FULL] > 0) & stamper & ~bomb_throw
        # Deterministic per-environment uniform-disk spread, explicitly an
        # assumed distribution inside the measured6deg standing/12deg air cone.
        counter = (
            frame[:, None] * 1664525
            + self.env_ids[:, None] * 1013904223
            + self.roles * 69069
            + self.seed_tensor
        ) & 0x7FFFFFFF
        rand1 = ((counter * 1103515245 + 12345) & 0x7FFFFFFF).float() / 2147483648
        rand2 = ((counter * 214013 + 2531011) & 0x7FFFFFFF).float() / 2147483648
        radius = (
            rand1.sqrt()
            * math.tan(math.radians(self.cfg.gun_spread_degrees))
            * torch.where(ground, 1.0, 2.0)
        )
        gun_direction = (
            fwd
            + right * (radius * torch.cos(rand2 * 2 * math.pi))[..., None]
            + up * (radius * torch.sin(rand2 * 2 * math.pi))[..., None]
        )
        gun_direction = gun_direction / gun_direction.norm(dim=-1, keepdim=True)
        emission_direction = torch.where(stamper[..., None], fwd, gun_direction)
        muzzle = (
            p
            + torch.where(
                full_emit[..., None],
                self.constants[3],
                up * 1.0 + fwd * 1.4,
            )
            + torch.where(full_emit, 0.8, 0.0)[..., None] * fwd
        )
        emit &= self.geo.clear(p + self.constants[4], muzzle, 8)
        for k in range(8):
            choose = emit & ((frame[:, None] // 1) % 8 == k)
            speed_shot = torch.where(
                stamper,
                torch.where(full_emit, 0.8, 2.82),
                self.gun["spawn_speed_units_per_frame"],
            )
            q[:, :, k, :3] = torch.where(choose[..., None], muzzle, q[:, :, k, :3])
            q[:, :, k, PVX : PVZ + 1] = torch.where(
                choose[..., None],
                emission_direction * speed_shot[..., None],
                q[:, :, k, PVX : PVZ + 1],
            )
            q[:, :, k, PA] = torch.where(choose, 0.0, q[:, :, k, PA])
            q[:, :, k, PL] = torch.where(
                choose,
                torch.where(stamper, torch.where(full_emit, 26.0, 6.0), 27.0),
                q[:, :, k, PL],
            )
            q[:, :, k, PD] = torch.where(
                choose,
                torch.where(stamper, torch.where(full_emit, 0.7, 0.35), 0.52),
                q[:, :, k, PD],
            )
            q[:, :, k, PK] = torch.where(
                choose,
                torch.where(stamper, torch.where(full_emit, 2.0, 1.0), 3.0),
                q[:, :, k, PK],
            )
            q[:, :, k, ACTIVE] = torch.where(choose, 1.0, q[:, :, k, ACTIVE])
            q[:, :, k, PR] = torch.where(
                choose,
                torch.where(stamper, torch.where(full_emit, 0.55, 0.37), 0.285),
                q[:, :, k, PR],
            )
            q[:, :, k, RX : RZ + 1] = torch.where(
                choose[..., None], right, q[:, :, k, RX : RZ + 1]
            )
            q[:, :, k, UX : UZ + 1] = torch.where(
                choose[..., None], up, q[:, :, k, UX : UZ + 1]
            )
            q[:, :, k, MASK] = torch.where(
                choose,
                torch.where(stamper, torch.where(full_emit, 127.0, 31.0), 1.0),
                q[:, :, k, MASK],
            )
            bomb_slot = choose & bomb_throw
            q[:, :, k, PK] = torch.where(bomb_slot, 4.0, q[:, :, k, PK])
            q[:, :, k, PL] = torch.where(bomb_slot, 120.0, q[:, :, k, PL])
            q[:, :, k, PD] = torch.where(bomb_slot, 0.25, q[:, :, k, PD])
            q[:, :, k, PVX : PVZ + 1] = torch.where(
                bomb_slot[..., None],
                fwd * 1.12 + self.constants[5],
                q[:, :, k, PVX : PVZ + 1],
            )
        painting = q[..., ACTIVE] > 0
        old = q[..., :3].clone()
        gun = q[..., PK] == 3
        bomb = q[..., PK] == 4
        gravity = torch.where(
            gun & (q[..., PA] >= 3),
            self.gun["free_gravity"],
            torch.where((q[..., PK] == 2) & (q[..., PA] >= 22), 0.0027, 0.0),
        )
        gravity = torch.where(bomb, 0.04, gravity)
        q[..., PVY] -= gravity
        # D4 measured .52 distance-age envelope, not sparse air-resist defaults
        # misinterpreted as the straight-to-brake transition.
        horizontal_speed = (
            torch.stack([q[..., PVX], q[..., PVZ]], -1).norm(dim=-1).clamp_min(1e-8)
        )
        gun_speed = self.gun_steps[q[..., PA].long().clamp(0, len(self.gun_steps) - 1)]
        q[..., PVX] = torch.where(
            gun, q[..., PVX] / horizontal_speed * gun_speed, q[..., PVX]
        )
        q[..., PVZ] = torch.where(
            gun, q[..., PVZ] / horizontal_speed * gun_speed, q[..., PVZ]
        )
        end = old + q[..., PVX : PVZ + 1]
        enemy_foot = t.flip(1)[..., :3]
        enemy_pos = enemy_foot + self.constants[6]
        is_full = q[..., PK] == 2
        is_light = q[..., PK] == 1
        direction = q[..., PVX : PVZ + 1] / q[..., PVX : PVZ + 1].norm(
            dim=-1, keepdim=True
        ).clamp_min(1e-9)
        earliest_hit = torch.full_like(q[..., PA], float("inf"))
        earliest_wall = torch.full_like(earliest_hit, float("inf"))
        any_hit = torch.zeros_like(gun)
        any_wall = torch.zeros_like(gun)
        mask = q[..., MASK].long()
        # Side balls keep their own alive bits. The unconfirmed half-clipping
        # switch groups them by side, rather than pretending it is known truth.
        newmask = mask.clone()
        blocked_bits = torch.zeros_like(mask)
        for j in range(7):
            shifts = []
            radii = []
            valids = []
            for key, count in [
                ("BulletSaberHorizontalParam", 5),
                ("BulletSaberVerticalParam", 7),
            ]:
                cp = self.saber[key]["CollisionParam"]
                off = cp["OffsetArray"][min(j, count - 1)]
                rad = cp["ParamArray"][min(j, count - 1)]["InitRadiusForPlayer"]
                shifts.append(
                    q[..., RX : RZ + 1] * off["X"]
                    + q[..., UX : UZ + 1] * off["Y"]
                    + direction * off["Z"]
                )
                radii.append(rad)
                valids.append(j < count)
            shift = torch.where(
                is_full[..., None],
                shifts[1],
                torch.where(is_light[..., None], shifts[0], 0.0),
            )
            enabled = (
                (q[..., ACTIVE] > 0)
                & ((mask & (1 << j)) > 0)
                & (is_full | (is_light & valids[0]) | ((gun | bomb) & (j == 0)))
            )
            start = old + shift
            finish = end + shift
            # Four swept samples prevent fast .52 shots tunnelling through a
            # single surface voxel. Target contact must precede terrain contact.
            cp_light = self.saber["BulletSaberHorizontalParam"]["CollisionParam"][
                "ParamArray"
            ][min(j, 4)]
            cp_full = self.saber["BulletSaberVerticalParam"]["CollisionParam"][
                "ParamArray"
            ][j]
            field_radius = torch.where(
                is_full,
                cp_full["InitRadiusForField"],
                torch.where(
                    is_light,
                    cp_light["InitRadiusForField"],
                    torch.where(bomb, 0.25, 0.15),
                ),
            )
            wall_t = self.geo.sweep(start, finish, 4, field_radius)
            radius = (
                torch.where(is_full, radii[1], torch.where(is_light, radii[0], 0.285))
                + 0.35
            )
            hit_t = capsule_first(start, finish, enemy_foot[:, :, None, :], radius)
            hit = (
                enabled
                & (hit_t < wall_t)
                & (hit_t <= 1)
                & (t.flip(1)[..., HP, None] > 0)
            )
            wall = enabled & (wall_t <= 1)
            earliest_hit = torch.minimum(
                earliest_hit, torch.where(hit, hit_t, float("inf"))
            )
            earliest_wall = torch.minimum(
                earliest_wall, torch.where(wall, wall_t, float("inf"))
            )
            any_hit |= hit
            any_wall |= wall
            blocked_bits |= wall.long() * (1 << j)
        if self.cfg.wave_clipping == "independent_halves":
            # Centre belongs to both halves, so a blocked centre removes both.
            light_negative = (blocked_bits & 7) > 0
            light_positive = (blocked_bits & 28) > 0
            full_negative = (blocked_bits & 15) > 0
            full_positive = (blocked_bits & 120) > 0
            remove = torch.where(
                is_full,
                full_negative.long() * 15 | full_positive.long() * 120,
                light_negative.long() * 7 | light_positive.long() * 28,
            )
            newmask = mask & ~remove
            wall = (newmask == 0) & ~gun
            wall |= (gun | bomb) & any_wall
        else:
            wall = any_wall
            any_hit &= earliest_hit < earliest_wall
        falloff = ((q[..., PA] - 11) / 16).clamp(0, 1)
        damage = torch.where(gun, 0.52 - 0.22 * falloff, q[..., PD])
        inflicted = (damage * any_hit).sum(-1)
        # Paint/blast originates on the incoming side of the first field contact.
        paint_fraction = (
            earliest_wall - 0.01 / (end - old).norm(dim=-1).clamp_min(0.01)
        ).clamp(0, 1)
        paint_end = old + (end - old) * paint_fraction[..., None]
        explosion = bomb & painting & (any_hit | any_wall)
        blast_delta = paint_end - enemy_pos[:, :, None, :]
        blast_distance = (blast_delta.norm(dim=-1) - 0.35).clamp_min(0)
        blast = torch.where(
            blast_distance <= 2.8, 0.35, torch.where(blast_distance <= 4.0, 0.25, 0.0)
        )
        blast *= self.geo.clear(paint_end, enemy_pos[:, :, None, :], 8).float()
        inflicted += (blast * explosion).sum(
            -1
        )  # Stage0: blast packets merge on impact, delay unmodelled.
        q[..., MASK] = newmask.float()
        q[..., :3] = end
        q[..., PA] += 1
        q[..., ACTIVE] *= (~any_hit & ~wall & (q[..., PA] < q[..., PL])).float()
        # Four-frame box/cylinder contacts, never replaced by a spherical proxy.
        delta = enemy_foot - p
        full_contact = s[..., FULL] > 0
        offset = torch.where(full_contact, 0.5, 0.3) + torch.where(
            full_contact, 0.7, 1.4
        )  # D4 local-forward anchor
        origin = (
            p
            + torch.where(full_contact, 1.2, 0.9)[..., None] * self.constants[7]
            + horizontal * offset[..., None]
        )
        ca = enemy_foot + self.constants[8]
        cb = enemy_foot + self.constants[1]
        local = torch.stack(
            [
                ((ca - origin) * right).sum(-1),
                ca[..., 1] - origin[..., 1],
                ((ca - origin) * horizontal).sum(-1),
            ],
            -1,
        )
        low = local - 0.35
        high = local + self.constants[9]
        half = torch.stack(
            [
                torch.where(full_contact, 0.5, 1.6),
                torch.where(full_contact, 1.4, 0.25),
                torch.where(full_contact, 0.7, 1.4),
            ],
            -1,
        )
        center = torch.stack(
            [
                torch.zeros_like(phase),
                torch.zeros_like(phase),
                torch.where(full_contact, 0.7, 0.4),
            ],
            -1,
        )
        box = ((high >= center - half) & (low <= center + half)).all(-1)
        cylinder = (
            segment_distance(
                ca,
                cb,
                origin - right * 0.5 + horizontal * 1.4,
                origin + right * 0.5 + horizontal * 1.4,
            )
            <= 1.4 + 0.35
        )
        contact = (
            (s[..., CONTACT] >= 1)
            & (s[..., CONTACT] <= 4)
            & (s[..., CONTACT_HIT] == 0)
            & live
            & (phase != 5)
            & (t.flip(1)[..., HP] > 0)
            & (box | (full_contact & cylinder))
        )
        if self.cfg.contact_occlusion == "whole_shape_clear":
            contact &= self.geo.clear(origin, enemy_pos, 8)
        inflicted += contact * torch.where(full_contact, 1.4, 0.2)
        t[..., CONTACT_HIT] = torch.where(contact, 1.0, t[..., CONTACT_HIT])
        # Explicit simple knockback impulse; native displacement calibration is
        # not claimed. It makes the next aim use the actual displaced target.
        push = horizontal * 0.06 * contact[..., None]
        t[..., :3] += push.flip(1)
        received = inflicted.flip(1) * (s[..., PROTECTED] <= 0)
        t[..., PROTECTED] = (s[..., PROTECTED] - 1).clamp_min(0)
        hp = (t[..., HP] - received).clamp_min(0)
        died = live & ((hp <= 1e-6) | (p[..., 1] < -25))
        t[..., HURT] = torch.where(received > 0, 0.0, t[..., HURT])
        recovery = live & (t[..., HURT] > 60) & ~died & ~enemy
        t[..., HURT] = torch.where(enemy, 0.0, t[..., HURT])
        hp = torch.where(recovery, (hp + 1 / 120).clamp_max(1.0), hp)
        hp = torch.where(
            enemy & live,
            torch.minimum(hp, torch.maximum(hp - 0.002, torch.full_like(hp, 0.6))),
            hp,
        )
        t[..., HP] = torch.where(died, 0.0, hp)
        t[..., INK] = torch.where(
            (t[..., RECOVER] == 0) & (charge == 0) & ~zr & ~sp,
            (t[..., INK] + torch.where(submerged, 1 / 180, 1 / 600)).clamp_max(1.0),
            t[..., INK],
        ).clamp(0, 1)
        credited = torch.minimum(received, (1 - s[..., CREDIT]).clamp_min(0))
        t[..., CREDIT] = (s[..., CREDIT] + credited).clamp_max(1.0)
        t[..., RESPAWN] = torch.where(died, 480.0, (s[..., RESPAWN] - 1).clamp_min(0))
        respawn = (s[..., HP] <= 0) & (t[..., RESPAWN] == 0)
        t[..., :3] = torch.where(respawn[..., None], self.geo.spawn, t[..., :3])
        t[..., HP] = torch.where(respawn, 1.0, t[..., HP])
        t[..., INK] = torch.where(respawn, 1.0, t[..., INK])
        t[..., CREDIT] = torch.where(respawn, 0.0, t[..., CREDIT])
        t[..., HURT] = torch.where(respawn, 10000.0, t[..., HURT])
        t[..., PROTECTED] = torch.where(respawn, 180.0, t[..., PROTECTED])
        t[..., PHASE] = torch.where(died | respawn, 0.0, t[..., PHASE])
        t[..., GAUGE] = torch.where(died, t[..., GAUGE] * 0.5, t[..., GAUGE])
        # Surface ink from projectile trails, limited to ground-adjacent cells.
        gains = []
        for owner in range(2):
            before = paint.clone()
            paint = self._paint_disks(
                paint,
                paint_end[:, owner],
                painting[:, owner],
                torch.where(
                    q[:, owner, :, PK] == 4,
                    4.0,
                    torch.where(q[:, owner, :, PK] == 1, 2.3, 1.8),
                ),
                owner,
            )
            gain = ((paint == owner) & (before != owner)).sum(-1).float()
            gains.append(gain)
            g = t[:, owner, GAUGE] + gain / (210.0)
            t[:, owner, GAUGE] = torch.where(
                t[:, owner, PHASE] == 0, g.clamp_max(1.0), t[:, owner, GAUGE]
            )
        paint_reward = (
            (gains[0] - gains[1])
            / self.paint_count
            * (100 * self.cfg.paint_shaping_per_percent)
        )
        damage_reward = (
            credited[:, 1] - credited[:, 0]
        ) * self.cfg.damage_shaping_scale
        # A damage KO is not an unassisted fall. The former counts as a kill;
        # self-splats only cost match time/paint, with no invented opponent kill.
        # Delayed knockback-fall assists are not modeled in this approximation.
        attributed = died & (hp <= 1e-6)
        kills = attributed[:, 1].float() - attributed[:, 0].float()
        r = kills + (damage_reward + paint_reward) * anneal
        reward = torch.stack([r, -r], -1)
        for slot, val in [
            (PREV_ZR, zr),
            (PREV_ZL, zl),
            (PREV_B, jump),
            (PREV_R, rr),
            (PREV_RS, rs),
        ]:
            t[..., slot] = val.float()
        event = torch.stack(
            [
                received,
                died.float(),
                shot.float(),
                hook.float(),
                (phase == 5).float(),
                attributed.float(),
            ],
            -1,
        )
        # Finished environments freeze completely; no hidden post-terminal state changes.
        playing = frame < self.cfg.duration_frames
        return (
            torch.where(playing[:, None, None], t, s),
            torch.where(playing[:, None, None, None], q, shots),
            torch.where(playing[:, None], paint, old_paint),
            reward * playing[:, None],
            event * playing[:, None, None],
        )

    def _observe(self, s, q, paint, frame):
        fwd, right, up = basis(
            s[..., YAW], s[..., PITCH] + self.cfg.camera_pitch_offset_radians
        )
        camera = (
            s[..., :3]
            + self.constants[10]
            - fwd * self.cfg.camera_distance
            + torch.stack(
                [
                    torch.sin(s[..., YAW]),
                    torch.zeros_like(s[..., YAW]),
                    torch.cos(s[..., YAW]),
                ],
                -1,
            )
            * self.cfg.camera_target_forward
        )
        xs = torch.linspace(-1, 1, 32, device=s.device) * math.tan(
            math.radians(self.cfg.camera_horizontal_fov_degrees / 2)
        )
        ys = torch.linspace(1, -1, 18, device=s.device) * math.tan(
            math.radians(self.cfg.camera_vertical_fov_degrees / 2)
        )
        yy, xx = torch.meshgrid(ys, xs, indexing="ij")
        direction = (
            fwd[:, :, None, None, :]
            + xx[None, None, :, :, None] * right[:, :, None, None, :]
            + yy[None, None, :, :, None] * up[:, :, None, None, :]
        )
        direction = direction / direction.norm(dim=-1, keepdim=True)
        origin = camera[:, :, None, None, :]
        dist, kind, normal = self.geo.ray(origin, direction, 64.0, 1.0)
        enemy = s.flip(1)
        person = (
            capsule_first(
                origin,
                origin + direction * 64,
                enemy[:, :, :3][:, :, None, None, :],
                0.35,
            )
            * 64
        )
        visible = (enemy[..., HP] > 0) & (enemy[..., SUB] == 0)
        person_hit = (person < dist) & visible[:, :, None, None]
        kind = torch.where(person_hit, 3, kind)
        dist = torch.where(person_hit, person, dist)
        hit = origin + direction * dist[..., None]
        color = self.geo.color(paint, hit)
        screen = torch.stack(
            [dist, (kind & 3).float(), color.float(), ((kind & 4) > 0).float()], -1
        )
        # Visible entities are projected relative to the camera; never expose xyz.
        positions = torch.cat(
            [
                (s.flip(1)[..., :3] + self.constants[6])[..., None, :],
                q[:, :, :, :3].reshape(self.n, 1, 16, 3).expand(-1, 2, -1, -1),
            ],
            -2,
        )
        velocity = torch.cat(
            [
                s.flip(1)[..., 3:6, None].transpose(-1, -2),
                q[:, :, :, 3:6].reshape(self.n, 1, 16, 3).expand(-1, 2, -1, -1),
            ],
            -2,
        )
        valid = torch.cat(
            [
                ((s.flip(1)[..., HP] > 0) & (s.flip(1)[..., SUB] == 0))[..., None],
                q[:, :, :, ACTIVE].reshape(self.n, 1, 16).expand(-1, 2, -1) > 0,
            ],
            -1,
        )
        delta = positions - camera[:, :, None, :]
        depth = (delta * fwd[:, :, None, :]).sum(-1)
        distance = delta.norm(dim=-1)
        sx = (
            (delta * right[:, :, None, :]).sum(-1)
            / depth.clamp_min(0.01)
            / math.tan(math.radians(self.cfg.camera_horizontal_fov_degrees / 2))
        )
        sy = (
            (delta * up[:, :, None, :]).sum(-1)
            / depth.clamp_min(0.01)
            / math.tan(math.radians(self.cfg.camera_vertical_fov_degrees / 2))
        )
        sight_direction = delta / distance[..., None].clamp_min(1e-6)
        obstruction, _, _ = self.geo.ray(
            camera[:, :, None, :], sight_direction, 64.0, 0.75
        )
        clear = (obstruction >= distance - 0.35) & (distance <= 64.0)
        visible = valid & (depth > 0) & (sx.abs() <= 1) & (sy.abs() <= 1) & clear
        order = torch.topk(
            torch.where(visible, distance, 1e6), 16, largest=False
        ).indices
        types = torch.cat(
            [
                torch.ones((self.n, 2, 1), device=s.device),
                q[:, :, :, PK].reshape(self.n, 1, 16).expand(-1, 2, -1) + 1,
            ],
            -1,
        )
        vx = (velocity * right[:, :, None, :]).sum(-1)
        vy = (velocity * up[:, :, None, :]).sum(-1)
        vz = (velocity * fwd[:, :, None, :]).sum(-1)
        entities = torch.stack([sx, sy, distance, types, vx, vy, vz], -1).gather(
            2, order[..., None].expand(-1, -1, -1, 7)
        )
        mask = visible.gather(2, order)
        entities = torch.where(mask[..., None], entities, 0.0)
        ratios = torch.stack(
            [(paint == i).sum(-1) / self.paint_count for i in range(2)], -1
        )
        turf = ratios[:, None, :].expand(-1, 2, -1)
        hud = torch.cat(
            [
                torch.stack(
                    [s[..., INK], s[..., GAUGE], s[..., SQUID], s[..., SUB]], -1
                ),
                (s[..., CHARGE] / 21).clamp_max(1)[..., None],
                s[..., PHASE, None],
                ((self.cfg.duration_frames - frame) / 60)[:, None, None].expand(
                    -1, 2, 1
                ),
                turf,
                (s[..., HP].clamp(0, 1).mul(4).ceil().div(4))[
                    ..., None
                ],  # own screen-damage cue, quantized
            ],
            -1,
        )
        top = self.geo.map_top
        value = paint[:, top.clamp_min(0)]
        value = torch.where(top >= 0, value, -1)
        minimap = torch.where(
            value[:, None] == self.roles[:, :, None, None],
            1,
            torch.where(value[:, None] >= 0, 2, 0),
        ).to(torch.uint8)
        return {
            "action_mask": self.action_mask.expand(self.n, -1, -1, -1),
            "screen": screen,
            "entities": entities,
            "entity_mask": mask,
            "hud": hud,
            "minimap": minimap,
            "audio": torch.zeros((self.n, 2, 0), device=s.device),
        }
