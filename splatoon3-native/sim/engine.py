"""Deterministic fixed60 core. All unmeasured defaults are explicit assumptions.

State is private to the referee. Policies receive the existing typed arena
projection, never an engine object. No imports of native runners or host APIs.
"""
from collections import Counter
from dataclasses import dataclass, field
import json
import math
import uuid

import numpy as np

from arena.control_process import OwnSpecial, encode_control
from arena.geometry import GeometricVision
from arena.process import validate_action
from arena.referee import PlayerTruth, PublicStatus, RefereeSnapshot
from arena.visibility import PolicyProjector
from rl.loadout import encode_loadout
from .parameters import Parameters
from .terrain import Paint, Terrain


def neutral():
    return dict(sticks=[0.] * 4, gyro=[0.] * 3, buttons=[0] * 6)


@dataclass(frozen=True)
class Assumptions:
    """World units / controlled present. These are NOT sparse-BYML defaults."""
    walk_speed: float = .096
    swim_speed: float = .192
    acceleration: float = .024
    enemy_ink_speed: float = .024
    gravity: float = .008
    jump_speed: float = .12
    terrain_radius: float = .3  # accepted A4 navigation approximation
    squid_recover: float = 1 / 180
    human_recover: float = 1 / 600
    hp_recover: float = 1 / 120
    hp_recover_delay: int = 60
    enemy_ink_damage: float = .002
    enemy_ink_hp_floor: float = .6
    respawn_frames: int = 480
    spawn_protection_frames: int = 180
    emerge_delay: int = 5  # A6 26 - 21 observed input boundary
    light_input_period: int = 30  # A6; 26-pulse rejected
    gyro_yaw_gain: float = .25062904  # A6 cold pulse; no native smoothing yet
    stick_yaw_gain: float = .018
    gyro_pitch_gain: float = .12
    points_per_world_area: float = 1.  # unknown native conversion
    death_special_retention: float = .5


def gear_ap(loadout):
    """Only directly declared skills; conditional/main-only effects not invented."""
    result = Counter()
    for slot in (loadout or {}).values():
        result[slot['main']] += 10
        for skill in slot['subs']:
            result[skill] += 3
    return result


def gear_factor(skill, ap):
    """Two A2 anchors; interpolation elsewhere is explicitly unvalidated."""
    if skill == 'swim_speed_up':
        # Mean observed 6-unit travel ratio, AP=19 (31.860587/28.085449,
        # 32.217042/27.948629). No claim about native curve or acceleration.
        return 1 + .138 * min(ap, 57) / 19
    if skill == 'ink_saver_main':
        return max(.1, 1 - (1 - .031779587 / .051999986) * min(ap, 57) / 38)
    return 1.


@dataclass
class Player:
    position: np.ndarray
    heading: float
    yaw: float
    pitch: float = 0.
    velocity: np.ndarray = field(default_factory=lambda: np.zeros(3))
    hp: float = 1.
    ink: float = 1.
    special: float = 0.
    alive: bool = True
    squid: bool = False
    submerged: bool = False
    grounded: bool = True
    charge: int = 0
    emerge: int = 0
    cooldown: int = 0
    recover_stop: int = 0
    hurt_at: int = -10000
    respawn_at: int = 0
    protected_until: int = 0
    previous: list = field(default_factory=lambda: [0] * 6)
    ap: dict = field(default_factory=dict)


@dataclass
class Projectile:
    owner: int
    position: np.ndarray
    direction: np.ndarray
    right: np.ndarray
    up: np.ndarray
    profile: dict
    age: int = 0
    velocity_y: float = 0.


@dataclass
class Slash:
    owner: int
    position: np.ndarray
    right: np.ndarray
    forward: np.ndarray
    profile: dict
    until: int
    hit: bool = False


def point_segment_distance(point, start, end):
    d = end - start
    t = np.clip(np.dot(point - start, d) / max(1e-12, np.dot(d, d)), 0., 1.)
    return float(np.linalg.norm(point - (start + t * d)))


