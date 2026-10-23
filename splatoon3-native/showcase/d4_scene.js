/* Enemy-conditioned tactical board. Offline grades and local exact route query. */
const D4_WORKER_CODE=__D4_WORKER_CODE__;
let d4Enemy=0,d4Source=null,d4Heading=0,d4Speed=40,d4View='forward',d4PickRole='enemy',d4MapId=null,d4Route=null,d4Frame=0,d4Playing=false,d4Worker=null,d4Serial=0,d4Latest=0,d4Ready=null;
const d4Decoded=new Map(),d4Temporary=new Map(),d4Requests=new Map();
// A heat pass is a UI cache entry, not proof that every bounded search resolved.
const d4HeatCache=new Map(),d4RouteCache=new Map();
let d4Generation=0,d4InitReject=null,d4AutoTimer=null,d4AutoState=null,d4HeatJob=null,d4HeatStamp=null;
const d4Aborted=()=>Object.assign(new Error('已取消旧敌情计算'),{name:'AbortError'});
function d4CancelWork(){
 clearTimeout(d4AutoTimer);d4AutoTimer=null;d4Generation++;
 if(d4Requests.size||d4InitReject){d4Worker?.terminate();d4Worker=null;d4Ready=null;d4InitReject?.(d4Aborted());d4InitReject=null;for(const r of d4Requests.values())r.reject(d4Aborted());d4Requests.clear()}
 d4HeatJob=null;d4HeatStamp=null;
}
function d4ProgressUI(){
 const box=$('d4-progress');if(!box)return;
 const state=d4HeatJob||d4HeatStamp;box.hidden=!d4On()||!state;
 if(!state)return;
 const busy=state.busy,percent=state.total?Math.floor(100*state.done/state.total):0;
 const seconds=(busy?(performance.now()-state.started):state.elapsed)/1000;
 box.dataset.state=busy?'running':state.error?'error':'done';box.dataset.key=state.key;
 box.dataset.elapsedMs=String(Math.round(seconds*1000));box.dataset.firstResultMs=String(state.firstResult??'');box.dataset.firstWinMs=String(state.firstWin??'');box.dataset.ordinaryMs=String(state.ordinaryMs??'');
 $('d4-progress-text').textContent=busy?`正在计算该敌情的全图开大点… ${percent}%`:state.error?'该敌情计算中断，请重新计算':state.cached?'已从本次浏览缓存载入 · 无需等待':'该敌情全图计算已完成 · 热图已更新';
 $('d4-progress-meter').value=state.error?0:busy?percent:100;
 $('d4-progress-detail').textContent=busy?`${state.done}/${state.total} 格 · 普通可站点优先、结果逐块显示 · ${seconds.toFixed(1)}s`:state.error?state.error:`${state.done}/${state.total} 格 · ${state.cached?'原次计算 ':''}${seconds.toFixed(2)}s · 截断与限定外仍为未知`;
 box.setAttribute('aria-busy',String(!!busy));
}
function d4QueueAuto(){
 const state=d4On()?d4Key()+':'+d4View:'off';if(state===d4AutoState)return;
 d4AutoState=state;d4CancelWork();
 if(!d4On()||d4View!=='forward'){d4ProgressUI();return}
 const key=d4Key(),cached=d4HeatCache.get(key);
 if(cached?.finished){d4HeatStamp={...cached,key,busy:false,cached:true};$('d4-compute-status').textContent='已从本次浏览缓存载入';d4ProgressUI();return}
 if(DATA.d4_presentation?.rankings[key]?.complete){d4ProgressUI();return}
 const m=d4Map();d4HeatJob={key,busy:true,done:cached?.rows.filter(Boolean).length||0,total:m.g,started:performance.now()};
 d4ProgressUI();const generation=d4Generation;
 d4AutoTimer=setTimeout(()=>{d4AutoTimer=null;if(generation===d4Generation)d4ComputeHeat(false)},300);
}
setInterval(()=>{if(d4HeatJob)d4ProgressUI()},1000);

