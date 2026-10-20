"""Opt-in effective A6 movement/sub/special model, with explicit unknowns.

Fitted numbers and extracted sparse tables are generated locally under work/.
This models motion witnesses, not native roll armor or exact wall material.
"""
import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path

import numpy as np

from tools.byml import read
from tools.stage_collision import unpack
from .parameters import ROOT, ROMFS, ENTRY, sha256


@dataclass
class Bomb:
    owner: int
    position: np.ndarray
    velocity: np.ndarray
    age: int = 0


class AdvancedModel:
    def __init__(self, data):
        if data['schema'] != 'sim.advanced.v1':
            raise ValueError('advanced schema')
        self.data = data

    @classmethod
    def load(cls, path):
        return cls(json.loads(Path(path).read_text()))

    def wall(self, env, i):
        p = env.players[i]
        start = p.position + [0, .7, 0]
        forward = np.array([math.sin(p.yaw), 0., math.cos(p.yaw)])
        mesh = env.terrain.obstacles
        if mesh is None:
            return None
        hit = mesh.hits(start, start+forward*.85, .00001)
        if not len(hit):
            return None
        point = start+forward*hit[0]
        return point if env.wall_ink.get(tuple(np.round(point*2).astype(int))) == i else None

    def paint_wall(self, env, point, owner, radius=1.5):
        # Coarse 0.5-unit surface neighborhood. It never scores ground turf.
        # Clinging still requires an actual obstacle ray at query time.
        center = np.round(np.asarray(point)*2).astype(int)
        k = math.ceil(radius*2)
        for x in range(-k, k+1):
            for y in range(-k, k+1):
                for z in range(-k, k+1):
                    if x*x+y*y+z*z <= (radius*2)**2:
                        env.wall_ink[tuple(center+[x, y, z])] = owner

    def prepare(self, env, i, action):
        p = env.players[i]
        b = action['buttons']
        if p.special_active:
            p.special_age += 1
            p.special = max(0., 1-max(0, p.special_age-self.data['zip_activation_delay'])*self.data['zip_drain'])
            if p.special_age > self.data['zip_activation_delay']:
                p.ink = max(0., p.ink-self.data['zip_ink_drain'])
            if not p.special:
                # Simplified return to anchor, no invulnerability/attack bonus.
                p.position = p.special_anchor.copy()
                p.velocity[:] = 0.
                p.grounded = False
                p.special_active = False
                env.events.append(dict(kind='zip_return', frame=env.frame, player=i))
            if b[2] and not p.previous[2]:
                env.unsupported['zipcaster_hook_displacement'] += 1
        elif b[3] and not p.previous[3] and p.special >= 1.:
            p.special_active = True
            p.special_age = 0
            p.special_anchor = p.position.copy()
            env.events.append(dict(kind='zip_activate_simplified', frame=env.frame, player=i))
        if p.previous[2] and not b[2] and not p.special_active and not p.squid:
            self.throw(env, i)

    def motion(self, env, i, action, old_velocity):
        """Called after ordinary horizontal velocity but before jump/collision."""
        p = env.players[i]
        b, sticks = action['buttons'], action['sticks']
        edge = bool(b[4] and not p.previous[4])
        release = bool(not b[4] and p.previous[4])
        forward = np.array([math.sin(p.yaw), math.cos(p.yaw)])
        desired = np.array([-sticks[0]*math.cos(p.yaw)+sticks[1]*math.sin(p.yaw),
                            sticks[0]*math.sin(p.yaw)+sticks[1]*math.cos(p.yaw)])
        magnitude = np.linalg.norm(desired)
        speed = np.linalg.norm(old_velocity[[0, 2]])
        reversal = float(np.dot(desired, old_velocity[[0, 2]])) < -.5*magnitude*speed
        if edge and p.submerged and speed >= self.data['roll_min_speed'] and magnitude >= .9 and reversal:
            p.roll_left = self.data['roll_duration']
            p.roll_direction = desired/magnitude
            p.velocity[1] = self.data['roll_impulse']
            p.grounded = p.submerged = False
            env.events.append(dict(kind='squid_roll', frame=env.frame, player=i))
        wall = self.wall(env, i) if p.squid and not p.roll_left and not p.surge_left else None
        if wall is not None:
            p.grounded = False
            if b[4]:
                p.wall_charge += 1
                p.velocity[:] = 0.
            elif release and p.wall_charge:
                powered = p.wall_charge >= self.data['surge_charge_frames']
                p.surge_left = self.data['surge_duration']
                p.surge_speed = self.data['surge_speed'] if powered else self.data['wall_jump_speed']
                p.wall_charge = 0
                env.events.append(dict(kind='squid_surge' if powered else 'wall_jump', frame=env.frame, player=i))
            else:
                p.velocity[[0, 2]] = forward*.02
                p.velocity[1] = max(0., sticks[1])*.12
        else:
            p.wall_charge = 0
        overridden = bool(p.roll_left or p.surge_left or p.dash_left or wall is not None)
        p.wall_cling = wall is not None
        if p.roll_left:
            elapsed = self.data['roll_duration']-p.roll_left
            p.velocity[[0, 2]] = p.roll_direction*(self.data['roll_speed'] if elapsed >= self.data['roll_latch_frames'] else 0.)
            p.roll_left -= 1
        if p.surge_left:
            p.velocity[1] = p.surge_speed
            p.velocity[[0, 2]] = forward*.025
            p.surge_left -= 1
        if p.dash_left:
            elapsed = self.data['dash_duration']-p.dash_left
            p.velocity[[0, 2]] = p.dash_direction*(self.data['dash_distance']/self.data['dash_move_frames']
                                                 if elapsed >= self.data['dash_charge_frames'] else 0.)
            p.dash_left -= 1
        return overridden

    def gravity(self, env, p):
        base = env.rules.gravity if env.motion_model is None else env.motion_model.data['jump']['gravity']
        return self.data['roll_gravity'] if p.roll_left else (0. if p.surge_left or p.wall_cling else base)

    def dash(self, env, i):
        p = env.players[i]
        p.dash_left = self.data['dash_duration']
        p.dash_end_frame = env.frame+p.dash_left-1
        p.dash_direction = np.array([math.sin(p.yaw), math.cos(p.yaw)])
        env.events.append(dict(kind='dash', frame=env.frame, player=i))

    def throw(self, env, i):
        p = env.players[i]
        table = self.data['bomb_parameters']
        cost = table['WeaponParam']['InkConsume']
        if p.ink+1e-8 < cost:
            env.events.append(dict(kind='dry_bomb', frame=env.frame, player=i))
            return
        p.ink -= cost
        p.recover_stop = table['WeaponParam']['InkRecoverStop']
        forward, _, direction, _ = env._basis(p)
        position = p.position+[0, 1., 0]+forward*.6
        if not env.terrain.human.clear(p.position+[0, .7, 0], position, .00001):
            position = p.position+[0, .7, 0]
        velocity = direction*table['MoveParam']['SpawnSpeedZSpecUp']['Low']+[0, table['MoveParam']['SpawnSpeedY'], 0]
        env.bombs.append(Bomb(i, position, velocity))
        env.events.append(dict(kind='burst_bomb_throw', frame=env.frame, player=i, cost=cost))

    def weapons(self, env):
        from .engine import segment_distance
        remaining = []
        for bomb in env.bombs:
            end = bomb.position+bomb.velocity
            target = 1-bomb.owner
            a, b, radius = env._capsule(target)
            wall = env.terrain.human.hits(bomb.position, end, .00001)
            length = np.linalg.norm(end-bomb.position)
            distance = wall[0] if len(wall) else math.inf
            # Keep blast ray origin on the incoming side of the wall. Starting
            # exactly on its triangle would evade the segment endpoint epsilon.
            fraction = min(1., max(0.,distance-.01)/max(length, 1e-9))
            impact = bomb.position+(end-bomb.position)*fraction
            direct = (env.players[target].alive and
                      segment_distance(bomb.position, impact, a, b) <= radius+self.data['bomb_radius'])
            if direct or distance < math.inf:
                if direct:
                    # Missing sparse direct-damage default: empirical A6 25.
                    env.damage_queue.append((env.frame+self.data['bomb_delivery_delay'], target,
                                             self.data['bomb_direct_damage'], bomb.owner, 'burst_bomb_direct'))
                dist = max(0., min(np.linalg.norm(impact-a), np.linalg.norm(impact-b))-radius)
                blast = self.data['bomb_parameters']['BlastParam']
                for row in blast['DistanceDamage']:
                    if dist <= row['Distance']:
                        if env.terrain.sight.clear(impact, env.players[target].position+[0, .7, 0], .00001):
                            delay = self.data['bomb_delivery_delay']+(self.data['bomb_packet_gap'] if direct else 0)
                            env.damage_queue.append((env.frame+delay, target, row['Damage']/1000, bomb.owner, 'burst_bomb_blast'))
                        break
                env._paint(bomb.owner, impact, blast['PaintRadius'])
                self.paint_wall(env, impact, bomb.owner)
                env.events.append(dict(kind='burst_bomb_impact', frame=env.frame, player=bomb.owner, direct=bool(direct)))
            elif bomb.age < 120:
                bomb.position = end
                bomb.velocity[1] -= self.data['bomb_gravity']
                bomb.age += 1
                remaining.append(bomb)
        env.bombs = remaining


