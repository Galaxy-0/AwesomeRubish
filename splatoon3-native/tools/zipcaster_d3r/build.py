"""Build a fresh opt-in host; all protected binaries/modules remain identical."""
import argparse,json,sys,shutil,subprocess,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3.native import sha
from tools.build_a7_host import build_inputs
def main(a):
 out=a.out.resolve();parent=ROOT/'work/d2b/round2-world-build/dmhost-sensors';record=json.loads(parent.with_suffix('.build.json').read_text())
 if not out.is_relative_to(ROOT/'work')or out.exists():raise ValueError('fresh work directory required')
 assert sha(parent)==record['output_sha256']
 for p,h in record['source_sha256'].items():assert sha(ROOT/p)==h,p
 protected={p:sha(p)for p in [parent,ROOT/'upstream/dm/host/dmhost',ROOT/'work/a8/dmhost-arena-v15',ROOT/'work/a8/dmhost-arena-special-v15']};out.mkdir(parents=True)
 aim=out/'test_aim.h';shutil.copy2(Path(__file__).with_name('test_aim.h'),aim)
 bullet=out/'bullet_sensor.h';bullet.write_text((ROOT/'tools/zipcaster_d3/bullet_sensor.h').read_text().replace('frame<d3_last+4','frame<d3_last+1'))
 sensor=out/'sensor.h';shutil.copy2(parent.parent/'sensor.h',sensor)
 old=parent.parent/'hle_rl.c';text=old.read_text().replace(str(parent.parent/'sensor.h'),str(sensor));text=text.replace('static void own_player(const uint64_t *r) {',f'#include "{aim}"\n#include "{bullet}"\nstatic void own_player(const uint64_t *r) {{',1);text=text.replace('    if(first)LOG("RL_SELF_SLOT','    d3r_update(player,slot,health);\n    d3_bullets(player);\n    if(first)LOG("RL_SELF_SLOT',1);text=text.replace('    d2b_init();','    d3r_init();\n    gate_obs_set(48,d3r_velocity_get);gate_obs_set(49,d3r_velocity_set);gate_obs_set(50,d3r_camera_compute);\n    d3_init();\n    d2b_init();',1);rl=out/'hle_rl.c';rl.write_text(text)
 dispatch=out/'hle.c';dispatch.write_text((parent.parent/'hle.c').read_text().replace('#define OBS_MAX 48','#define OBS_MAX 52',1))
 cmd=list(record['command']);cmd.insert(1,'-DSPL3_D3R_TEST_AIM=1');cmd[cmd.index('-o')+1]=str(out/'dmhost-aim')
 for i,v in enumerate(cmd):
  if v==str(old):cmd[i]=str(rl)
  if v==str(parent.parent/'hle.c'):cmd[i]=str(dispatch)
 inputs=set(build_inputs(cmd))|{old,aim,bullet,sensor,Path(__file__).resolve(),Path(__file__).with_name('test_aim.h')};frozen={str(p.relative_to(ROOT)):sha(p)for p in sorted(inputs)}
 with (out/'build.log').open('w')as f:subprocess.run(cmd,cwd=ROOT/'upstream/dm/host',stdout=f,stderr=subprocess.STDOUT,check=True)
 host=out/'dmhost-aim';host.with_suffix('.build.json').write_text(json.dumps(record|dict(output=str(host.relative_to(ROOT)),output_sha256=sha(host),source_sha256=frozen,command=cmd,test_only=True,test_feature='direct_aim_upper_bound',diagnostic='D3R candidate camera fields, equivalence pending'),indent=2)+'\n')
 modules=out/'modules';shutil.copytree(parent.parent/'modules',modules)
 rewrite=out/'rewrite.py';base=(parent.parent/'rewrite.py').read_text();needle="'28c4287aee36f7499da60f3e68b54c70': [\n";assert base.count(needle)==1
 base=base.replace(needle,needle+"    (0x1a40710,48,'bd513000','D3R native projectile velocity getter; readonly'),\n    (0x1a40720,49,'f9400028','D3R native projectile velocity setter; readonly input'),\n    (0x28ed548,50,'d102c3ff','D3R opt-in canonical camera pre-compute'),\n",1);rewrite.write_text(base)
 env={k:v for k,v in os.environ.items()if not k.startswith('DM_')};env['DM_RULESET']='native'
 with (out/'rewrite.log').open('w')as f:subprocess.run([sys.executable,str(rewrite),str(ROOT/'work/data/v720896/ExeFS/main'),str(modules),'main'],env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
 manifest=json.loads(host.with_suffix('.build.json').read_text());manifest['private_module_sha256']={p.name:sha(p)for p in modules.iterdir()if p.is_file()};manifest['source_sha256'][str(rewrite.relative_to(ROOT))]=sha(rewrite);host.with_suffix('.build.json').write_text(json.dumps(manifest,indent=2)+'\n')
 for p,h in protected.items():assert sha(p)==h,p
 (out/'protected.json').write_text(json.dumps({str(p.relative_to(ROOT)):h for p,h in protected.items()},indent=2)+'\n');print(host)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args())
