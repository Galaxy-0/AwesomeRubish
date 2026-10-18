"""Durable numeric result checkpoints; raw game traces stay in ignored work/."""
import copy
import hashlib
import json
from pathlib import Path
from .scoring import compare_scores,SCORING_RULE
from .statistics import tournament_statistics

ROOT=Path(__file__).resolve().parents[1]
COORDINATOR_CHANGES={'arena/runner.py','arena/schedule.py','arena/statistics.py'}


def sha256(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def path_at_root(path):
    p=Path(path)
    return p if p.is_absolute() else ROOT/p


def relative(path):return str(path_at_root(path).resolve().relative_to(ROOT))


def migrate_legacy(source):
    """Reconcile completed old Winners from their recorded native barriers."""
    from .hud_events import HudEvents
    from .lib.atlas import MapAtlas
    source=Path(source).resolve();old=json.loads(source.read_text());matches=[];excluded=[]
    evidence={relative(source):sha256(source)}
    frozen=json.loads((source.parent/'runtime-sha256.json').read_text())
    immutable={relative(p):h for p,h in frozen.items() if relative(p) not in COORDINATOR_CHANGES}
    for m in old['matches']:
        if m.get('cancelled'):
            excluded.append({k:copy.deepcopy(m[k]) for k in ('round','attempt','stage','cancelled','artifacts','wall_seconds','errors')});continue
        trace=path_at_root(m['artifacts'])/'native-barriers.jsonl'
        evidence[relative(trace)]=sha256(trace)
        with trace.open() as stream:
            first=json.loads(next(stream));last=first
            for line in stream:last=json.loads(line)
        infos=last['infos']
        if not all(i['phase']==3 and i['score_valid'] and i['turf_valid'] and i['score_units']==1 for i in infos.values()):
            raise ValueError('legacy attempt did not reach valid Winners')
        verdict=compare_scores(infos['player_0']['score'],infos['player_1']['score'],m['role_to_policy'])
        item=copy.deepcopy(m);item.update(verdict)
        item.pop('traceback',None)
        item.update(legacy_verdict=dict(passed=m['passed'],errors=m['errors']),errors=[],cancelled=False,
                    frames=last['frame'],native_winners=True,controlled_end_wall=last['wall_time'],
                    passed=not verdict['void'],reconciled_from_native_trace=True)
        if 'hud_by_role' not in item:
            origins={a:dict(frame=i['frame']-first['frame']) for a,i in first['infos'].items()}
            events=HudEvents(origins,MapAtlas.load(m['stage']))
            with trace.open() as stream:
                for line in stream:
                    row=json.loads(line);events.update(row['infos'],row['frame'])
            item['hud_by_role']={a:events.summary(a,'player_1' if a=='player_0' else 'player_0') for a in infos}
        if any(h[k] is None for h in item['hud_by_role'].values() for k in ('enemy_hud_downs','own_hud_downs')):
            raise ValueError('legacy HUD counters unavailable')
        item['source_hashes']=old['source_hashes'];matches.append(item)
    next_attempt={str(n):max([m.get('attempt',0) for m in old['matches'] if m['round']==n],default=-1)+1 for n in range(old['games_requested'])}
    return dict(schema='arena.checkpoint.v1',scoring_rule=SCORING_RULE,passed=False,full_a5_passed=False,
                games_requested=old['games_requested'],parallel_games=old['parallel_games'],
                policies=old['policies'],source_hashes=old['source_hashes'],matches=matches,
                statistics=tournament_statistics(matches),elapsed_wall_seconds=old['elapsed_wall_seconds'],
                first_started_wall=old['started_wall'],
                excluded_attempts=excluded,next_attempt_by_round=next_attempt,
                evidence_sha256=evidence,immutable_runtime_sha256=immutable,
                legacy_source_result=relative(source),legacy_runtime_exceptions=sorted(COORDINATOR_CHANGES))


def load_resume(path,specs,games):
    d=json.loads(Path(path).read_text())
    if d.get('scoring_rule')!=SCORING_RULE or d.get('games_requested')!=games:
        raise ValueError('resume scoring rule/fixture count differs')
    if d['source_hashes']!=[s.source_sha256 for s in specs] or d['policies']!=[s.name for s in specs]:
        raise ValueError('resume policy source or order changed')
    matches=d['matches'];valid=set()
    for m in matches:
        n=m['round']
        if not 0<=n<games or m['stage']!=(n//2)%3+1 or m['role_to_policy']!=([0,1] if n%2==0 else [1,0]):
            raise ValueError('resume paired fixture differs')
        if m.get('passed'):
            if n in valid:raise ValueError('duplicate resumed valid fixture')
            valid.add(n)
            if not m.get('native_winners'):raise ValueError('resumed valid fixture lacks native Winners')
            v=compare_scores(*m['score_peers_native_order'],m['role_to_policy'])
            if v['void'] or any(m.get(k)!=value for k,value in v.items()):
                raise ValueError('resume score verdict differs')
        elif not m.get('void'):raise ValueError('resume contains a fatal/cancelled attempt')
    for group in ('evidence_sha256','immutable_runtime_sha256'):
        for p,h in d.get(group,{}).items():
            if sha256(path_at_root(p))!=h:raise ValueError('resume evidence/runtime hash changed: '+p)
    return d


def write_checkpoint(report,path):
    """Export numeric summaries, hashes and local relative evidence references."""
    d=copy.deepcopy(report);d['schema']='arena.checkpoint.v1'
    for m in d['matches']+d.get('excluded_attempts',[]):
        for key in ('artifacts','session','shared_load_slots'):
            if m.get(key):m[key]=relative(m[key])
        if m.get('sessions_created'):m['sessions_created']=[relative(p) for p in m['sessions_created']]
    if d.get('artifacts'):d['artifacts']=relative(d['artifacts'])
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,indent=2)+'\n')
    return d


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--legacy',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();report=migrate_legacy(args.legacy);write_checkpoint(report,args.out)
    print(json.dumps(report['statistics'],indent=2))
