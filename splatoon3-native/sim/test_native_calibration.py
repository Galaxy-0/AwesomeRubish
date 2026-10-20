"""Offline regressions for the native window; no host processes launched."""
import io
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import numpy as np

from .identify import response
from .motion import MotionModel
from .test_motion import model_fixture
from .calibration.paint import collect


class NativeCalibrationTests(unittest.TestCase):
    def test_radial_quartic_matches_independent_cardinal_and_mixed_axes(self):
        np.testing.assert_allclose(response(np.array([0.,.5]),0.,4.,'radial'),[0.,.0625])
        np.testing.assert_allclose(response(np.array([1.,.25]),0.,4.,'radial')*.096,[.09313368,.02328342],atol=1e-8)
        # Radial response preserves direction at a diagonal, instead of
        # raising each component separately and rotating a1:.25 input.
        v=response(np.array([.85,.4]),0.,4.,'radial')
        self.assertAlmostEqual(v[0]/v[1],.85/.4)

    def test_new_radial_scalar_and_batch_motion_agree(self):
        m=model_fixture();m.data['modes']['human'].update(response_space='radial',exponent=4.,speed=.096)
        sticks=np.array([[.6,.6],[1.,.25],[0.,.5]])
        velocity=np.zeros((3,2));yaws=np.array([0.,1.,2.])
        out,target=m.batch_advance(velocity,sticks,yaws,np.zeros(3,int))
        for i in range(3):
            actual,desired=m.advance(np.zeros(3),sticks[i],yaws[i],'human')
            np.testing.assert_allclose(actual,out[i]);np.testing.assert_allclose(desired,target[i])

    def test_paint_completion_does_not_project_judge_or_send_to_terminated_agent(self):
        class Env:
            agents=['player_0','player_1'];calls=0;process_infos={}
            def step(self,actions):
                self.asserted=set(actions)==set(self.agents)
                if not self.asserted:raise AssertionError('wrong active agents')
                self.calls+=1
                self.agents=['player_0'] if self.calls==1 else []
                infos={f'player_{i}':dict(phase=1 if i==0 and self.calls==1 else 2,score_valid=0) for i in (0,1)}
                self.process_infos=infos
                return {},{}, {},dict.fromkeys(actions,False),infos
            def advance_settlement(self):
                self.process_infos={f'player_{i}':dict(phase=3,score_valid=1,score=[.1,.1]) for i in (0,1)}
                return {},self.process_infos
        env=Env();lab=SimpleNamespace(env=env,budget=0,count=0,stream=io.StringIO(),result={},
             api=SimpleNamespace(update=Mock(side_effect=AssertionError('Judge must not enter InGame projector'))),
             info=lambda i:dict(own_view=dict(pitch=-.28)),save=lambda:None)
        with patch('sim.calibration.paint.sequence'):
            collect(lab,dict(settings=dict(hold=12,strokes=1),frame_budget=13000))
        self.assertEqual(env.calls,2);self.assertIn('native_winners',lab.result)
        lab.api.update.assert_not_called()

    def test_stop_file_prevents_queued_room_admission(self):
        from .calibration.p0 import run_case
        with tempfile.TemporaryDirectory() as directory:
            Path(directory,'STOP').touch()
            with patch('sim.calibration.p0.make_lab',side_effect=AssertionError('must not start room')):
                status=run_case((dict(id='cancelled',kind='p0_opening',stage=1),directory,1e20))
        self.assertEqual(status['status'],'failed')
        self.assertIn('cancellation',status['errors'][0])

    def test_launch_hands_off_and_foot_paint_waits_until_due_in_scalar_and_batch(self):
        from .engine import BatchSimulator,neutral
        from .batch import VectorBatchSimulator
        from .opening import OpeningModel
        from .paint_model import PaintModel
        from .parameters import Parameters
        from .test_core import fixture
        opening=OpeningModel(dict(schema='sim.opening.v1',steer_start=0,steer_speed=.02,
            stages={'1':dict(end_frame=4,ground_frame=4,knots=[[0,1,1,1],[4,1,0,1]],squid_start=1,squid_end=3)}))
        paint=PaintModel(dict(schema='sim.paint.v1',weak_radius=1.,full_radius=1.5,weak_delay=3,full_delay=2))
        motion=model_fixture();motion.data['run_speed_up_curve']=[[0,1],[19,1.26],[57,1.5]]
        kwargs=dict(parameters=Parameters.local(),terrain=fixture(),duration_frames=30,motion_model=motion,opening_model=opening,paint_model=paint)
        scalar=BatchSimulator(2,**kwargs);batch=VectorBatchSimulator(2,**kwargs)
        actions=[{f'player_{r}':neutral() for r in (0,1)} for _ in range(2)]
        for frame in range(1,11):
            for pair in actions:
                pair['player_0']['sticks'][:2]=[.6,.6]
                pair['player_0']['buttons'][0]=int(frame==5)
            for e,a in zip(scalar.envs,actions):e.step(a,observe=False)
            batch.step(actions,observe=False)
            for a,b in zip(scalar.envs,batch.envs):
                np.testing.assert_allclose(a.players[0].position,b.players[0].position,atol=1e-10)
                self.assertEqual(a.events,b.events)
            foot=[e for e in scalar.envs[0].events if e['kind']=='foot_paint']
            self.assertEqual(bool(foot),frame>=9)
        self.assertEqual(foot[0]['frame'],9)
        self.assertAlmostEqual(motion.gear_multiplier('human',{'run_speed_up':19}),1.26)
        self.assertEqual(motion.gear_multiplier('charge',{'run_speed_up':57}),1.)

    def test_noncore_field_sphere_cannot_reappear_behind_low_wall(self):
        from .engine import Simulator
        from .paint_model import PaintModel
        from .terrain import Mesh,Terrain
        from .test_core import fixture
        base=fixture()
        wall=[[[0,0,3],[0,1.2,3],[10,1.2,3]],[[0,0,3],[10,1.2,3],[10,0,3]]]
        mesh=Mesh(np.concatenate((base.human.triangles,np.asarray(wall))))
        terrain=Terrain(base.atlas,mesh,mesh)
        model=PaintModel(dict(schema='sim.paint.v1',weak_radius=0.,full_radius=0.,weak_delay=14,full_delay=11,field_collision_core_only=True))
        e=Simulator(1,terrain=terrain,paint_model=model)
        e.players[0].yaw=0.;e.players[1].squid=True
        e._spawn(0,True,'projectile')
        blocked=False;passed=False
        for _ in range(16):
            e.frame+=1;e._weapons()
            if e.projectiles:
                blocked|=bool(e.projectiles[0].field_blocked)
                passed|=e.projectiles[0].position[2]>4.
        self.assertTrue(blocked);self.assertTrue(passed)
        self.assertEqual(e.players[1].hp,1.)

    def test_respawn_waits_on_launcher_and_requires_new_unlocked_ZR_edge(self):
        from .engine import Simulator,neutral
        from .opening import OpeningModel
        from .test_core import fixture
        m=OpeningModel(dict(schema='sim.opening.v1',steer_start=0,steer_speed=0.,
            stages={'1':dict(end_frame=4,ground_frame=4,knots=[[0,1,1,1],[4,1,0,1]],squid_start=1,squid_end=3)},
            respawn=dict(ready_delay=3,unlock_delay=6)))
        e=Simulator(1,terrain=fixture(),motion_model=model_fixture(),opening_model=m,duration_frames=40)
        e.frame=10;e._kill(0,1,'test')
        def step(zr):
            a={f'player_{i}':neutral() for i in (0,1)};a['player_0']['buttons'][0]=zr;e.step(a,observe=False)
        for _ in range(3):step(0)
        self.assertFalse(e.players[0].alive);self.assertEqual(e.players[0].hp,1.)
        np.testing.assert_allclose(e.players[0].position,[1,1,1])
        for _ in range(5):step(1)  # press before unlock; holding cannot create another edge
        self.assertFalse(e.players[0].alive)
        step(0);step(1)
        self.assertTrue(e.players[0].alive);self.assertEqual(e.players[0].launch_at,20)
        step(0);self.assertFalse(e.players[0].grounded)
        self.assertGreater(e.players[0].position[1],0.)

    def test_launch_sensitivity_preserves_height_and_offset_after_first_frame(self):
        from .engine import Simulator,neutral
        from .opening import OpeningModel
        from .ranking import perturb
        from .test_core import fixture
        m=OpeningModel(dict(schema='sim.opening.v1',steer_start=0,steer_speed=0.,
            stages={'1':dict(end_frame=4,ground_frame=4,knots=[[0,1,10,1],[4,1,9,1]],squid_start=1,squid_end=3)}))
        e=Simulator(1,terrain=fixture(),motion_model=model_fixture(),opening_model=m)
        perturb(e,3);delta=e.players[0].opening_delta.copy()
        self.assertEqual(e.players[0].position[1],10.)
        e.step({f'player_{i}':neutral() for i in (0,1)},observe=False)
        np.testing.assert_allclose(e.players[0].position[[0,2]],np.array([1,1])+delta)


if __name__=='__main__':unittest.main()
