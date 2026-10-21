import copy,sys,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'tools/zipcaster_d3'),str(ROOT)]
from tools.zipcaster_d3r.motion_calibration import own_profile
class MotionTests(unittest.TestCase):
 def fixture(self):
  d=dict(trial=0,speed_frames=40,combo='full-light',events=[dict(event='before-R',infos=dict(player_0=dict(frame=0,hp=1))),dict(event='arrival',infos=dict(player_0=dict(frame=10,hp=1)))])
  rows=[dict(infos=dict(player_0=dict(frame=f,position=[0,max(0,2-(f-10)/30),1],hp=1,alive=True,referee_motion=dict(ground_contact=4))))for f in range(1,132)]
  return d,rows
 def test_enemy_and_outcome_are_not_fit_inputs(self):
  d,rows=self.fixture();a=own_profile(d,rows);self.assertIsNotNone(a);d['outcome']=dict(kill=True)
  for row in rows:row['infos']['player_1']=dict(hp=0,position=[999,999,999],alive=False)
  b=own_profile(d,rows);np.testing.assert_array_equal(a['post'],b['post'])
 def test_held_out_rejected(self):
  d,rows=self.fixture();d['trial']=2
  with self.assertRaises(ValueError):own_profile(d,rows)
 def test_impulse_or_unsettled_motion_cannot_fill_missing_tail(self):
  d,rows=self.fixture();rows[40]['infos']['player_0']['hp']=.48;self.assertIsNone(own_profile(d,rows))
  d,rows=self.fixture()
  for row in rows:row['infos']['player_0']['position'][1]=row['infos']['player_0']['frame']*.1
  self.assertIsNone(own_profile(d,rows))
if __name__=='__main__':unittest.main()
