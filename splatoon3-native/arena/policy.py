"""Allowlisted policy records and the only permitted policy wire encoder.

This module has no referee import, native socket or raw-state accessor. A policy
runner must send encode_policy(observation), never dataclasses.asdict(truth).
The coordinator uses the independent sandboxed worker in process.py.
"""
from dataclasses import dataclass
import json
import math

Vec3 = tuple[float, float, float]


@dataclass(frozen=True)
class PublicPlayer:
    player_id: str
    team: int
    weapon: int
    alive: bool | None


@dataclass(frozen=True)
class OwnState:
    public: PublicPlayer
    position: Vec3 | None
    heading: float | None
    hp: float | None
    ink: float | None
    sample_frame: int | None
    form_squid: bool | None = None
    submerged: bool | None = None
    view_yaw: float | None = None
    view_pitch: float | None = None


@dataclass(frozen=True)
class EnemyView:
    public: PublicPlayer
    visible: bool
    position: Vec3 | None = None
    heading: float | None = None
    sample_frame: int | None = None
    last_seen_position: Vec3 | None = None
    last_seen_frame: int | None = None


@dataclass(frozen=True)
class PolicyObservation:
    match_id: str
    frame: int
    own: OwnState
    enemies: tuple[EnemyView, ...]
    remaining_seconds: float | None
    stage_id: int | None = None


def _point(p):
    if p is None:
        return None
    if type(p) is not tuple or len(p) != 3 or not all(math.isfinite(v) for v in p):
        raise ValueError('invalid policy coordinate')
    return list(p)


def _public(p):
    if type(p) is not PublicPlayer:
        raise TypeError('policy public record required')
    return dict(player_id=p.player_id, team=p.team, weapon=p.weapon, alive=p.alive)


def encode_policy(obs: PolicyObservation) -> bytes:
    """Rebuild a fixed schema; reject truth/dict/subclasses rather than dump them."""
    if type(obs) is not PolicyObservation or type(obs.own) is not OwnState:
        raise TypeError('only PolicyObservation may cross the policy channel')
    own = obs.own
    own_data = dict(public=_public(own.public), position=_point(own.position),
                    heading=own.heading, hp=own.hp, ink=own.ink,
                    sample_frame=own.sample_frame,form_squid=own.form_squid,submerged=own.submerged,
                    view_yaw=own.view_yaw,view_pitch=own.view_pitch)
    enemies = []
    for e in obs.enemies:
        if type(e) is not EnemyView:
            raise TypeError('policy enemy record required')
        if not e.visible and any(v is not None for v in (e.position, e.heading, e.sample_frame)):
            raise ValueError('hidden enemy carries current private state')
        if (e.last_seen_position is None) != (e.last_seen_frame is None):
            raise ValueError('last seen position and frame must be paired')
        enemies.append(dict(public=_public(e.public), visible=e.visible,
                            position=_point(e.position), heading=e.heading,
                            sample_frame=e.sample_frame,
                            last_seen_position=_point(e.last_seen_position),
                            last_seen_frame=e.last_seen_frame))
    payload = dict(schema='arena.policy.v1', match_id=obs.match_id, frame=obs.frame,
                   own=own_data, enemies=enemies, remaining_seconds=obs.remaining_seconds,stage_id=obs.stage_id)
    return (json.dumps(payload, allow_nan=False, separators=(',', ':'))+'\n').encode()
