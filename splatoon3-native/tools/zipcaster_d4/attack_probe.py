"""Bounded, predeclared native contact/elevation controls, never a win-rate run.

Uses accepted test-only ideal aim/infinite-special fixture. Native placement,
HP, projectile collision and damage are unmodified. One room per invocation.
Natural recovery is required between shots; a KO ends the probe, not a retry.
"""
import argparse,json,math,sys,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.control import new_lab,fixture,neutral,sha
from tools.zipcaster_d3r.setup_navigation import place
from tools.zipcaster_d3r.weapon_aim import blade_angles

def main(a):
 plan=json.loads(a.plan.read_text());point=next(p for p in plan['points']if p['id']==a.point)
 meta=json.loads((ROOT/point['graph']/'graph.json').read_text());lab=new_lab('d4-attack-'+a.name,meta['stage'],a.host);records=[]
 lab.result.update(schema='inklab.d4.attack.probe.v1',records=records,point=point,plan_sha256=sha(a.plan),probe_name=a.name,ideal_operation_fixture=True,special_fixture='infinite',calibration_eligible=False,full_d4_passed=False,predeclared_cases=[dict(style=k,pitch_delta=p)for k in a.styles for p in a.pitches],scope='Adaptive diagnosis only, not held-out ranking or finite-gauge evidence. Native HP/pose/collision remain authoritative.')
 for p in[Path(__file__),ROOT/'tools/zipcaster_d3r/weapon_aim.py']:(lab.out/('tested-'+p.name)).write_bytes(p.read_bytes())
 try:
  with fixture(lab,roles=(0,),meter='infinite')as aim:
   lab.start();place(lab,{0:point['source'],1:point['enemy']});aim.off();lab.step(lab.actions(),'attack-natural-settle',60)
   errors=[math.dist(lab.info(n)['position'],point['source']if n==0 else point['enemy'])for n in[0,1]];lab.result['setup_errors']=errors
   if max(errors)>1.5 or min(lab.info(n)['hp']for n in[0,1])<.999:raise AssertionError('ordinary placement/full-health precondition')
   act=neutral();act['buttons'][3]=1;lab.act(0,act,'attack-RS',6);lab.step(lab.actions(),'attack-activation',25)
   params=json.loads(a.parameters.read_text());lab.result['parameters_sha256']=sha(a.parameters)
   for index,c in enumerate(lab.result['predeclared_cases']):
    if lab.info(0)['remaining_time']<15:lab.result['bounded_stop']='less15s native match time';break
    if not all(lab.info(n)['alive']for n in[0,1]):lab.result['bounded_stop']='native KO; no HP/respawn repair';break
    aim.off();lab.paint_floor(1);lab.refill(1,300);lab.step(lab.actions(),'attack-natural-heal',40)
    if lab.info(1)['hp']<.999:lab.result['bounded_stop']='natural recovery not full';break
    yaw,pitch=blade_angles(lab.info(0)['position'],lab.info(1)['position'],params,style=c['style']);pitch=max(-.85,min(.85,pitch+c['pitch_delta']));aim.set_native(0,yaw,pitch);lab.step(lab.actions(),'attack-preaim',4)
    row=dict(index=index,**c,yaw=yaw,native_pitch=pitch,before=lab.env.process_infos,history=[]);records.append(row);lab.save()
    for phase,n,press in[('hold',21 if c['style']=='full'else 1,True),('release',65,False)]:
     for tick in range(n):
      act=neutral();act['buttons'][0]=int(press);lab.act(0,act,'attack-'+phase,1);row['history'].append(dict(phase=phase,tick=tick,infos=lab.env.process_infos))
      if not lab.info(1)['alive']:break
     if not lab.info(1)['alive']:break
    row['after']=lab.env.process_infos;aim.off();lab.save();print('D4_ATTACK_CASE '+json.dumps(dict(index=index,style=c['style'],pitch_delta=c['pitch_delta'],minimum_hp=min(h['infos']['player_1']['hp']for h in row['history']),actual_source=row['before']['player_0']['position'],actual_enemy=row['before']['player_1']['position'])),flush=True)
   lab.result.update(passed=True,driver_completed=True)
 except BaseException as e:lab.result.update(errors=lab.result['errors']+[repr(e)],traceback=traceback.format_exc())
 finally:lab.finish()
 print('D4_ATTACK_CLOSED '+str(lab.out),flush=True);return 0 if lab.result['passed']else 1
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--point',required=True);p.add_argument('--name',required=True);p.add_argument('--pitches',type=float,nargs='+',default=[0.,.12,-.12,.24]);p.add_argument('--styles',choices=['full','light'],nargs='+',default=['full','light']);p.add_argument('--parameters',type=Path,default=ROOT/'work/d3r/attack-parameters-v1.json');p.add_argument('--host',type=Path,default=ROOT/'work/d4/meter-v1/dmhost-aim');raise SystemExit(main(p.parse_args()))
