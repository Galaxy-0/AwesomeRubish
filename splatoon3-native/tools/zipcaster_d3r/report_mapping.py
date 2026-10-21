"""Reduce closed mapping cohort to source-safe numeric evidence and notes."""
import argparse,datetime,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.analyze_direction import sha

def main(a):
 batch=json.loads((ROOT/'work/d3r/mapping-v1/batch.json').read_text());ray=json.loads(a.ray.read_text());sweep=json.loads(a.sweep.read_text());frozen=json.loads(a.parameters.read_text());assert len(batch['results'])==15 and all(r['passed']and r['eligible_casts']==8 for r in batch['results']);assert len(sweep['rows'])==120 and not sweep['open_rooms_excluded'];assert sweep['parameters_sha256']==sha(a.parameters)
 intervals=[];owned=[]
 for run in sweep['runs']:
  p=ROOT/run['path'];d=json.loads(p.read_text());assert sha(p)==run['sha256'];assert d['freeze_before']==d['freeze_after'];assert d['clock']=='fixed60'and d['pixels'];owned+=d['owned_pids']
  if d['mapping_job']['batch']>=3:assert frozen['frozen_unix']<p.stat().st_mtime,'confirmatory parameter chronology'
  for raw,h in d['raw_sha256'].items():assert sha(raw)==h
  start=datetime.datetime.strptime(re.search(r'(\d{8}-\d{6}-\d{6})$',p.parent.name)[1],'%Y%m%d-%H%M%S-%f').timestamp();intervals.extend([(start,1),(p.stat().st_mtime,-1)])
 active=peak=0
 for _,delta in sorted(intervals):active+=delta;peak=max(peak,active)
 assert active==0 and peak<=3
 live={int(line.split(None,1)[0]):line.split(None,1)[1]for line in subprocess.check_output(['ps','-axo','pid=,comm='],text=True).splitlines()if line.strip()}
 assert all('dmhost'not in live.get(pid,'')for pid in owned)
 for p,h in json.loads((ROOT/'work/d3r/aim-v1/protected.json').read_text()).items():assert sha(ROOT/p)==h
 for p,h in json.loads((ROOT/'work/d2b/round2-world-build/provenance.json').read_text())['original_module_sha256'].items():assert sha(ROOT/p)==h
 from rl.session import SAVE_HASH
 for p in[ROOT/'work/save_ref/save.dat',ROOT.parent/'splatoon-rl-lab/saves/bis/user/save/0000000000000001/0/save.dat']:assert sha(p)==SAVE_HASH
 casts=[{k:r[k]for k in['map','batch','index','id','split','kind','source_region','source','command','native_bind','anchor','normal','tip_count','arrival','artifact','raw_sha256','sensor_sha256']}|dict(predicted=r['p_sweep'],sweep_anchor_error=r['sweep'].get('anchor_error'))for r in sweep['rows']]
 out=dict(schema='inklab.d3r.mapping.report.v1',step2_completed=True,full_d3r_passed=False,rate_scope='native binding/anchor mapping, not combat probability',native_casts=120,maps={m:dict(casts=sum(r['map']==m for r in casts),bound=sum(r['map']==m and r['native_bind']for r in casts))for m in['Yunohana','District00','Yagara']},tangent_ray_metrics=ray['metrics'],sweep_metrics=sweep['metrics'],sweep_per_map=sweep['per_map'],frozen_parameters=frozen,rooms=15,hosts=len(set(owned)),peak_rooms=peak,owned_hosts_exited=True,protected_unchanged=True,casts=casts,source_sha256={str(p.relative_to(ROOT)):sha(p)for p in[Path(__file__),a.ray,a.sweep,a.parameters,ROOT/'work/d3r/map-plan-v1.json']},limits=['R1 vertical-linear ray exploratory. R2 tangent ray fitted on batches0/1, confirmed on2/3/4. R3 sweep/material developed on0/1/2, confirmed on3/4; no future outcome refit.','Binding accuracy and spatial anchor error are separate. Missing predicted first hit is not silently removed from binary accuracy. Spatial denominator is reported.','Effective sphere radius, Fence handling and origin are surrogate hypotheses; no claim of native collider recovery.','Only measured directions/poses/materials. A 48-cast confirmatory subset cannot certify all continuous hooks.','Measured native anchors/arrivals feed subsequent execution, not requested geometry. No combat-ranking proof from hook-only trials.'])
 out['confirmatory_by_kind']={kind:dict(n=len(rs),correct=sum(r['predicted']==r['native_bind']for r in rs),native_bound=sum(r['native_bind']for r in rs))for kind in['sampled-wall','untargeted-direction']for rs in[[r for r in casts if r['batch']>=3 and r['kind']==kind]]}
 stem=ROOT/'notes'/('d3r-mapping-'+datetime.datetime.now().strftime('%Y%m%d'));stem.with_suffix('.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');c=sweep['metrics']['confirmatory'];d=ray['metrics']['confirmatory'];b=frozen['best']
 lines=[f'# D3-R 第2步：三图出钩映射（{datetime.date.today()}）','',f'15个独立房间、120个预定方向（每图40），全部8次完成；最多{peak}房，{len(set(owned))}个自建host已退出。原始记录、失败和固定事前split都保留；仅测试宿主直接相机夹具，正式对战禁用。','',f'方向映射采用 atan({frozen["ray_parameters"]["tangent_scale"]:.8f} × tan(native pitch) {frozen["ray_parameters"]["tangent_bias"]:+.8f})，前三阶段不同确认集分开报告。正切映射的独立确认方向中位误差 {d["direction_median_degrees"]:.6f}°；不是只读相机角度的自证。','',f'细射线仍有擦过矮墙上沿、栅栏提前遮挡的问题。训练开发集拟合有效扫掠半径{b["radius"]}u、跳过Fence={b["skip_fence"]}，CantBind仍阻挡且拒绑；最短距离{b["minimum_distance"]}u，最大35u。这些是几何代理参数，不是实测原生碰撞半径。','',f'最终未参与拟合的批3/4共{c["n"]}次：绑定判定准确率{c["accuracy"]:.2%}（TP {c["tp"]}, FP {c["fp"]}, TN {c["tn"]}, FN {c["fn"]}）；原生绑定率{c["native_bind_rate"]:.2%}。可比较锚点{c["anchor_n"]}次，中位误差{c["anchor_median"]:.4f}u，P90 {c["anchor_p90"]:.4f}u，最大{c["anchor_max"]:.4f}u。没有把不命中/不绑定从准确率分母删掉；空间误差使用单独分母。','', '| 地图 | 次数 | 原生绑定 | 独立确认准确率 | 锚点中位 / P90 u |','|---|---:|---:|---:|---:|']
 for m,v in out['maps'].items():
  q=sweep['per_map'][m];lines.append(f'| {m} | {v["casts"]} | {v["bound"]} | {q["accuracy"]:.2%} | {q["anchor_median"]:.3f} / {q["anchor_p90"]:.3f} |')
 lines+=['','拟合与确认：R1是线性竖直分量；R2只用批0/1训练射线拟合，批2–4独立确认。R3只用批0–2的事前train，70种离散设置全保留，批3/4独立确认。早期held-out已用于开发检查，所以不冒称最终盲测；最终确认参数文件在最终两批关闭前冻结。详见JSON及其源/原始SHA。','', '范围：这完成测量和受限预测确认，不是全地图连续表面的完备证明。短钩尖记录、动态碰撞、极端角度/近表面规则仍可能有误差。后续优先用实际锚点和到达姿态重新出刀/校准，不把请求位置当作到达，也不从这120次推出击杀率。','',f'原件：`work/d3r/mapping-v1/`、`work/a6/d3-r-map-*/`。冻结参数`{a.parameters.relative_to(ROOT)}`；全量减缩`{a.sweep.relative_to(ROOT)}`。数值报告`{stem.with_suffix(".json").relative_to(ROOT)}`。不提交游戏资源、派生网格、截图或生成页。']
 lines+=['','分层核查：最终确认中，原候选墙面方向35/36判定正确（97.22%），原生绑定34/36；不指向预选墙面的方向只有6/12判定正确。7个假阳性包括近地面/擦地6例和KeepOut边界1例；冻结确认结果不事后重分类修饰。后续挂点模型只用实测墙面，不把近地面、边界或天花板外推成已验证规则。']
 stem.with_suffix('.md').write_text('\n'.join(lines)+'\n');print(str(stem))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--ray',type=Path,required=True);p.add_argument('--sweep',type=Path,required=True);p.add_argument('--parameters',type=Path,default=ROOT/'work/d3r/sweep-v1-frozen.json');a=p.parse_args();a.ray=a.ray.resolve();a.sweep=a.sweep.resolve();a.parameters=a.parameters.resolve();main(a)
