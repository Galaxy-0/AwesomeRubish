"""Freeze scoped direct-aim direction evidence; no grid/resource export."""
import json,math,sys,subprocess,datetime,re
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.analyze_direction import angle,sha
from rl.session import SAVE_HASH
def main():
 files={name:ROOT/f'work/d3r/{name}.json'for name in ['gun-r2-direction','sword-v1-retry-direction','hook-v1-direction']};gun,sword,hook=[json.loads(files[k].read_text())for k in files]
 for d in [gun,sword,hook]:assert d['driver_completed']and not d['errors'];assert sha(d['source'])==d['source_sha256']
 assert all(c['n']==[3,3]and c['mean_angle_degrees']<.001 for c in sword['comparisons'])
 assert hook['mean_angle_degrees']<.1
 g=gun['comparisons'][0];assert g['n']==[6,6]and g['mean_angle_degrees']<max(g['controller_internal_max_degrees'],g['direct_internal_max_degrees'])
 changed={s:angle(sword['groups']['direct-same-'+s]['mean_direction'],sword['groups']['direct-changed-'+s]['mean_direction'])for s in ['light','full']};assert all(v>40 for v in changed.values())
 off=ROOT/'work/a6/d3-r-direct-gun-v1-20261021-230154-544698/result.json';d=json.loads(off.read_text());assert d['passed']and not d['ideal_operation_fixture'];views={e['event']:e['infos']['player_1']['own_view']for e in d['events']if 'infos'in e};drift=views['direct-changed-before']['yaw']-views['controller-before']['yaw'];assert abs(drift)<.001
 for n in [0,1]:
  text=(Path(d['session'])/f'player-{n}/host.log').read_text();assert'D3R_APPLY'not in text and'D3R_TEST_AIM'not in text
 host=ROOT/'work/d3r/aim-v1/dmhost-aim';record=json.loads(host.with_suffix('.build.json').read_text());assert sha(host)==record['output_sha256']
 for p,h in record['source_sha256'].items():assert sha(ROOT/p)==h,p
 for p,h in json.loads((host.parent/'protected.json').read_text()).items():assert sha(ROOT/p)==h,p
 for p,h in json.loads((ROOT/'work/d2b/round2-world-build/provenance.json').read_text())['original_module_sha256'].items():assert sha(ROOT/p)==h,p
 assert b'D3R_TEST_AIM'not in(ROOT/'upstream/dm/host/dmhost').read_bytes()
 for p in [ROOT/'work/save_ref/save.dat',ROOT.parent/'splatoon-rl-lab/saves/bis/user/save/0000000000000001/0/save.dat']:assert sha(p)==SAVE_HASH,p
 paths=list((ROOT/'work/a6').glob('d3-r-direct-*/result.json'));times=[];owned=[];runs=[]
 for p in paths:
  r=json.loads(p.read_text());assert'freeze_after'in r and r['freeze_before']==r['freeze_after'];owned+=r['owned_pids']
  for src,h in r['raw_sha256'].items():assert sha(src)==h
  start=datetime.datetime.strptime(re.search(r'(\d{8}-\d{6}-\d{6})$',p.parent.name)[1],'%Y%m%d-%H%M%S-%f').timestamp();times.extend([(start,1),(p.stat().st_mtime,-1)]);runs.append(dict(artifact=str(p.relative_to(ROOT)),sha256=sha(p),passed=r['passed'],errors=r['errors'],owned_pids=r['owned_pids']))
 active=peak=0
 for _,delta in sorted(times):active+=delta;peak=max(peak,active)
 assert active==0 and peak<=3
 live=subprocess.check_output(['ps','-axo','pid=,comm='],text=True);commands={int(v.split(None,1)[0]):v.split(None,1)[1]for v in live.splitlines()if v.strip()};assert all('dmhost'not in commands.get(pid,'')for pid in owned)
 anchors=[hook['groups'][g]['binds'][0]['anchor']for g in ['controller','direct-same']]
 out=dict(schema='inklab.d3r.step1.v1',date='2026-10-21',step1_scoped_passed=True,direct_aim_fixture_ready_for_mapping=True,full_d3r_passed=False,runtime=dict(host=str(host.relative_to(ROOT)),sha256=sha(host),test_only=True,test_switch='DM_TEST_AIM=1 plus DM_TEST_AIM_FILE absolute path',default_off=True,protected_hosts_modules_unchanged=True),canonical_state=dict(type='PlayerCamera',vtable='main+5d31468',owner='object+19c0',yaw_horizontal_vector='object+18c',native_pitch_scalar='object+16c',apply_context='native camera compute entry main+28ed548; original instruction replayed',physical_sensor='native velocity getter/setter main+1a40710/1a40720, vector+1130; readonly'),comparisons=dict(gun=gun['comparisons'],sword=sword['comparisons'],hook=dict(casts_per_mode=1,mean_angle_degrees=hook['mean_angle_degrees'],anchor_distance=float(np.linalg.norm(np.asarray(anchors[0])-anchors[1]))),sword_changed_direction_degrees=changed),default_off_control=dict(artifact=str(off.relative_to(ROOT)),sha256=sha(off),requested_yaw_change=1.,observed_yaw_drift=drift,no_activation_or_write_logs=True),formal_entry_guards=['arena.runner.run_match','arena.runner.tournament','arena.t1.run_round','tests.proficiency.run','rl.native_start.validate_runtime'],component_log=dict(path='work/d3r/guard-components-v1.log',sha256=sha(ROOT/'work/d3r/guard-components-v1.log'),cases=11),evidence={name:dict(path=str(p.relative_to(ROOT)),sha256=sha(p))for name,p in files.items()},native_runs=runs,resource=dict(rooms=len(runs),owned_hosts=len(set(owned)),peak_rooms=peak,all_owned_hosts_exited=True),limits=['Scoped fixed-pose diagonal direction A/B, not all directions/forms/gyro states or complete game-state equivalence.','52 mean difference is compatible with observed stochastic spread; no bitwise RNG-stream equivalence claim.','Hook first-difference direction uses two 4f tip samples per cast; no sub-frame precision claim.','Native pitch scalar is not identical to emitted world elevation; measure/invert per weapon/context before aiming at world targets.','R1 hook stalled during ordinary navigation before any enabled aim/hook. V1 sword refill omitted disable;600f expiry protected host, corrected retry completed. Originals retained.','No body/position/HP/armor/weapon-damage or projectile writes; no policy interface extension. Stage2–6 pending.'],source_sha256={str(Path(__file__).relative_to(ROOT)):sha(__file__)})
 dest=ROOT/'notes/d3r-step1-20261021.json';dest.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(dict(comparisons=out['comparisons'],resource=out['resource']),indent=2))
if __name__=='__main__':main()
