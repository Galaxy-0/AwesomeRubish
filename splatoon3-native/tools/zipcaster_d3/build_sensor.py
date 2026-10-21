"""Build fresh isolated derivative; original host/modules always hash checked."""
import argparse,json,subprocess,sys,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from native import ROOT,sha
from tools.build_a7_host import build_inputs
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();out=a.out.resolve()
if ROOT/'work'not in out.parents or out.exists():raise ValueError('fresh work/ directory required')
parent=ROOT/'work/a8/dmhost-arena-special-v15';record=json.loads(parent.with_suffix('.build.json').read_text())
assert sha(parent)==record['output_sha256']
for name,digest in record['source_sha256'].items():assert sha(ROOT/name)==digest,name
protected={p:sha(p)for p in [parent,ROOT/'upstream/dm/host/dmhost',ROOT/'work/a8/dmhost-arena-v15']}
out.mkdir(parents=True);observer=out/'bullet_sensor.h';shutil.copyfile(Path(__file__).with_name('bullet_sensor.h'),observer)
rl=out/'hle_rl.c';original=ROOT/'upstream/dm/host/hle_rl.c';text=original.read_text();needle='static void own_player(const uint64_t *r) {';assert text.count(needle)==1
text=text.replace(needle,f'#include "{observer}"\n'+needle).replace('    if(first)LOG("RL_SELF_SLOT','    d3_bullets(player);\n    if(first)LOG("RL_SELF_SLOT',1).replace('    gate_obs_set(OBS_SPL3_OWN_PLAYER,own_player);','    d3_init();\n    gate_obs_set(OBS_SPL3_OWN_PLAYER,own_player);',1);rl.write_text(text)
command=list(record['command']);command[command.index('-o')+1]=str(out/'dmhost-bullets');command[command.index('hle_rl.c')]=str(rl);command.insert(1,'-I'+str(original.parent))
inputs=set(build_inputs(command))|{original,observer,Path(__file__).resolve()};frozen={str(p.relative_to(ROOT)):sha(p)for p in sorted(inputs)}
with (out/'build.log').open('w')as f:subprocess.run(command,cwd=original.parent,stdout=f,stderr=subprocess.STDOUT,check=True)
host=out/'dmhost-bullets';host.with_suffix('.build.json').write_text(json.dumps(record|dict(output=str(host.relative_to(ROOT)),output_sha256=sha(host),source_sha256=frozen,command=command,diagnostic='d3_readonly_bullet'),indent=2)+'\n')
for p,h in protected.items():assert sha(p)==h,p
(out/'protected.json').write_text(json.dumps({str(p.relative_to(ROOT)):h for p,h in protected.items()},indent=2)+'\n');print(host)
