#!/usr/bin/env python3
"""A3 interface-only regression. These fixtures do not accept native visibility."""
from dataclasses import replace
import json
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from arena.policy import encode_policy
from arena.referee import Knockdown, PaintGrid, PlayerTruth, PublicStatus, RefereeSnapshot, VisibilityWitness
from arena.visibility import PolicyProjector
from arena.native_referee import NativeRefereeAdapter


def snapshot(frame=10):
    own = PlayerTruth('a', 0, 8000, True, (1., 2., 3.), .1, 1., 1., False, frame)
    enemy = PlayerTruth('b', 1, 8000, True, (23., 2., 31.), 1.2, .73, .42, False, frame)
    return RefereeSnapshot('match', frame, (own, enemy), 120.,
                           public_status=(PublicStatus('a', 'b', True, frame),))


def witness(s, **changes):
    w = VisibilityWitness(s.match_id, s.frame, 'a', 'b', s.players[1].sample_frame, True, True)
    return replace(w, **changes)


class PolicyBoundary(unittest.TestCase):
    def test_hidden_state_noninterference(self):
        """Hidden movement, damage, paint and attribution must not change wire data."""
        s = snapshot()
        expected = encode_policy(PolicyProjector('match').observe(s, 'a'))
        rng = random.Random(324)
        for i in range(100):
            p = replace(s.players[1], position=tuple(rng.uniform(-100, 100) for _ in range(3)),
                        heading=rng.uniform(-3.14, 3.14), hp=rng.random(), ink=rng.random(),
                        alive=rng.choice([True, False, None]),
                        submerged=rng.choice([True, False, None]), sample_frame=rng.randrange(11))
            changed = replace(s, players=(s.players[0], p),
                              paint=PaintGrid((0., 0.), 1., 1, 1, (i % 2,), 10),
                              knockdowns=(Knockdown('secret-victim', 'secret-attacker', 9999, 8),))
            self.assertEqual(expected, encode_policy(PolicyProjector('match').observe(changed, 'a')))
        data = json.loads(expected)
        self.assertIsNone(data['enemies'][0]['position'])
        self.assertIsNone(data['enemies'][0]['sample_frame'])
        self.assertNotIn('hp', data['enemies'][0])
        self.assertNotIn('paint', data)
        self.assertNotIn('knockdowns', data)

    def test_missing_or_mismatched_witness_hides(self):
        s = snapshot()
        for changes in [dict(in_fov=False), dict(in_fov=None), dict(line_clear=False),
                        dict(line_clear=None), dict(observer='b'), dict(target='a'),
                        dict(match_id='other'), dict(frame=9), dict(target_sample_frame=9)]:
            obs = PolicyProjector('match').observe(s, 'a', (witness(s, **changes),))
            self.assertFalse(obs.enemies[0].visible, changes)
            self.assertIsNone(obs.enemies[0].position)

    def test_submerged_unknown_dead_and_stale_hide(self):
        s = snapshot()
        for changes in [dict(submerged=True), dict(submerged=None), dict(alive=False),
                        dict(alive=None), dict(sample_frame=1), dict(sample_frame=11),
                        dict(position=None), dict(position=(float('nan'), 0., 0.))]:
            changed = replace(s, players=(s.players[0], replace(s.players[1], **changes)))
            obs = PolicyProjector('match').observe(changed, 'a', (witness(changed),))
            self.assertFalse(obs.enemies[0].visible, changes)

    def test_last_seen_updates_only_when_observed(self):
        s = snapshot()
        projector = PolicyProjector('match')
        seen = projector.observe(s, 'a', (witness(s),))
        self.assertTrue(seen.enemies[0].visible)
        self.assertEqual(seen.enemies[0].last_seen_frame, 10)
        hidden = replace(s, frame=11, players=(s.players[0], replace(s.players[1],
                          position=(101., 102., 103.), sample_frame=11, submerged=True)))
        obs = projector.observe(hidden, 'a', (witness(hidden),))
        self.assertIsNone(obs.enemies[0].position)
        self.assertIsNone(obs.enemies[0].heading)
        self.assertIsNone(obs.enemies[0].sample_frame)
        self.assertEqual(obs.enemies[0].last_seen_position, s.players[1].position)
        self.assertEqual(obs.enemies[0].last_seen_frame, 10)
        back = replace(hidden, frame=12, players=(s.players[0], replace(hidden.players[1],
                       sample_frame=12, submerged=False)))
        found = projector.observe(back, 'a', (witness(back),))
        self.assertEqual(found.enemies[0].last_seen_position, (101., 102., 103.))
        # Another observer and another match do not inherit this memory.
        self.assertIsNone(projector.observe(back, 'b').enemies[0].last_seen_position)
        self.assertIsNone(PolicyProjector('new').observe(replace(back, match_id='new'), 'a').enemies[0].last_seen_position)

    def test_encoder_rejects_referee_or_hidden_current_state(self):
        s = snapshot()
        with self.assertRaises(TypeError):
            encode_policy(s)
        with self.assertRaises(TypeError):
            encode_policy({'truth': s})
        obs = PolicyProjector('match').observe(s, 'a')
        bad_enemy = replace(obs.enemies[0], position=s.players[1].position)
        with self.assertRaises(ValueError):
            encode_policy(replace(obs, enemies=(bad_enemy,)))

    def test_referee_keeps_private_data_and_explicit_unavailability(self):
        s = snapshot()
        self.assertEqual(s.players[1].hp, .73)
        self.assertIsNone(s.paint)
        self.assertIsNone(s.knockdowns)
        projector = PolicyProjector('match')
        projector.observe(s, 'a')
        with self.assertRaises(ValueError):
            projector.observe(s, 'a')
        with self.assertRaises(ValueError):
            PolicyProjector('different').observe(s, 'a')
        with self.assertRaises(ValueError):
            PolicyProjector('match').observe(s, 'a', (witness(s), witness(s)))

    def test_host_frame_origins_and_missing_native_signals(self):
        initial = {'a': dict(frame=15000), 'b': dict(frame=10000)}
        adapter = NativeRefereeAdapter('match', initial, {'a': 8000, 'b': 8000}, {'a': 0, 'b': 1})
        def info(frame):
            return dict(frame=frame, phase=1, position_sample_frame=frame-4,
                        position=[1., 2., 3.], position_valid=1, hp=.5, hp_valid=1,
                        heading=.1, heading_valid=1, ink=.7, ink_valid=1,
                        alive=1, alive_valid=1, remaining_time=177., time_valid=1,
                        hud_downs=[0, 1])
        infos = {'a': info(15015), 'b': info(10015)}
        truth = adapter.snapshot(infos)
        self.assertEqual(truth.frame, 15)
        self.assertEqual([p.sample_frame for p in truth.players], [11, 11])
        self.assertEqual([p.hp for p in truth.players], [.5, .5])
        self.assertTrue(all(p.submerged is None for p in truth.players))
        self.assertIsNone(truth.paint)
        self.assertIsNone(truth.knockdowns)
        # Even a geometric witness cannot override unknown native submergence.
        self.assertFalse(PolicyProjector('match').observe(truth, 'a', (witness(truth),)).enemies[0].visible)
        with self.assertRaises(ValueError):
            adapter.snapshot(infos | {'b': info(10016)})

    def test_deferred_a3b_never_fabricates_paint_or_attribution(self):
        initial = {'a': {'frame': 0}, 'b': {'frame': 10}}
        adapter = NativeRefereeAdapter('m', initial, dict(a=8000, b=8000), dict(a=0, b=1))
        for frame in (1, 7, 50):
            infos = {p: dict(frame=origin['frame'] + frame, phase=1,
                            paint=[[0, 1]], paint_points=900, kills=12,
                            knockdowns=[{'victim': 'b', 'attacker': 'a', 'weapon': 8000}],
                            hud_downs=[0, frame], score=[99, 1], score_valid=1)
                     for p, origin in initial.items()}
            truth = adapter.snapshot(infos)
            self.assertIsNone(truth.paint)
            self.assertIsNone(truth.knockdowns)
            wire = json.loads(encode_policy(PolicyProjector('m').observe(truth, 'a')))
            self.assertNotIn('paint', wire)
            self.assertNotIn('knockdowns', wire)

    def test_enemy_public_status_uses_observers_hud(self):
        s = snapshot()
        # Remote truth Down has not yet reached observer a's public HUD.
        s = replace(s, players=(s.players[0], replace(s.players[1], alive=False)))
        obs = PolicyProjector('match').observe(s, 'a')
        self.assertTrue(obs.enemies[0].public.alive)
        # Without local HUD evidence, do not substitute private remote state.
        unknown = PolicyProjector('match').observe(replace(s, public_status=()), 'a')
        self.assertIsNone(unknown.enemies[0].public.alive)

    def test_native_form_contact_motion_and_ninja_exception(self):
        def info(frame,x,form,contact):
            return dict(frame=frame,phase=1,position_sample_frame=frame,position=[x,0.,0.],position_valid=1,
                        referee_motion=dict(form_squid=form,ground_contact=contact))
        for ninja in [(),('b',)]:
            adapter=NativeRefereeAdapter('m',{'a':{'frame':0},'b':{'frame':0}},dict(a=8000,b=8000),dict(a=0,b=1),ninja)
            def state(f,x,form,contact):return adapter.snapshot(dict(a=info(f,0.,0,4),b=info(f,x,form,contact))).players[1]
            self.assertFalse(state(1,0.,0,0).submerged)  # Human standing in ink.
            self.assertFalse(state(2,0.,1,4).submerged)  # Squid outside ink.
            self.assertTrue(state(3,0.,1,0).submerged)
            self.assertFalse(state(4,0.,1,0).motion_visible)
            self.assertEqual(state(8,1.,1,0).motion_visible,not ninja)
            repeated=info(9,1.,1,0);repeated['position_sample_frame']=8
            own=info(9,0.,0,4)
            self.assertEqual(adapter.snapshot(dict(a=own,b=repeated)).players[1].motion_visible,not ninja)
            self.assertFalse(state(12,1.,1,5).submerged)  # Airborne exception.
            self.assertIsNone(state(16,1.,1,2).submerged)  # Unmapped contact stays unknown.


if __name__ == '__main__':
    unittest.main()
