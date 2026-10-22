"""Accepted aim host plus one lightweight read-only counter log per present.

Keeps large D2B snapshots at their accepted4f cadence. Fresh private path only.
"""
import argparse,json,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.analyze_direction import sha
from tools.build_a7_host import build_inputs
HELPER=r'''
static void d4_meter(uintptr_t player,int slot){
 static uint64_t last=~(uint64_t)0;
 if(!d2b_enabled||!dm_rl_active()||atomic_load(&rl_phase)!=1||slot!=rl_self_slot)return;
 uint64_t frame=dm_guest_frame();if(frame==last)return;last=frame;
 uintptr_t storage=0,key_pointer=0;uint32_t key=0,value=0;
 if(d2b_read(player+0x108,&storage,8)&&storage&&
    d2b_read(d2b_base+0x6001130,&key_pointer,8)&&key_pointer&&
    d2b_read(key_pointer,&key,4)&&d2b_read(storage+0xd18,&value,4))
  LOG("D4_METER frame=%llu slot=%d remaining=%d readonly=1",frame,slot,(int32_t)(value^key));
}
'''
def main(a):
 parent=ROOT/'work/d3r/aim-v1';r=json.loads((parent/'dmhost-aim.build.json').read_text());out=a.out.resolve()
 if not out.is_relative_to(ROOT/'work')or out.exists():raise ValueError('fresh work path required')
 assert sha(parent/'dmhost-aim')==r['output_sha256']
 for p,h in r['source_sha256'].items():assert sha(ROOT/p)==h,p
 protected={p:sha(ROOT/p)for p in json.loads((parent/'protected.json').read_text())};protected[str((parent/'dmhost-aim').relative_to(ROOT))]=sha(parent/'dmhost-aim');out.mkdir(parents=True)
 for name in ['hle.c','hle_rl.c','test_aim.h','bullet_sensor.h','sensor.h']:(out/name).write_text((parent/name).read_text().replace(str(parent),str(out)))
 p=out/'hle_rl.c';s=p.read_text();needle='static void own_player(const uint64_t *r) {';assert s.count(needle)==1;s=s.replace(needle,HELPER+'\n'+needle).replace('    d2b_damage((uintptr_t)r[0],slot);','    d2b_damage((uintptr_t)r[0],slot);\n    d4_meter(player,slot);',1);p.write_text(s)
 command=[str(out/v[len(str(parent))+1:])if v.startswith(str(parent)+'/')else v for v in r['command']];sources=set(build_inputs(command))|{out/n for n in ['sensor.h','test_aim.h','bullet_sensor.h']}|{Path(__file__).resolve()};manifest={str(p.relative_to(ROOT)):sha(p)for p in sources}
 with(out/'build.log').open('w')as f:subprocess.run(command,cwd=ROOT/'upstream/dm/host',stdout=f,stderr=subprocess.STDOUT,check=True)
 shutil.copytree(parent/'modules',out/'modules');host=out/'dmhost-aim';r.update(output=str(host.relative_to(ROOT)),output_sha256=sha(host),source_sha256=manifest,command=command,diagnostic='D4 lightweight readonly1f meter; original4f snapshots and aim/module bytes unchanged',parent_sha256=sha(parent/'dmhost-aim'),private_module_sha256={p.name:sha(p)for p in(out/'modules').iterdir()if p.is_file()})
 for p,h in protected.items():assert sha(ROOT/p)==h,p
 host.with_suffix('.build.json').write_text(json.dumps(r,indent=2)+'\n');(out/'protected.json').write_text(json.dumps(protected,indent=2)+'\n');print(host)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args())
