"""Compare recorded final-model routes to existing native packet-clock traces."""
import json
from pathlib import Path
import numpy as np

from sim.parameters import ROOT,sha256
from sim.corpus import Trace


def main():
    base=ROOT/'work/sim/window-20261021';source=ROOT/'work/sim/ranking/sources.json'
    sources=json.loads(source.read_text());corpus=json.loads((ROOT/'work/sim/fidelity/corpus.json').read_text())
    old=json.loads((ROOT/'work/sim/diagnosis/native.json').read_text());reports=[]
    for pair,swap in (('R1',True),('R2',False)):
        directory=base/'route-check'/f'{pair}-map1-side{int(swap)}'
        result=json.loads((directory/'routes.json').read_text())
        if not result['trajectory_digests_match']:raise ValueError('recorder changed simulation')
        match=next(m for m in sources['references'][pair]['matches'] if m['stage']==1)
        canonical=str((ROOT/match['source']).relative_to(ROOT))
        entry=next(e for e in corpus['games'] if e['path']==canonical);trace=Trace(entry)
        order=[match['role_to_policy'].index(i) for i in (0,1)]
        native=next(g for g in old['games'] if g['pair']==pair and g['stage']==1)
        with np.load(directory/'trace-0.npz') as data:states=data['states'];actions=data['actions']
        roles=[]
        for role in (0,1):
            physical=order[role];ids=trace.samples[physical];ids=ids[ids<len(states)]
            errors=np.linalg.norm(trace.states[ids,physical,:3]-states[ids,role,:3],axis=1)
            first=int(ids[np.flatnonzero(errors>1.)[0]]) if (errors>1.).any() else None
            delta=np.max(np.abs(trace.actions[:len(actions),physical]-actions[:trace.frames,role]),axis=1)
            first_action=int(np.flatnonzero(delta>1e-6)[0]) if (delta>1e-6).any() else None
            observed=trace.states[ids,physical];n50=ids[abs(observed[:,2])<50]
            s50=np.flatnonzero(abs(states[:,role,2])<50)
            point=dict(frame=first,native=trace.states[first,physical,:3].tolist(),simulated=states[first,role,:3].tolist(),
                native_view_yaw=float(trace.states[first,physical,4]),simulated_view_yaw=float(states[first,role,4])) if first is not None else None
            roles.append(dict(role=role,first_action_difference=first_action,first_position_error_over1=point,
                first_absZ_below50_native=int(n50[0]) if len(n50) else None,first_absZ_below50_simulated=int(s50[0]) if len(s50) else None,
                native=native['routes'][role],simulated=result['games'][0]['routes'][role]))
        reports.append(dict(pair=pair,stage=1,swap=swap,roles=roles,trace_sha256=sha256(directory/'trace-0.npz'),
            native_source=entry,recording_sha256=sha256(directory/'routes.json')))
    report=dict(games=reports,source_sha256=sha256(source),native_summary_sha256=sha256(ROOT/'work/sim/diagnosis/native.json'),
        report_code_sha256=sha256(Path(__file__)),corpus_manifest_sha256=sha256(ROOT/'work/sim/fidelity/corpus.json'),
        scope='复核R1/R2各一个图1固定起点代表局；对应两组六起点共12次记录重放的轨迹digest全部逐位等于最终排名，记录器没有改变轨迹。原生仅在自身sample frame比较，角色映射到策略顺序，没有新增原生对局。闭环输入可能先不同，位置差不能单独识别地形碰撞。')
    (base/'routes-comparison.json').write_text(json.dumps(report,indent=2)+'\n')
    lines=['### 最终模型的路线反例复核','',report['scope'],'',
        '| 局/角色 | 首次输入不同帧 | 首次位置差>1帧 | 到absZ<50 原生/模拟 | 首次可见 原生/模拟 | 高台首次 原生/模拟 |',
        '| --- | ---: | ---: | --- | --- | --- |']
    for game in reports:
        for r in game['roles']:
            n,s=r['native'],r['simulated'];f=r['first_position_error_over1']
            lines.append(f"| {game['pair']}/图1/{'alpha' if r['role']==0 else 'bravo'} | {r['first_action_difference']} | {f['frame'] if f else None} | {r['first_absZ_below50_native']} / {r['first_absZ_below50_simulated']} | {n['first_visible_frame']} / {s['first_visible_frame']} | {n['high_first_frame']} / {s['high_first_frame']} |")
    lines+=['','这里是闭环偏离定位；输入已经不同，不能据两条不同路线直接拟合物理碰撞。完整XYZ、相机和终点保留在`routes-comparison.json`；None表示整个窗口没有观测到。', '']
    (base/'routes-comparison.md').write_text('\n'.join(lines));print(json.dumps(report,indent=2))


if __name__=='__main__':main()
