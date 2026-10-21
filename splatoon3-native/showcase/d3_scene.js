/* Numerical model layer only; traces and model trajectories remain distinct. */
let selectedD3=null,selectedD3Enemy=0;
const d3Metric=()=>$('d3-metric').value;
const d3Upper=()=>$('d3-version').value==='upper';
const d3Value=p=>d3Metric()==='worst'?p.worst:p.expected;
const d3Pct=x=>x>0&&x<.0001?'<0.01%':(100*x).toFixed(x<.01?2:1)+'%';
const d3Style=s=>s==='light3'?'三连轻斩':'满蓄70＋轻斩35';
const d3MapName=id=>({Yunohana:'温泉峡谷',District00:'District00',Yagara:'Yagara'})[id];
function d3View(p){
 if(!d3Upper())return p;
 const variants=p.variants.filter(v=>v.speed===Number($('d3-speed').value));
 variants.sort((a,b)=>d3Value(b)-d3Value(a)||b.expected-a.expected||a.spent-b.spent);
 return variants.length?{...p,...variants[0]}:null;
}
function d3Points(m=currentMap()){
 const kind=$('d3-kind').value,maps=d3Upper()?DATA.d3r.maps:DATA.d3.maps;
 return (maps.find(x=>x.id===m.id)?.points||[]).map(d3View).filter(p=>p&&(kind==='all'||(kind==='single'?p.sequence.length===1:p.sequence.length>1))).sort((a,b)=>d3Value(b)-d3Value(a));
}
function d3UpdateUI(){
 const on=$('show-d3').checked,ps=d3Points();$('d3-panel').hidden=!on;
 document.querySelector('.inspector').classList.toggle('d3-active',on);document.querySelector('.map-content').classList.toggle('model-mode',on);
 $('d3-speed-field').hidden=!d3Upper();$('d3-layer-tag').textContent=d3Upper()?'理想操作上限':'旧手柄模型';
 $('d3-phase-note').textContent=d3Upper()?(Number($('d3-speed').value)===20?'20f满蓄未在本夹具成立，此档仅比较已测三连轻斩。':'档位：到达确认→发射动作；弹体生成另加6/11f。40f两刀有原生校准，其余方案是模型外推。'):'旧手柄执行层基线；原54案只有1次击倒，不能当玩家推荐榜。';
 selectedD3=ps.find(p=>p.id===selectedD3?.id)||ps[0]||null;
 $('d3-point').replaceChildren(...ps.map((p,i)=>{const o=el('option','',`${String(i+1).padStart(2,'0')} · ${p.sequence.length>1?p.sequence.length+'钩':'单钩'} · ${d3Pct(d3Value(p))}${d3Upper()?' · '+d3Style(p.style):''}`);o.value=p.id;return o}));
 $('d3-point').value=selectedD3?.id||'';
 const box=$('d3-detail');box.replaceChildren();if(!selectedD3){box.append(el('p','','此档暂无预算内路径。'));return}
 const p=selectedD3,n=p.native,upper=d3Upper(),dl=el('dl');
 const nativeLabel=n?`${n.kills}/${n.n} 击倒 · ${n.bind_success}/${n.n} 绑定`:'本点尚无对练概率';
 const entries=[['全图期望 / 最坏',`${d3Pct(p.expected)} / ${d3Pct(p.worst)}`],['30u近场期望',d3Pct(p.local)],...(upper?[['动作',d3Style(p.style)],['原生40f两刀',nativeLabel],['精算敌位',`${p.enemy.length} 格 · 空白未精算`]]:[['旧原生对照',nativeLabel]]),['槽预算',`${(p.spent*100).toFixed(1)}% · 含启动损耗`]];
 for(const[k,v]of entries){const row=el('div');row.append(el('dt','',k),el('dd','mono',v));dl.append(row)}box.append(dl);
 if(upper&&n&&(p.style!=='full-light'||p.speed!==40))box.append(el('p','d3-caveat','本点原生数字属于40f满蓄＋轻斩；当前招式/手速没有同范围概率校准。'));
 box.append(el('p','','地面热度：固定这个切入后，对精算敌位的条件击杀率。平均口径含8朝向、有效形态和声明反应分布；最坏取三种行为的最低值。'));
 const enemyLabel=el('label','zip-field','精算敌位'),enemySelect=el('select');enemySelect.id='d3-enemy';enemySelect.setAttribute('aria-label','查看精算敌位');
 p.enemy.forEach((e,i)=>{const o=el('option','',`${String(i+1).padStart(2,'0')} · ${d3Pct(e[d3Metric()==='worst'?4:3])} · X${e[0]} Z${e[2]}`);o.value=i;enemySelect.append(o)});selectedD3Enemy=Math.min(selectedD3Enemy,Math.max(0,p.enemy.length-1));enemySelect.value=selectedD3Enemy;enemySelect.onchange=()=>{selectedD3Enemy=Number(enemySelect.value);drawMap()};enemyLabel.append(enemySelect);box.append(enemyLabel);
 const e=p.enemy[selectedD3Enemy];if(e)box.append(el('p','mono',`敌位 ${e.slice(0,3).join(' / ')} · 距落点 ${Math.hypot(e[0]-p.landing[0],e[1]-p.landing[1],e[2]-p.landing[2]).toFixed(1)}u`));
 const sequence=el('ol','d3-steps');p.sequence.forEach((id,i)=>sequence.append(el('li','',`${i+1} 钩 · ${id.split('-').slice(-2).join('-')}${i&&upper?' / B6后再出钩（预测）':''}`)));sequence.append(el('li','',upper?`${p.speed}f档 · ${d3Style(p.style)}`:'B跳离 → 重瞄 → 满蓄70＋轻斩35'));sequence.append(el('li','','保留回程余量 · 回程受击规则仍未定'));box.append(sequence);
 const attack=p.events?.find(e=>e.event==='满蓄释放'||e.event.startsWith('轻斩输入'));if(upper&&attack)box.append(el('p','',`出钩计0f；第${attack.frame}f发射动作。标记含输入/预测时间，不是实测最短帧数。`));
 if(upper&&p.events?.length){const details=el('details','d3-action-timing'),summary=el('summary','','预测动作时间表 · 非原生最短纪录'),list=el('ol');for(const e of p.events)list.append(el('li','mono',`F${e.frame} · ${e.event}`));details.append(summary,list);box.append(details)}
 if(p.sequence.length>1)box.append(el('p','d3-caveat','连钩是≤3深度、束宽6的预测路径。单钩原生概率不归给连钩，尚不能当实测绕后路线。'));
 if(n?.rate_beta95)box.append(el('p','',`该原生点95%后验区间 ${(100*n.rate_beta95[0]).toFixed(1)}–${(100*n.rate_beta95[1]).toFixed(1)}%。三个人形站位/朝向，分母不同于全图模型，样本不足以证明点位最优。`));
 if(n?.clip_id){const b=el('button','','看本点的原生试次 ↗');b.onclick=()=>{chooseClip(n.clip_id);drawMap();app?.setPreset('follow')};box.append(b)}
}
function setupD3(scene,m){
 scene.d3Group=new THREE.Group();scene.root.add(scene.d3Group);
 const points=[...(DATA.d3.maps.find(x=>x.id===m.id)?.points||[]),...(DATA.d3r.maps.find(x=>x.id===m.id)?.points||[])];
 for(const p of points){const marker=new THREE.Mesh(new THREE.OctahedronGeometry(1.5),new THREE.MeshBasicMaterial({transparent:true,depthTest:false,depthWrite:false}));marker.position.set(...p.position);marker.position.y+=.6;marker.renderOrder=15;marker.userData.d3Id=p.id;scene.d3Group.add(marker);const label=scene.label(`${p.sequence.length>1?'连钩终点':'模型挂点'}`,p.position,'d3');label.d3Id=p.id}
}
function refreshD3(scene){
 d3UpdateUI();if(!scene.d3Group)return;scene.d3Group.visible=$('show-d3').checked;
 const ps=d3Points(),ids=new Set(ps.map(p=>p.id)),scale=Math.max(.01,...ps.map(d3Value));
 for(const marker of scene.d3Group.children){const p=ps.find(p=>p.id===marker.userData.d3Id);marker.visible=ids.has(marker.userData.d3Id);if(!p)continue;marker.material.color.set(cssToken('--accent'));marker.material.opacity=.25+.75*d3Value(p)/scale;marker.scale.setScalar(p.id===selectedD3?.id?1.5:1);marker.material.wireframe=p.sequence.length>1}
 if(!scene.d3Group.visible||!selectedD3)return;
 const p=selectedD3,path=d3Upper()&&p.path?.length?p.path:[p.source,...p.anchors,p.landing];const route=scene.line(path.map(a=>new THREE.Vector3(a[0],a[1]+.5,a[2])),cssToken('--accent'),2,true);route.material.depthTest=false;route.renderOrder=14;scene.overlay.add(route);
 const cells=p.enemy;
 if(cells.length){const heat=new THREE.InstancedMesh(new THREE.PlaneGeometry(2.4,2.4),new THREE.MeshBasicMaterial({transparent:true,opacity:.78,side:THREE.DoubleSide,depthWrite:false,depthTest:false}),cells.length),dummy=new THREE.Object3D();cells.forEach((c,i)=>{const v=c[d3Metric()==='worst'?4:3];dummy.position.set(c[0],c[1]+.28,c[2]);dummy.rotation.x=-Math.PI/2;dummy.updateMatrix();heat.setMatrixAt(i,dummy.matrix);heat.setColorAt(i,new THREE.Color(cssToken('--line')).lerp(new THREE.Color(cssToken('--heat-high')),v))});heat.renderOrder=13;scene.overlay.add(heat)}
 const origin=new THREE.Mesh(new THREE.CylinderGeometry(1.1,1.1,.25,20),new THREE.MeshBasicMaterial({color:cssToken('--accent')}));origin.position.set(...p.source);origin.position.y+=.4;scene.overlay.add(origin);
 const enemy=p.enemy[selectedD3Enemy];if(enemy){const ring=scene.ring(enemy,1.8,cssToken('--bravo'));ring.material.depthTest=false;ring.renderOrder=15;scene.overlay.add(ring)}
}
function bindD3(){
 $('show-d3').onchange=()=>{if($('show-d3').checked){playing=false;$('show-zip').checked=false;selectedZip=null}d3UpdateUI();drawMap()};
 for(const id of['d3-metric','d3-kind','d3-version','d3-speed'])$(id).onchange=()=>{selectedD3=null;selectedD3Enemy=0;d3UpdateUI();drawMap()};
 $('d3-point').onchange=()=>{selectedD3=d3Points().find(p=>p.id===$('d3-point').value);selectedD3Enemy=0;drawMap()};$('d3-best').onclick=()=>{selectedD3=d3Points()[0];selectedD3Enemy=0;drawMap()};
 const table=$('d3-summary');for(const m of DATA.d3r.maps){const card=el('article','d3-map-summary');card.append(el('h3','',d3MapName(m.id)));for(const speed of DATA.d3r.speeds){const candidates=m.points.flatMap(p=>p.variants.filter(v=>v.speed===speed).map(v=>({...p,...v}))).sort((a,b)=>b.expected-a.expected);const best=candidates[0];if(best)card.append(el('p','',`${speed}f · ${best.sequence.length}钩 / ${d3Style(best.style)} · ${d3Pct(best.expected)}`))}const b=el('button','','在地图比较 ↗');b.onclick=()=>{switchMap(DATA.maps.findIndex(x=>x.id===m.id));$('show-d3').checked=true;$('show-zip').checked=false;$('d3-version').value='upper';playing=false;selectedD3=null;drawMap();$('maps').scrollIntoView({behavior:reducedMotion.matches?'instant':'smooth'})};card.append(b);table.append(card)}
 const c=DATA.d3r.calibration,fmt=x=>x===null||x===undefined?'未定义':x.toFixed(3);$('d3-calibration').textContent=c?`新原生 ${c.native_trials} 案，${c.kills} 次击倒。${c.summary} 原生最高排名仍未证实。`:'新54案原生校准进行中。当前颜色是理想操作条件模型，不是已验证的实战胜率。';
 const errors=$('d3r-errors');if(c){const rank=c.rankings;for(const[k,label]of[['global_prior_vs_native','全图分数对原生组'],['matched_before','匹配初态 / 修正前'],['matched_after','匹配初态 / 训练修正后']]){const row=rank[k];if(row){const card=el('article');card.append(el('b','',label),el('p','mono',`Spearman ${fmt(row.spearman)} / Kendall ${fmt(row.kendall_tau_b)}`));errors.append(card)}}const held=c.metrics['held-out'];if(held){const card=el('article');card.append(el('b','',`留出 ${held.before.n} 案`),el('p','mono',`MAE ${fmt(held.before.mae)} → ${fmt(held.after.mae)}`),el('small','',`Brier ${fmt(held.before.brier)} → 仅轨迹 ${fmt(held.motion_only.brier)} → 加训练ρ ${fmt(held.after.brier)}；ρ=${fmt(c.fit.rho)}。常数训练率基线 ${fmt(held.constant_train_rate.brier)}，全零 ${fmt(held.constant_zero.brier)}。MAE仍高于全零基线 ${fmt(held.constant_zero.mae)}；小误差不自动等于排名有效。`));errors.append(card)}const a=c.threat_audit;if(a)errors.append(el('p','note',`水刀进入.52视线 ${a.visible_trials}/${c.native_trials} · 开火 ${a.fired_trials}/${c.native_trials} · 水刀HP确认大幅掉血 ${a.body_hit_trials}/${c.native_trials}。开火与命中分开，射程外开火不当作有效威胁。`))}
 $('d3-loss-replay').onclick=()=>{const id=DATA.d3r.calibration?.replay_examples.find(p=>p.kind==='counter')?.clip_id||'d3r-control-Yunohana';chooseClip(id);$('enemy-fov').checked=true;drawMap();app?.setPreset('follow');$('maps').scrollIntoView({behavior:reducedMotion.matches?'instant':'smooth'})};
 d3UpdateUI();
}
window.drawD32D=(ctx,xy)=>{if(!$('show-d3').checked)return;const ps=d3Points(),scale=Math.max(.01,...ps.map(d3Value));for(const p of ps){const[x,y]=xy(p.position);ctx.beginPath();ctx.arc(x,y,p.id===selectedD3?.id?6:4,0,Math.PI*2);ctx.globalAlpha=.3+.7*d3Value(p)/scale;ctx.fillStyle=cssToken('--accent');ctx.fill();ctx.globalAlpha=1}if(selectedD3){for(const c of selectedD3.enemy){const[x,y]=xy(c);ctx.globalAlpha=.3+.65*c[d3Metric()==='worst'?4:3];ctx.fillStyle=cssToken(c[d3Metric()==='worst'?4:3]>0?'--heat-high':'--line');ctx.fillRect(x-2,y-2,4,4)}ctx.globalAlpha=1}};
