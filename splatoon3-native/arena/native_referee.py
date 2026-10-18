"""Private coordinator adapter for M6's currently verified own-state packets.

No policy should import or receive this adapter. It deliberately leaves the
unmapped A3 signals unavailable. Submergence combines verified native form and
contact codes, never the ZL input or form alone. Public HUD Down events do not
provide attacker attribution.
"""
from collections.abc import Mapping
import math

from .referee import PlayerTruth, PublicStatus, RefereeSnapshot


class NativeRefereeAdapter:
    def __init__(self, match_id: str, initial_infos: Mapping, weapons: Mapping,
                 teams: Mapping, splash_suppressed=()):
        if not match_id or not initial_infos or set(initial_infos) != set(weapons) or set(initial_infos) != set(teams):
            raise ValueError('match identity and per-player metadata required')
        self.match_id = match_id
        self.origins = {p: int(i['frame']) for p, i in initial_infos.items()}
        self.weapons, self.teams = dict(weapons), dict(teams)
        self.last_frame = -1
        self._previous = {}
        self.splash_suppressed = frozenset(splash_suppressed)

    def snapshot(self, infos: Mapping) -> RefereeSnapshot:
        if set(infos) != set(self.origins):
            raise ValueError('referee requires every host at the barrier')
        frames = {int(i['frame'])-self.origins[p] for p, i in infos.items()}
        if len(frames) != 1 or min(frames) <= self.last_frame:
            raise ValueError('hosts are not at the same increasing match frame')
        frame = next(iter(frames))
        players, timers, public_status = [], [], []
        for player_id, i in infos.items():
            if i.get('phase') != 1:
                raise ValueError('native referee snapshot requires InGame')
            sample = int(i.get('position_sample_frame', -1))-self.origins[player_id]
            sampled = 0 <= sample <= frame
            def scalar(key):
                value = i.get(key)
                return float(value) if (sampled and i.get(key+'_valid') and
                       isinstance(value, (int, float)) and math.isfinite(value)) else None
            raw_position = i.get('position')
            position = tuple(float(v) for v in raw_position) if (sampled and i.get('position_valid') and
                       raw_position is not None and len(raw_position) == 3 and
                       all(math.isfinite(v) for v in raw_position)) else None
            alive = bool(i['alive']) if i.get('alive_valid') else None
            motion = i.get('referee_motion', {})
            form = motion.get('form_squid', -1)
            squid = bool(form) if form in (0, 1) and sampled else None
            contact = motion.get('ground_contact', -1)
            submerged = (False if squid is False else
                         (contact == 0 if squid is True and contact in (0, 4, 5) else None))
            previous = self._previous.get(player_id)
            splash = previous[2] if previous is not None and sample == previous[0] else False
            if position is not None and sample >= 0:
                if previous is not None and sample > previous[0]:
                    speed = math.hypot(position[0]-previous[1][0], position[2]-previous[1][2])/(sample-previous[0])
                    splash = (submerged is True and speed >= .045 and player_id not in self.splash_suppressed)
                if previous is None or sample > previous[0]:self._previous[player_id] = (sample, position, splash)
            players.append(PlayerTruth(player_id, self.teams[player_id], self.weapons[player_id],
                                       alive, position, scalar('heading'), scalar('hp'), scalar('ink'),
                                       submerged, sample if sampled else None, squid, splash))
            if i.get('time_valid') and math.isfinite(i.get('remaining_time', float('nan'))):
                timers.append(float(i['remaining_time']))
            slots = i.get('hud_slot_agents', {})
            for slot_text, target in slots.items():
                slot = int(slot_text)
                valid = i.get('hud_valid', [0]*8)
                states = i.get('hud_status', [2]*8)
                samples = i.get('hud_sample_frame', [0]*8)
                if target not in self.origins or not 0 <= slot < 8:
                    raise ValueError('invalid public native slot mapping')
                hud_frame = int(samples[slot])-self.origins[player_id]
                if valid[slot] and states[slot] in (0, 1) and 0 <= hud_frame <= frame:
                    public_status.append(PublicStatus(player_id, target, states[slot] == 0, hud_frame))
        # Do not substitute one peer's timer for a missing or divergent peer.
        remaining = min(timers) if len(timers) == len(players) and max(timers)-min(timers) <= .25 else None
        self.last_frame = frame
        return RefereeSnapshot(self.match_id, frame, tuple(players), remaining,
                               paint=None, knockdowns=None, public_status=tuple(public_status))
