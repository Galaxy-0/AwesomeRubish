"""D4 enemy-conditioned4bit heat bank and closed native examples.

Only scalar grades/stealth are embedded; selected exact route/value is recomputed
locally with the same own worker. No ranked-start/old uniform-prior substitute.
"""
import base64,gzip,hashlib,json,zlib
from pathlib import Path
import numpy as np
from d3 import native_trace
from projectiles import augment
SPEEDS=[20,40,60,129]
def code(row):
 if not row.get('complete'):return 12
 if row.get('probability')==1:
  r=row['remaining'];return(7 if r>.3 else 6 if r>=.1 else 5)+(3 if row['stealth']else 0)
 return {'occupied':11,'unreachable-in-declared-graph':2,'dies-before-any-declared-route-can-move-or-kill':3,'no-winning-route-in-declared-model':4}.get(row['status'],12)
def compile_d4(root,source):
 states=json.loads(source('work/d4/all-enemy-states-v1.json').read_text());common=json.loads(source('work/d4/common-enemy-states-v2.json').read_text())['states'];maps=[];bindings={};counts={'complete':0,'unresolved':0,'missing':0};cache=root/'work/d4/browser';cache.mkdir(parents=True,exist_ok=True)
 for name in['Yunohana','District00','Yagara']:
  z=np.load(root/f'work/d4/graph-v2-{name}/graph.npz');ground=z['ground'];g=len(ground);values=np.zeros((g*16,g),np.uint8);seen=set();support=[r['ordinary_route_supported']for r in states['states']if r['map']==name]
  # The all-state bank overrides pilot common queries, never the reverse.
  files={p.name:p for bank in['common-full-v3','all-full-v3','all-full-v4']for p in(root/'work/d4'/bank).glob(name+'-*.json.gz')}
  for p in files.values():
   try:
    raw=p.read_bytes();d=json.loads(gzip.decompress(raw))
   except(EOFError,OSError,json.JSONDecodeError):continue # active immutable file not closed yet
   if not all(k in d for k in['enemy_index','heading','speed']):continue
   rowindex=d['enemy_index']*16+d['heading']*4+SPEEDS.index(d['speed']);q=d['result'];seen.add(rowindex);bindings[str(p.relative_to(root))]=hashlib.sha256(raw).hexdigest();counts['complete'if d['status']=='complete'else'unresolved']+=1
   for row in q.get('rows',[]):values[rowindex,row['start']]=code(row)
  counts['missing']+=g*16-len(seen);flat=values.ravel();packed=(flat[::2]|(np.r_[flat[1::2],np.zeros(len(flat)%2,np.uint8)]<<4));compressed=zlib.compress(packed.tobytes(),9);default=next(r['enemy_index']for r in common if r['map']==name and r['region']=='center');maps.append(dict(id=name,g=g,ground=ground.tolist(),ordinary_support=support,codes=base64.b64encode(compressed).decode(),codes_encoding='zlib-base64-4bit-low-first',complete_queries=sum(1 for i in seen if not np.any(values[i]==0)and not np.any(values[i]==12)),total_queries=g*16,default_enemy=default,bytes=len(compressed)))
 digest=hashlib.sha256(json.dumps(bindings,sort_keys=True).encode()).hexdigest();manifest=cache/f'heat-inputs-{digest[:16]}.json'
 if not manifest.exists():manifest.write_text(json.dumps(dict(inputs=bindings,compiler_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),scope='Closed gzipped numerical query results; raw game assets not included'),indent=2)+'\n')
 source(manifest);clips=[]
 examples=[('work/d4/pilot-native-v3/batch.json','Yunohana-fly-v3-top1','d4-native-hook','D4 原生 · 修正后飞索两刀'),('work/d4/pilot-native-v1/batch.json','Yunohana-pilot-ground','d4-native-ground','D4 原生 · 零钩背后两刀'),('work/d4/pilot-native-v1/batch.json','Yunohana-pilot-control','d4-native-counter','D4 原生 · 正面起机被反杀')]
 for b,point,cid,label in examples:
  batch=json.loads(source(b).read_text());r=next(x for x in batch['results']if x['point']==point);path=Path(r['artifact']);path=path if path.is_absolute()else root/path;run=json.loads(source(path).read_text());clip=native_trace(root,source,path.parent,cid,label);clip['map']=run['point']['graph'].split('-')[-1];clip['enemy_fov_degrees']=180;clip['enemy_fov_heading']=run['point']['heading']*np.pi/2;clip['ideal_operation_fixture']=True;clip['description']='D4原生直接瞄准夹具：固定世界方向180°逻辑视锥，敌人不主动移动、不转视锥，进入射程立即理想枪口瞄准。实际散布/伤害/击退保留。零钩基线、飞索路线与负对照分开；不是正式重复击杀率。';history=run['defender_history'];clip['logical_visibility']=[[h['frame'],h['visible'],h['in_range']]for h in history];seen=next((h['frame']for h in history if h['visible']),None);clip['first_seen_frame']=seen
  if seen is not None:clip['annotations'].append(dict(frame=seen,label='进入固定180°视锥且无遮挡',kind='seen',evidence='D4 fixed-half-plane GeometricVision fixture history'))
  augment(root,source,clip);clips.append(clip)
 report=root/'notes/d4-calibration-20261022.json';native=json.loads(source(report).read_text())if report.exists()else None
 data=dict(schema='showcase.d4.v1',validation_status='uncalibrated-projectile-only; near-contact140 missing; native counterexamples retained',maps=maps,speeds=SPEEDS,counts=counts,native=native,heat_codes={'unknown':0,'unreachable':2,'dies_before_move':3,'no_winning_route':4,'extreme':5,'normal':6,'stable':7,'stealth_extreme':8,'stealth_normal':9,'stealth_stable':10,'occupied':11,'unresolved':12},scope='敌情条件、理想瞄准上限；固定敌位/四向，无误差分布时P为0/1。自然槽归零前须实际击倒。底图静态可站候选包含未原生确认的孤立层，普通导航支持另标，不冒充所有点可站。',limits=['0–3钩含零钩近身基线；不能把其成功归给飞索切入。','未知/超时不显示为0；全图枚举完成度单列。','仅有限动作库/3u挂点图，不是连续空间完备证明。','满蓄/轻斩含枪口到生成点扫掠；B/飞行/高差仍为测量代理。','固定逻辑视锥内理想枪口跟瞄，100HP累积；用户未补充时沿用该声明解释。'])
 return data,clips
