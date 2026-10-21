"""Freeze new hint cohort summaries, preserving old stopped D3 evidence."""
import argparse,json,math,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from native import ROOT,sha
from report_hint import reduce
NAMES=['r1-wall','r1-jump','r1-meter','r1-combo','r2-low-wall','r2-low-jump','r2-district-rehook','sequence-preaim','district-jump']
def main(out):
    runs=[]
    for name in NAMES:
        paths=list((ROOT/'work/a6').glob('d3-hint-'+name+'-[0-9]*/result.json'));assert len(paths)==1
        p=paths[0];d=json.loads(p.read_text());assert 'freeze_after'in d
        for path,h in d['raw_sha256'].items():assert sha(path)==h
        r=reduce(p);gs=r['groups'];records=[]
        for g in gs:
            residual=[]
            for a,b in zip(g['native'],g['native'][1:]):
                x=a['remaining_counter']-b['remaining_counter']-.9*(b['frame']-a['frame'])
                if x>2:residual.append(x)
            records.append(dict(label=g['label'],first=g['first'],last=g['last'],yaw_delta_deg=g['yaw_delta_deg'],counter_extra_above_natural=sum(residual),states=sorted(set(s['state_native']for s in g['sensors']))))
        bind=[];prev=-1
        for g in gs:
            for s in g['sensors']:
                if s['state_native']==2 and prev!=2 and s['bind_witness']:bind.append({k:s[k]for k in ['native_frame','anchor_world','hit_normal_world']})
                prev=s['state_native']
        raw={str(Path(k).relative_to(ROOT)):v for k,v in d['raw_sha256'].items()};raw[str(p.relative_to(ROOT))]=sha(p)
        raw[str(p.with_name('sensors.jsonl').relative_to(ROOT))]=sha(p.with_name('sensors.jsonl'))
        tested=p.parent/'tested-hint_probe.py';raw[str(tested.relative_to(ROOT))]=sha(tested)
        events=[dict(event=e['event'],players={k:{f:v[f] for f in ['frame','position','heading','own_view','referee_motion','hp','special','ink'] if f in v}for k,v in e['infos'].items()})for e in r['events']]
        runs.append(dict(name=name,artifact=r['artifact'],passed=r['passed'],errors=r['errors'],meter=r['meter'],jump=r['jump'],mode=r['mode'],events=events,groups=records,bindings=bind,raw_sha256=raw,owned_pids=d['owned_pids']))
    result=dict(schema='inklab.d3.hint.summary.v1',full_d3_passed=False,runs=runs,parameters=json.loads((ROOT/'work/d3/hint-parameters.json').read_text()),scope='Mechanism checkpoint only. No ranking/calibration cohort claimed. B6 has a native jump and two static full-light KOs; universal B necessity not proven. First District rehook fixture used overlapping source/target and had no binds, excluded.',source_sha256={str(p.relative_to(ROOT)):sha(p)for p in [Path(__file__),Path(__file__).with_name('report_hint.py'),Path(__file__).with_name('hint_parameters.py')]})
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(dict(runs=len(runs),bindings=[(r['name'],len(r['bindings']))for r in runs]),ensure_ascii=False))
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=ROOT/'notes/d3-hint-20261021.json');main(ap.parse_args().out)
