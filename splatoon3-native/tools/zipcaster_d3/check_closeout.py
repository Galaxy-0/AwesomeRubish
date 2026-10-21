"""Audit stopped D3 evidence, intervals, ownership, protected inputs and scope."""
import datetime,hashlib,json,math,re,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from native import ROOT,sha
from rl.session import SAVE_HASH
checks=0

def check(v):
 global checks
 assert v;checks+=1
model=json.loads((ROOT/'notes/d3-model-20261021.json').read_text());block=json.loads((ROOT/'notes/d3-blocker-20261021.json').read_text());phase=json.loads((ROOT/'notes/d3-52-20261021.json').read_text())
for r in [model,block]:check(not r['full_d3_passed'])
check(not model['calibrated']);check(model['not_for_player_recommendation']);check(block['spearman']is None and block['kendall_tau_b']is None and block['calibration_error']is None)
for source,digest in model['provenance']['source_sha256'].items():check(sha(ROOT/source)==digest)
for source,digest in model['provenance']['inputs'].items():check(sha(ROOT/source)==digest)
count=episodes=0
for m in model['maps']:
 check(m['evaluated_tactics']==9)
 for p in m['points']:
  count+=1;episodes+=p['mc_episodes'];check(0<=p['statewise_worst_kill_probability']<=p['worst_behavior_kill_probability']+1e-12);check(p['worst_behavior_kill_probability']<=p['expected_kill_probability']+1e-12);check(p['expected_kill_probability']<=1);check(p['enemy_nodes_all_within30']);check(1<=len(p['sequence'])<=3)
  check(abs(sum(b['p_local']for b in p['behavior_results'])/3*p['near_prior_mass']-p['expected_kill_probability'])<1e-10)
check(count==27);check(episodes==model['scale']['fine_mc_episodes'])
paths=[ROOT/r['path']for r in phase['records']['rooms']]+[ROOT/r['artifact']for r in block['prototypes']]
paths += [next((ROOT/'work/a6').glob('d3-'+name+'-[0-9]*/result.json'))for name in ['bullet-r1','bullet-r2']]
intervals=[];owned=[]
for p in paths:
 d=json.loads(p.read_text());check('freeze_after'in d);owned.extend(d['owned_pids'])
 for source,digest in d['raw_sha256'].items():check(sha(source)==digest)
 begin=datetime.datetime.strptime(re.search(r'(\d{8}-\d{6}-\d{6})$',p.parent.name)[1],'%Y%m%d-%H%M%S-%f').timestamp();intervals.extend([(begin,1),(p.stat().st_mtime,-1)])
active=peak=0
for _,delta in sorted(intervals):active+=delta;peak=max(peak,active)
check(len(paths)==19 and len(set(owned))==38);check(active==0 and peak<=3)
for pid in owned:
 cmd=subprocess.run(['ps','-p',str(pid),'-o','comm='],text=True,capture_output=True).stdout;check('dmhost'not in cmd)
for build in ['bullet-build-r1','bullet-build-r2']:
 for p,digest in json.loads((ROOT/f'work/d3/{build}/protected.json').read_text()).items():check(sha(ROOT/p)==digest)
provenance=json.loads((ROOT/'work/d2b/round2-world-build/provenance.json').read_text())
for p,digest in provenance['original_module_sha256'].items():check(sha(ROOT/p)==digest)
for p in [ROOT/'work/save_ref/save.dat',ROOT.parent/'splatoon-rl-lab/saves/bis/user/save/0000000000000001/0/save.dat']:check(sha(p)==SAVE_HASH)
check(sha(ROOT/'showcase/index.html')=='69828a44619426503166e1ea191e4f03b63d9fe1f0d4cd83c3a52089febf8978')
for p in block['prototypes']:
 check(not p['calibration_eligible']);check(p['visibility_gate_audited']);check(sha(ROOT/p['artifact'])==p['sha256'])
result=dict(passed=True,checks=checks,meaning='Evidence/scope audit only; D3 native calibration failed, not a milestone pass.',native_rooms=19,owned_hosts=38,all_owned_hosts_exited=True,conservative_peak_rooms=peak,fine_tactics=27,full_d3_passed=False)
(ROOT/'work/d3/closeout-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