def segment_distance(a, b, c, d):
    """Minimum distance of two finite 3D segments, including parallel cases."""
    u, v, w = b - a, d - c, a - c
    aa, bb, cc = np.dot(u, u), np.dot(u, v), np.dot(v, v)
    dd, ee = np.dot(u, w), np.dot(v, w)
    determinant = aa * cc - bb * bb
    candidates = [point_segment_distance(a, c, d), point_segment_distance(b, c, d),
                  point_segment_distance(c, a, b), point_segment_distance(d, a, b)]
    if determinant > 1e-12:
        s, t = (bb * ee - cc * dd) / determinant, (aa * ee - bb * dd) / determinant
        if 0 <= s <= 1 and 0 <= t <= 1:
            candidates.append(float(np.linalg.norm(w + s * u - t * v)))
    return min(candidates)


class Simulator:
    metadata = {'render_modes': [], 'name': 's1_core_v1'}

    def __init__(self, stage_id=1, *, parameters=None, terrain=None, assumptions=None,
                 loadouts=None, duration_frames=10800, swap=False):
        if stage_id not in (1, 2, 3) or type(duration_frames) is not int or duration_frames < 1:
            raise ValueError('stage/duration')
        self.stage_id = stage_id
        self.params = parameters or Parameters.local()
        self.terrain = terrain or Terrain.load(stage_id)
        self.rules = assumptions or Assumptions()
        self.loadouts = loadouts or [None, None]
        if len(self.loadouts) != 2:
            raise ValueError('two loadouts required')
        for loadout in self.loadouts:
            if loadout is not None:
                encode_loadout(loadout)
        self.duration = duration_frames
        self.swap = bool(swap)
        self.reset()

    def reset(self, seed=None, options=None):
        # Core has no random mechanics. Seed retained for reproducibility metadata.
        self.seed = seed
        self.frame = 0
        self.match_id = 'sim-' + uuid.uuid4().hex
        self.paint = Paint(self.terrain)
        self.players = []
        for team in range(2):
            side = team ^ self.swap
            yaw = math.pi if side == 0 else 0.
            self.players.append(Player(self.terrain.spawn[side].copy(), yaw, yaw,
                                       ap=gear_ap(self.loadouts[team])))
        self.projectiles, self.slashes, self.scheduled = [], [], []
        self.events = []
        self.unsupported = Counter()
        supported_gear = {'swim_speed_up', 'ink_saver_main', 'quick_super_jump', 'ninja_squid'}
        for p in self.players:
            for skill in p.ap:
                if skill not in supported_gear:
                    self.unsupported['gear:' + skill] += 1
        self.projector = PolicyProjector(self.match_id, stage_id=self.stage_id)
        self.vision = GeometricVision(self.terrain.sight)
        self._observations = None
        return self.observations(), self.info()

    @property
    def done(self):
        return self.frame >= self.duration

    def info(self):
        ratios = self.paint.ratios()
        return dict(frame=self.frame, turf_ratio_by_role=ratios,
                    winner=(None if not self.done or ratios[0] == ratios[1] else int(ratios[1] > ratios[0])),
                    unsupported=dict(self.unsupported), fidelity='approximate_core',
                    native_paint_comparable=False)

    def truth(self):
        players, public = [], []
        for i, p in enumerate(self.players):
            motion = bool(np.linalg.norm(p.velocity[[0, 2]]) > .045 or not p.grounded)
            if p.ap.get('ninja_squid') and p.grounded:
                motion = False
            players.append(PlayerTruth(f'player_{i}', i, 8000, p.alive,
                           tuple(map(float, p.position)), p.heading, p.hp, p.ink,
                           p.submerged, self.frame, p.squid, motion, p.yaw, p.pitch))
            public.append(PublicStatus(f'player_{1-i}', f'player_{i}', p.alive, self.frame))
        # Private simulator paint is in Paint; the existing native-unavailable
        # fields remain None so no synthetic grid is mistaken for native A3b.
        return RefereeSnapshot(self.match_id, self.frame, tuple(players),
                               max(0, (self.duration - self.frame) / 60), public_status=tuple(public))

    def typed_observation(self, team):
        self.observations()
        return self._typed[team]

    def observations(self):
        if self._observations is None:
            truth = self.truth()
            self._typed, self._observations = {}, {}
            for i, p in enumerate(self.players):
                observer = f'player_{i}'
                obs = self.projector.observe(truth, observer, self.vision.witnesses(truth, observer))
                self._typed[i] = obs
                self._observations[observer] = json.loads(encode_control(obs, OwnSpecial(observer, self.frame, p.special)))
        # Caller cannot mutate subsequent observations or simulator state.
        return json.loads(json.dumps(self._observations))

    def step(self, actions, frames=1, *, observe=True):
        if type(frames) is not int or frames < 1 or self.frame + frames > self.duration:
            raise ValueError('step budget outside match')
        if set(actions) != {'player_0', 'player_1'}:
            raise ValueError('both simultaneous actions required')
        values = [validate_action(actions[f'player_{i}']) for i in range(2)]
        for _ in range(frames):
            self.frame += 1
            # Update both movement/weapon states before resolving any damage.
            for i, action in enumerate(values):
                self._player(i, action)
            self._weapons()
            self._observations = None
        return (self.observations() if observe else None), self.info()

    def _kill(self, target, attacker, cause):
        p = self.players[target]
        if not p.alive:
            return
        p.alive = False
        p.hp = 0.
        p.respawn_at = self.frame + self.rules.respawn_frames
        p.special *= self.rules.death_special_retention
        p.charge = 0
        p.velocity[:] = 0
        p.squid = p.submerged = False
        self.events.append(dict(kind='knockdown', frame=self.frame, target=target,
                                attacker=attacker, cause=cause))

    def _player(self, i, action):
        p, r = self.players[i], self.rules
        b, sticks, gyro = action['buttons'], action['sticks'], action['gyro']
        if not p.alive:
            if self.frame >= p.respawn_at:
                side = i ^ self.swap
                p.position = self.terrain.spawn[side].copy()
                p.hp = p.ink = 1.
                p.alive = True
                p.cooldown = p.emerge = p.recover_stop = 0
                p.grounded = True
                p.yaw = p.heading = math.pi if side == 0 else 0.
                p.pitch = 0.
                p.protected_until = self.frame + r.spawn_protection_frames
                p.previous = list(b)
                self.events.append(dict(kind='respawn', frame=self.frame, player=i))
            return
        p.cooldown = max(0, p.cooldown - 1)
        p.recover_stop = max(0, p.recover_stop - 1)
        p.yaw = math.atan2(math.sin(p.yaw - sticks[2] * r.stick_yaw_gain + gyro[2] * r.gyro_yaw_gain),
                           math.cos(p.yaw - sticks[2] * r.stick_yaw_gain + gyro[2] * r.gyro_yaw_gain))
        p.pitch = float(np.clip(p.pitch - gyro[0] * r.gyro_pitch_gain + sticks[3] * .012, -.9, .9))
        if b[5] and not p.previous[5]:
            p.yaw = p.heading
        previous_submerged = p.submerged
        p.squid = bool(b[1])
        color = self.paint.at(p.position)
        p.submerged = p.squid and p.grounded and color == i
        if previous_submerged and not p.squid:
            p.emerge = r.emerge_delay
        elif p.emerge:
            p.emerge -= 1
        if p.squid:
            p.charge = 0  # no charge keep
        elif b[0] and not p.cooldown and not p.emerge:
            p.charge += 1
        elif not b[0] and p.previous[0] and p.charge:
            self._release(i, dash=sticks[1] >= .9)
        if b[2] and not p.previous[2]:
            self.unsupported['burst_bomb'] += 1
        if b[3] and not p.previous[3]:
            self.unsupported['zipcaster'] += 1
        x, z = sticks[:2]
        norm = max(1., math.hypot(x, z))
        speed = r.walk_speed
        if p.submerged:
            speed = r.swim_speed * gear_factor('swim_speed_up', p.ap.get('swim_speed_up', 0))
        elif color not in (-1, i) and p.grounded:
            speed = r.enemy_ink_speed
        elif p.squid:
            speed *= .5
        if p.charge:
            speed *= self.params.charge['MoveSpeedFullCharge']
        if p.cooldown:
            speed = min(speed, self.params.swing['WeakSwingMoveVelLimit'])
        target = np.array([-x * math.cos(p.yaw) + z * math.sin(p.yaw), 0.,
                            x * math.sin(p.yaw) + z * math.cos(p.yaw)]) * speed / norm
        for axis in (0, 2):
            p.velocity[axis] += float(np.clip(target[axis] - p.velocity[axis], -r.acceleration, r.acceleration))
        if math.hypot(x, z) > .1 or b[0]:
            p.heading = p.yaw
        if b[4] and not p.previous[4] and p.grounded:
            p.velocity[1] = r.jump_speed
            p.grounded = False
            p.submerged = False
            if p.squid:
                self.unsupported['squid_roll_or_surge_as_ordinary_jump'] += 1
        old = p.position.copy()
        p.position = self.terrain.move(p.position, p.velocity, r.terrain_radius, p.grounded)
        ground = self.terrain.human.floor(p.position[0], p.position[2], p.position[1] + .205)
        if p.grounded and (ground is None or p.position[1] - ground > .3):
            p.grounded = False
        if not p.grounded:
            p.velocity[1] -= r.gravity
            next_y = p.position[1] + p.velocity[1]
            # Head sweep prevents jumping through ceilings.
            if p.velocity[1] > 0 and not self.terrain.human.clear(p.position + [0, 1.3, 0],
                                            np.array([p.position[0], next_y + 1.3, p.position[2]]), .00001):
                p.velocity[1] = 0.
            elif p.velocity[1] <= 0 and ground is not None and next_y <= ground:
                p.position[1] = ground
                p.velocity[1] = 0.
                p.grounded = True
            else:
                p.position[1] = next_y
        if p.position[1] < -25:
            self._kill(i, None, 'fall')
        if p.grounded:
            p.velocity[[0, 2]] = (p.position - old)[[0, 2]]
        color = self.paint.at(p.position)
        p.submerged = p.squid and p.grounded and color == i
        if color not in (-1, i) and p.grounded and self.frame >= p.protected_until:
            p.hp = max(min(p.hp, r.enemy_ink_hp_floor), p.hp - r.enemy_ink_damage)
            p.hurt_at = self.frame
        elif self.frame - p.hurt_at > r.hp_recover_delay:
            p.hp = min(1., p.hp + r.hp_recover)
        if not p.recover_stop and not p.charge and not b[0]:
            p.ink = min(1., p.ink + (r.squid_recover if p.submerged else r.human_recover))
        p.previous = list(b)

    def _release(self, owner, dash=False):
        p = self.players[owner]
        full = p.charge >= self.params.charge['ChargeFrameFullCharge'] + 1
        if full and dash:
            self.unsupported['dash_as_ordinary_charge'] += 1
        cost = (self.params.charge['InkConsumeFullCharge'] if full else self.params.swing['InkConsume'])
        cost *= gear_factor('ink_saver_main', p.ap.get('ink_saver_main', 0))
        p.charge = 0
        if p.ink + 1e-9 < cost:
            self.events.append(dict(kind='dry', frame=self.frame, player=owner))
            return
        p.ink = max(0., p.ink - cost)
        p.recover_stop = self.params.swing['InkRecoverStop']
        p.cooldown = (self.params.swing['ChargeSwingFrame'] + self.params.swing['ChargeSwingPostDelayFrame']
                      if full else self.rules.light_input_period - 1)
        prefix = 'Charge' if full else 'Weak'
        for kind, suffix in (('projectile', 'Bullet'), ('slash', 'Slash')):
            delay = self.params.swing[f'{prefix}SwingShot{suffix}Frame']
            self.scheduled.append((self.frame + delay, owner, full, kind))
        self.events.append(dict(kind='release', frame=self.frame, player=owner, full=full, cost=cost))

    def _basis(self, p):
        forward = np.array([math.sin(p.yaw), 0., math.cos(p.yaw)])
        right = np.array([math.cos(p.yaw), 0., -math.sin(p.yaw)])
        direction = forward * math.cos(p.pitch) + np.array([0., math.sin(p.pitch), 0.])
        up = np.cross(direction, right)
        return forward, right, direction, up

    def _spawn(self, owner, full, kind):
        p = self.players[owner]
        if not p.alive:
            return
        forward, right, direction, up = self._basis(p)
        suffix = 'Vertical' if full else 'Horizontal'
        if kind == 'projectile':
            profile = self.params.weapon[f'BulletSaber{suffix}Param']
            offset = self.params.swing['ShotBulletOffset_Vertical' if full else 'ShotBulletOffset_L']
            position = p.position + right * offset['X'] + up * offset['Y'] + direction * offset['Z']
            # Never spawn on the far side of a wall between player and muzzle.
            if self.terrain.human.clear(p.position + [0, .7, 0], position, .00001):
                self.projectiles.append(Projectile(owner, position, direction, right, up, profile))
        else:
            profile = self.params.weapon[f'BulletSaberSlash{suffix}Param']
            offset = self.params.swing['ShotSlashOffset_Vertical' if full else 'ShotSlashOffset_L']
            position = p.position + right * offset['X'] + [0, offset['Y'], 0] + forward * offset['Z']
            self.slashes.append(Slash(owner, position, right, forward, profile,
                                      self.frame + profile['MoveParam']['AliveFrame']))

    def _capsule(self, target):
        p = self.players[target]
        shape = self.params.target_capsule
        def vec(key):
            return np.array([shape[key][axis] for axis in 'XYZ'])
        if p.squid:
            # RomFS squid radius override, floor-anchored approximation.
            rad = self.params.data['tables']['SplPlayer']['spl__PlayerCollisionParam']['ColBullet_Radius_Squid']
            a = p.position + [0, .25, 0]
            return a, a, rad
        return p.position + vec('CenterA'), p.position + vec('CenterB'), shape['Radius']

    def _damage(self, target, amount, owner, cause):
        p = self.players[target]
        if p.alive and self.frame >= p.protected_until:
            p.hp = max(0., p.hp - amount)
            p.hurt_at = self.frame
            self.events.append(dict(kind='damage', frame=self.frame, target=target,
                                    attacker=owner, amount=amount, cause=cause))
            if p.hp <= 1e-9:
                self._kill(target, owner, cause)

    def _paint(self, owner, position, radius):
        floor = self.terrain.human.floor(position[0], position[2], position[1] + .1)
        if floor is not None and 0 <= position[1] - floor < 3.1:
            area = self.paint.disk((position[0], floor, position[2]), radius, owner)
            p = self.players[owner]
            p.special = min(1., p.special + area * self.rules.points_per_world_area / self.params.data['weapon_info']['SpecialPoint'])

    def _weapons(self):
        pending = []
        for frame, owner, full, kind in self.scheduled:
            if frame == self.frame:
                self._spawn(owner, full, kind)
            else:
                pending.append((frame, owner, full, kind))
        self.scheduled = pending
        hits, surviving = [], []
        for shot in self.projectiles:
            profile = shot.profile
            move = profile['MoveParam']
            speed = move['SpawnSpeed']
            if shot.age >= move['GoStraightToBrakeStateFrame']:
                shot.velocity_y -= move['BrakeGravity']
            end = shot.position + shot.direction * speed + [0, shot.velocity_y, 0]
            target = 1 - shot.owner
            a, b, radius = self._capsule(target)
            hit = False
            field_hit = math.inf
            for offset, shape in zip(profile['CollisionParam']['OffsetArray'], profile['CollisionParam']['ParamArray']):
                shift = shot.right * offset['X'] + shot.up * offset['Y'] + shot.direction * offset['Z']
                start_s, end_s = shot.position + shift, end + shift
                obstacle = self.terrain.human.sweep(start_s, end_s, shape['InitRadiusForField'])
                field_hit = min(field_hit, obstacle)
                # Test the part of the sphere path before field collision only.
                length = np.linalg.norm(end_s - start_s)
                fraction = min(1., obstacle / max(1e-9, length))
                end_visible = start_s + (end_s - start_s) * fraction
                if (self.players[target].alive and segment_distance(start_s, end_visible, a, b)
                        <= radius + shape['InitRadiusForPlayer']):
                    hit = True
            if hit:
                hits.append((target, profile['DamageParam']['HitDamage'] / 1000, shot.owner, 'ink_blade'))
            fraction = min(1., field_hit / max(1e-9, np.linalg.norm(end - shot.position)))
            paint_end = shot.position + (end - shot.position) * fraction
            self._paint(shot.owner, paint_end, profile['PaintParam']['WidthHalf'])
            shot.age += 1
            shot.position = end
            if not hit and not math.isfinite(field_hit) and shot.age < profile['BurstParam']['BurstFrame']:
                surviving.append(shot)
        self.projectiles = surviving
        slashes = []
        for slash in self.slashes:
            if self.frame >= slash.until:
                continue
            target = 1 - slash.owner
            shape = slash.profile['ShapeParam']
            a, b, radius = self._capsule(target)
            center = np.array([shape['BoxCenter'][k] for k in 'XYZ'])
            half = np.array([shape['BoxHalfExtents'][k] for k in 'XYZ'])
            # Vertical target capsule intersects oriented slash box, expanded
            # by its radius. This is conservative at box corners.
            local_a = np.array([np.dot(a - slash.position, slash.right), a[1] - slash.position[1], np.dot(a - slash.position, slash.forward)])
            local_b = local_a + [0, b[1] - a[1], 0]
            low, high = np.minimum(local_a, local_b) - radius, np.maximum(local_a, local_b) + radius
            hit = bool(np.all(high >= center - half) and np.all(low <= center + half))
            if shape['HasCylinderShape']:
                def world(key):
                    v = shape[key]
                    return slash.position + slash.right * v['X'] + [0, v['Y'], 0] + slash.forward * v['Z']
                hit |= segment_distance(a, b, world('CylinderCenterA'), world('CylinderCenterB')) <= radius + shape['CylinderRadius']
            if (not slash.hit and self.players[target].alive and hit and
                    self.terrain.human.clear(slash.position, (a + b) / 2, .00001)):
                hits.append((target, slash.profile['DamageParam']['DamageValue'] / 1000, slash.owner, 'contact'))
                slash.hit = True
            slashes.append(slash)
        self.slashes = slashes
        # Resolve collected hits after both shooters have acted: simultaneous
        # lethal attacks can trade instead of depending on player index.
        for target, damage, owner, cause in hits:
            self._damage(target, damage, owner, cause)


class BatchSimulator:
    """Parallel-env shaped API, serial CPU stepping; no vectorization claim."""
    def __init__(self, count, stage_id=1, **kwargs):
        if type(count) is not int or count < 1:
            raise ValueError('positive batch size required')
        params = kwargs.pop('parameters', None) or Parameters.local()
        terrain = kwargs.pop('terrain', None) or Terrain.load(stage_id)
        self.envs = [Simulator(stage_id, parameters=params, terrain=terrain, **kwargs) for _ in range(count)]

    def reset(self, seed=None):
        return [env.reset(None if seed is None else seed + i) for i, env in enumerate(self.envs)]

    def step(self, actions, frames=1):
        if len(actions) != len(self.envs):
            raise ValueError('one simultaneous action dictionary per environment')
        return [env.step(a, frames) for env, a in zip(self.envs, actions)]
