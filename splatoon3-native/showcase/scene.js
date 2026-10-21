/* Presentation only: primitives, camera and playback UI over unchanged derived data. */
(() => {
  const host=$('scene'),traceSelect=$('trace-select'),timeline=$('trace-time');
  const THREE=window.THREE,reducedMotion=matchMedia('(prefers-reduced-motion: reduce)');
  let app=null,clip=DATA.traces[0],frame=clip.start_frame,playing=false,previousTick=null,selectedZip=null;

  const regionNames={center:'中路',central_high:'中央高台',west_lane:'西侧通路',east_lane:'东侧通路'};
  function zipPoints(map=currentMap(),filtered=true){
    const region=$('zip-region').value,combo=$('zip-combo').value;
    const native=DATA.zipcaster.verified.filter(p=>p.map===map.id&&(!filtered||((region==='all'||p.region===region)&&(combo==='all'||combo===p.combo))));
    const candidates=DATA.zipcaster.maps.find(m=>m.id===map.id).candidates.flatMap(p=>{
      const targets=p.targets.filter(t=>!filtered||((region==='all'||t.region===region)&&(combo==='all'||combo==='full-light'&&t.full_light||combo==='bomb-full'&&t.bomb_full_geometry)));
      return targets.length?[{...p,displayTarget:targets.find(t=>t.full_light)||targets[0]}]:[];
    });return [...native,...candidates];
  }
  function zipDetail(point){
    const box=$('zip-detail');box.replaceChildren();if(!point){box.append(el('p','',$('zip-combo').value==='bomb-light'?'60＋35＝95，不足击倒100血。这个筛选没有满血击倒候选。':'当前筛选无匹配点；此图仍没有原生已验证挂点。'));return}
    const native=point.status==='verified',target=point.displayTarget;
    box.append(el('strong','',native?'已实测验证 · 中路夹具':'待验证候选 · '+point.id.split('-').at(-1)));
    const dl=el('dl');
    const entries=native?[['连招','蓄斩70 → 轻斩收尾'],['观测耗时','150f · 含重瞄'],['样本','静止满血靶 · 1次'],['位置',point.position.map(x=>fmt(x,1)).join(' / ')]]:
      [['目标区域',regionNames[target.region]],['距估计落点',fmt(target.distance,1)+' u'],['落点潜在视域',point.view===null?'—':fmt(point.view,1)+'%'],['出钩参考距离',fmt(point.approach_range,1)+' u']];
    for(const[k,v]of entries){const row=el('div');row.append(el('dt','',k),el('dd','',v));dl.append(row)}box.append(dl);
    box.append(el('p','',native?point.caveat:($('zip-combo').value==='bomb-full'?'130只是条件伤害算术。大招内炸弹输入、投掷轨迹和命中未验证。':target.full_light?'满足估计落点19u内与中心射线条件；105伤害须两刀命中且目标未回血。':'只满足静态切入筛选，未证实能在落点接满血击倒连招。')));
    if(!native)box.append(el('p','','虚线为几何参考连线，非原生飞行轨迹；标记穿透显示，不代表对手可见性。'));
  }
  function updateZipUI(){
    const visible=$('show-zip').checked,points=zipPoints(),native=points.filter(p=>p.status==='verified').length;
    $('zip-panel').hidden=!visible;
    selectedZip=points.find(p=>p.id===selectedZip?.id)||points[0]||null;
    document.querySelector('.inspector').classList.toggle('zip-active',visible);
    $('zip-count').textContent=`${native} 处实测 / ${points.length-native} 处候选 · 原始${DATA.zipcaster.maps.find(m=>m.id===currentMap().id).total}处节选`;
    const options=points.map(p=>{const o=el('option','',p.status==='verified'?'● 实测 · 中路夹具':`○ ${regionNames[p.displayTarget.region]} · ${p.id.split('-').at(-1)}`);o.value=p.id;return o});
    if(!options.length){const o=el('option','','无匹配点');o.value='';options.push(o)}
    $('zip-point').replaceChildren(...options);$('zip-point').value=selectedZip?.id||'';zipDetail(selectedZip);
    $('zip-replay').hidden=!visible||currentMap().id!=='Yunohana';
    if(!visible)selectedZip=null;
  }
  window.clearZipFocus=()=>{$('show-zip').checked=false;updateZipUI()};
  window.drawZip2D=(ctx,xy)=>{if(!$('show-zip').checked)return;for(const p of zipPoints()){const[x,y]=xy(p.position);ctx.beginPath();ctx.arc(x,y,p.status==='verified'?5:3,0,Math.PI*2);ctx.strokeStyle=cssToken('--accent');ctx.lineWidth=p.id===selectedZip?.id?2.5:1;ctx.stroke();if(p.status==='verified'){ctx.fillStyle=cssToken('--accent');ctx.fill()}}};

  const formName={human:'人形',squid:'乌贼',submerged:'潜墨'};
  function sample(player,f){
    const rows=player.states;if(!rows.length||f<rows[0][0]||f>rows.at(-1)[0]+6)return null;
    let lo=0,hi=rows.length-1;while(lo<hi){const mid=Math.ceil((lo+hi)/2);if(rows[mid][0]<=f)lo=mid;else hi=mid-1}
    const a=rows[lo],b=rows[Math.min(lo+1,rows.length-1)];
    if(f-a[0]>18)return null;
    const value=a.slice();
    if(b[0]>a[0]&&b[0]-a[0]<=18){const t=Math.min(1,(f-a[0])/(b[0]-a[0]));for(const i of [2,3,4])value[i]=a[i]+(b[i]-a[i])*t;if(a[5]!==null&&b[5]!==null){const d=Math.atan2(Math.sin(b[5]-a[5]),Math.cos(b[5]-a[5]));value[5]=a[5]+d*t}}
    return value;
  }

  function updateHUD(){
    const offset=Math.round(frame-clip.start_frame),duration=clip.end_frame-clip.start_frame;
    for(const input of [timeline,$('quick-time')]){input.value=String(offset);input.max=String(duration)}
    $('quick-stamp').replaceChildren(el('b','',((frame-clip.start_frame)/60).toFixed(1)+'s'),el('small','',`F${Math.round(frame)}`));
    $('quick-play').textContent=playing?'Ⅱ':'▶';$('quick-play').setAttribute('aria-label',playing?'地图内暂停回放':'地图内播放回放');
    $('quick-follow').value=$('follow-player').value;
    $('trace-stamp').textContent=`${((frame-clip.start_frame)/60).toFixed(2)} / ${(duration/60).toFixed(0)} s`;
    $('trace-frame').textContent=`F ${Math.round(frame)}`;
    $('trace-source').textContent=clip.source_kind==='native_observation'?'原生 · 自身观测':'S1 · 模拟状态';
    $('play-trace').textContent=playing?'Ⅱ 暂停':'▶ 播放';$('play-trace').setAttribute('aria-label',playing?'暂停回放':'播放回放');
    $('replay-hud').replaceChildren(...clip.players.map(p=>{
      const s=sample(p,frame),card=el('div',`player-hud ${p.id}`),head=el('div');
      head.append(el('strong','mono',p.display_name||p.id.toUpperCase()),el('div','form-label',s?`${formName[s[6]]||'形态未知'} · ${s[8]===true?'活动状态':s[8]===false?'倒下 / 待回场':'存活未知'}`:'状态缺失'));
      const hp=el('div'),track=el('div','hp-track'),bar=el('i');bar.style.width=s&&s[7]!==null?`${Math.max(0,Math.min(100,s[7]*100))}%`:'0';track.append(bar);
      hp.append(el('small','',`HP ${s&&s[7]!==null?Math.round(s[7]*100)+'%':'—'} · 采样 F${s?s[1]:'—'}`),track);card.append(head,hp);return card;
    }));
    const recent=clip.players.flatMap(p=>p.events.filter(e=>e.frame<=frame&&e.frame>frame-120&&['ZR_release','R_release'].includes(e.type)).map(e=>({...e,who:p.id}))).sort((a,b)=>b.frame-a.frame).slice(0,4);
    $('event-feed').replaceChildren(...(recent.length?recent.map(e=>{const span=el('span');span.append(el('b',e.who,e.who),document.createTextNode(` · F${e.frame} 松 ${e.type==='R_release'?'R / 出钩输入':'ZR'} · 持 ${e.hold_frames??'?'} 帧`));return span}):[el('span','',currentMap().id===clip.map?'此刻没有新的出刀输入。':'此图暂无片段；播放将切回温泉峡谷。')]));
  }
  // These are visual ticks over recorded input/state edges, never inferred hits.
  function paintEventTicks(){
    const ticks=[];
    for(const p of clip.players){
      for(const e of p.events)if(e.type==='R_release')ticks.push({frame:e.frame,kind:'hook',text:'松R / 出钩输入',who:p.id});else if(e.type==='ZR_release')ticks.push({frame:e.frame,kind:'slash',text:'出刀输入',who:p.id});
      p.states.forEach((s,i)=>{if(!i)return;const previous=p.states[i-1];
        if(previous[8]===true&&s[8]===false)ticks.push({frame:s[0],kind:'down',text:'倒下状态',who:p.id});
        if((previous[6]==='submerged')!==(s[6]==='submerged'))ticks.push({frame:s[0],kind:'dive',text:'潜墨切换',who:p.id});
      });
    }
    for(const id of ['quick-events','trace-events'])$(id).replaceChildren(...ticks.map(t=>{
      const marker=el('i',t.kind);marker.style.left=`${100*(t.frame-clip.start_frame)/(clip.end_frame-clip.start_frame)}%`;
      marker.title=`${t.who} · ${t.text} · F${t.frame}`;marker.dataset.event=t.kind;return marker;
    }));
  }
  class AtlasScene {
    constructor(){
      this.renderer=new THREE.WebGLRenderer({antialias:true,alpha:false,powerPreference:'low-power'});
      this.renderer.setPixelRatio(Math.min(devicePixelRatio||1,1.5));this.renderer.outputColorSpace=THREE.SRGBColorSpace;host.append(this.renderer.domElement);
      this.scene=new THREE.Scene();this.camera=new THREE.OrthographicCamera(-100,100,100,-100,.1,1600);this.aspect=1;
      this.sky=new THREE.HemisphereLight('#ffffff','#405774',2);this.scene.add(this.sky);
      const sun=new THREE.DirectionalLight('#eff6ff',2.1);sun.position.set(-75,150,70);this.scene.add(sun);
      this.root=new THREE.Group();this.scene.add(this.root);this.actors=new THREE.Group();this.scene.add(this.actors);
      this.actorObjects={};this.labels=[];this.mapId=null;this.target=new THREE.Vector3();this.yaw=1.1;this.elevation=Math.PI/4;this.radius=220;
      this.preset='oblique';this.pointers=new Map();this.moved=0;this.raycaster=new THREE.Raycaster();this.bindInput();new ResizeObserver(()=>this.resize()).observe(host);this.resize();
    }
    resize(){const w=host.clientWidth,h=host.clientHeight;if(!w||!h)return;this.renderer.setSize(w,h,false);this.aspect=w/h;if(this.bounds&&['top','oblique'].includes(this.preset)){const mobile=w<500;this.yaw=this.preset==='top'?(mobile?0:Math.PI/2):(mobile?.22:.62);this.fit()}this.projectCamera()}
    projectCamera(){this.camera.left=-this.radius*this.aspect/2;this.camera.right=this.radius*this.aspect/2;this.camera.top=this.radius/2;this.camera.bottom=-this.radius/2;this.camera.updateProjectionMatrix()}
    disposeMap(){this.root.traverse(o=>{o.geometry?.dispose();if(o.material)(Array.isArray(o.material)?o.material:[o.material]).forEach(m=>m.dispose())});this.root.clear();this.labels.forEach(l=>l.element.remove());this.labels=[]}
    fit(){
      if(!this.bounds)return;
      const center=this.bounds.getCenter(new THREE.Vector3());this.target.copy(center);
      const right=new THREE.Vector3(Math.cos(this.yaw),0,-Math.sin(this.yaw));
      const up=new THREE.Vector3(-Math.sin(this.yaw)*Math.sin(this.elevation),Math.cos(this.elevation),-Math.cos(this.yaw)*Math.sin(this.elevation));
      let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;
      // Fit the visible derived footprint, avoiding the empty corners of a long map's AABB.
      for(const point of this.fitPoints){const v=point.clone().sub(center),a=v.dot(right),b=v.dot(up);minX=Math.min(minX,a);maxX=Math.max(maxX,a);minY=Math.min(minY,b);maxY=Math.max(maxY,b)}
      this.target.addScaledVector(right,(minX+maxX)/2).addScaledVector(up,(minY+maxY)/2);
      this.radius=Math.max((maxY-minY)/.72,(maxX-minX)/(this.aspect*.82));
    }
    setPreset(value){
      this.preset=value;const mobile=host.clientWidth<500;
      if(value==='follow'){$('follow-player').value=$('follow-player').value==='free'?'alpha':$('follow-player').value;this.elevation=Math.PI/4;this.radius=70}
      else{$('follow-player').value='free';this.elevation=value==='top'?Math.PI/2-.001:Math.PI/4;this.yaw=value==='top'?(mobile?0:Math.PI/2):(mobile?.22:.62);this.fit()}
      document.querySelectorAll('[data-camera]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.camera===value)));this.projectCamera();updateHUD();
    }
    reset(){this.setPreset('oblique')}
    label(text,p,kind){const element=el('div','scene-label');element.textContent=text;host.append(element);const item={element,position:new THREE.Vector3(p[0],p[1]+3,p[2]),kind};this.labels.push(item);return item}
    setMap(m){
      this.disposeMap();this.mapId=m.id;this.bounds=new THREE.Box3();this.fitPoints=[];
      m.cells.forEach(c=>{this.bounds.expandByPoint(new THREE.Vector3(c[0]-m.grid/2,c[1]-.7,c[2]-m.grid/2));this.bounds.expandByPoint(new THREE.Vector3(c[0]+m.grid/2,c[1]+1,c[2]+m.grid/2))});
      m.walls.forEach(w=>this.bounds.expandByPoint(new THREE.Vector3(w[0],w[3],w[1])));
      for(const c of m.cells)for(const x of [c[0]-m.grid/2,c[0]+m.grid/2])for(const z of [c[2]-m.grid/2,c[2]+m.grid/2])for(const y of [c[1]-.7,c[1]])this.fitPoints.push(new THREE.Vector3(x,y,z));
      for(const w of m.walls)for(const x of [w[0]-.95,w[0]+.95])for(const z of [w[1]-.95,w[1]+.95])for(const y of [w[2],w[3]])this.fitPoints.push(new THREE.Vector3(x,y,z));
      this.reset();
      const matrix=new THREE.Matrix4(),side=new THREE.MeshStandardMaterial({color:'#a6b7ca',roughness:1}),top=new THREE.MeshStandardMaterial({roughness:1});
      this.floors=new THREE.InstancedMesh(new THREE.BoxGeometry(m.grid*.994,.7,m.grid*.994),[side,side,top,side,side,side],m.cells.length);
      this.tint=new THREE.InstancedMesh(new THREE.PlaneGeometry(m.grid*.994,m.grid*.994).rotateX(-Math.PI/2),new THREE.MeshBasicMaterial({transparent:true,opacity:.56,depthWrite:false}),m.cells.length);
      m.cells.forEach((c,i)=>{matrix.makeTranslation(c[0],c[1]-.35,c[2]);this.floors.setMatrixAt(i,matrix);matrix.makeTranslation(c[0],c[1]+.025,c[2]);this.tint.setMatrixAt(i,matrix)});
      this.root.add(this.floors,this.tint);
      this.walls=new THREE.InstancedMesh(new THREE.BoxGeometry(1.9,1,1.9),new THREE.MeshStandardMaterial({roughness:1}),m.walls.length);
      m.walls.forEach((v,i)=>{matrix.compose(new THREE.Vector3(v[0],(v[2]+v[3])/2,v[1]),new THREE.Quaternion(),new THREE.Vector3(1,v[3]-v[2],1));this.walls.setMatrixAt(i,matrix)});this.root.add(this.walls);
      const edges=[],lookup=new Map(m.cells.map(c=>[`${c[0]}:${c[2]}`,c])),half=m.grid/2;
      for(const c of m.cells)for(const [dx,dz]of [[1,0],[-1,0],[0,1],[0,-1]]){
        const next=lookup.get(`${c[0]+dx*m.grid}:${c[2]+dz*m.grid}`);if(next&&Math.abs(next[1]-c[1])<1.5)continue;
        if(dx)edges.push(c[0]+dx*half,c[1]+.06,c[2]-half,c[0]+dx*half,c[1]+.06,c[2]+half);
        else edges.push(c[0]-half,c[1]+.06,c[2]+dz*half,c[0]+half,c[1]+.06,c[2]+dz*half);
      }
      const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(edges,3));
      this.edges=new THREE.LineSegments(geo,new THREE.LineBasicMaterial({transparent:true,opacity:.32}));this.root.add(this.edges);
      this.grid=new THREE.GridHelper(340,34);this.grid.position.y=m.heights[0]-3;this.grid.material.transparent=true;this.grid.material.opacity=.2;this.root.add(this.grid);
      this.spawnGroup=new THREE.Group();m.spawns.forEach((p,i)=>{const marker=new THREE.Mesh(new THREE.CylinderGeometry(2.5,2.5,.5,24),new THREE.MeshStandardMaterial());marker.position.set(p[0],p[1]+.4,p[2]);this.spawnGroup.add(marker);this.label(`${i?'B':'A'} 出生`,p,'spawn').side=i});this.root.add(this.spawnGroup);
      this.regionGroup=new THREE.Group();m.points.forEach((p,i)=>{const marker=new THREE.Mesh(new THREE.OctahedronGeometry(1.3),new THREE.MeshStandardMaterial());marker.position.set(p.position[0],p.position[1]+1.5,p.position[2]);marker.userData.point=p.id;this.regionGroup.add(marker);Object.assign(this.label(p.label,p.position,'eta'),{pointId:p.id,point:p,number:String(i+1).padStart(2,'0')})});this.root.add(this.regionGroup);
      this.ambushGroup=new THREE.Group();m.ambush.forEach((p,i)=>{const marker=new THREE.Mesh(new THREE.OctahedronGeometry(.9),new THREE.MeshStandardMaterial());marker.position.set(p.position[0],p.position[1]+1.3,p.position[2]);marker.userData.ambush=i;this.ambushGroup.add(marker)});this.root.add(this.ambushGroup);
      const prompt=el('option','',`选择伏击候选（${m.ambush.length}）`);prompt.value='';prompt.disabled=true;prompt.selected=true;
      $('ambush-select').replaceChildren(prompt,...m.ambush.map((p,i)=>{const o=el('option','',`${p.label} / 对 ${p.approach_side} 侧接近 / ${p.distance}u`);o.value=String(i);return o}));
      this.zipGroup=new THREE.Group();zipPoints(m,false).forEach(p=>{const native=p.status==='verified';const marker=new THREE.Mesh(native?new THREE.OctahedronGeometry(1.4):new THREE.RingGeometry(.7,.95,24),new THREE.MeshBasicMaterial({transparent:true,opacity:native?1:.8,side:THREE.DoubleSide,depthTest:false,depthWrite:false}));marker.position.set(p.position[0],p.position[1]+.5,p.position[2]);marker.renderOrder=12;marker.userData.zipId=p.id;marker.userData.candidate=!native;this.zipGroup.add(marker);if(native){const label=this.label('实测挂墙姿态',p.position,'zip');label.zipId=p.id;label.element.classList.add('zip-scene-label')}});this.root.add(this.zipGroup);
      this.overlay=new THREE.Group();this.root.add(this.overlay);this.setClipPaths();
      const index=document.querySelector('.point-index');index.replaceChildren(...m.points.map((p,i)=>{const s=el('span');s.append(el('b','',String(i+1).padStart(2,'0')),document.createTextNode(p.label));return s}));
    }
    clearOverlay(){this.overlay.traverse(o=>{o.geometry?.dispose();o.material?.dispose()});this.overlay.clear()}
    line(points,color,width=1,dashed=false){const material=dashed?new THREE.LineDashedMaterial({color,dashSize:1.2,gapSize:.8,transparent:true,opacity:.8}):new THREE.LineBasicMaterial({color,transparent:true,opacity:.86,linewidth:width});const line=new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),material);if(dashed)line.computeLineDistances();return line}
    ring(position,radius,color,dashed=false){return this.line(Array.from({length:81},(_,i)=>new THREE.Vector3(position[0]+Math.sin(i/80*Math.PI*2)*radius,position[1]+.35,position[2]+Math.cos(i/80*Math.PI*2)*radius)),color,1,dashed)}
    refresh(){
      const m=currentMap();if(this.mapId!==m.id)this.setMap(m);updateZipUI();
      this.renderer.setClearColor(cssToken('--scene-bg'));this.scene.background=new THREE.Color(cssToken('--scene-bg'));
      m.cells.forEach((c,i)=>{this.floors.setColorAt(i,new THREE.Color(heightColor(c,m)));this.tint.setColorAt(i,new THREE.Color(cellColor(c,m)))});
      this.floors.instanceColor.needsUpdate=true;this.tint.instanceColor.needsUpdate=true;this.tint.visible=mode!=='height';
      this.walls.material.color.set(cssToken('--wall'));this.edges.material.color.set(cssToken('--edge'));this.grid.material.color.set(cssToken('--scene-grid'));
      this.spawnGroup.children.forEach((o,i)=>o.material.color.set(i?colors.bravo:colors.alpha));this.regionGroup.children.forEach(o=>o.material.color.set(cssToken('--marker')));this.ambushGroup.children.forEach(o=>o.material.color.set(cssToken('--marker')));
      this.spawnGroup.visible=$('show-spawns').checked;this.regionGroup.visible=$('show-eta').checked;this.ambushGroup.visible=$('show-ambush').checked;$('ambush-select').hidden=!this.ambushGroup.visible;this.walls.visible=$('show-walls').checked;
      const visibleIds=new Set(zipPoints().map(p=>p.id));this.zipGroup.visible=$('show-zip').checked;this.zipGroup.children.forEach(o=>{o.visible=visibleIds.has(o.userData.zipId);o.material.color.set(cssToken('--accent'));o.scale.setScalar(o.userData.zipId===selectedZip?.id?1.45:1)});
      this.clearOverlay();if(selectedZip&&this.zipGroup.visible){
        const p=selectedZip,end=p.landing?.every(v=>v!==null)?p.landing:p.position,target=p.status==='verified'?p.target:p.displayTarget.position;
        this.overlay.add(this.line([new THREE.Vector3(...p.start),new THREE.Vector3(...p.position)],cssToken('--accent'),1,true));
        this.overlay.add(this.line([new THREE.Vector3(...end).add(new THREE.Vector3(0,1,0)),new THREE.Vector3(...target).add(new THREE.Vector3(0,1,0))],cssToken('--accent'),1,true));
        const marker=new THREE.Mesh(new THREE.OctahedronGeometry(1.1),new THREE.MeshBasicMaterial({color:cssToken('--accent'),depthTest:false}));marker.position.set(target[0],target[1]+1,target[2]);marker.renderOrder=12;this.overlay.add(marker);
        if($('ranges').checked){this.overlay.add(this.ring(end,19,cssToken('--accent')));this.overlay.add(this.ring(end,22,cssToken('--accent'),true))}
      }else if(selected){
        if($('routes').checked&&selected.routes)selected.routes.forEach((r,i)=>{if(r.length)this.overlay.add(this.line(r.map(p=>new THREE.Vector3(p[0],p[1]+.7,p[2])),i?colors.bravo:colors.alpha,2))});
        if($('ranges').checked){this.overlay.add(this.ring(selected.position,19,cssToken('--accent')));this.overlay.add(this.ring(selected.position,22,cssToken('--accent'),true))}
      }
      if(selected?.ambush&&this.ambushGroup.visible){const a=selected.ambush,threat=new THREE.Mesh(new THREE.SphereGeometry(1.3,8,6),new THREE.MeshBasicMaterial({color:colors.alpha}));threat.position.set(a.threat[0],a.threat[1]+1.1,a.threat[2]);this.overlay.add(threat);this.overlay.add(this.line([new THREE.Vector3(...a.position).add(new THREE.Vector3(0,.25,0)),threat.position.clone()],colors.alpha,1,true))}
      for(const [id,actor]of Object.entries(this.actorObjects))for(const key of ['body','arrow','ring','slash'])actor[key].material.color.set(id==='alpha'?colors.alpha:colors.bravo);
      this.setClipPaths();updateHUD();
    }
    makeActor(id){
      const color=id==='alpha'?colors.alpha:colors.bravo,group=new THREE.Group();
      const body=new THREE.Mesh(new THREE.CapsuleGeometry(.6,1.1,4,8),new THREE.MeshStandardMaterial({color,roughness:.65}));body.position.y=1.15;group.add(body);
      const arrow=new THREE.Mesh(new THREE.ConeGeometry(.65,1.9,3),new THREE.MeshBasicMaterial({color}));arrow.rotation.x=Math.PI/2;arrow.position.set(0,.5,1.6);group.add(arrow);
      const ring=this.ring([0,0,0],22,color,true);ring.material.opacity=.24;group.add(ring);const slash=this.ring([0,0,0],19,color);group.add(slash);
      for(const object of [body,arrow,ring,slash]){object.material.depthTest=false;object.material.depthWrite=false;object.renderOrder=20}
      const label=el('div',`scene-label actor-label ${id}`,id==='alpha'?'α':'β');host.append(label);const actor={group,body,arrow,ring,slash,label};this.actors.add(group);this.actorObjects[id]=actor;return actor;
    }
    setClipPaths(){
      if(this.trails){this.root.remove(this.trails);this.trails.traverse(o=>{o.geometry?.dispose();o.material?.dispose()})}
      this.trails=new THREE.Group();this.root.add(this.trails);
      if(clip&&clip.map===this.mapId)clip.players.forEach(p=>{const segments=[];p.states.forEach((s,i)=>{if(!i||s[0]-p.states[i-1][0]>18)segments.push([]);segments.at(-1).push(new THREE.Vector3(s[2],s[3]+.8,s[4]))});segments.filter(v=>v.length>1).forEach(points=>{const path=this.line(points,p.id==='alpha'?colors.alpha:colors.bravo);path.material.opacity=.18;path.material.depthTest=false;path.renderOrder=10;this.trails.add(path)})});
    }
    updateActors(){
      this.actors.visible=clip.map===this.mapId;
      for(const p of clip.players){const actor=this.actorObjects[p.id]||this.makeActor(p.id),s=sample(p,frame);actor.group.visible=!!s;if(!s)continue;
        actor.group.position.set(s[2],s[3],s[4]);actor.group.rotation.y=s[5]??0;
        const squid=s[6]==='squid'||s[6]==='submerged';actor.body.scale.set(squid?1.4:1,squid?.3:1,squid?1.2:1);actor.body.position.y=squid?.35:1.15;actor.body.material.opacity=s[8]===false?.25:1;actor.body.material.transparent=s[8]===false;actor.ring.visible=$('ranges').checked;
        const release=p.events.find(e=>e.type==='ZR_release'&&e.frame<=frame&&e.frame>frame-12);actor.slash.visible=!!release;const r=release?.hold_frames>=21?22:19;actor.slash.scale.set(r/19,1,r/19);actor.slash.material.opacity=release?Math.max(0,1-(frame-release.frame)/12):0;
        if($('follow-player').value===p.id&&this.actors.visible){const t=reducedMotion.matches?1:.16;this.target.lerp(new THREE.Vector3(s[2],s[3]+2,s[4]),t);this.radius+=(70-this.radius)*t}
      }
    }
    renderLabels(){
      const W=host.clientWidth,H=host.clientHeight,occupied=[],items=[];
      for(const l of this.labels){
        l.element.hidden=true;if(l.kind!=='zip'&&!(l.kind==='spawn'?this.spawnGroup.visible:this.regionGroup.visible))continue;
        const expanded=l.kind==='eta'&&!selectedZip&&(l.pointId===selectedKey||l.pointId===this.hoverKey);
        if(l.kind==='zip'){if(!this.zipGroup.visible||l.zipId!==selectedZip?.id)continue;items.push({element:l.element,position:l.position,priority:0});continue}
        l.element.classList.toggle('point-number',l.kind==='eta'&&!expanded);
        if(l.kind==='eta'){
          const signature=expanded?'full':'number';if(l.signature!==signature){l.signature=signature;l.element.replaceChildren(document.createTextNode(expanded?`${l.number} ${l.point.label}`:l.number));if(expanded){const small=el('small');small.append(el('span','alpha',`A ${fmt(l.point.times[0])}s`),document.createTextNode(' / '),el('span','bravo',`B ${fmt(l.point.times[1])}s`));l.element.append(el('br'),small)}}
        }else l.element.style.color=l.side?cssToken('--bravo'):cssToken('--alpha');
        items.push({element:l.element,position:l.position,priority:expanded?0:l.kind==='spawn'?2:3});
      }
      for(const [id,a]of Object.entries(this.actorObjects)){a.label.hidden=true;if(this.actors.visible&&a.group.visible)items.push({element:a.label,position:a.group.position.clone().add(new THREE.Vector3(0,3.5,0)),priority:1})}
      items.sort((a,b)=>a.priority-b.priority);
      for(const item of items){
        const e=item.element,p=item.position.clone().project(this.camera);if(p.z>1||Math.abs(p.x)>1||Math.abs(p.y)>1)continue;
        e.hidden=false;const w=e.offsetWidth,h=e.offsetHeight,px=(p.x*.5+.5)*W,py=(-p.y*.5+.5)*H;
        let placed=false;for(const [dx,dy]of [[0,0],[0,-30],[35,0],[-35,0],[0,32],[42,-32],[-42,-32],[0,-62]]){
          const x=Math.max(w/2+8,Math.min(W-w/2-8,px+dx)),y=Math.max(88+h,Math.min(H-98,py+dy)),box={x:x-w/2,y:y-h,w,h};
          if(occupied.some(o=>box.x<o.x+o.w+5&&box.x+box.w+5>o.x&&box.y<o.y+o.h+4&&box.y+box.h+4>o.y))continue;
          occupied.push(box);e.style.left=`${x}px`;e.style.top=`${y}px`;placed=true;break;
        }e.hidden=!placed;
      }
    }
    render(){
      if(host.hidden||!host.clientWidth)return;this.updateActors();this.projectCamera();
      this.camera.position.set(this.target.x+Math.sin(this.yaw)*Math.cos(this.elevation)*500,this.target.y+Math.sin(this.elevation)*500,this.target.z+Math.cos(this.yaw)*Math.cos(this.elevation)*500);this.camera.lookAt(this.target);this.zipGroup.children.forEach(o=>{if(o.userData.candidate)o.quaternion.copy(this.camera.quaternion)});this.renderer.render(this.scene,this.camera);this.renderLabels();
    }
    pick(x,y,hover=false){
      const r=host.getBoundingClientRect();this.raycaster.setFromCamera(new THREE.Vector2((x-r.left)/r.width*2-1,-(y-r.top)/r.height*2+1),this.camera);
      const targets=hover?this.regionGroup.children:[this.floors,...(this.regionGroup.visible?this.regionGroup.children:[]),...(this.ambushGroup.visible?this.ambushGroup.children:[])];
      const zipHit=!hover&&this.zipGroup.visible?this.raycaster.intersectObjects(this.zipGroup.children.filter(o=>o.visible),false)[0]:null;const hit=zipHit||this.raycaster.intersectObjects(targets,false)[0];if(hover){this.hoverKey=hit?.object.userData.point;return}if(!hit)return;
      if(hit.object.userData.zipId){selectedZip=zipPoints().find(p=>p.id===hit.object.userData.zipId);drawMap();return}
      if(hit.object.userData.point){window.clearZipFocus();choosePoint(hit.object.userData.point);return}if(hit.object.userData.ambush!==undefined){this.selectAmbush(hit.object.userData.ambush);return}
      if(hit.instanceId!==undefined){window.clearZipFocus();const c=currentMap().cells[hit.instanceId];selectedKey=null;selected={position:c.slice(0,3),times:c.slice(3,5),vision:c[5],name:'自选站位',routes:null};updateInspector();drawMap()}
    }
    selectAmbush(index){window.clearZipFocus();const c=currentMap().ambush[index],cell=nearestCell(c.position);selectedKey=null;selected={position:c.position,times:cell.slice(3,5),vision:cell[5],name:`${c.label} · 伏击候选`,routes:null,ambush:c};$('ambush-select').value=String(index);updateInspector();$('point-insight').textContent=`假定对手由 ${c.approach_side} 侧接近，洋红球为观察位；潜墨低姿态被遮挡，距要道 ${c.distance}u。己墨与出墨命中待验证。`;$('point-insight').classList.add('ambush-hint');drawMap()}
    freeCamera(){this.preset='free';$('follow-player').value='free';document.querySelectorAll('[data-camera]').forEach(b=>b.setAttribute('aria-pressed','false'))}
    bindInput(){
      host.oncontextmenu=e=>e.preventDefault();
      host.addEventListener('pointerdown',e=>{host.setPointerCapture(e.pointerId);this.pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});this.moved=0;this.button=e.button});
      host.addEventListener('pointermove',e=>{
        if(!this.pointers.has(e.pointerId)){this.pick(e.clientX,e.clientY,true);return}
        const old=this.pointers.get(e.pointerId),dx=e.clientX-old.x,dy=e.clientY-old.y;this.moved+=Math.hypot(dx,dy);
        if(this.pointers.size>1){const other=[...this.pointers.entries()].find(([id])=>id!==e.pointerId)[1],a=Math.hypot(old.x-other.x,old.y-other.y),b=Math.hypot(e.clientX-other.x,e.clientY-other.y);if(a>1&&b>1)this.radius=Math.max(25,Math.min(550,this.radius*a/b))}
        else if(this.button===2||e.shiftKey){this.target.x-=dx*this.radius*.0015;this.target.z-=dy*this.radius*.0015}
        else{this.yaw-=dx*.007;this.elevation=Math.max(.18,Math.min(Math.PI/2-.001,this.elevation+dy*.006))}
        this.freeCamera();this.pointers.set(e.pointerId,{x:e.clientX,y:e.clientY});
      });
      host.addEventListener('pointerup',e=>{this.pointers.delete(e.pointerId);if(this.moved<5&&this.button===0)this.pick(e.clientX,e.clientY)});
      host.addEventListener('pointercancel',e=>this.pointers.delete(e.pointerId));host.addEventListener('pointerleave',()=>{this.hoverKey=null});
      host.addEventListener('wheel',e=>{e.preventDefault();this.radius=Math.max(25,Math.min(550,this.radius*Math.exp(e.deltaY*.001)));this.freeCamera()},{passive:false});
    }
  }
  traceSelect.replaceChildren(...DATA.traces.map(c=>{const o=el('option','',c.label);o.value=c.id;return o}));
  $('quick-clip').replaceChildren(...DATA.traces.map(c=>{const o=el('option','',c.short_label||`${c.source_kind==='native_observation'?'原生':'模拟'} R${c.id.slice(-1)}`);o.value=c.id;return o}));
  function chooseClip(id){clip=DATA.traces.find(t=>t.id===id);traceSelect.value=id;$('quick-clip').value=id;$('clip-description').textContent=clip.description||'';frame=clip.start_frame;playing=false;const i=DATA.maps.findIndex(m=>m.id===clip.map);if(i!==mapIndex)switchMap(i);app?.setClipPaths();paintEventTicks();updateHUD()}
  traceSelect.onchange=()=>{$('quick-clip').value=traceSelect.value;chooseClip(traceSelect.value)};
  $('quick-clip').onchange=()=>{traceSelect.value=$('quick-clip').value;chooseClip(traceSelect.value)};
  function seek(value){frame=clip.start_frame+Number(value);playing=false;updateHUD()}
  timeline.oninput=()=>seek(timeline.value);$('quick-time').oninput=()=>seek($('quick-time').value);
  $('play-trace').onclick=()=>{if(currentMap().id!==clip.map)switchMap(DATA.maps.findIndex(m=>m.id===clip.map));if(frame>=clip.end_frame)frame=clip.start_frame;playing=!playing;updateHUD()};
  $('quick-play').onclick=()=>$('play-trace').onclick();
  $('rewind-trace').onclick=()=>{frame=clip.start_frame;playing=false;updateHUD()};
  $('quick-speed').onchange=()=>{$('play-speed').value=$('quick-speed').value};$('play-speed').onchange=()=>{$('quick-speed').value=$('play-speed').value};
  $('follow-player').onchange=()=>{const value=$('follow-player').value;if(currentMap().id!==clip.map)switchMap(DATA.maps.findIndex(m=>m.id===clip.map));$('follow-player').value=value;app?.setPreset(value==='free'?'oblique':'follow')};
  $('quick-follow').onchange=()=>{$('follow-player').value=$('quick-follow').value;$('follow-player').onchange()};
  document.querySelectorAll('[data-camera]').forEach(b=>b.onclick=()=>{if(b.dataset.camera==='follow'&&currentMap().id!==clip.map)switchMap(DATA.maps.findIndex(m=>m.id===clip.map));app?.setPreset(b.dataset.camera)});
  $('ambush-select').onchange=()=>{if($('ambush-select').value!=='')app?.selectAmbush(Number($('ambush-select').value))};
  $('reset-camera').onclick=()=>app?.reset();
  $('view-toggle').onclick=()=>{const show3D=host.hidden;canvas.hidden=show3D;host.hidden=!show3D;$('view-toggle').textContent=show3D?'2D':'3D';drawMap();app?.resize()};
  for(const id of ['show-spawns','show-eta','show-ambush','show-walls','show-zip'])$(id).onchange=()=>{updateZipUI();drawMap()};
  for(const id of ['zip-region','zip-combo'])$(id).onchange=()=>{selectedZip=null;updateZipUI();drawMap()};
  $('zip-point').onchange=()=>{selectedZip=zipPoints().find(p=>p.id===$('zip-point').value);drawMap()};
  function showCombo(){$('show-zip').checked=true;$('zip-region').value='center';$('zip-combo').value='full-light';selectedZip=DATA.zipcaster.verified[0];chooseClip('zipcaster-mid');drawMap();app?.setPreset('follow');$('maps').scrollIntoView({behavior:reducedMotion.matches?'instant':'smooth',block:'start'});}
  $('zip-replay').onclick=showCombo;$('zip-card-replay').onclick=showCombo;
  updateZipUI();
  try{if(!THREE)throw new Error('three.js CDN 未加载');app=new AtlasScene();window.updateScene=()=>app.refresh();app.refresh()}catch(error){host.append(el('div','webgl-error',`3D 未能初始化：${error.message}。可以使用“2D”查看相同离线图层。`));$('reset-camera').disabled=true}
  let hudLast=0;
  function tick(time){const dt=previousTick===null?0:Math.min(.1,(time-previousTick)/1000);previousTick=time;if(playing&&document.visibilityState==='visible'){frame=Math.min(clip.end_frame,frame+dt*60*Number($('play-speed').value));if(frame>=clip.end_frame)playing=false}if(time-hudLast>90){updateHUD();hudLast=time}app?.render();requestAnimationFrame(tick)}
  chooseClip(clip.id);requestAnimationFrame(tick);
})();