const d4On=()=>!!$('show-d4')?.checked;
const d4Map=()=>DATA.d4.maps.find(m=>m.id===currentMap().id);
const d4Key=()=>[currentMap().id,d4Enemy,d4Heading,d4Speed].join(':');
const d4Win=c=>c>=5&&c<=10;
const d4Stealth=c=>c>=8&&c<=10;
const d4Grade=c=>c>=8?c-3:c;
const d4Text=c=>({0:'未计算',2:'无预算内路线',3:'起步前被击倒',4:'未找到获胜路线',5:'极限 · 剩槽0–10%',6:'正常 · 剩槽10–30%',7:'稳 · 剩槽>30%',8:'极限 · 全程偷袭',9:'正常 · 全程偷袭',10:'稳 · 全程偷袭',11:'与敌人重叠',12:'计算未决',13:'限定外未知 · 非原生失败',14:'原生摆位集合外'}[c]||'未知');
const d4Color=c=>cssToken(c===3?'--d4-danger':d4Grade(c)===7?'--d4-stable':d4Grade(c)===6?'--d4-normal':d4Grade(c)===5?'--d4-extreme':c===0||c===12||c===13||c===14?'--d4-unknown':'--line');
// UI labels copy existing complete-query values; the numerical worker stays unchanged.
let d4PresentationKey=null,d4Ranks=[],d4VisualRevision=0;
const d4LocalRankings=new Map(),d4PinNumbers=['①','②','③'];
window.d4LayerOn=d4On;
function d4Ranking(){return DATA.d4_presentation?.rankings[d4Key()]||d4LocalRankings.get(d4Key())||null}
function d4ChooseRank(i){const p=d4Ranks[i];if(!p)return;d4Source=p.start;d4PickRole='source';d4QueryRoute()}
function d4SyncPresentation(){
 const key=d4Key()+':'+d4View+':'+d4VisualRevision;
 if(key===d4PresentationKey)return;
 d4PresentationKey=key;d4Ranks=d4View==='forward'?(d4Ranking()?.points||[]):[];
 if(d4View==='forward'){
  d4Source=d4Ranks[0]?.start??null;d4Route=null;d4Frame=0;d4Playing=false;
  if(d4Source!==null&&!d4HeatJob)queueMicrotask(()=>d4QueryRoute());
 }
}
function d4Brief(){
 const m=d4Map(),E=m.ground[d4Enemy],head=$('d4-headline'),list=$('d4-top-points');
 const heading=['↑ +Z','→ +X','↓ −Z','← −X'][d4Heading],state=`敌人在 (${E.map(v=>v.toFixed(1)).join(', ')}) 朝 ${heading}`;
 head.replaceChildren();list.replaceChildren();
 if(d4View==='inverse'){
  head.append(el('strong','',`反查开大点 ${d4Source??'待选'}：能处理哪些敌情`),el('small','','颜色按当前固定开大点读取；切换四向查看敌人的不同朝向。'));
  head.dataset.empty='false';return;
 }
 const first=d4Ranks[0],ranked=d4Ranking();head.dataset.empty=String(!first);
 if(first){
  head.append(el('strong','',`${state}：${ranked.complete?'最佳开大点':'已计算候选'}① #${first.start} · 剩槽 ${(first.remaining*100).toFixed(1)}% · ${first.stealth?'全程偷袭':'暴露 '+(first.exposure_frames??'待核')+' 帧'}`),el('small','',ranked.complete?'①②③沿用已有完整查询的普通可站集合排序；模型条件结果，不是原生玩家胜率。':'①②③为当前已计算候选；尚未穷尽，不作全图最优结论。'));
  d4Ranks.forEach((r,i)=>{const b=el('button');b.type='button';b.setAttribute('aria-label',`查看开大点${d4PinNumbers[i]}，编号${r.start}`);b.setAttribute('aria-pressed',String(d4Source===r.start));const name=el('span');name.append(el('b','',d4PinNumbers[i]),document.createTextNode('#'+r.start));b.append(name,el('small','',`${(r.remaining*100).toFixed(1)}% · ${r.stealth?'偷袭':'暴露'}`));b.onclick=()=>d4ChooseRank(i);list.append(b)});
 }else{
  const decoded=d4Decoded.get(m.id)instanceof Uint8Array;
  if(d4HeatJob){head.append(el('strong','',`${state}：正在寻找可确认开大点…`),el('small','','不用点按钮；普通可站点优先，①②③随结果出现。未知不表示不能杀。'));list.append(el('p','note','正在计算，候选点会自动显示。'));return}
  head.append(el('strong','',decoded?'该敌态在限定口径下无已确认击杀点':'正在载入该敌态热图…'),el('small','',`${state}。${decoded?'建议切换朝向；新敌态自动补算，未知和未计算不等于不能杀。':'未知保持虚框，不涂成失败。'}`));
  list.append(el('p','note','暂无可列出的①②③；试试其他朝向。'));
 }
}
function d4PinLayer(project,width,height){
 const layer=$('d4-pins');if(!d4On()){layer.hidden=true;return}layer.hidden=false;
 const signature=d4Key()+':'+d4View+':'+d4Ranks.map(r=>r.start).join(',');
 if(layer.dataset.signature!==signature){
  layer.dataset.signature=signature;layer.replaceChildren();
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('aria-hidden','true');layer.append(svg);
  d4Ranks.forEach((r,i)=>{const b=el('button','d4-map-pin',d4PinNumbers[i]);b.type='button';b.title=`开大点${d4PinNumbers[i]} · #${r.start} · ${(r.remaining*100).toFixed(1)}%`;b.setAttribute('aria-label',b.title);for(const type of['pointerdown','pointerup'])b.addEventListener(type,e=>e.stopPropagation());b.onclick=e=>{e.stopPropagation();d4ChooseRank(i)};layer.append(b)});
  const enemy=el('div','d4-enemy-pin');enemy.setAttribute('aria-label','敌人，朝向见红色箭头');enemy.innerHTML='<svg viewBox="0 0 20 30" aria-hidden="true"><circle cx="10" cy="5" r="3" fill="currentColor"/><path d="M10 11v9m-6-4 6-5 6 5m-10 12 4-8 4 8" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>';layer.append(enemy);
 }
 const svg=layer.querySelector(':scope > svg');svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.replaceChildren();
 // Keep the fixed 180-degree sight boundary legible above opaque heat cells.
 const enemyPosition=d4Route?.enemy_path?.[Math.round(d4Frame)]||d4Map().ground[d4Enemy],facing=d4Heading*Math.PI/2;
 const arc=Array.from({length:49},(_,i)=>project([enemyPosition[0]+30*Math.sin(facing-Math.PI/2+i/48*Math.PI),enemyPosition[1]+.4,enemyPosition[2]+30*Math.cos(facing-Math.PI/2+i/48*Math.PI)]));
 const center=project(enemyPosition),tip=project([enemyPosition[0]+Math.sin(facing)*9,enemyPosition[1],enemyPosition[2]+Math.cos(facing)*9]);
 const sight=document.createElementNS('http://www.w3.org/2000/svg','polyline');sight.setAttribute('points',[center,...arc,center].map(p=>p.join(',')).join(' '));sight.setAttribute('fill','none');sight.setAttribute('stroke',cssToken('--d4-enemy'));sight.setAttribute('stroke-width','1.8');sight.setAttribute('opacity','.85');svg.append(sight);
 const angle=Math.atan2(tip[1]-center[1],tip[0]-center[0]),arrowPoints=[center,tip,[tip[0]-9*Math.cos(angle-.5),tip[1]-9*Math.sin(angle-.5)],tip,[tip[0]-9*Math.cos(angle+.5),tip[1]-9*Math.sin(angle+.5)]];
 const arrow=document.createElementNS('http://www.w3.org/2000/svg','polyline');arrow.setAttribute('points',arrowPoints.map(p=>p.join(',')).join(' '));arrow.setAttribute('fill','none');arrow.setAttribute('stroke',cssToken('--d4-enemy'));arrow.setAttribute('stroke-width','3');svg.append(arrow);
 if(d4Route?.probability===1&&d4Route.path?.length){
  const r=d4Route;let segment=[];
  const stroke=(positions,color,dashed=false)=>{if(positions.length<2)return;const points=positions.map(p=>project(p).map(v=>v.toFixed(2)).join(',')).join(' ');for(const[c,width]of[['#ffffff',5],[color,2.6]]){const line=document.createElementNS('http://www.w3.org/2000/svg','polyline');line.setAttribute('points',points);line.setAttribute('fill','none');line.setAttribute('stroke',c);line.setAttribute('stroke-width',width);line.setAttribute('stroke-linejoin','round');if(dashed)line.setAttribute('stroke-dasharray','5 4');svg.append(line)}};
  for(let i=0;i<r.path.length;i++){segment.push(r.path[i]);if(i===r.path.length-1||i>0&&r.visible[i]!==r.visible[i-1]){stroke(segment,cssToken(r.visible[Math.max(0,i-1)]?'--d4-danger':'--d4-stable'));segment=[segment.at(-1)]}}
  stroke([r.path.at(-1),r.enemy_path?.at(-1)||d4Map().ground[d4Enemy]],cssToken('--accent'),true);
 }
 const occupied=[],points=layer.querySelectorAll('.d4-map-pin');
 d4Ranks.forEach((r,i)=>{
  const [x,y]=project(d4Map().ground[r.start]),b=points[i];if(!Number.isFinite(x)||x<0||x>width||y<0||y>height){b.hidden=true;return}b.hidden=false;
  let px=x,py=y-12;
  for(const [dx,dy]of [[0,-16],[-38,-16],[38,-16],[0,-66],[-42,-66],[42,-66],[-75,-28],[75,-28]]){
   px=Math.max(24,Math.min(width-24,x+dx));py=Math.max(118,Math.min(height-147,y+dy));
   if(!occupied.some(q=>Math.abs(q[0]-px)<39&&Math.abs(q[1]-py)<43))break;
  }
  occupied.push([px,py]);b.style.left=px+'px';b.style.top=py+'px';b.setAttribute('aria-pressed',String(d4Source===r.start));
  for(const[color,stroke]of[['#ffffff',4],['#166344',1.6]]){const line=document.createElementNS('http://www.w3.org/2000/svg','path');line.setAttribute('d',`M${px},${py-3}L${x},${y}`);line.setAttribute('stroke',color);line.setAttribute('stroke-width',stroke);line.setAttribute('fill','none');svg.append(line)}
 });
 const t=Math.round(d4Frame),E=d4Route?.enemy_path?.[t]||d4Map().ground[d4Enemy],[ex,ey]=project(E),enemy=layer.querySelector('.d4-enemy-pin');enemy.style.left=ex+'px';enemy.style.top=ey+'px';enemy.hidden=!Number.isFinite(ex)||ex<0||ex>width||ey<0||ey>height;
}
function d4ProjectPins(scene){if(!d4On()||$('scene').hidden)return;const host=$('scene');d4PinLayer(p=>{const v=new THREE.Vector3(...p).add(new THREE.Vector3(0,.8,0)).project(scene.camera);return[(v.x*.5+.5)*host.clientWidth,(-v.y*.5+.5)*host.clientHeight]},host.clientWidth,host.clientHeight)}
async function d4Unpack(text){const raw=Uint8Array.from(atob(text),c=>c.charCodeAt(0));return new Uint8Array(await new Response(new Blob([raw]).stream().pipeThrough(new DecompressionStream('deflate'))).arrayBuffer())}
function d4Codes(m){if(!d4Decoded.has(m.id))d4Decoded.set(m.id,d4Unpack(m.codes).then(a=>{d4Decoded.set(m.id,a);drawMap();return a}));return d4Decoded.get(m.id)}
function d4Code(enemy,start,heading=d4Heading,speed=d4Speed){const m=d4Map(),temporary=d4Temporary.get([m.id,enemy,heading,speed].join(':'));if(temporary&&temporary[start]!==undefined)return temporary[start];const data=d4Codes(m);if(!(data instanceof Uint8Array))return 0;const index=((enemy*16+heading*4+DATA.d4.speeds.indexOf(speed))*m.g+start),byte=data[index>>1];return index&1?byte>>4:byte&15}
function d4Reset(){const m=d4Map();if(d4MapId===m.id)return;d4CancelWork();d4MapId=m.id;d4Heading=m.default_heading??0;d4Enemy=m.default_enemy;d4Source=null;d4Route=null;d4Playing=false;d4Frame=0;d4PresentationKey=null;const options=m.ground.map((p,i)=>{const o=el('option','',`${i} · X${p[0].toFixed(1)} Y${p[1].toFixed(1)} Z${p[2].toFixed(1)}${m.ordinary_support[i]?'':' · 层位待确认'}`);o.value=i;return o});$('d4-enemy').replaceChildren(...options);$('d4-source').max=m.g-1;$('d4-source').value='';d4Codes(m)}
function d4InitializeWorker(){
 if(d4Ready)return d4Ready;
 d4Ready=new Promise((resolve,reject)=>{d4InitReject=reject;
  try{
   const url=URL.createObjectURL(new Blob([D4_WORKER_CODE],{type:'text/javascript'}));
   const worker=d4Worker=new Worker(url);URL.revokeObjectURL(url);
   worker.onerror=e=>{if(worker!==d4Worker)return;d4InitReject=null;reject(Error(e.message));for(const r of d4Requests.values())r.reject(Error(e.message));d4Requests.clear();worker.terminate();d4Worker=null;d4Ready=null};
   worker.onmessage=e=>{
    if(worker!==d4Worker)return;const m=e.data;
    if(m.type==='ready'){d4InitReject=null;resolve();return}
    const request=d4Requests.get(m.id);if(!request)return;
    if(m.type==='progress'){
     if(request.progress)request.progress(m);
     else if(m.id===d4Latest)$('d4-compute-status').textContent=m.total?`本地计算 ${m.done}/${m.total} 个敌位…`:`路线搜索 ${m.done.toLocaleString()} 步…`;
     return;
    }
    d4Requests.delete(m.id);m.type==='error'||m.type==='cancelled'?request.reject(m.type==='cancelled'?d4Aborted():Error(m.error)):request.resolve(m);
   };
   worker.postMessage({type:'init',id:0,runtime:DATA.d4_runtime});
  }catch(e){d4InitReject=null;reject(e)}
 });return d4Ready;
}
async function d4Call(type,extra={},progress=null){
 const generation=d4Generation,requestData={type,map:currentMap().id,enemy:d4Enemy,heading:d4Heading,speed:d4Speed,...extra};
 await d4InitializeWorker();if(generation!==d4Generation)throw d4Aborted();
 const id=++d4Serial;d4Latest=id;
 return new Promise((resolve,reject)=>{d4Requests.set(id,{resolve,reject,type,progress});d4Worker.postMessage({...requestData,id})});
}
async function d4QueryRoute(){
 d4Route=null;d4Playing=false;d4Frame=0;
 if(d4Source===null||!d4On()){drawMap();return}
 // A route message would cancel the heat pass in the single-worker dispatcher.
 // Keep the selected pin while heat is running, then rebuild it on completion.
 if(d4HeatJob){$('d4-compute-status').textContent='热图逐块更新中；完成后自动重建所选路线。';drawMap();return}
 const key=[d4Key(),d4Source].join(':'),generation=d4Generation;
 if(d4RouteCache.has(key)){d4Route=d4RouteCache.get(key);d4RouteUI();drawMap();return}
 drawMap();$('d4-compute-status').textContent='本地重建这条路线…';
 try{
  const response=await d4Call('route',{start:d4Source});
  if(generation!==d4Generation||key!==[d4Key(),d4Source].join(':')||!d4On())return;
  d4Route=response.result;d4RouteCache.set(key,d4Route);
  if(d4Route.probability===1&&!d4Ranking()){const point={...d4Route,start:d4Source,position:d4Map().ground[d4Source]};d4LocalRankings.set(d4Key(),{complete:false,points:[point]});d4Ranks=[point]}
  $('d4-compute-status').textContent=d4Route.complete?'路线计算完成 · 理想操作模型':'路线搜索未决，不能当不可达';d4RouteUI();drawMap();
 }catch(e){if(e.name!=='AbortError'&&generation===d4Generation&&key===[d4Key(),d4Source].join(':'))$('d4-compute-status').textContent='本地计算不可用：'+e.message}
}
const d4RowCode=r=>!r.complete?12:r.probability===1?(r.remaining>.3?7:r.remaining>=.1?6:5)+(r.stealth?3:0):({occupied:11,'unreachable-in-declared-graph':2,'dies-before-any-declared-route-can-move-or-kill':3,'no-winning-route-in-declared-model':4,'no-contact-excluded-route; unrestricted-kill-unknown':13,'excluded-from-native-setup-domain':14}[r.status]||12);
function d4ApplyHeatRows(key,m,rows){
 const cached=d4HeatCache.get(key),codes=d4Temporary.get(key)||[];
 for(const row of rows){cached.rows[row.start]=row;codes[row.start]=d4RowCode(row)}d4Temporary.set(key,codes);
 const points=cached.rows.filter(r=>r?.complete&&r.probability===1&&m.ordinary_support[r.start]).sort((a,b)=>b.remaining-a.remaining||a.start-b.start).slice(0,3).map(r=>({...r,position:m.ground[r.start]}));
 const previous=d4LocalRankings.get(key)?.points||[];
 d4LocalRankings.set(key,{complete:false,points});
 if(points.map(r=>r.start).join(',')!==previous.map(r=>r.start).join(','))d4VisualRevision++;
}
async function d4ComputeHeat(force=true){
 const key=d4Key(),inverse=d4View==='inverse',start=d4Source,m=d4Map(),map=m.id,heading=d4Heading,speed=d4Speed;
 if(inverse&&start===null){$('d4-compute-status').textContent='先选一个开大点，再反查敌人状态。';return}
 // Cancel synchronously, including a worker inside one expensive geometry query.
 if(force)d4CancelWork();
 const generation=d4Generation,started=!force&&d4HeatJob?.key===key?d4HeatJob.started:performance.now();
 if(!inverse){
  if(force)d4HeatCache.delete(key);
  const cached=d4HeatCache.get(key)||{rows:[],finished:false};d4HeatCache.set(key,cached);
  d4HeatJob={key,busy:true,done:cached.rows.filter(Boolean).length,total:m.g,started,firstResult:null};d4ProgressUI();
 }
 $('d4-compute-status').textContent=inverse?'逐敌位反查此开大点；切换查询可中止…':'普通可站点优先，正在逐块更新热图…';
 const valid=()=>generation===d4Generation&&key===d4Key()&&d4On()&&(inverse?d4View==='inverse':d4View==='forward');
 try{
  const response=await d4Call(inverse?'inverse':'heat',inverse?{start}:{ordinary:m.ordinary_support,initialRows:d4HeatCache.get(key).rows.filter(Boolean)},inverse?null:progress=>{
   if(!valid())return;
   const job=d4HeatJob;job.done=progress.done;job.firstResult??=progress.rows?.length?performance.now()-started:null;
   if(progress.rows?.some(r=>r.complete&&r.probability===1))job.firstWin??=performance.now()-started;
   if(progress.ordinary_done)job.ordinaryMs??=performance.now()-started;
   if(progress.rows?.length){d4ApplyHeatRows(key,m,progress.rows);drawMap()}
   d4ProgressUI();
  });
  if(!valid())return;
  if(inverse){for(const row of response.rows){const k=[map,row.enemy,heading,speed].join(':'),codes=d4Temporary.get(k)||[];codes[start]=d4RowCode(row);d4Temporary.set(k,codes)}}
  else{
   const job=d4HeatJob;d4ApplyHeatRows(key,m,response.rows);
   const cached=d4HeatCache.get(key);Object.assign(cached,{finished:true,done:m.g,total:m.g,elapsed:performance.now()-started,firstResult:job.firstResult,firstWin:job.firstWin,ordinaryMs:job.ordinaryMs});
   d4HeatJob=null;d4HeatStamp={...cached,key,busy:false};d4PresentationKey=null;
  }
  $('d4-compute-status').textContent='本地限定热图已更新；预算截断与限定外仍标未知';d4ProgressUI();drawMap();
 }catch(e){if(valid()&&e.name!=='AbortError'){d4HeatJob=null;d4HeatStamp={key,busy:false,error:e.message,elapsed:performance.now()-started};d4ProgressUI();$('d4-compute-status').textContent=e.message;drawMap()}}
}
function d4UpdateUI(){d4Reset();d4QueueAuto();d4ProgressUI();const on=d4On(),m=d4Map();$('d4-panel').hidden=!on;document.querySelector('.inspector').classList.toggle('d4-active',on);document.querySelector('.map-content').classList.toggle('d4-mode',on);$('d4-headline').hidden=!on;$('d4-map-key').hidden=!on;$('d4-pins').hidden=!on;if(!on){$('map-subtitle').textContent=`简化碰撞图 · ${currentMap().visibility.length} 个视域采样`;return}d4SyncPresentation();d4Brief();$('map-subtitle').textContent='中性高度底图 · 颜色仅表示开大结果';$('d4-enemy').value=d4Enemy;if(document.activeElement!==$('d4-source'))$('d4-source').value=d4Source??'';$('d4-speed').value=d4Speed;$('d4-view').value=d4View;$('d4-compute').textContent=d4View==='inverse'?'重新计算此点敌情':'重新计算';document.querySelectorAll('[data-d4-heading]').forEach(b=>b.setAttribute('aria-pressed',Number(b.dataset.d4Heading)===d4Heading?'true':'false'));document.querySelectorAll('[data-d4-pick]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.d4Pick===d4PickRole?'true':'false'));const enemy=m.ground[d4Enemy];$('d4-state-line').textContent=`敌 ${d4Enemy} · ${enemy.map(v=>v.toFixed(1)).join(' / ')} · ${d4Heading*90}° · ${d4Speed}f`;let win=0,stealth=0,unknown=0;if(d4View==='forward')for(let s=0;s<m.g;s++){const c=d4Code(d4Enemy,s);win+=d4Win(c);stealth+=d4Stealth(c);unknown+=c===0||c===12||c===13||c===14}else if(d4Source!==null)for(let e=0;e<m.g;e++){const c=d4Code(e,d4Source);win+=d4Win(c);stealth+=d4Stealth(c);unknown+=c===0||c===12||c===13||c===14}$('d4-layer-summary').textContent=`${win} 格模型可击杀 · ${stealth} 格全程偷袭 · ${unknown} 格未定`;$('d4-support-note').textContent=m.ordinary_support[d4Enemy]?'敌位有普通导航图支持，仍以原生专项验证为准。':'该高度层只有几何候选，可能孤立或位于封闭物体内；不当作已确认可站。';$('d4-coverage').textContent=`离线 ${m.complete_queries.toLocaleString()}/${m.total_queries.toLocaleString()} 敌情×手速查询 · 全图${m.g}个候选开大点`;d4RouteUI()}
function d4Gauge(t,r){const c=DATA.d4_runtime.config;let spent=Math.max(0,t-c.activation_drain_grace)*c.drain;for(const e of r.route_events||[])if(e.event==='出钩'&&t>=e.frame)spent+=c.hook_cost;for(const[event,kind]of r.inputs||[]){const f=r.arrival+event;if(kind==='light'&&t>=f)spent+=c.light_cost;if(kind==='full')spent+=c.full_cost*Math.max(0,Math.min(1,(t-(f-21))/21))}return Math.max(0,1-spent)}
function d4RouteUI(){const box=$('d4-route-detail');box.replaceChildren();const r=d4Route;if(d4Source===null){box.append(el('p','','先选敌人和朝向，再点地面选开大点。也可以反查一个开大点能处理哪些敌情。'));$('d4-playback').hidden=true;return}const m=d4Map(),p=m.ground[d4Source],c=d4Code(d4Enemy,d4Source);box.append(el('strong','',`开大点 ${d4Source} · ${p.map(x=>x.toFixed(1)).join(' / ')}`),el('p','',d4Text(c)));if(!m.ordinary_support[d4Source])box.append(el('p','d3-caveat','此层无普通导航图支持。几何模型可能给出路线，但不能宣称原生可站。'));if(!r){box.append(el('p','note','点选后在本机重建精确模型路线；颜色只表示当前敌情下的预测。'));$('d4-playback').hidden=true;return}if(r.probability!==1){box.append(el('p','','本次重建：'+d4Text(({occupied:11,'unreachable-in-declared-graph':2,'dies-before-any-declared-route-can-move-or-kill':3,'no-winning-route-in-declared-model':4,'no-contact-excluded-route; unrestricted-kill-unknown':13,'excluded-from-native-setup-domain':14,unresolved:12})[r.status]||12)));$('d4-playback').hidden=true;return}const dl=el('dl');for(const[k,v]of[['理想模型 P(kill)','1（确定性条件模型）'],['击倒后剩槽',(r.remaining*100).toFixed(2)+'%'],['路线',r.hooks.length?r.hooks.length+'钩':'零钩 · 已在出刀距离内'],['连招',({'full-light':'满蓄70＋轻斩35',light3:'三连轻斩','light-full':'轻斩＋满蓄','full2':'两次满蓄'})[r.program]],['暴露',r.exposure_frames+'f · '+(r.stealth?'全程偷袭':'曾被看见')],['开大→击倒',r.enemy_down+'f / '+(r.enemy_down/60).toFixed(2)+'s']]){const row=el('div');row.append(el('dt','',k),el('dd','mono',v));dl.append(row)}box.append(dl);if(!r.program_native_verified)box.append(el('p','d3-caveat','此为本点模型路线；原生零钩资格/重复另列，不能外推连钩与每个几何点。'));const list=el('ol','d4-steps');for(const e of r.events||[])list.append(el('li','',`F${e.frame} · ${e.event}`));box.append(list);$('d4-playback').hidden=false;$('d4-time').max=r.enemy_down;$('d4-time').value=Math.min(d4Frame,r.enemy_down);const width=260,height=74,points=Array.from({length:r.enemy_down+1},(_,t)=>`${8+t/r.enemy_down*(width-16)},${height-8-d4Gauge(t,r)*(height-16)}`).join(' ');$('d4-gauge').innerHTML=`<line x1="8" y1="8" x2="8" y2="66" class="axis"/><line x1="8" y1="66" x2="252" y2="66" class="axis"/><polyline fill="none" stroke="var(--accent)" stroke-width="2" points="${points}"/><text x="12" y="13">100%</text><text x="12" y="63">0</text>`;d4PlaybackStamp()}
function d4PlaybackStamp(){if(!d4Route?.path)return;$('d4-time').value=d4Frame;$('d4-play').textContent=d4Playing?'暂停':'播放';$('d4-stamp').textContent=`F${Math.round(d4Frame)} / ${(d4Frame/60).toFixed(2)}s · 槽${(100*d4Gauge(d4Frame,d4Route)).toFixed(1)}%`;const t=Math.round(d4Frame),step=[...(d4Route.events||[])].reverse().find(e=>e.frame<=t);$('d4-step').textContent=(step?.event||'开大准备')+(d4Route.visible[t]?' · 已进入敌方视野':' · 敌人看不见')}
function d4EnemyChanged(){d4AutoState=null;d4QueueAuto();d4Route=null;d4Frame=0;d4Playing=false;d4PresentationKey=null;if(d4View==='inverse'&&d4Source!==null)d4QueryRoute();else drawMap()}
function d4Pick(index){if(!d4On())return;if(d4PickRole==='enemy'){d4Enemy=index;d4EnemyChanged()}else{d4Source=index;d4QueryRoute()}}
function d4PickPosition(p){const m=d4Map();let best=0,cost=Infinity;for(let i=0;i<m.g;i++){const q=m.ground[i],d=(p.x-q[0])**2+4*(p.y-q[1])**2+(p.z-q[2])**2;if(d<cost){cost=d;best=i}}d4Pick(best)}
function refreshD4(scene){
 d4UpdateUI();scene.d4HeatMeshes=[];scene.d4Actors=null;if(!d4On())return;
 const m=d4Map();let records=[];
 if(d4View==='forward')records=m.ground.map((p,i)=>({p,i,c:d4Code(d4Enemy,i)}));
 else if(d4Source!==null)records=m.ground.map((p,i)=>({p,i,c:d4Code(i,d4Source)}));
 records=records.filter(r=>m.ordinary_support[r.i]||$('d4-unsupported').checked);
 const cells=records.filter(r=>d4Win(r.c)||r.c===3);
 if(cells.length){
  const mesh=new THREE.InstancedMesh(new THREE.PlaneGeometry(2.7,2.7),new THREE.MeshBasicMaterial({opacity:.96,transparent:true,side:THREE.DoubleSide,depthWrite:false,depthTest:false}),cells.length),dummy=new THREE.Object3D();
  cells.forEach((r,j)=>{dummy.position.set(r.p[0],r.p[1]+.2,r.p[2]);dummy.rotation.x=-Math.PI/2;dummy.updateMatrix();mesh.setMatrixAt(j,dummy.matrix);mesh.setColorAt(j,new THREE.Color(d4Color(r.c)))});
  mesh.renderOrder=13;mesh.userData.d4Ids=cells.map(c=>c.i);scene.overlay.add(mesh);scene.d4HeatMeshes.push(mesh);
 }
 // No fill for unreachable/no-winning-route; unknown has a distinct dashed frame.
 const borders=[];
 for(const r of records.filter(r=>[0,12,13,14].includes(r.c))){const[x,y,z]=r.p,h=1.16;for(const[a,b,c,d]of[[-h,-h,h,-h],[h,-h,h,h],[h,h,-h,h],[-h,h,-h,-h]])borders.push(x+a,y+.28,z+b,x+c,y+.28,z+d)}
 if(borders.length){const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(borders,3));const frame=new THREE.LineSegments(g,new THREE.LineDashedMaterial({color:cssToken('--d4-unknown'),transparent:true,opacity:.58,dashSize:.55,gapSize:.4,depthTest:false,depthWrite:false}));frame.computeLineDistances();frame.renderOrder=14;scene.overlay.add(frame)}
 const stealth=records.filter(r=>d4Stealth(r.c));
 if(stealth.length){const mesh=new THREE.InstancedMesh(new THREE.CircleGeometry(.48,8),new THREE.MeshBasicMaterial({color:'#ffffff',transparent:true,opacity:1,side:THREE.DoubleSide,depthTest:false,depthWrite:false}),stealth.length),dummy=new THREE.Object3D();stealth.forEach((r,i)=>{dummy.position.set(r.p[0],r.p[1]+.32,r.p[2]);dummy.rotation.x=-Math.PI/2;dummy.updateMatrix();mesh.setMatrixAt(i,dummy.matrix)});mesh.renderOrder=15;scene.overlay.add(mesh)}
 const E=m.ground[d4Enemy],fan=[],arc=[new THREE.Vector3(E[0],E[1]+.36,E[2])];
 for(let i=0;i<=48;i++){const a=d4Heading*Math.PI/2-Math.PI/2+i/48*Math.PI,p=[E[0]+30*Math.sin(a),E[1]+.36,E[2]+30*Math.cos(a)];arc.push(new THREE.Vector3(...p));if(i<48){const b=a+Math.PI/48;fan.push(E[0],E[1]+.36,E[2],...p,E[0]+30*Math.sin(b),E[1]+.36,E[2]+30*Math.cos(b))}}arc.push(new THREE.Vector3(E[0],E[1]+.36,E[2]));
 const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(fan,3));
 const cone=new THREE.Mesh(geo,new THREE.MeshBasicMaterial({color:cssToken('--d4-enemy'),opacity:.12,transparent:true,side:THREE.DoubleSide,depthWrite:false,depthTest:false}));cone.renderOrder=9;scene.overlay.add(cone);
 const boundary=scene.line(arc,cssToken('--d4-enemy'));boundary.material.depthTest=false;boundary.material.opacity=.75;boundary.renderOrder=16;cone.add(boundary);
 const enemy=new THREE.Mesh(new THREE.CapsuleGeometry(.7,1.2,4,8),new THREE.MeshBasicMaterial({color:cssToken('--d4-enemy'),transparent:true,depthTest:false,depthWrite:false}));enemy.position.set(E[0],E[1]+1.2,E[2]);enemy.renderOrder=21;scene.overlay.add(enemy);
 const ering=scene.ring(E,2.1,cssToken('--d4-enemy'));ering.material.depthTest=false;ering.renderOrder=22;scene.overlay.add(ering);
 const arrow=new THREE.Mesh(new THREE.ConeGeometry(1.15,3.4,3),new THREE.MeshBasicMaterial({color:cssToken('--d4-enemy'),transparent:true,depthTest:false,depthWrite:false}));arrow.rotation.order='YXZ';arrow.rotation.x=Math.PI/2;arrow.rotation.y=d4Heading*Math.PI/2;arrow.position.set(E[0]+Math.sin(d4Heading*Math.PI/2)*5,E[1]+.7,E[2]+Math.cos(d4Heading*Math.PI/2)*5);arrow.renderOrder=23;scene.overlay.add(arrow);
 if(d4Source!==null){const ring=scene.ring(m.ground[d4Source],1.5,'#ffffff');ring.material.depthTest=false;ring.renderOrder=20;scene.overlay.add(ring)}
 if(d4Route?.path&&d4Route.probability===1){const r=d4Route;let segment=[];for(let i=0;i<r.path.length;i++){const p=r.path[i];segment.push(new THREE.Vector3(p[0],p[1]+.6,p[2]));if(i===r.path.length-1||i>0&&r.visible[i]!==r.visible[i-1]){if(segment.length>1){const line=scene.line(segment,cssToken(r.visible[Math.max(0,i-1)]?'--d4-danger':'--d4-stable'),2);line.material.depthTest=false;line.renderOrder=18;scene.overlay.add(line)}segment=[segment.at(-1)]}}
  const actor=new THREE.Mesh(new THREE.CapsuleGeometry(.6,1.1,4,8),new THREE.MeshBasicMaterial({color:cssToken('--d4-stable'),transparent:true,depthTest:false,depthWrite:false}));actor.renderOrder=22;scene.overlay.add(actor);scene.d4Actors={actor,enemy,cone,arrow,ering,enemyOrigin:E};updateD4Frame(scene);
 }
}
function updateD4Frame(scene){if(!d4On()||!scene.d4Actors||!d4Route?.path)return;const r=d4Route,t=clampD4(Math.round(d4Frame),0,r.path.length-1),p=r.path[t],actor=scene.d4Actors.actor;actor.position.set(p[0],p[1]+1.15,p[2]);actor.material.color.set(cssToken(r.visible[t]?'--d4-danger':'--d4-stable'));const ep=r.enemy_path?.[t];if(ep){const a=scene.d4Actors,o=a.enemyOrigin,delta=ep.map((v,k)=>v-o[k]);a.enemy.position.set(ep[0],ep[1]+1.2,ep[2]);a.cone.position.set(...delta);a.ering.position.set(...delta);a.arrow.position.set(ep[0]+Math.sin(d4Heading*Math.PI/2)*5,ep[1]+.7,ep[2]+Math.cos(d4Heading*Math.PI/2)*5)}if(scene.preset==='follow'){scene.target.set(p[0],p[1]+2,p[2]);scene.radius=70}}
const clampD4=(x,a,b)=>Math.max(a,Math.min(b,x));
function d4Tick(dt){if(d4On()&&d4Playing&&d4Route?.path&&document.visibilityState==='visible'){const slow=(d4Route.events||[]).some(e=>Math.abs(d4Frame-e.frame)<10)?.35:1;d4Frame=Math.min(d4Route.enemy_down,d4Frame+dt*60*Number($('d4-play-speed').value)*slow);if(d4Frame>=d4Route.enemy_down)d4Playing=false}if(d4On()&&d4Route?.path)d4PlaybackStamp()}
function d4ApplySource(){const value=$('d4-source').value.trim();if(value===''){d4Source=null;d4Route=null;drawMap();return}const n=Number(value);if(Number.isInteger(n)&&n>=0&&n<d4Map().g){d4Source=n;d4QueryRoute()}}
function bindD4(){if(!DATA.d4)return;$('show-d4').onchange=()=>{if(d4On()){$('show-d3').checked=false;$('show-zip').checked=false;playing=false;d4PickRole='enemy';d4PresentationKey=null}else d4Playing=false;drawMap()};$('show-d3').addEventListener('change',()=>{if($('show-d3').checked){$('show-d4').checked=false;d4Playing=false;drawMap()}});$('show-zip').addEventListener('change',()=>{if($('show-zip').checked){$('show-d4').checked=false;d4Playing=false;drawMap()}});$('d4-enemy').onchange=()=>{d4Enemy=Number($('d4-enemy').value);d4EnemyChanged()};$('d4-source').onchange=d4ApplySource;$('d4-source-go').onclick=d4ApplySource;$('d4-source').onkeydown=e=>{if(e.key==='Enter')d4ApplySource()};for(const b of document.querySelectorAll('[data-d4-heading]'))b.onclick=()=>{d4Heading=Number(b.dataset.d4Heading);d4EnemyChanged()};for(const b of document.querySelectorAll('[data-d4-pick]'))b.onclick=()=>{d4PickRole=b.dataset.d4Pick;drawMap()};$('d4-speed').onchange=()=>{d4Speed=Number($('d4-speed').value);d4EnemyChanged()};$('d4-view').onchange=()=>{d4CancelWork();d4View=$('d4-view').value;d4PickRole=d4View==='inverse'?'source':'enemy';drawMap()};$('d4-compute').onclick=()=>d4ComputeHeat(true);$('d4-unsupported').onchange=()=>drawMap();$('d4-example').onclick=()=>{const m=d4Map(),E=m.ground[d4Enemy];let best=null,cost=Infinity;for(let i=0;i<m.g;i++){const c=d4Code(d4Enemy,i),p=m.ground[i],d=Math.hypot(...p.map((v,j)=>v-E[j]));if(d4Win(c)&&m.ordinary_support[i]&&d<cost){best=i;cost=d}}if(best!==null){d4Source=best;d4PickRole='source';d4QueryRoute()}};$('d4-play').onclick=()=>{if(d4Frame>=d4Route.enemy_down)d4Frame=0;d4Playing=!d4Playing};$('d4-time').oninput=()=>{d4Frame=Number($('d4-time').value);d4Playing=false;d4PlaybackStamp()};$('d4-native').onclick=()=>{chooseClip('d4-native-safe');drawMap();app?.setPreset('follow')};$('d4-data-line').textContent=`3图 · ${DATA.d4.maps.reduce((s,m)=>s+m.g,0).toLocaleString()}候选地面格 · 四朝向×四手速 · ${DATA.d4.counts.complete.toLocaleString()}/${DATA.d4.maps.reduce((s,m)=>s+m.total_queries,0).toLocaleString()}离线查询完成 · 原生重复另列`;d4NativeSummary();d4UpdateUI()}
window.drawD42D=(ctx,xy)=>{
 if(!d4On())return;const m=d4Map(),[a,b]=xy([0,0,0]),[c,d]=xy([3,0,0]),tile=Math.max(3,Math.hypot(c-a,d-b)*.9),E=m.ground[d4Enemy],heading=d4Heading*Math.PI/2;
 ctx.save();
 const points=Array.from({length:49},(_,i)=>xy([E[0]+Math.sin(heading-Math.PI/2+i/48*Math.PI)*30,E[1],E[2]+Math.cos(heading-Math.PI/2+i/48*Math.PI)*30]));
 const[ex,ey]=xy(E);ctx.beginPath();ctx.moveTo(ex,ey);for(const p of points)ctx.lineTo(...p);ctx.closePath();ctx.globalAlpha=.12;ctx.fillStyle=cssToken('--d4-enemy');ctx.fill();ctx.globalAlpha=.8;ctx.strokeStyle=cssToken('--d4-enemy');ctx.lineWidth=1.2;ctx.stroke();
 for(let i=0;i<m.g;i++){
  if(!m.ordinary_support[i]&&!$('d4-unsupported').checked)continue;
  const code=d4View==='forward'?d4Code(d4Enemy,i):d4Source===null?0:d4Code(i,d4Source),[x,y]=xy(m.ground[i]);
  if(d4Win(code)||code===3){ctx.globalAlpha=.97;ctx.fillStyle=d4Color(code);ctx.fillRect(x-tile/2,y-tile/2,tile,tile);if(d4Stealth(code)){ctx.globalAlpha=1;ctx.fillStyle='#fff';ctx.beginPath();ctx.arc(x,y,1.25,0,Math.PI*2);ctx.fill()}}
  else if([0,12,13,14].includes(code)){ctx.globalAlpha=.62;ctx.strokeStyle=cssToken('--d4-unknown');ctx.lineWidth=.8;ctx.setLineDash([2,2]);ctx.strokeRect(x-tile/2,y-tile/2,tile,tile);ctx.setLineDash([])}
 }
 ctx.globalAlpha=1;const[ax,ay]=xy([E[0]+Math.sin(heading)*7,E[1],E[2]+Math.cos(heading)*7]),angle=Math.atan2(ay-ey,ax-ex);ctx.beginPath();ctx.moveTo(ex,ey);ctx.lineTo(ax,ay);ctx.lineTo(ax-Math.cos(angle-.55)*7,ay-Math.sin(angle-.55)*7);ctx.moveTo(ax,ay);ctx.lineTo(ax-Math.cos(angle+.55)*7,ay-Math.sin(angle+.55)*7);ctx.strokeStyle=cssToken('--d4-enemy');ctx.lineWidth=2.7;ctx.stroke();ctx.restore();
 const rect=canvas.getBoundingClientRect();d4PinLayer(xy,rect.width,rect.height);
};

