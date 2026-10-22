"""Fresh derivative of the accepted private aim host, read-only stride1 only.

Never rebuild/overwrite the protected upstream or accepted private host. Module
bytes and aim logic are copied unchanged; no new game writes or policy API.
"""
import argparse,json,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.analyze_direction import sha
from tools.build_a7_host import build_inputs

def main(a):
 parent=ROOT/'work/d3r/aim-v1';record=json.loads((parent/'dmhost-aim.build.json').read_text());out=a.out.resolve()
 if not out.is_relative_to(ROOT/'work')or out.exists():raise ValueError('fresh work path required')
 assert sha(parent/'dmhost-aim')==record['output_sha256']
 for p,h in record['source_sha256'].items():assert sha(ROOT/p)==h,p
 protected={p:sha(ROOT/p)for p in json.loads((parent/'protected.json').read_text())};protected[str((parent/'dmhost-aim').relative_to(ROOT))]=sha(parent/'dmhost-aim');out.mkdir(parents=True)
 for name in ['hle.c','hle_rl.c','test_aim.h','bullet_sensor.h']:(out/name).write_text((parent/name).read_text().replace(str(parent),str(out)))
 s=(parent/'sensor.h').read_text();assert s.count('+4')>=3;s=s.replace('+4','+1').replace('sample_stride=4','sample_stride=1');(out/'sensor.h').write_text(s)
 cmd=[str(out/v[len(str(parent))+1:])if v.startswith(str(parent)+'/')else v for v in record['command']]
 sources=set(build_inputs(cmd))|{out/'sensor.h',out/'test_aim.h',out/'bullet_sensor.h',Path(__file__).resolve()};manifest={str(p.relative_to(ROOT)):sha(p)for p in sources}
 with(out/'build.log').open('w')as f:subprocess.run(cmd,cwd=ROOT/'upstream/dm/host',stdout=f,stderr=subprocess.STDOUT,check=True)
 shutil.copytree(parent/'modules',out/'modules');host=out/'dmhost-aim';record.update(output=str(host.relative_to(ROOT)),output_sha256=sha(host),source_sha256=manifest,command=cmd,diagnostic='D4 read-only superhook/canonical stride1; accepted aim writes unchanged',parent_sha256=sha(parent/'dmhost-aim'),private_module_sha256={p.name:sha(p)for p in(out/'modules').iterdir()if p.is_file()})
 for p,h in protected.items():assert sha(ROOT/p)==h,p
 host.with_suffix('.build.json').write_text(json.dumps(record,indent=2)+'\n');(out/'protected.json').write_text(json.dumps(protected,indent=2)+'\n');print(host)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args())