def build(out=ROOT/'work/sim/advanced/model.json'):
    out = Path(out).resolve()
    if ROOT/'work' not in out.parents:
        raise ValueError('extracted/fitted data must stay under work/')
    accepted = json.loads((ROOT/'arena/results/a6-acceptance.json').read_text())['native']
    sources = {}
    def case(group, kind):
        ref = accepted[group]; path = ROOT/ref['path']
        if sha256(path) != ref['sha256']:
            raise ValueError('A6 source drift')
        sources[group] = dict(path=ref['path'], sha256=ref['sha256'])
        return next(c for c in json.loads(path.read_text())['cases'] if c['kind'] == kind)
    roll = case('roll', 'squid-roll-matched')
    edge = next(v['infos']['player_0']['frame'] for v in roll['history'] if v['phase'] == 'roll_edge')
    baseline = next(v['infos']['player_0']['position'] for v in reversed(roll['history']) if v['phase'] == 'swim')
    unique = {v['infos']['player_0']['position_sample_frame']:v['infos']['player_0']['position']
              for v in roll['history'] if v['phase'] in ('roll_edge', 'roll_travel')}
    ts, ys = [], []
    for f, pos in sorted(unique.items()):
        t = f-edge+1
        if t > 0:
            ts.append(t); ys.append(pos[1]-baseline[1])
    t = np.array(ts)
    # Integrator first step is impulse-gravity. Preserve effective input origin.
    impulse, gravity = np.linalg.lstsq(np.column_stack([t, -.5*t*(t+1)]), ys, rcond=None)[0]
    positions = np.array([pos for f,pos in sorted(unique.items()) if f > edge])
    times = np.array([f for f in sorted(unique) if f > edge])
    roll_speed = float(np.median(np.linalg.norm(np.diff(positions[:, [0, 2]], axis=0), axis=1)/np.diff(times)))
    surge = case('aim_surge', 'surge-stopped-charge')
    control = case('aim_surge', 'surge-stopped-control')
    def powered_speed(c, phase):
        rows = [v for v in c['history'] if v['phase'] == phase]
        start = rows[0]['infos']['player_0']['frame']-rows[0].get('frames', 3)
        base = (next(v['infos']['player_0']['position'][1] for v in reversed(c['history']) if v['phase']=='wall_charge')
                if phase == 'surge_release' else c['before']['position'][1])
        unique = {v['infos']['player_0']['position_sample_frame']:v['infos']['player_0']['position'][1] for v in rows}
        ts = np.array([max(0, f-start) for f in unique], float)
        ys = np.array([y-base for y in unique.values()])
        return float(np.dot(ts, ys)/np.dot(ts, ts))
    bomb = case('combo_bomb', 'burst-bomb')
    zipcase = case('zip_activation', 'zipcaster')
    pack = ROMFS/'Pack/Params.pack.zs'
    tables = unpack(pack)
    weapon = read(tables[ENTRY.format('WeaponSaberNormal')])['GameParameters']['spl__WeaponSaberParam']
    side = weapon['SwingParam']['SideStepParam']
    bomb_table = read(tables[ENTRY.format('WeaponBombQuick')])['GameParameters']
    player = read(tables[ENTRY.format('SplPlayer')])['GameParameters']
    model = dict(schema='sim.advanced.v1', sources=sources,
                 fitting_source_sha256=sha256(__file__),
                 sparse_source=dict(path=str(pack.relative_to(ROOT)), sha256=sha256(pack)),
                 roll_impulse=float(impulse), roll_gravity=float(gravity), roll_speed=roll_speed,
                 roll_latch_frames=2, roll_duration=36, roll_min_speed=.12,
                 surge_speed=powered_speed(surge, 'surge_release'),
                 wall_jump_speed=powered_speed(control, 'unpowered_release'), surge_duration=24,
                 surge_charge_frames=player['spl__PlayerGearSkillParam_ActionSpecUp_Squid']['WallJumpChargeFrm_Low'],
                 dash_charge_frames=side['ChargeFrame'], dash_move_frames=side['MoveFrame'],
                 dash_duration=side['ChargeFrame']+side['MoveFrame'], dash_distance=side['MoveDist'],
                 dash_projectile_frame=weapon['SwingParam']['ChargeSwingStepShotBulletFrame'],
                 dash_slash_frame=weapon['SwingParam']['ChargeSwingStepShotSlashFrame'],
                 bomb_parameters=bomb_table, bomb_gravity=.04, bomb_radius=.25,
                 bomb_direct_damage=.25, bomb_delivery_delay=6, bomb_packet_gap=8,
                 bomb_reference_loss=bomb['target_hp_loss'], zip_activation_delay=9,
                 zip_ink_drain=(zipcase['before']['ink']-zipcase['after']['ink'])/(zipcase['after']['position_sample_frame']-zipcase['before']['frame']-9),
                 zip_drain=(1-zipcase['after']['special'])/(zipcase['after']['position_sample_frame']-zipcase['before']['frame']-9),
                 limitations=['A6 fits are calibration rechecks, no held-out advanced rooms.',
                              'Roll data ends before apex/landing; extrapolated duration, trigger threshold and armor unknown.',
                              'Surge uses powered rise, coarse wall ink, AP=0 threshold; climb/material/gear effects unknown.',
                              'Bomb gravity/radius/muzzle and packet decomposition are effective candidates; blast uses sparse table.',
                              'Zipcaster only activation, drain and return; hook displacement unsupported, no armor.'])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(model, indent=2)+'\n')
    return model


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, default=ROOT/'work/sim/advanced/model.json')
    a = p.parse_args()
    d = build(a.out)
    print(json.dumps({k:v for k,v in d.items() if k not in ('bomb_parameters',)}, indent=2))
