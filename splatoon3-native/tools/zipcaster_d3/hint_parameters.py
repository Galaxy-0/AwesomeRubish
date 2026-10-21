"""Extract only D3 resource scalars from local sparse parameters (not assets)."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.stage_collision import unpack
from tools.byml import read

def extract(out):
    pack=ROOT/'work/data/v720896/RomFS/Pack/Params.pack.zs';entries=unpack(pack)
    names=['Component/GameParameterTable/WeaponSpSuperHook.game__GameParameterTable.bgyml','Component/GameParameterTable/WeaponSaberNormal.game__GameParameterTable.bgyml']
    hook=read(entries[names[0]])['GameParameters']['WeaponParam'];saber=read(entries[names[1]])['GameParameters']['spl__WeaponSaberParam'];capacity=hook['InkCapacityRt']
    raw=dict(capacity=capacity,hook_ink=hook['InkConsume_Hook']['Low'],natural_ink_per_second=hook['InkConsume_PerSec']['Low'],light_ink=saber['SwingParam']['InkConsume'],full_ink=saber['ChargeParam']['InkConsumeFullCharge'],counter=hook['SpecialTotalFrame'])
    data=dict(schema='inklab.d3.resource.parameters.v1',build='11.3.0',raw_scalars=raw,normalized=dict(per_hook=raw['hook_ink']/capacity,per_light=raw['light_ink']/capacity,per_full=raw['full_ink']/capacity,natural_per_present=raw['natural_ink_per_second']/capacity/60),provenance=dict(pack_sha256=hashlib.sha256(pack.read_bytes()).hexdigest(),entries={}),limits=['Low/Mid/High names are parameter interpolation endpoints; native default QS57AP cohort verifies Low rates only.','Budget reservations are not a recovered native charge integrator.'])
    data['provenance']['entries']={n:hashlib.sha256(entries[n]).hexdigest()for n in names}
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');return data
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=ROOT/'work/d3/hint-parameters.json');print(json.dumps(extract(ap.parse_args().out),indent=2))
