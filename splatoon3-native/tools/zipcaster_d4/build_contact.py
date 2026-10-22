"""Fresh private sensor host/modules, never rewrites any accepted runtime."""
import argparse,json,os,shutil,struct,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.analyze_direction import sha
from tools.build_a7_host import build_inputs

def main(a):
    parent=ROOT/'work/d4/meter-v1';host=parent/'dmhost-aim'
    record=json.loads(host.with_suffix('.build.json').read_text());out=a.out.resolve()
    if out.exists()or not out.is_relative_to(ROOT/'work'):raise ValueError('fresh private work path required')
    assert sha(host)==record['output_sha256']
    for p,h in record['source_sha256'].items():assert sha(ROOT/p)==h,p
    protected=json.loads((parent/'protected.json').read_text());protected[str(host.relative_to(ROOT))]=sha(host)
    for p,h in protected.items():assert sha(ROOT/p)==h,p
    # Rewriter guards use ARM64 instruction words, not byte-order hex strings.
    image=(ROOT/'work/d2b/main.bin').read_bytes()
    assert struct.unpack_from('<I',image,0x19ec100)[0]==0xd10583ff
    out.mkdir(parents=True)
    shutil.copy2(Path(__file__),out/'tested-build_contact.py')
    for name in ['hle.c','hle_rl.c','test_aim.h','bullet_sensor.h','sensor.h']:
        (out/name).write_text((parent/name).read_text().replace(str(parent),str(out)))
    selected=a.sensor.resolve()
    if not selected.is_relative_to(ROOT/'tools/zipcaster_d4'):raise ValueError('repository sensor source required')
    sensor=out/'contact_sensor.h';shutil.copy2(selected,sensor)
    rl=out/'hle_rl.c';text=rl.read_text();needle='static void own_player(const uint64_t *r) {';assert text.count(needle)==1
    text=text.replace(needle,f'#include "{sensor}"\n'+needle).replace('    d2b_init();','    d2b_init();\n    d4_contact_init();',1);rl.write_text(text)
    command=[str(out/v[len(str(parent))+1:])if v.startswith(str(parent)+'/')else v for v in record['command']]
    with(out/'build.log').open('w')as f:subprocess.run(command,cwd=ROOT/'upstream/dm/host',stdout=f,stderr=subprocess.STDOUT,check=True)
    shutil.copytree(parent/'modules',out/'modules')
    rewrite=out/'rewrite.py';text=(ROOT/'work/d3r/aim-v1/rewrite.py').read_text();needle="'28c4287aee36f7499da60f3e68b54c70': [\n";assert text.count(needle)==1
    text=text.replace(needle,needle+"    (0x19ec100,51,'d10583ff','D4 SaberSlash live calc readonly matrix/shape snapshot'),\n",1);rewrite.write_text(text)
    env={k:v for k,v in os.environ.items()if not k.startswith('DM_')};env['DM_RULESET']='native'
    with(out/'rewrite.log').open('w')as f:subprocess.run([sys.executable,str(rewrite),str(ROOT/'work/data/v720896/ExeFS/main'),str(out/'modules'),'main'],env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
    inputs=set(build_inputs(command))|{sensor,Path(__file__).resolve(),rewrite,selected}
    record.update(output=str((out/'dmhost-aim').relative_to(ROOT)),output_sha256=sha(out/'dmhost-aim'),command=command,source_sha256={str(p.relative_to(ROOT)):sha(p)for p in inputs},private_module_sha256={p.name:sha(p)for p in(out/'modules').iterdir()if p.is_file()},contact_readonly_sensor=True,parent_sha256=sha(host),diagnostic='D4 default-off live SaberSlash readonly matrix/snapshot51; requires existing test aim fixture')
    (out/'dmhost-aim.build.json').write_text(json.dumps(record,indent=2)+'\n')
    assert all(sha(ROOT/p)==h for p,h in protected.items())
    (out/'protected.json').write_text(json.dumps(protected,indent=2)+'\n');print(out/'dmhost-aim')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--sensor',type=Path,default=Path(__file__).with_name('contact_sensor_v3.h'));main(p.parse_args())
