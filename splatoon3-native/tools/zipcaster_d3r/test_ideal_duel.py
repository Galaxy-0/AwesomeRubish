import sys,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/zipcaster_d3'))
from tools.zipcaster_d3r.ideal_duel import Config,duel_batch
class DuelTests(unittest.TestCase):
 def trial(self,style,blocked=False):
  path=np.zeros((160,3));enemy=np.array([[0.,0.,8.]]);clear=np.zeros((160,1),bool)
  return duel_batch(path,0,enemy,np.array([0.]),np.array([False]),clear,cfg=Config(style=style),samples=2,blade_clear=lambda x,y,f:np.full(len(x),not blocked,bool))
 def test_full_light_and_three_lights_require_real_damage(self):
  for style in['full-light','light3']:
   r=self.trial(style);self.assertTrue(r['kills'].all());self.assertTrue(r['hit35'].all())
   if style=='full-light':self.assertTrue(r['hit70'].all())
   else:self.assertFalse(r['hit70'].any());self.assertGreaterEqual(r['def_ko'].min(),92)
 def test_field_blocker_does_not_change_visibility_or_deal_damage(self):
  r=self.trial('full-light',True);self.assertFalse(r['kills'].any());self.assertFalse(r['hit70'].any());self.assertFalse(r['hit35'].any());self.assertTrue((r['first_seen']==-1).all())
if __name__=='__main__':unittest.main()
