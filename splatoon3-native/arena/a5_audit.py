"""Audit a stopped A5 run against native settlement records and the 70-game gate."""
import argparse
from collections import Counter
import json
from pathlib import Path

from .checkpoint import ROOT, load_resume, path_at_root, relative, sha256
from .config import PolicySpec
from .hud_events import HudEvents
from .lib.atlas import MapAtlas
from .statistics import tournament_statistics,meets_a5_threshold

STAGES={1:'Yunohana',2:'District00',3:'Yagara'}
POLICIES=('rush','high-ground')


def winners_from_local_scores(score0,score1,roles):
    """Scores are [own, enemy] for each observer; roles map seat to policy."""
    def seat_winner(own,enemy,seat):
        if abs(own-enemy)<1e-6:return None
        return seat if own>enemy else 1-seat
    seats=[seat_winner(*score0,0),seat_winner(*score1,1)]
    if seats[0]!=seats[1]:return seats,None
    if seats[0] is None:return seats,'draw'
    return seats,'a' if roles[seats[0]]==0 else 'b'


def last_native_barrier(path):
    last=None
    with path.open() as stream:
        for line in stream:last=json.loads(line)
    if last is None:raise ValueError(f'empty native trace: {path}')
    return last


def replay_hud(path,stage):
    with path.open() as stream:first=json.loads(next(stream))
    origins={seat:dict(frame=info['frame']) for seat,info in first['infos'].items()}
    events=HudEvents(origins,MapAtlas.load(stage))
    with path.open() as stream:
        for line in stream:
            row=json.loads(line);events.update(row['infos'],row['frame'])
    return {seat:events.summary(seat,'player_1' if seat=='player_0' else 'player_0')
            for seat in ('player_0','player_1')}


