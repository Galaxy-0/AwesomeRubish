"""Trusted local measurement fixture. Never extends arena.policy.v1 actions."""
import json,math,re,struct,sys
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'tools/zipcaster_d3'),str(ROOT)]
from native import DuelLab,NativeSession,owned_options,neutral,sha

class Aim:
 def __init__(self,lab):
  self.lab=lab;self.sequence=[0,0];self.paths=[lab.out/f'direct-aim-{n}.txt'for n in (0,1)]
  for n in (0,1):self.set_native(n,0,0,False)
 def set_native(self,player,yaw,pitch,enabled=True):
  if player not in (0,1)or not math.isfinite(yaw)or not math.isfinite(pitch)or abs(pitch)>.9:raise ValueError('finite native camera angles only; pitch <=.9')
  yaw=math.atan2(math.sin(yaw),math.cos(yaw));self.sequence[player]+=1;p=self.paths[player];tmp=p.with_suffix('.tmp');tmp.write_text(f'D3Rv1 {self.sequence[player]} {int(enabled)} {yaw:.9g} {pitch:.9g}\n');tmp.replace(p)
  return dict(player=player,sequence=self.sequence[player],yaw=yaw,native_pitch=pitch,enabled=bool(enabled))
 def off(self):
  for n in (0,1):self.set_native(n,0,0,False)

@contextmanager
def fixture(lab,roles=(0,),meter='infinite'):
 host=getattr(lab,'_d3r_host',None)
 if host is None:raise ValueError('use new_lab with an explicit measurement host')
 record=json.loads(host.with_suffix('.build.json').read_text())
 if not record.get('test_only')or record.get('test_feature')!='direct_aim_upper_bound':raise ValueError('wrong fixture runtime')
 aim=Aim(lab)
 with owned_options(special=True,sensors=True,meter=meter):
  original=NativeSession.host_options
  def options(self,n):return original(self,n)|({'DM_TEST_AIM':'1','DM_TEST_AIM_FILE':str(aim.paths[n])}if n in roles else{})
  with patch.object(NativeSession,'host_options',options):
   try:yield aim
   finally:aim.off()

class Sensors:
 def __init__(self,lab):self.path=Path(lab.result['session'])/'player-0/host.log';self.cursor=0;self.phase=None;self.frame=-1;self.remaining=None
 def poll(self):
  with self.path.open(errors='replace')as f:f.seek(self.cursor);text=f.read();self.cursor=f.tell()
  states=[]
  for m in re.finditer(r'D2B_SNAPSHOT frame=(\d+) kind=superhook [^\n]*data=([0-9a-f]+)',text):
   self.frame=int(m[1]);self.phase=struct.unpack_from('<i',bytes.fromhex(m[2]),0x40)[0];states.append((self.frame,self.phase))
  for m in re.finditer(r'D2B_CANONICAL frame=\d+ slot=\d+ key=\d+ remaining=(-?\d+)',text):self.remaining=int(m[1])
  return states

def new_lab(name,stage,host):
 host=Path(host).resolve();record=json.loads(host.with_suffix('.build.json').read_text())
 if not record.get('test_only')or record.get('test_feature')!='direct_aim_upper_bound':raise ValueError('explicit direct-aim measurement host required')
 lab=DuelLab('r-'+name,stage,host=host,modules=host.parent/'modules');lab._d3r_host=host;lab.result['d3r_host']=str(host);return lab
