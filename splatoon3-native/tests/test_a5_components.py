#!/usr/bin/env python3
"""Tournament statistics and policy manifest invariants; no native match claim."""
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'arena/lib'))
from atlas import MapAtlas
from arena.config import PolicySpec
from arena.statistics import exact_interval,summarize
from arena.hud_events import HudEvents


class TournamentComponents(unittest.TestCase):
    def test_winning_seat_is_not_winning_policy_after_spawn_swap(self):
        from arena.a5_audit import winners_from_local_scores
        from arena.scoring import compare_scores
        # The same player_1 victory belongs to different policies when roles swap.
        for roles,expected in [([0,1],'b'),([1,0],'a')]:
            seats,outcome=winners_from_local_scores([1,2],[2,1],roles)
            self.assertEqual(seats,[1,1]);self.assertEqual(outcome,expected)
            self.assertEqual(compare_scores([1,2],[2,1],roles)['outcome'],expected)
        # Opposite seat victories can belong to the same policy.
        self.assertEqual(winners_from_local_scores([2,1],[1,2],[1,0]),([0,0],'b'))

    def test_revised_70_game_void_gate_boundaries(self):
        from arena.statistics import meets_a5_threshold
        self.assertFalse(meets_a5_threshold(69,0,4))
        self.assertTrue(meets_a5_threshold(70,7,4))
        self.assertFalse(meets_a5_threshold(70,8,4))
        self.assertFalse(meets_a5_threshold(70,0,2))

    def test_winner_agreement_averages_and_preserves_both_raw_scores(self):
        from arena.scoring import compare_scores
        small=compare_scores([.7,1.3],[1.4,.7],[0,1])
        self.assertFalse(small['void']);self.assertFalse(small['suspect']);self.assertEqual(small['outcome'],'b')
        self.assertEqual(small['score_peers_native_order'],[[.7,1.3],[1.4,.7]])
        self.assertAlmostEqual(small['score_by_role'][1],1.35)
        self.assertAlmostEqual(small['score_difference_by_role'][1],-.1)
        self.assertEqual(compare_scores([1,4],[8,1],[1,0])['outcome'],'a')
        self.assertTrue(compare_scores([1,4],[8,1],[0,1])['suspect'])
        self.assertFalse(compare_scores([1,4],[6,1],[0,1])['suspect'])

    def test_winner_disagreement_including_tie_is_void_not_average_winner(self):
        from arena.scoring import compare_scores
        for a,b in [([3,2],[3,2]),([2,2],[2,1])]:
            result=compare_scores(a,b,[0,1]);self.assertTrue(result['void'])
            self.assertIsNone(result['outcome']);self.assertEqual(result['void_reason'],'peer_winner_disagreement')
        self.assertEqual(compare_scores([2,2],[2,2],[0,1])['outcome'],'draw')
        with self.assertRaises(ValueError):compare_scores([float('nan'),2],[2,1],[0,1])

    def test_resume_never_submits_completed_33_and_retains_cancelled_attempt_number(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        from arena.schedule import schedule
        initial=[dict(round=n,attempt=0,passed=True,void=False) for n in range(33)]
        submitted=[];stop=threading.Event()
        def play(t):submitted.append(t);return dict(t,passed=True,void=False)
        with ThreadPoolExecutor(max_workers=4) as pool:
            matches,reason=schedule([dict(round=n,attempt=1 if n<36 else 0) for n in range(100)],
                lambda t:pool.submit(play,t),stop,lambda *x:None,4,11,initial_matches=initial)
        self.assertIsNone(reason);self.assertEqual(len(matches),100)
        self.assertEqual({t['round'] for t in submitted},set(range(33,100)))
        self.assertTrue(all(t['attempt']==1 for t in submitted if t['round']<36))

    def test_resume_rejects_duplicate_verdict_tampering_and_evidence_change(self):
        import tempfile,copy
        from arena.checkpoint import load_resume,sha256
        from arena.scoring import compare_scores,SCORING_RULE
        specs=[PolicySpec.load(ROOT/'arena/policies'/name) for name in ('rush','high-ground')]
        m=dict(round=0,stage=1,role_to_policy=[0,1],passed=True,native_winners=True,**compare_scores([1,2],[2,1],[0,1]))
        d=dict(scoring_rule=SCORING_RULE,games_requested=100,source_hashes=[s.source_sha256 for s in specs],policies=[s.name for s in specs],matches=[m])
        with tempfile.TemporaryDirectory(dir=ROOT/'work/tests') as directory:
            p=Path(directory)/'checkpoint.json'
            p.write_text(json.dumps(d));self.assertEqual(len(load_resume(p,specs,100)['matches']),1)
            for changed in [dict(d,matches=[m,m]),dict(d,source_hashes=['changed','changed'])]:
                p.write_text(json.dumps(changed))
                with self.assertRaises(ValueError):load_resume(p,specs,100)
            changed=copy.deepcopy(d);changed['matches'][0]['score_by_role']=[10,20];p.write_text(json.dumps(changed))
            with self.assertRaises(ValueError):load_resume(p,specs,100)
            evidence=Path(directory)/'evidence';evidence.write_text('old')
            changed=dict(d,evidence_sha256={str(evidence):sha256(evidence)});evidence.write_text('new');p.write_text(json.dumps(changed))
            with self.assertRaises(ValueError):load_resume(p,specs,100)

    def test_real_match_error_path_only_watchdog_is_void_and_preserves_cleanup_error(self):
        import tempfile,threading
        from unittest.mock import patch
        from arena.runner import run_match
        with tempfile.TemporaryDirectory(dir=ROOT/'work/tests') as directory:
            base=Path(directory);session=base/'session';(session/'player-1').mkdir(parents=True)
            log=session/'player-1/host.log'
            class FailedEnv:
                session=None
                def __init__(self,**kw):self.artifacts=[session]
                def reset(self,**kw):raise RuntimeError('connection closed')
                def close(self):raise RuntimeError('unclean exit -6')
            stop=threading.Event()
            task=dict(round=2,attempt=1,stage=2,roles=[0,1],timeout=10,
                      policy_paths=[ROOT/'arena/policies/rush',ROOT/'arena/policies/high-ground'])
            with patch('arena.runner.NativeParallelEnv',FailedEnv),patch('arena.runner._STOP',stop):
                log.write_text('[dm] FATAL RL_STALL no present progress frame=300 remaining=12\n')
                void=run_match(dict(task,out=str(base/'void')))
                self.assertTrue(void['void']);self.assertFalse(void['passed']);self.assertFalse(stop.is_set())
                self.assertIn('unclean exit',void['errors'][-1]);self.assertEqual(len(void['watchdog_evidence']),1)
                log.write_text('[dm] FATAL other integrity failure\n')
                fatal=run_match(dict(task,out=str(base/'fatal')))
                self.assertFalse(fatal['void']);self.assertFalse(stop.is_set())

    def test_void_retries_fixture_without_cancelling_other_room(self):
        import threading,time
        from concurrent.futures import ThreadPoolExecutor
        from arena.schedule import schedule
        stop=threading.Event();other_finished=threading.Event();seen=[];reports=[]
        tasks=[dict(round=n,stage=2,roles=[n%2,1-n%2]) for n in range(4)]
        def play(task):
            seen.append(dict(task))
            if task['round']==0 and task['attempt']==0:
                return dict(**task,passed=False,void=True,cancelled=False)
            if task['round']==1:
                time.sleep(.08);self.assertFalse(stop.is_set());other_finished.set()
            return dict(**task,passed=True,void=False)
        with ThreadPoolExecutor(max_workers=2) as pool:
            matches,reason=schedule(tasks,lambda t:pool.submit(play,t),stop,
                lambda ms,r:reports.append((len(ms),r)),2,3)
        self.assertIsNone(reason);self.assertTrue(other_finished.is_set());self.assertFalse(stop.is_set())
        self.assertEqual(sum(m['passed'] for m in matches),4);self.assertEqual(sum(m['void'] for m in matches),1)
        self.assertEqual([t for t in seen if t['round']==0],
            [dict(tasks[0],attempt=0),dict(tasks[0],attempt=1)])

    def test_excess_voids_drain_other_rooms_and_do_not_count_wins(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        from arena.schedule import schedule
        stop=threading.Event()
        def play(t):return dict(**t,passed=t['round']!=0,void=t['round']==0,cancelled=False)
        with ThreadPoolExecutor(max_workers=2) as pool:
            matches,reason=schedule([dict(round=i) for i in range(4)],lambda t:pool.submit(play,t),stop,lambda *x:None,2,1)
        self.assertEqual(reason,'void_budget_exceeded');self.assertFalse(stop.is_set())
        self.assertEqual(sum(m['void'] for m in matches),2)
        self.assertTrue(any(m['passed'] for m in matches))

    def test_aggregate_void_denominator_swapped_hud_scores_and_times(self):
        from arena.statistics import tournament_statistics
        hud=dict(enemy_hud_downs=3,own_hud_downs=2,enemy_environmental_downs=1,own_environmental_downs=0)
        matches=[dict(passed=True,void=False,outcome='b',role_to_policy=[1,0],
                      hud_by_role={'player_0':hud,'player_1':hud},score_by_role=[5.,2.],wall_seconds=30,controlled_seconds=20),
                 dict(passed=False,void=True)]
        s=tournament_statistics(matches)
        self.assertEqual(s['games'],1);self.assertEqual(s['losses'],1);self.assertEqual(s['void_rate'],.5)
        self.assertEqual(s['by_policy'][0]['score_percentage_points']['mean'],2.)
        self.assertEqual(s['by_policy'][1]['wins'],1)
        self.assertEqual(s['by_policy'][0]['enemy_environmental_downs'],1)
        self.assertEqual(s['wall_seconds']['sum'],30)

    def test_three_room_overlap_excludes_stalled_interval(self):
        from arena.schedule import overlap_windows
        matches=[dict(round=n,attempt=0,controlled_start_wall=10+n,last_progress_wall=30+n,
                      host_pids=[100+2*n,101+2*n]) for n in range(3)]
        windows=overlap_windows(matches,3)
        self.assertEqual(windows[0]['hosts'],6);self.assertEqual(windows[0]['overlap_seconds'],18)
        matches[0]['last_progress_wall']=11
        self.assertEqual(overlap_windows(matches,3),[])

    def test_exact_interval_and_no_false_superiority(self):
        self.assertEqual(exact_interval(0,0),(0.,1.))
        self.assertAlmostEqual(exact_interval(0,10)[1],1-.025**.1,places=10)
        self.assertAlmostEqual(exact_interval(10,10)[0],.025**.1,places=10)
        self.assertFalse(summarize(['a']*60+['b']*40)['stronger'])
        self.assertTrue(summarize(['a']*61+['b']*39)['stronger'])
        self.assertEqual(summarize(['draw']*3)['decided_exact_95_interval'],[0.,1.])

    def test_four_rooms_must_actually_overlap_with_eight_distinct_hosts(self):
        from arena.runner import concurrency_window
        matches=[dict(round=n,controlled_start_wall=10+n,controlled_end_wall=30+n,host_pids=[100+n*2,101+n*2]) for n in range(4)]
        window=concurrency_window(matches)
        self.assertEqual(window['hosts'],8);self.assertEqual(window['rooms'],4)
        self.assertEqual(window['overlap_seconds'],17)
        matches[-1]['controlled_start_wall']=40
        with self.assertRaises(AssertionError):concurrency_window(matches)
        matches[-1]['controlled_start_wall']=13;matches[-1]['host_pids']=[100,101]
        with self.assertRaises(AssertionError):concurrency_window(matches)

    def test_cancel_before_session_exists_terminates_only_owned_startup_process(self):
        import subprocess,threading,time
        from types import SimpleNamespace
        from arena.runner import abort_on_cancel
        stop=threading.Event();finished=threading.Event();env=SimpleNamespace(session=None)
        thread=threading.Thread(target=abort_on_cancel,args=(env,stop,finished));thread.start();stop.set()
        owned=subprocess.Popen([sys.executable,'-c','import time;time.sleep(10)'])
        unrelated=subprocess.Popen([sys.executable,'-c','import time;time.sleep(10)'])
        try:
            time.sleep(.1);env.session=SimpleNamespace(hosts=[(0,owned,None)],air=None)
            self.assertNotEqual(owned.wait(2),0)
            self.assertIsNone(unrelated.poll())
        finally:
            finished.set();thread.join(1)
            for process in (owned,unrelated):
                if process.poll() is None:process.terminate()
                process.wait(2)

    def test_room_activation_is_separate_but_two_slot_locks_are_shared(self):
        import tempfile,fcntl
        from types import SimpleNamespace
        from arena.runner import link_load_slots
        with tempfile.TemporaryDirectory(dir=ROOT/'work/tests') as directory:
            root=Path(directory);shared=root/'shared';shared.mkdir()
            for n in range(2):(shared/f'slot-{n}').touch()
            rooms=[]
            for name in ('a','b'):
                p=root/name;p.mkdir();(p/'load-slots').mkdir();rooms.append(p)
                link_load_slots(SimpleNamespace(out=p),shared)
            a,b=rooms
            (a/'load-slots/active').touch()
            self.assertFalse((b/'load-slots/active').exists());self.assertFalse((shared/'active').exists())
            self.assertEqual((a/'load-slots/slot-0').stat().st_ino,(b/'load-slots/slot-0').stat().st_ino)
            with (a/'load-slots/slot-0').open('r+') as first,(b/'load-slots/slot-0').open('r+') as second:
                fcntl.flock(first,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with self.assertRaises(BlockingIOError):fcntl.flock(second,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(RuntimeError):link_load_slots(SimpleNamespace(out=a),shared)

    def test_only_two_simple_baseline_manifests_and_legal_loadouts(self):
        policies=[ROOT/'arena/policies'/name for name in ('high-ground','rush')]
        for path in policies:
            spec=PolicySpec.load(path)
            self.assertEqual(spec.step_frames,12)
            self.assertEqual(len(spec.source_sha256),64)

    def test_observer_counter_is_not_private_alive_or_hp_and_fall_is_separate(self):
        atlas=MapAtlas(dict(schema='arena.map.v1',nodes=[[0,0,0,1],[10,0,10,1]],edges=[[],[]],regions={},spawns={},resolution=1,scope={'min_y':0}))
        initial=dict(a={'frame':100},b={'frame':200});events=HudEvents(initial,atlas)
        def info(base,downs,position,alive):
            return dict(frame=base+10,position_sample_frame=base+10,position_valid=1,position=position,
                        alive=alive,hp=1.,hud_slot_agents={'0':'a','4':'b'},hud_downs=[0,0,0,0,downs,0,0,0],
                        hud_counter_valid=[1,0,0,0,1,0,0,0],hud_sample_frame=[base+10]*8)
        events.update(dict(a=info(100,0,[0,0,0],1),b=info(200,0,[10,-5,10],0)),10)
        self.assertEqual(events.summary('a','b')['enemy_hud_downs'],0)
        events.update(dict(a=info(100,1,[0,0,0],1),b=info(200,0,[10,-5,10],0)),11)
        stats=events.summary('a','b');self.assertEqual(stats['enemy_hud_downs'],1);self.assertEqual(stats['enemy_environmental_downs'],1)
        self.assertIsNone(events.events[0]['attacker']);self.assertIsNone(events.events[0]['weapon'])
        events.update(dict(a=info(100,1,[0,0,0],1),b=info(200,0,[10,0,10],1)),12)
        self.assertEqual(events.summary('a','b')['enemy_hud_downs'],1)


if __name__=='__main__':unittest.main()
