"""Alpha-only checks for A6 boundaries and failure cases seen in round 0."""
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
import time
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'arena/lib')]
spec = importlib.util.spec_from_file_location('alpha_candidate', HERE / 'policy.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


def observation(frame, *, enemy=True, hp=1., ink=1., alive=True, position=(0., 3., -5.)):
    own = dict(public=dict(player_id='player_0', team=0, weapon=8000, alive=alive),
               position=list(position), heading=0., hp=hp, ink=ink,
               sample_frame=frame, view_yaw=0., view_pitch=0., submerged=False,
               form_squid=False, special=None)
    e = dict(public=dict(player_id='player_1', team=1, weapon=8000, alive=True),
             visible=enemy, position=[0., 3., 5.] if enemy else None,
             heading=0. if enemy else None, sample_frame=frame if enemy else None,
             last_seen_position=None, last_seen_frame=None)
    return dict(schema='arena.policy.v1', match_id='alpha-check', stage_id=1,
                frame=frame, remaining_seconds=170., own=own, enemies=[e])


class CheckPolicy(unittest.TestCase):
    def test_full_charge_holds_24_and_releases_one_present(self):
        bot = policy.Alpha(observation(0))
        actions = [bot.act(observation(f)) for f in range(60)]
        start = next(f for f, a in enumerate(actions) if a['buttons'][0])
        self.assertEqual([a['buttons'][0] for a in actions[start:start + 25]], [1] * 24 + [0])
        self.assertEqual(bot.plan.cancelled if bot.plan else None, None)

    def test_brief_visibility_loss_clears_velocity_but_commits_slash(self):
        bot = policy.Alpha(observation(0))
        for f in range(25):
            bot.act(observation(f))
        self.assertIsNotNone(bot.plan)
        a = bot.act(observation(25, enemy=False))
        self.assertEqual(a['buttons'][0], 1)
        self.assertIsNone(bot.aim.previous)
        self.assertIsNotNone(bot.plan)
        for f in range(26, 72):
            bot.act(observation(f, enemy=False))
        self.assertIsNone(bot.plan)

    def test_hit_keeps_countercharge_and_adds_escape_movement(self):
        bot = policy.Alpha(observation(0))
        for f in range(25):
            bot.act(observation(f))
        a = bot.act(observation(25, hp=.3))
        self.assertIsNotNone(bot.plan)
        self.assertEqual(a['buttons'][0], 1)
        self.assertEqual(a['buttons'][1], 0)
        self.assertGreater(math.hypot(*a['sticks'][:2]), .5)
        self.assertGreater(bot.retreat_until, 25)
        self.assertIsNotNone(bot.retreat_goal)

    def test_retreat_keeps_camera_on_timed_memory(self):
        bot = policy.Alpha(observation(0, enemy=False))
        bot.threat_position = (0., 3., 5.)
        bot.threat_frame = 0
        for f in range(16):
            bot.aim.turner.aim(observation(f, enemy=False), (0., 4.1, 5.))
        a = bot.act(observation(16, enemy=False, hp=.3))
        self.assertAlmostEqual(a['sticks'][2], 0.)
        self.assertAlmostEqual(a['gyro'][2], 0.)
        self.assertLess(a['sticks'][1], 0.)
        self.assertIsNone(bot.aim.previous)

    def test_world_heading_survives_view_rotation_without_dead_zone(self):
        a = policy.neutral()
        a['sticks'][1] = .65
        b = policy.rebase_move(a, 0., math.pi/4)
        x, y = b['sticks'][:2]
        dx = -x*math.cos(math.pi/4)+y*math.sin(math.pi/4)
        dz = x*math.sin(math.pi/4)+y*math.cos(math.pi/4)
        self.assertAlmostEqual(dx, 0.)
        self.assertGreater(dz, 0.)
        self.assertGreaterEqual(max(abs(x),abs(y)), .59)
        self.assertLessEqual(math.hypot(x,y), .95)

    def test_home_anchors_return_and_only_down_enables_recovery_route(self):
        spawn = (23.9, 31., -104.7)
        bot = policy.Alpha(observation(0, enemy=False, position=spawn))
        bot.act(observation(0, enemy=False, position=spawn))
        self.assertGreater(len(bot.home_anchors), 0)
        for q in bot.home_anchors:
            self.assertTrue(bot.atlas.plan(q, bot.atlas.region('center')))
        self.assertFalse(bot.recovery_targets)
        bot.act(observation(100, enemy=False, hp=0., alive=False))
        bot.act(observation(600, enemy=False, position=spawn))
        self.assertTrue(bot.recovery_targets)

    def test_spawn_launcher_preserves_home_targets_until_near_walkable_layer(self):
        spawn = (23.9, 31., -104.7)
        bot = policy.Alpha(observation(0, enemy=False, position=spawn))
        bot.act(observation(0, enemy=False, position=spawn))
        bot.act(observation(100, enemy=False, hp=0., alive=False))
        for f in range(600, 692):
            self.assertEqual(bot.act(observation(f, enemy=False, position=spawn)), policy.neutral())
            self.assertEqual(len(bot.recovery_targets), 2)
        # Own foot position measured at round-1 selftest respawn f5284.
        landed = (23.6296749, 10.8022318, -72.4763947)
        bot.act(observation(692, enemy=False, position=landed))
        self.assertIsNone(bot.recovery_launch)
        self.assertEqual(len(bot.recovery_targets), 2)
        self.assertTrue(bot.nav.path)

    def test_visible_threat_outside_charge_range_is_watched_without_firing(self):
        o = observation(0)
        o['enemies'][0]['position'] = [0., 3., 10.5]  # 15.5 units, beyond charge initiation
        o['own']['view_yaw'] = math.pi/2
        bot = policy.Alpha(o)
        motion = policy.neutral()
        motion['sticks'][1] = .65
        motion['buttons'][0] = 1
        bot.paint = lambda obs: policy.clone(motion)
        a = bot.act(o)
        self.assertIsNone(bot.plan)
        self.assertIsNotNone(bot.aim.previous)
        self.assertEqual(a['buttons'][0], 0)
        self.assertEqual(a['sticks'][:2], motion['sticks'][:2])

    def test_refill_hysteresis(self):
        bot = policy.Alpha(observation(0, enemy=False))
        for f, ink in [(0, .1), (1, .5)]:
            self.assertEqual(bot.act(observation(f, enemy=False, ink=ink))['buttons'][1], 1)
        self.assertEqual(bot.act(observation(2, enemy=False, ink=.9))['buttons'][1], 0)

    def test_recovered_spawn_pulse_needs_fresh_full_own_state(self):
        spawn = (23.9, 31., -104.7)
        bot = policy.Alpha(observation(0, enemy=False, position=spawn))
        bot.act(observation(0, enemy=False, position=spawn))
        self.assertEqual(bot.act(observation(100, enemy=False, hp=0., alive=False, position=spawn))['buttons'][0], 0)
        self.assertEqual(bot.act(observation(300, enemy=False, alive=False, position=spawn))['buttons'][0], 1)
        stale = observation(330, enemy=False, alive=False, position=spawn)
        stale['own']['sample_frame'] = 300
        self.assertEqual(bot.act(stale), policy.neutral())
        unknown = observation(360, enemy=False, alive=None, position=spawn)
        self.assertEqual(bot.act(unknown), policy.neutral())

    def test_missing_camera_is_neutral(self):
        o = observation(0)
        bot = policy.Alpha(o)
        o['own']['view_yaw'] = None
        self.assertEqual(bot.act(o), policy.neutral())

    def test_recorded_round1_streams_validate_without_hidden_velocity(self):
        from arena.process import validate_action
        root = ROOT / 'work/arena/t1/round-001'
        if not root.is_dir():
            self.skipTest('local round-1 records are not available')
        calls, maximum = 0, 0.
        for game in range(3):
            path = root / f'game-{game}-attempt-000/policy-1.jsonl'
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            bot = policy.Alpha(rows[0]['observation'])
            for row in rows:
                obs = row['observation']
                before = time.perf_counter()
                validate_action(bot.act(obs))
                maximum = max(maximum, time.perf_counter()-before)
                if not any(e['visible'] for e in obs['enemies']):
                    self.assertIsNone(bot.aim.previous)
                calls += 1
        print(json.dumps(dict(recorded_observation_calls=calls, max_seconds=maximum,
                              scope='action validity, not counterfactual match outcome')))

    def test_actual_sandbox_cold_start_and_per_present_actions(self):
        from arena.control_process import ControlProcess
        from arena.policy import PolicyObservation, OwnState, PublicPlayer, EnemyView
        from arena.process import validate_action
        from arena.config import PolicySpec
        manifest = PolicySpec.load(HERE)
        latencies = []
        with tempfile.TemporaryDirectory(dir=HERE, prefix='.component-') as tmp:
            with ControlProcess(HERE, Path(tmp) / 'stderr.log', manifest.step_timeout) as child:
                for frame in range(65):
                    own = OwnState(PublicPlayer('player_0', 0, 8000, True), (0., 3., -5.), 0.,
                                   .3 if frame>=40 else 1., 1., frame, False, False, 0., 0.)
                    enemy = EnemyView(PublicPlayer('player_1', 1, 8000, True), True,
                                      (0., 3., 5.), 0., frame)
                    obs = PolicyObservation('sandbox-check', frame, own, (enemy,), 170., 1)
                    before = time.perf_counter()
                    validate_action(child.act(obs))
                    latencies.append(time.perf_counter() - before)
            self.assertEqual((Path(tmp) / 'stderr.log').read_text(), '')
        print(json.dumps(dict(sandbox_calls=len(latencies), max_seconds=max(latencies),
                              timeout_seconds=manifest.step_timeout)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
