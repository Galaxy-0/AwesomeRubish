"""Independent numeric/source/ownership audit for the frozen stage1 cohort."""
import json,sys,re,datetime,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from native import ROOT,sha
r=json.loads((ROOT/'notes/d3-52-20261021.json').read_text());checks=0;intervals=[];owned=[]
def check(ok):
 global checks
 assert ok;checks+=1
for room in r['records']['rooms']:
 p=ROOT/room['path'];check(sha(p)==room['sha256']);d=json.loads(p.read_text());check(d['weapons']==[8000,50]);check([k['main']for k in room['native_kits']]==[8000,50]);check(bool(room['loadouts']))
 for source,digest in d['raw_sha256'].items():check(sha(source)==digest)
 owned.extend(d['owned_pids']);start=datetime.datetime.strptime(re.search(r'(\d{8}-\d{6}-\d{6})$',p.parent.name)[1],'%Y%m%d-%H%M%S-%f').timestamp();intervals.extend([(start,1),(p.stat().st_mtime,-1)])
for name in ['bullet-r1','bullet-r2']:
 paths=list((ROOT/'work/a6').glob('d3-'+name+'-[0-9]*/result.json'));check(len(paths)==1);p=paths[0];d=json.loads(p.read_text());check(d['passed']);owned.extend(d['owned_pids'])
 for source,digest in d['raw_sha256'].items():check(sha(source)==digest)
 start=datetime.datetime.strptime(re.search(r'(\d{8}-\d{6}-\d{6})$',p.parent.name)[1],'%Y%m%d-%H%M%S-%f').timestamp();intervals.extend([(start,1),(p.stat().st_mtime,-1)])
active=peak=0
for t,change in sorted(intervals):active+=change;peak=max(peak,active)
check(peak<=3);check(active==0)
for pid in owned:
 cmd=subprocess.run(['ps','-p',str(pid),'-o','comm='],text=True,capture_output=True).stdout
 check('dmhost'not in cmd)
for build in ['bullet-build-r1','bullet-build-r2']:
 for name,digest in json.loads((ROOT/f'work/d3/{build}/protected.json').read_text()).items():check(sha(ROOT/name)==digest)
check(len(r['records']['shots'])==59);check(len(r['records']['turn'])==2);check(abs(r['measurements']['damage_min_observed_hp']-49.2)<.001)
for shot in r['records']['shots']:
 for event in shot['damage_events']:check(abs(event['hp_before']-event['hp_after']-event['delta_hp'])<1e-6)
check(r['status']=='measurement_checkpoint_with_explicit_limits')
output=dict(passed=True,checks=checks,measurement_rooms=12,conservative_peak_rooms=peak,owned_hosts=len(owned),all_measurement_hosts_exited=True,limits='D3 active duel prototype is outside this closed measurement cohort; no model/native ranking acceptance.')
(ROOT/'work/d3/stage1-audit.json').write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(output,indent=2))
