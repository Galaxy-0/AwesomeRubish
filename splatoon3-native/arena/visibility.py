"""Referee-side projection. Missing native visibility evidence always hides.

This is the information boundary, not a native FOV/occlusion implementation.
The latter must supply synchronized, validated VisibilityWitness records.
"""
import math

from .policy import EnemyView, OwnState, PolicyObservation, PublicPlayer
from .referee import RefereeSnapshot, VisibilityWitness


def _public(p, alive):
    return PublicPlayer(p.player_id, p.team, p.weapon, alive)


def _valid_position(p):
    return p is not None and len(p) == 3 and all(math.isfinite(v) for v in p)


class PolicyProjector:
    """One instance per match; last-seen memory is independent for each observer."""

    def __init__(self, match_id: str, max_sample_age: int = 8):
        if max_sample_age < 0:
            raise ValueError('negative sample age')
        self.match_id = match_id
        self.max_sample_age = max_sample_age
        self._last_seen = {}
        self._last_frame = {}

    def observe(self, truth: RefereeSnapshot, observer: str,
                witnesses: tuple[VisibilityWitness, ...] = ()) -> PolicyObservation:
        if type(truth) is not RefereeSnapshot or truth.match_id != self.match_id:
            raise ValueError('wrong referee snapshot/match')
        if truth.frame <= self._last_frame.get(observer, -1):
            raise ValueError('policy frames must increase for each observer')
        players = {p.player_id: p for p in truth.players}
        if len(players) != len(truth.players) or observer not in players:
            raise ValueError('duplicate/missing referee identity')
        own = players[observer]
        public_alive = {}
        for status in truth.public_status:
            if status.observer != observer:
                continue
            if status.target in public_alive:
                raise ValueError('ambiguous observer public HUD status')
            public_alive[status.target] = (status.alive if
                0 <= truth.frame-status.sample_frame <= 120 else None)
        by_target = {}
        for w in witnesses:
            if type(w) is not VisibilityWitness:
                raise TypeError('referee visibility witness required')
            if w.observer != observer:
                continue
            if w.target in by_target:
                raise ValueError('ambiguous visibility witness')
            by_target[w.target] = w
        enemies = []
        own_fresh = own.sample_frame is not None and 0 <= truth.frame-own.sample_frame <= self.max_sample_age
        for target in truth.players:
            if target.team == own.team:
                continue
            w = by_target.get(target.player_id)
            fresh = (target.sample_frame is not None and
                     0 <= truth.frame-target.sample_frame <= self.max_sample_age)
            visible = bool(own_fresh and own.alive is True and target.alive is True and
                           (target.submerged is False or
                            (target.submerged is True and target.motion_visible is True)) and fresh and
                           _valid_position(target.position) and w is not None and
                           w.match_id == truth.match_id and w.frame == truth.frame and
                           w.target_sample_frame == target.sample_frame and
                           w.in_fov is True and w.line_clear is True)
            key = (observer, target.player_id)
            if visible:
                self._last_seen[key] = (target.position, truth.frame)
            last_position, last_frame = self._last_seen.get(key, (None, None))
            # Public HUD must come from this observer, not the remote host's
            # own alive flag (which can precede the local public HUD update).
            enemies.append(EnemyView(_public(target, public_alive.get(target.player_id)), visible,
                                     target.position if visible else None,
                                     target.heading if visible else None,
                                     target.sample_frame if visible else None,
                                     last_position, last_frame))
        self._last_frame[observer] = truth.frame
        return PolicyObservation(truth.match_id, truth.frame,
                                 OwnState(_public(own, own.alive), own.position, own.heading,
                                          own.hp, own.ink, own.sample_frame,own.form_squid,own.submerged),
                                 tuple(enemies), truth.remaining_seconds)