window.d4Pick2D=cell=>{if(!d4On())return false;d4PickPosition({x:cell[0],y:cell[1],z:cell[2]});return true};

function d4NativeSummary(){
 const n=DATA.d4.native;if(!n)return;
 const box=$('d4-native-summary');box.replaceChildren();
 box.append(el('strong','',n.complete_new216?'限定原生队列 · 216次闭合':'限定原生队列 · 尚未完成'),el('p','',`${n.valid}/${n.planned}有效 · ${n.setup_void_attempts}次发动前无效 · ${n.unresolved_combats}次对战未决 · 旧12次不并入`));
 const table=el('table'),head=el('tr');for(const text of ['敌态','top1','top2','对照'])head.append(el('th','',text));table.append(head);
 for(const s of n.by_state){const row=el('tr'),state=el('td','',s.map+' / '+({center:'中路',central_high:'高台',west_lane:'侧路'}[s.region]||s.region));if(s.enemy)state.append(el('div','d4-count',`(${s.enemy.map(v=>Number(v.toFixed(2))).join(', ')}) · ${['↑ +Z','→ +X','↓ −Z','← −X'][s.heading]}`));row.append(state);for(const b of ['top1','top2','control']){const c=s.bands[b];row.append(el('td','mono',c?`${c.wins}/${c.n}`:'未测'))}table.append(row)}box.append(table);
 if(n.stop_reason)box.append(el('p','d3-caveat','预设停止条件触发：'+n.stop_reason));
 box.append(el('p','',`零钩、40f、我方理想瞄准 / 固定.52脚本；对手直线瞄准未补下坠，不是完美防守方或玩家胜率，也不外推连钩。实际姿态可判${n.actual_pose_concordance.eligible}次，其中${n.actual_pose_concordance.mismatches.length}次胜负不一致；另${n.valid-n.actual_pose_concordance.eligible}次未知。完整D4、接触规则与全局最优未闭合。`));
}
