"""Source-safe measured D3-R execution controls, including failed experiments."""
import datetime,json,sys,math,re,subprocess
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.analyze_direction import sha,PAT
from tools.zipcaster_d3r.blade_field import BladeField
from rl.session import SAVE_HASH

def load(p):return json.loads((ROOT/p).read_text())
def ref(p):return dict(path=str(Path(p).relative_to(ROOT)),sha256=sha(p))
def first_projectile(d,after,kind):
 vt='5c76df0'if kind=='full'else'5c75510';minimum=.75 if kind=='full'else 2.7;seen=[]
 for line in (Path(d['session'])/'player-0/host.log').open(errors='replace'):
  m=PAT.search(line)
  if m and after<int(m[1])<=after+36 and m[4]==vt and m[2]=='setter_input':
   v=np.array(list(map(float,m[5].split(','))))
   if np.linalg.norm(v)>=minimum:seen.append(dict(frame=int(m[1]),object=m[3],velocity=v.tolist(),position=list(map(float,m[6].split(',')))))
 return seen[0]if seen else None

def main():
 full=load('work/d3r/blade-full-v2-analysis.json');light=load('work/d3r/blade-light-v2-analysis.json');gun=load('work/d3r/blade-gun-v2-analysis.json');assert len(full['shots'])==7 and len(light['shots'])==7 and len(gun['shots'])==6
 batch=load('work/d3r/passive-pilot-v3b/batch.json');pilots=[]
 for r in batch['results']:
  d=load(r['artifact']);assert d['control_eligible']and d['passed']and d['outcome']==dict(kill=True,attacker_down=False);events={e['event']:e['infos']for e in d['events']};assert events['before-R']['player_1']['hp']>.999 and events['charge-start']['player_1']['hp']>.999
  born=first_projectile(d,events['full-release']['player_0']['frame'],'full');assert born is not None
  pilots.append(dict(map=r['map'],artifact=ref(ROOT/r['artifact']),target_full_health_at_charge=True,kill=True,attacker_down=False,arrival_frame=events['arrival']['player_0']['frame'],release_frame=events['full-release']['player_0']['frame'],target_hp_before_light=events['light-input']['player_1']['hp'],full_projectile=born,full_muzzle_above_target=born['position'][1]-events['full-release']['player_1']['position'][1]))
 threats=[]
 for p in sorted((ROOT/'work/a6').glob('d3-r-reactive-*/result.json')):
  d=json.loads(p.read_text());assert d['threat_passed']and d['passed']and len(d['large_damage_edges'])>=2;threats.append(dict(artifact=ref(p),distance=float(np.linalg.norm(np.array(d['initial']['player_0']['position'])-d['initial']['player_1']['position'])),reaction_frames=18,first_visible_tick=next(h['t']for h in d['reactive_history']if h['visible']),first_fired_tick=next(h['t']for h in d['reactive_history']if h['fired']),damage_edges=d['large_damage_edges'],first_down_control_frame=d['history'][-1]['player_1']['frame']-d['initial']['player_1']['frame']))
 assert len(threats)==2
 p=next((ROOT/'work/a6').glob('d3-r-precharge-*/result.json'));d=json.loads(p.read_text());release=next(e['infos']['player_0']['frame']for e in d['events']if e['event']=='full-release');pre=dict(artifact=ref(p),full_light20_supported=False,full_projectile=first_projectile(d,release,'full'),light_projectile=first_projectile(d,release,'light'),kill=d['outcome']['kill'],meaning='ZR held in Attack3 and through B/20f after arrival acknowledgement still emitted light, not full. Does not prove all precharge variants impossible.');assert pre['full_projectile']is None and pre['light_projectile']is not None
 p=next((ROOT/'work/a6').glob('d3-r-ideal4-*/result.json'));d=json.loads(p.read_text());assert d['combo']=='light3'and d['speed_frames']==20 and d['outcome']['kill'];last=1.;edges=[]
 for line in p.with_name('steps.jsonl').open():
  row=json.loads(line);hp=row['infos']['player_1']['hp'];delta=(last-hp)*100
  if delta>25:edges.append(dict(frame=row['infos']['player_0']['frame'],damage_hp=delta))
  last=hp
 assert len(edges)==3
 light3=dict(artifact=ref(p),style='light3',first_attack_input_after_arrival_ack=20,cadence=30,damage_edges=edges,kill=True,nominal_damage=[35,35,35],last_damage_hp_capped_by_remaining_health=True)
 impacts=[]
 for name,origin,velocity,end in [('Yunohana',[-2.31253529,4.00787354,-5.85946465],[-3.53175473,.0322786756,-2.28489089],[-2.9998064,4.01167822,-6.00009155]),('Yagara',[-2.41019297,6.73057127,-2.7656672],[-3.87375093,-.626149416,-1.88935506],[-5.07397175,6,-4.06487942])]:
  field=BladeField(ROOT/f'work/arena/maps/{name}');hit=field.hit(origin,velocity,.3,15);assert hit is not None;error=float(np.linalg.norm(hit[1]-end));assert error<.001;impacts.append(dict(map=name,native_origin=origin,native_velocity=velocity,native_stop=end,predicted_contact=hit[1].tolist(),error_units=error,core_radius=.3,interpretation='Native stop coincides with static field sphere contact; no native hit-callback interception.'))
 for p,h in load('work/d3r/aim-v1/protected.json').items():assert sha(ROOT/p)==h
 for p,h in load('work/d2b/round2-world-build/provenance.json')['original_module_sha256'].items():assert sha(ROOT/p)==h
 for p in[ROOT/'work/save_ref/save.dat',ROOT.parent/'splatoon-rl-lab/saves/bis/user/save/0000000000000001/0/save.dat']:assert sha(p)==SAVE_HASH
 out=dict(schema='inklab.d3r.mechanics.v1',date=str(datetime.date.today()),full_d3r_passed=False,step3_scoped_controls_passed=True,rate_scope='local direct-aim ideal-operation fixture, not player win rate',flat_scans=dict(full=full,light=light,gun=gun),physical_birth_delay_frames=dict(full_after_charge_start=27,full_after_release=6,light_after_input=11,gun_after_input=2),passive_combo_controls=pilots,exact_reactive52_controls=threats,twenty_full_probe=pre,twenty_light3=light3,field_stop_checks=impacts,parameters=load('work/d3r/attack-parameters-v1.json'),source_sha256={str(p.relative_to(ROOT)):sha(p)for p in[Path(__file__),ROOT/'tools/zipcaster_d3r/duel_v3.py',ROOT/'tools/zipcaster_d3r/weapon_aim.py',ROOT/'tools/zipcaster_d3r/reactive_control.py',ROOT/'tools/zipcaster_d3r/blade_field.py',ROOT/'tools/zipcaster_d3r/native_kinematics.py']},limits=['Seven native pitch bins each sword, six singleton gun shots: finite grid/one flat layout, no continuous all-pose boundary.','Full70 from elevated B trajectories and grounded35 proved in three separated controls. Dedicated stationary upward/downward elevation grid not completed; final native cohort will retain actual heights.','B6 rise now~3.11u in two low-wall profiles; old2.10u curve was a different context. Not universal wall-jump physics.','20f full-light is unsupported by this measured precharge plan;20f heatmap uses separately validated light3 only. Frame band is arrival acknowledgement to first firing action (full release or light press), not projectile birth; sampled arrival can lag native transition by up to4f.','Initial full-flight stage substring bug selected light muzzle before full spawn. Retired scripts/raw evidence kept; explicit style regression tests and three-map v3 controls pass.','Initial neutral healing failed over hostile ink. V2 uses ordinary floor painting/refill, never HP writes; instant35/70/52 edges separated from slow ink chip.','Initial District control target was outside bravo graph component; hub alone did not fix it. New geometry-only control target is reachable; cohort samples reachable nodes before outcomes.','Core radii .3/.5 selected from sparse local Saber params; two light stops agree within.001u. Side-sphere, dynamic collision, long curved trajectory not certified.','Native rank calibration and page remain pending. No policy/default host/save changes, no T1/S1.'])
 stem=ROOT/'notes'/('d3r-mechanics-'+datetime.datetime.now().strftime('%Y%m%d'));stem.with_suffix('.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
 lines=[f'# D3-R：理想操作夹具与出刀实测（{datetime.date.today()}）','','直接瞄准仍只用于隔离的本地测量宿主；不改HP/位置/伤害，不用于正式arena/T1。以下是有限姿态证据，不是实战胜率。','', '| 测量 | 原生结果 |','|---|---|', '| 平地满蓄 | 7角度；native pitch −0.2/−0.1/0/0.1 单次70，−0.3/0.2/0.3无70；按21f持ZR |','| 平地轻斩 | 7角度；0/0.1 单次35，其余无35。慢性敌墨掉血单列 |','| .52 | 6角度；−0.16/−0.10/−0.04单发52，其余无52 |','| 原生弹体生成 | 满蓄开始+27f（释放+6）；轻斩输入+11；.52输入+2 |','| 三图落点70+35 | 3/3静止靶KO，水刀均存活；起蓄时靶100HP |','| 精确反应式.52威胁 | 两案均52→剩余血量归零；R18/有限转速/过滤观测，35f与70f倒下 |','| 20f满蓄预蓄试验 | 飞行中持ZR接B/20f释放，只生成轻斩；该方案unsupported，非所有方案不可能的证明 |','| 20f合法替代 | 到达确认后20f横斩输入，30f间隔三连，35+35+剩余30 KO |','', '角度是原生camera scalar，不等于世界仰角。两刀物理方向拟合约 `world_elevation=1.058686×native_pitch+0.002413`；.52六单发约 `1.279705×pitch+0.087019`，包含随机散布，不能当精确常数。固定站位粗采样不是连续命中边界。三图满蓄弹体出现在靶脚点上方数u，随后轻斩收尾；JSON保留实际高度、向量和HP。独立低打高/高打低完整网格未做，不填假结论。','', '弯角/台阶必须用弹体场地碰撞体积。两个旧失败轻斩的原生停止点，0.3u核心球扫掠复现误差均<0.001u；仅中心细射线会漏过。参数中轻斩core radius0.3、满蓄0.5；其余侧球、动态物体和远端弯曲尚未完整复制。可见性依旧使用原GeometricVision薄射线，不把武器体积混进视线判定。','', '夹具修正记录：`full-flight`包含`light`导致阶段误选枪口高度，改成显式刀种；三图重新通过。原地等待不能让敌墨中的靶满血，改正常涂地/回墨；没有直接写HP。District旧控制目标不在bravo连通分量，hub重试也失败，改用事前几何筛选且可达的控制目标；正式校准敌人站位按可达格预定。所有失败原件保留。','', '20/40/60/129档按「到达确认→发射动作（满蓄松键/轻斩按键）」定义，弹体生成延迟另加；到达传感有≤4f采样窗。20档只比较已测三连轻斩，40/60/129比较满蓄+轻斩和三轻斩。不得把20档原来未证实的满蓄热图继续显示为成立。','', '下一步：将B6新轨迹、11f轻斩生成和核心场地碰撞纳入新模型，重新分档；固定试次0/1训练、2留出。已用同一套Defender证明枪真的会命中，不能用不具威胁的脚本假成功。原宿主/模块/原存档SHA不变；不恢复T1/S1。', '',f'数值/原始SHA：`{stem.with_suffix(".json").relative_to(ROOT)}`。原件全部在work/a6与work/d3r，不提交游戏资源/派生网格/截图/生成页。']
 stem.with_suffix('.md').write_text('\n'.join(lines)+'\n');print(stem)
if __name__=='__main__':main()
