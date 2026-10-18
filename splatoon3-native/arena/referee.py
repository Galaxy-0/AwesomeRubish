"""Private referee types. Never serialize these to a policy process.

Frames here are match-relative controlled presents, not per-host absolute frame
numbers. A future native adapter must convert the latter before constructing a
snapshot. Unknown signals remain None; an empty tuple means measured no events.
"""
from dataclasses import dataclass

Vec3 = tuple[float, float, float]


@dataclass(frozen=True)
class PlayerTruth:
    player_id: str
    team: int
    weapon: int
    alive: bool | None
    position: Vec3 | None
    heading: float | None
    hp: float | None
    ink: float | None
    submerged: bool | None
    sample_frame: int | None
    form_squid: bool | None = None
    motion_visible: bool | None = None
    view_yaw: float | None = None
    view_pitch: float | None = None


@dataclass(frozen=True)
class Knockdown:
    victim: str
    attacker: str | None  # None only for a verified environmental death.
    weapon: int | None
    frame: int


@dataclass(frozen=True)
class PaintGrid:
    origin_xz: tuple[float, float]
    cell_size: float
    width: int
    height: int
    teams: tuple[int, ...]  # -1 unknown, -2 measured unpainted, >=0 team.
    sample_frame: int


@dataclass(frozen=True)
class PublicStatus:
    observer: str
    target: str
    alive: bool | None
    sample_frame: int


@dataclass(frozen=True)
class RefereeSnapshot:
    match_id: str
    frame: int
    players: tuple[PlayerTruth, ...]
    remaining_seconds: float | None = None
    paint: PaintGrid | None = None
    knockdowns: tuple[Knockdown, ...] | None = None
    public_status: tuple[PublicStatus, ...] = ()


@dataclass(frozen=True)
class VisibilityWitness:
    """Trusted visibility backend output, kept entirely in the referee.

    Uses the authorized geometric approximation: fixed eye heights, body
    heading, horizontal FOV, range and static collision segment tests.
    """
    match_id: str
    frame: int
    observer: str
    target: str
    target_sample_frame: int
    in_fov: bool | None
    line_clear: bool | None
