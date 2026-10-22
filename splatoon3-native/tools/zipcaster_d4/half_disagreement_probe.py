"""Last supplemental slash: core blocked, upper balls geometrically clear.

Fixed predeclared pitch.30; ideal yaw tracks actual static target bearing.
Uses existing isolated aim/read-only host. No pose/HP/game-parameter writes.
"""
import argparse,math
from pathlib import Path
from unittest.mock import patch
from tools.zipcaster_d4 import half_probe
from tools.zipcaster_d4 import duel_v6 as duel


def main(a):
 original=duel.World
 def world(*args,**kwargs):
  w=original(*args,**kwargs);original_evaluate=w.shots.evaluate
  def aim(source,target,style,step=.01):
   if style!='full':raise ValueError('single full-only disagreement probe')
   yaw=math.atan2(target[0]-source[0],target[2]-source[2])
   result=original_evaluate(source,target,style,yaw,.30)
   result.update(native_pitch=.30,yaw=yaw,contact=False)
   return result
  w.shots.best=aim
  w.shots.best_contact=lambda source,target,style,step=.01:aim(source,target,style,step)|dict(hit=False,contact=True,damage=0,diagnostic_contact_excluded=True)
  return w
 with patch.object(duel,'World',world):return half_probe.main(a)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--point',required=True);p.add_argument('--host',type=Path,required=True);p.add_argument('--passive',action='store_true');p.add_argument('--repeat',type=int,default=0);p.add_argument('--hold-r',type=int,default=1)
 p.add_argument('--parameters',type=Path,default=duel.ROOT/'work/d3r/attack-parameters-v1.json');p.add_argument('--ray',type=Path,default=duel.ROOT/'work/d3r/ray-v2-frozen.json');raise SystemExit(main(p.parse_args()))