def audit_checkpoint(path):
    path=Path(path).resolve();d=json.loads(path.read_text())
    if d['policies']!=list(POLICIES):raise ValueError('unexpected policy order')
    specs=[PolicySpec.load(ROOT/'arena/policies'/name) for name in POLICIES]
    load_resume(path,specs,d['games_requested'])
    # The source run was intentionally interrupted after its 70th valid game.
    # Preserve that original status while judging the completed subset below.
    if d.get('errors') not in ([], ['KeyboardInterrupt()']) or d.get('stop_reason'):
        raise ValueError('tournament has an unexpected coordinator error')
    if d.get('parallel_games')!=4 or not any(
        w['rooms']>=4 and w['hosts']>=8 and w['overlap_seconds']>0
        for w in d.get('concurrency_windows',[])
    ):
        raise ValueError('four native rooms did not overlap')
    matches=d['matches'];valid={};void=[];rows=[];evidence={}
    for m in matches:
        n=m['round'];roles=m['role_to_policy']
        if m['stage']!=(n//2)%3+1 or roles!=([0,1] if n%2==0 else [1,0]):
            raise ValueError(f'paired fixture changed: {n}')
        artifacts=path_at_root(m['artifacts']);trace=artifacts/'native-barriers.jsonl'
        result=artifacts/'result.json'
        if not trace.exists() or not result.exists():raise ValueError(f'missing attempt evidence: {n}')
        evidence[relative(trace)]=sha256(trace)
        evidence[relative(result)]=sha256(result)
        if m.get('passed'):
            if n in valid or m.get('void'):raise ValueError(f'duplicate/void valid round: {n}')
            last=last_native_barrier(trace);infos=last['infos']
            if not all(i['phase']==3 and i['score_valid'] and i['turf_valid'] and i['score_units']==1 for i in infos.values()):
                raise ValueError(f'no native Winners: {n}')
            raw=[infos[f'player_{seat}']['score'] for seat in (0,1)]
            if raw!=m['score_peers_native_order']:raise ValueError(f'native score changed: {n}')
            seats,outcome=winners_from_local_scores(*raw,roles)
            if outcome is None or seats!=m['winner_by_observer'] or outcome!=m['outcome']:
                raise ValueError(f'policy winner mapping differs: {n}')
            average=[(raw[0][0]+raw[1][1])/2,(raw[0][1]+raw[1][0])/2]
            if any(abs(a-b)>1e-8 for a,b in zip(average,m['score_by_role'])):
                raise ValueError(f'average score differs: {n}')
            if replay_hud(trace,m['stage'])!=m['hud_by_role']:
                raise ValueError(f'HUD events differ from native trace: {n}')
            valid[n]=m
            images=[artifacts/f'winners-player_{seat}.png' for seat in (0,1)]
            rows.append(dict(round=n,map=STAGES[m['stage']],attempt=m['attempt'],
                             role_to_policy=roles,observer0_own_enemy=raw[0],
                             observer1_own_enemy=raw[1],winning_seat=seats[0],
                             winning_policy=POLICIES[roles[seats[0]]] if seats[0] is not None else None,
                             outcome=outcome,score_by_seat=average,suspect=m['suspect'],
                             trace_sha256=evidence[relative(trace)],
                             winners_images=[relative(i) for i in images if i.exists()]))
        elif m.get('void') and not m.get('cancelled'):
            if m['void_reason']=='native_progress_watchdog':
                actual=[]
                for item in m['watchdog_evidence']:
                    log=path_at_root(item['log'])
                    if log.exists() and item['line'] in log.read_text(errors='replace'):
                        actual.append(item)
                        evidence[relative(log)]=sha256(log)
                if not any('FATAL RL_STALL no present progress' in e['line'] for e in actual):
                    raise ValueError(f'watchdog evidence absent: {n}')
            elif m['void_reason']=='peer_winner_disagreement':
                raw=m['score_peers_native_order'];seats,outcome=winners_from_local_scores(*raw,roles)
                if seats[0]==seats[1] or outcome is not None:raise ValueError(f'not a score void: {n}')
            else:raise ValueError(f'unknown void reason: {n}')
            void.append(m)
        else:raise ValueError(f'failed or cancelled counted attempt: {n}')
    if len(valid)<70 or set(valid)!=set(range(len(valid))):
        raise ValueError('A5 needs at least 70 consecutive completed fixtures')
    stats=tournament_statistics(matches)
    if not meets_a5_threshold(stats['valid_games'],stats['void_games'],d['parallel_games']) or stats['failed_or_cancelled']:
        raise ValueError('revised A5 acceptance gate failed')
    if stats!=d['statistics']:raise ValueError('checkpoint statistics differ from audited matches')
    by_map={}
    for stage,name in STAGES.items():
        selected=[m for m in valid.values() if m['stage']==stage]
        by_map[name]=dict(valid=len(selected),rush_wins=sum(m['outcome']=='a' for m in selected),
                          high_ground_wins=sum(m['outcome']=='b' for m in selected),
                          void=sum(m['stage']==stage for m in void))
    seat_wins=Counter(row['winning_seat'] for row in rows)
    rows.sort(key=lambda row:row['round'])
    return dict(schema='arena.a5.audit.v1',accepted=True,
                criterion='at least 70 valid native games; void/(valid+void) <= 10%',
                source_checkpoint=relative(path),source_sha256=sha256(path),
                policy_order=list(POLICIES),valid_rounds=len(valid),
                statistics=stats,by_map=by_map,
                seat_wins={'player_0':seat_wins[0],'player_1':seat_wins[1]},
                voids=[dict(round=m['round'],attempt=m['attempt'],map=STAGES[m['stage']],
                            reason=m['void_reason'],artifacts=relative(m['artifacts'])) for m in void],
                elapsed_wall_seconds=d['elapsed_wall_seconds'],
                native_overlap_windows=len(d['concurrency_windows']),
                evidence_sha256=evidence,rounds=rows)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('checkpoint',type=Path);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();report=audit_checkpoint(args.checkpoint)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('accepted','valid_rounds','seat_wins','by_map','voids','elapsed_wall_seconds')},indent=2))
