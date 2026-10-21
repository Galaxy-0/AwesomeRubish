"""Resume completed immutable v2 tactic rows into a NEW output directory."""
import argparse,json,sys,time
from pathlib import Path
from dataclasses import asdict
sys.path.insert(0,str(Path(__file__).resolve().parent))
import search_v2 as search
from native import ROOT,sha
from model_v2 import Config

def key(p):return (p['map'],p['start_region'],tuple(p.get('sequence',[p['id']])))
def main(a):
    if a.out.exists():raise ValueError('fresh output required')
    manifest=json.loads(a.manifest.read_text())
    for path,h in manifest.items():assert sha(ROOT/path)==h,path
    coarse=json.loads(a.coarse.read_text());beam=json.loads(a.beam.read_text());partial=json.loads(a.partial.read_text())
    selected=search.select_fine(coarse)+[r|dict(band='beam')for m in beam['maps']for r in m['fine_sequences']]
    selected=[r for r in selected if r['stage']==a.stage];done=partial['points'];donekeys={key(r)for r in done}
    if len(donekeys)!=len(done)or not donekeys<=set(map(key,selected)):raise ValueError('partial selection mismatch')
    missing=[r for r in selected if key(r)not in donekeys];search.select_fine=lambda data:missing
    single=a.out.parent/'resumed-missing.json';a.out.parent.mkdir(parents=True,exist_ok=False)
    print('RESUME_MISSING '+json.dumps([key(r)for r in missing]),flush=True)
    if missing:
        search.fine(argparse.Namespace(coarse=a.coarse,beam=None,stage=a.stage,enemy_nodes=0,samples=8,out=single))
        result=json.loads(single.read_text());new=[r for m in result['maps']for r in m['points']]
    else:result={};new=[]
    bykey={key(r):r for r in done+new};assert set(bykey)==set(map(key,selected))
    m=next(m for m in coarse['maps']if m['stage']==a.stage)
    result.update(schema='inklab.d3.fine.v2',config=asdict(Config()),coarse_sha256=sha(a.coarse),maps=[dict(id=m['id'],stage=a.stage,points=[bykey[key(r)]for r in selected])],seconds=sum(r['seconds']for r in done)+result.get('seconds',0),timing_scope='Completed pre-pause point wall sums plus resumed job wall; aborted in-progress work and old inter-point overhead unknown. Not uninterrupted job wall.',resume=dict(partial=str(a.partial.relative_to(ROOT)),partial_sha256=sha(a.partial),completed_rows=len(done),recomputed_rows=len(new),original_source_manifest_sha256=sha(a.manifest),wrapper_sha256=sha(__file__)))
    search.write(a.out,result)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',type=int,required=True);p.add_argument('--partial',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--coarse',type=Path,default=ROOT/'work/d3/coarse-v2.json');p.add_argument('--beam',type=Path,default=ROOT/'work/d3/beam-v2.json');p.add_argument('--manifest',type=Path,default=ROOT/'work/d3/fine-v2-sources/manifest.json');a=p.parse_args();a.partial=a.partial.resolve();a.out=a.out.resolve();main(a)
