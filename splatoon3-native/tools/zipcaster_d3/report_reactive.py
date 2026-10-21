"""Audit current-visible .52 reaction controls before ranking experiments."""
import json,math,sys,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from native import ROOT,sha

def control(pattern,target):
    paths=list((ROOT/'work/a6').glob(pattern+'/result.json'));assert len(paths)==1
    p=paths[0];d=json.loads(p.read_text());assert d['passed']and'freeze_after'in d
    rows=[json.loads(l)for l in p.with_name('steps.jsonl').open()];history=d['reactive_history'];first=next(r['t']for r in history if r['visible'])
    shots=[r for r in history if r['fired']];assert shots and all(r['visible']and r['t']-first>=18 for r in shots)
    hp=[]
    for a,b in zip(rows,rows[1:]):
        aa=a['infos'][target];bb=b['infos'][target]
        if aa['hp']-bb['hp']>.1:
            hp.append(dict(frame=bb['frame'],before=aa['hp']*100,after=bb['hp']*100,damage=(aa['hp']-bb['hp'])*100,label=b['label'],target_position=bb['position'],shooter_position=b['infos']['player_1']['position'],distance=math.dist(bb['position'],b['infos']['player_1']['position'])))
    assert len(hp)>=2 and hp[-1]['after']==0 and all(abs(r['damage']-52)<1e-4 or r['after']==0 for r in hp)
    hashes={str(Path(k).relative_to(ROOT)):h for k,h in d['raw_sha256'].items()}
    hashes[str(p.relative_to(ROOT))]=sha(p)
    for k,h in hashes.items():assert sha(ROOT/k)==h,k
    for pid in d['owned_pids']:assert'dmhost'not in subprocess.run(['ps','-p',str(pid),'-o','comm='],capture_output=True,text=True).stdout
    return dict(artifact=str(p.relative_to(ROOT)),raw_sha256=hashes,first_visible_tick=first,first_fired_tick=shots[0]['t'],visible_ticks=sum(r['visible']for r in history),fire_ticks=len(shots),damage_notifications=hp,two_hit_notification_gap=hp[-1]['frame']-hp[-2]['frame'],full_health_before=hp[0]['before']==100,ko=True,owned_pids=d['owned_pids'])
if __name__=='__main__':
    controls=[control('d3-hint-reactive-control-r1-*','player_0'),control('d3-hint-duel-District00-hook-0585-3-*','player_0')]
    out=dict(schema='inklab.d3.reactive.controls.v1',full_d3_passed=False,controls=controls,conclusion='Filtered visible-only .52 script produces native52 damage and two-hit KO on flat near target and on arrived Zipcaster attacker. This validates threat existence, not all ballistic/distribution assumptions.',source_sha256={str(Path(__file__).relative_to(ROOT)):sha(__file__),str((ROOT/'tools/zipcaster_d3/validate.py').relative_to(ROOT)):sha(ROOT/'tools/zipcaster_d3/validate.py')})
    p=ROOT/'notes/d3-reactive-controls-20261021.json';p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps([{k:r[k]for k in ['artifact','fire_ticks','damage_notifications','two_hit_notification_gap']}for r in controls],ensure_ascii=False,indent=2))
