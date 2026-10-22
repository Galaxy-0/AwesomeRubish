/* Contact-disjoint, whole-wave-clear D4 model. Own numerical implementation.
 * Loaded after d4_worker.js exports. No native processes or network calls. */
(()=>{
'use strict';
const E=globalThis.D4Engine,{add,sub,mul,dot,norm,clamp,interp}=E.D4Math;
const xyz=o=>[o.X,o.Y,o.Z],inf=Infinity;
function basis(yaw,e){const sy=Math.sin(yaw),cy=Math.cos(yaw),se=Math.sin(e),ce=Math.cos(e);return [[cy,0,-sy],[-sy*se,ce,-cy*se],[sy*ce,se,cy*ce]]} // columns
const rotate=(r,p)=>[0,1,2].map(k=>r[0][k]*p[0]+r[1][k]*p[1]+r[2][k]*p[2]);
function capsule(a,b,radius,low=.35,high=1.30){const d=sub(b,a),near=sub(a,[0,clamp(a[1],low,high),0]);if(dot(near,near)<=radius*radius)return 0;let out=inf,aa=d[0]**2+d[2]**2,bb=a[0]*d[0]+a[2]*d[2],cc=a[0]**2+a[2]**2-radius*radius,disc=bb*bb-aa*cc;if(aa>1e-15&&disc>=0){const t=(-bb-Math.sqrt(disc))/aa,y=a[1]+t*d[1];if(t>=0&&t<=1&&y>=low&&y<=high)out=t}aa=dot(d,d);for(const y of[low,high]){const q=sub(a,[0,y,0]);bb=dot(q,d);cc=dot(q,q)-radius*radius;disc=bb*bb-aa*cc;if(aa>1e-15&&disc>=0){const t=(-bb-Math.sqrt(disc))/aa;if(t>=0&&t<=1)out=Math.min(out,t)}}return out}
function axisDistance(a,b,low=.35,high=1.30){const u=sub(b,a),w=sub(a,[0,low,0]),height=high-low,aa=dot(u,u),bb=u[1]*height,cc=height*height,dd=dot(u,w),ee=w[1]*height,den=aa*cc-bb*bb;let s=den>1e-15?clamp((bb*ee-cc*dd)/Math.max(den,1e-300),0,1):0,t=(bb*s+ee)/cc;if(t<0)s=clamp(-dd/Math.max(aa,1e-300),0,1);if(t>1)s=clamp((bb-dd)/Math.max(aa,1e-300),0,1);t=clamp(t,0,1);const q=add(w,mul(u,s));q[1]-=t*height;return norm(q)}
const sameDirection=(a,b)=>Math.max(...a.map((v,k)=>Math.abs(v-b[k])))<=1e-10;
function trace(world,points,frames,enemies,r,collision,bound='initial'){
 const k=collision.OffsetArray.length,offsets=collision.OffsetArray.map(o=>rotate(r,xyz(o))),body=new Array(k).fill(inf),margins=new Array(k).fill(-inf),field=new Array(k).fill(inf);
 for(let j=0;j<k;j++)for(let t=0;t<points.length-1;t++){
  const a=sub(add(points[t],offsets[j]),enemies[t]),b=sub(add(points[t+1],offsets[j]),enemies[t+1]),rad=.35+collision.ParamArray[j].InitRadiusForPlayer;
  body[j]=Math.min(body[j],frames[t]+(frames[t+1]-frames[t])*capsule(a,b,rad));margins[j]=Math.max(margins[j],rad-axisDistance(a,b));
 }
 if(body.some(Number.isFinite)){
  const movements=points.slice(1).map((p,i)=>sub(p,points[i])),units=movements.map(v=>mul(v,1/Math.max(norm(v),1e-15))),cuts=[0];
  for(let i=0;i<units.length-1;i++)if(!sameDirection(units[i],units[i+1]))cuts.push(i+1);cuts.push(points.length-1);
  for(let c=0;c<cuts.length-1;c++){
   const lo=cuts[c],hi=cuts[c+1],delta=sub(points[hi],points[lo]),length=norm(delta),direction=mul(delta,1/Math.max(length,1e-15)),cumulative=points.slice(lo,hi+1).map(p=>norm(sub(p,points[lo])));
   for(let j=0;j<k;j++){
    const p=collision.ParamArray[j],radius=bound==='end'?(p.EndRadiusForField??p.InitRadiusForField):p.InitRadiusForField,hit=world.geometry.sphere(add(points[lo],offsets[j]),direction,radius,Math.max(length,1e-12));if(hit.index<0)continue;
    let slot=cumulative.filter(d=>hit.distance>=d).length-1;slot=clamp(slot,0,hi-lo-1);
    const before=cumulative[slot],after=cumulative[slot+1],time=frames[lo+slot]+(frames[lo+slot+1]-frames[lo+slot])*(hit.distance-before)/Math.max(after-before,1e-15);field[j]=Math.min(field[j],time);
   }
  }
 }
 const stop=Math.min(...field),valid=body.map(t=>t<stop-1e-7?t:inf),time=Math.min(...valid),chosen=valid.indexOf(time);
 return {hit:Number.isFinite(time),time,chosen,body,field,offsets,margins,stop};
}
class SafeShots{
 constructor(world,data){this.w=world;this.p=data.parameters;this.fit=data.fit;this.bounds=data.contact_bounds;this.cache=new Map()}
 direction(yaw,pitch,style){const c=this.fit.elevation[style].coefficients,e=c[0]*pitch+c[1],r=basis(yaw,e);return {direction:r[2],elevation:e,r}}
 paths(source,yaw,pitch,style){const d=this.direction(yaw,pitch,style),full=style==='full',r=d.r,launch=full?add(source,[0,2.2,0]):add(source,r[1]),origin=add(launch,full?mul(basis(yaw,0)[2],.8):mul(d.direction,1.4)),life=full?26:6,speed=full?.8:2.82,points=[launch],frames=[-1];for(let t=0;t<=life;t++){const p=add(origin,mul(d.direction,t*speed));if(full)p[1]-=.0027*Math.max(t-22,0)*(Math.max(t-22,0)+1)/2;points.push(p);frames.push(t)}return {...d,launch,origin,life,speed,points,frames}}
 collision(style){return this.p[(style==='full'?'vertical':'horizontal')+'_projectile'].CollisionParam}
 evaluate(source,target,style,yaw,pitch,targetPositions=null){if(Math.abs(pitch)>.85000000001)throw Error('pitch outside fixture');const q=this.paths(source,yaw,pitch,style),enemies=targetPositions||q.points.map(()=>target),col=this.collision(style),initial=trace(this.w,q.points,q.frames,enemies,q.r,col),end=trace(this.w,q.points,q.frames,enemies,q.r,col,'end');let clearance;
  if(initial.hit)clearance=Math.min(initial.margins[initial.chosen],(Math.min(q.life,initial.stop)-Math.max(0,initial.time))*q.speed);
  else clearance=Math.max(...initial.body.map((b,j)=>Number.isFinite(b)&&Number.isFinite(Math.min(initial.field[j],initial.field[col.CoreIndex]))?Math.min(initial.margins[j],(Math.min(initial.field[j],initial.field[col.CoreIndex])-b)*q.speed):initial.margins[j]));
  return {style,yaw,native_pitch:pitch,elevation:q.elevation,origin:q.origin,launch_start:q.launch,lifetime:q.life,hit:initial.hit,assembly_uncertain:false,radius_bound_uncertain:initial.hit!==end.hit,player_contact_age:initial.hit?Math.max(0,initial.time):null,clearance,body_margin:initial.hit?initial.margins[initial.chosen]:-inf,damage:style==='full'?70:35,_q:q,_initial:initial,_end:end};
 }
 best(source,target,style){const key=JSON.stringify([source,target,style]);if(this.cache.has(key))return this.cache.get(key);const yaw=Math.atan2(target[0]-source[0],target[2]-source[2]),rows=[];let best=null;
  for(let i=0;i<=170;i++){
   const pitch=-.85+i*.01,r=this.evaluate(source,target,style,yaw,pitch),q=r._q,a=r._initial,b=r._end;let clearance;
   if(a.hit)clearance=Math.min(a.margins[a.chosen],(Math.min(q.life,a.stop)-Math.max(a.time,0))*q.speed);
   else clearance=Math.max(...a.body.map((t,j)=>Number.isFinite(t)&&Number.isFinite(a.stop)?Math.min(a.margins[j],(a.stop-t)*q.speed):a.margins[j]));
   let fm=0;
   if(a.hit){let lo=0,hi=Math.max(clearance,0);const endpoint=add(q.origin,mul(q.direction,q.speed*Math.max(a.time,0)));
    for(let n=0;n<9;n++){const middle=(lo+hi)/2;let blocked=false;for(let j=0;j<a.offsets.length&&!blocked;j++)for(const[from,to]of[[q.launch,q.origin],[q.origin,endpoint]]){const start=add(from,a.offsets[j]),delta=sub(to,from),length=norm(delta),radius=this.collision(style).ParamArray[j].InitRadiusForField+middle;if(this.w.geometry.sphere(start,mul(delta,1/Math.max(length,1e-15)),radius,Math.max(length,1e-12)).index>=0){blocked=true;break}}if(blocked)hi=middle;else lo=middle}fm=lo;clearance=Math.min(clearance,lo);
   }
   const uncertain=a.hit!==b.hit,rank=[a.hit&&!uncertain?1:0,clearance,-Math.abs(pitch)];r.clearance=clearance;r.field_margin=fm;r.radius_bound_uncertain=uncertain;r.assembly_uncertain=uncertain;
   if(!best||rank[0]>best.rank[0]||rank[0]===best.rank[0]&&(rank[1]>best.rank[1]||rank[1]===best.rank[1]&&rank[2]>best.rank[2]))best={rank,result:r};
  }
  const result=best.result;delete result._q;delete result._initial;delete result._end;if(this.cache.size>=8192)this.cache.clear();this.cache.set(key,result);return result;
 }
 exclusion(source,target,style){const distance=Math.hypot(source[0]-target[0],source[2]-target[2]),bound=this.bounds[style];return distance>bound}
}
function forcedDistance(profile,age){return age< -1?0:interp(age,[-1,...profile.frames],[0,...profile.distance])}
function attackSequence(world,body,enemy,inputs){const target=body.map(()=>enemy.slice()),events=[],casts=[],unknown=[];
 for(let i=0;i<inputs.length;i++){
  const[release,style]=inputs[i],cb=release+(style==='full'?4:9),pb=release+(style==='full'?6:11),safe=[0,1,2,3].every(t=>world.shots.exclusion(body[cb+t],target[cb+t],style));if(!safe)unknown.push('possible contact');
  const aim=world.shots.best(body[pb],target[pb],style),poses=[target[pb-1],...target.slice(pb,pb+aim.lifetime+1)],prediction=world.shots.evaluate(body[pb],target[pb],style,aim.yaw,aim.native_pitch,poses);
  if(prediction.assembly_uncertain||aim.radius_bound_uncertain)unknown.push('assembly/radius');
  if(prediction.hit){const due=pb+Math.ceil(prediction.player_contact_age)+world.cfg.receive_delay,damage=prediction.damage;events.push({input:release,birth:pb,due,kind:style,damage,source:'projectile'});const profile=world.recoil[style];if(profile){const direction=[Math.sin(aim.yaw),0,Math.cos(aim.yaw)];for(let t=0;t<target.length;t++)target[t]=add(target[t],mul(direction,forcedDistance(profile,t-due)))}else unknown.push('missing recoil')}
  casts.push({release,style,pb});let hp=100,earliest=null;for(const e of events.slice().sort((a,b)=>a.due-b.due)){hp-=e.damage;if(hp<=0){earliest=e.due;break}}if(earliest!==null&&(i+1===inputs.length||earliest<=inputs[i+1][0]))break;
 }
 events.sort((a,b)=>a.due-b.due);let hp=100,kill=null;for(const e of events){hp-=e.damage;if(hp<=0){kill=e.due;break}}
 for(const e of events)for(const cast of casts)if(cast.release>e.input&&world.recoil[e.kind]&&cast.pb-e.due>world.recoil[e.kind].measured_until)unknown.push('unmeasured recoil tail');
 return {kill_frame:kill,damage_events:events,target_path:target,uncertainties:[...new Set(unknown)]};
}
class D4SafeWorld extends E.D4World{
 static async create(runtime,map){const w=await E.D4World.create(runtime,map);Object.setPrototypeOf(w,D4SafeWorld.prototype);w.safe=runtime.safe_model;w.recoil=w.safe.recoil;w.shots=new SafeShots(w,w.safe);w.termCache=new Map();return w}
 visibility(path,enemy,heading){const series=Array.isArray(enemy[0]),visible=[],danger=[];for(let t=0;t<path.length;t++){const e=series?enemy[t]:enemy,p=path[t],d=sub(p,e),distance=norm(d);let v=d[0]*Math.sin(heading)+d[2]*Math.cos(heading)>=-1e-8&&distance<=this.cfg.vision_range;if(v)v=[.12,.7,1.3].some(h=>this.geometry.clear(add(e,[0,1.1,0]),add(p,[0,h,0])));visible.push(v);danger.push(v&&distance<=this.cfg.gun_range)}return {visible,danger}}
 terminal(node,enemy,speed,program,ground=false){const key=JSON.stringify([node,enemy,speed,program,ground]);if(this.termCache.has(key))return this.termCache.get(key);let term=null;const inputs=E.d4Schedule(speed,program,this.cfg);if(inputs.length){const position=ground?this.ground[node]:this.attach[node];if(norm(sub(position,enemy))<=28){const horizon=inputs.at(-1)[0]+80,body=ground?Array.from({length:horizon+1},()=>position):this.post(position,this.floor[node],horizon),r=attackSequence(this,body,enemy,inputs),kill=r.kill_frame;if(kill!==null&&!r.uncertainties.length){const used=inputs.filter(([t])=>t<=kill),cost=(kill+(ground?this.cfg.activation_frames-this.cfg.activation_drain_grace:0))*this.cfg.drain+used.reduce((s,[,k])=>s+(k==='full'?this.cfg.full_cost:this.cfg.light_cost),0);term={node,ground,speed,program,cost,kill_frame:kill,damage_events:r.damage_events,inputs:used,post:body.slice(0,kill+1),enemy_path:r.target_path.slice(0,kill+1),uncertainties:[],program_native_verified:false}}}}if(this.termCache.size>=4096)this.termCache.clear();this.termCache.set(key,term);return term}
 simulate(path,arrival,term,enemy,heading,phase=0){const c=this.cfg,target=path.map(()=>enemy);if(term.enemy_path){const count=Math.min(term.enemy_path.length,path.length-arrival);for(let t=0;t<count;t++)target[arrival+t]=term.enemy_path[t];for(let t=arrival+count;t<target.length;t++)target[t]=target[arrival+count-1]}const{visible,danger}=this.visibility(path,target,heading),due=term.damage_events.map(e=>({...e,input:arrival+e.input,birth:arrival+e.birth,due:arrival+e.due}));let hp=100,ehp=100,attacker_down=null,enemy_down=null,fireAt=phase;const pending=new Map(),bullets=[],shots=[],events=[];
  for(let t=0;t<path.length;t++){const p=path[t];hp-=pending.get(t)||0;if(hp<=0&&attacker_down===null)attacker_down=t;for(const e of due)if(e.due===t&&(attacker_down===null||e.birth<attacker_down)){ehp-=e.damage;events.push({frame:t,event:'命中'+e.damage,source:e.source})}if(ehp<=0&&enemy_down===null)enemy_down=t;if(attacker_down!==null||enemy_down!==null)break;
   if(danger[t]&&t>=fireAt){const origin=add(target[t],[0,1.1,0]),delta=sub(add(p,[0,1.1,0]),origin),d=mul(delta,1/Math.max(norm(delta),1e-12));bullets.push({birth:t+c.gun_spawn,origin,direction:d,last:origin,stopped:false});shots.push(t);fireAt=t+c.gun_interval}
   for(const b of bullets){const age=t-b.birth;if(b.stopped||age<1)continue;if(age>35){b.stopped=true;continue}const end=add(b.origin,mul(b.direction,this.gunDistance(age))),start=b.last,movement=sub(end,start),length=norm(movement),previous=path[Math.max(0,t-1)],hit=capsule(sub(start,previous),sub(end,p),.35+c.gun_radius),wall=length>1e-9?this.geometry.sphere(start,movement,c.gun_radius,Math.max(length,1e-9)):{index:-1};if(Number.isFinite(hit)&&(wall.index<0||length*hit<wall.distance-1e-6)){const travel=this.gunDistance(age-1)+length*hit;pending.set(t+c.receive_delay,(pending.get(t+c.receive_delay)||0)+this.gunDamage(travel));b.stopped=true}else if(wall.index>=0)b.stopped=true;b.last=end}
  }
  const finish=Math.min(path.length-1,...[enemy_down,attacker_down].filter(x=>x!==null))+1;return {kill:enemy_down!==null&&(attacker_down===null||enemy_down<attacker_down),attacker_down,enemy_down,exposure_frames:visible.slice(0,finish).filter(Boolean).length,danger_frames:danger.slice(0,finish).filter(Boolean).length,stealth:!visible.slice(0,finish).some(Boolean),visible,shots,events,enemy_path:target};
 }
 initialDeath(start,enemy,heading){const horizon=this.cfg.activation_frames,r=this.simulate(Array.from({length:horizon+1},()=>this.ground[start]),0,{damage_events:[],kill_frame:horizon},enemy,heading);return r.attacker_down!==null&&r.attacker_down<horizon?r.attacker_down:null}
}

const programs=['full-light','light3','light-full','full2'];
function terminalBound(w,node,enemy,speed,program,ground){
 const inputs=E.d4Schedule(speed,program,w.cfg);if(!inputs.length)return null;
 const position=ground?w.ground[node]:w.attach[node],body=t=>ground?position:w.post(position,w.floor[node],t).at(-1),[first,style]=inputs[0],cb=first+(style==='full'?4:9);
 if(![0,1,2,3].every(t=>w.shots.exclusion(body(cb+t),enemy,style)))return null;
 const events=[];
 for(const[release,kind]of inputs){const full=kind==='full',pb=release+(full?6:11),p=body(pb),horizontal=Math.max(0,Math.hypot(enemy[0]-p[0],enemy[2]-p[2])-(full?.8:0)),low=enemy[1]+.35-p[1]-(full?2.2:0),high=enemy[1]+1.3-p[1]-(full?2.2:0),distance=Math.hypot(horizontal,Math.max(low,-high,0)),col=w.shots.collision(kind),radius=Math.max(...col.OffsetArray.map((o,i)=>norm(xyz(o))+col.ParamArray[i].InitRadiusForPlayer))+.6,free=radius+(full?.03:Math.hypot(1,1.4)),travel=full?26*.8:6*2.82,velocity=full?.8:2.82;
  if(distance<=travel+free+1e-8){const age=Math.max(0,Math.ceil((distance-free-1e-8)/velocity));events.push([pb+age+w.cfg.receive_delay,full?70:35])}
 }
 events.sort((a,b)=>a[0]-b[0]);let hp=100;for(const[due,damage]of events){hp-=damage;if(hp<=0)return (due+(ground?w.cfg.activation_frames-w.cfg.activation_drain_grace:0))*w.cfg.drain+inputs.reduce((s,[t,k])=>s+(t<=due?(k==='full'?w.cfg.full_cost:w.cfg.light_cost):0),0)}return null;
}
D4SafeWorld.prototype.prepare=function(enemyIndex,headingQuadrant,speed,minHooks=0){
 const key=[enemyIndex,headingQuadrant,speed,minHooks].join(':');if(this.prepared?.key===key)return this.prepared;
 // Inverse queries visit every enemy; do not retain full paths for all states.
 this.termCache.clear();
 const enemy=this.ground[enemyIndex],heading=headingQuadrant*Math.PI/2,terms=[],n=this.g+this.h,byTerminal=Array.from({length:n},()=>[]),groundTerms=new Map(),base=new Float64Array(n).fill(inf);
 for(const ground of[false,true]){if(ground&&minHooks)continue;const count=ground?this.g:this.h;for(let node=0;node<count;node++){const pos=ground?this.ground[node]:this.attach[node];if(Math.hypot(pos[0]-enemy[0],pos[2]-enemy[2])>27)continue;for(const program of programs){const cost=terminalBound(this,node,enemy,speed,program,ground);if(cost===null||cost+(ground?0:(this.cfg.activation_frames-this.cfg.activation_drain_grace)*this.cfg.drain)>=1-1e-10)continue;const index=terms.length,t={node,ground,program,cost};terms.push(t);const id=ground?node:this.g+node;byTerminal[id].push(index);base[id]=Math.min(base[id],cost);if(ground){if(!groundTerms.has(node))groundTerms.set(node,[]);groundTerms.get(node).push(t)}}}}
 const cost=new Float64Array(this.dest.length);for(let src=0;src<n;src++)for(let e=this.ptr[src];e<this.ptr[src+1];e++)cost[e]=(this.edgeFrames[e]+(src<this.g?this.cfg.activation_frames-this.cfg.activation_drain_grace:6))*this.cfg.drain+this.cfg.hook_cost;
 const lower=[base];for(let depth=1;depth<=3;depth++){const value=base.slice();for(let src=0;src<n;src++)for(let e=this.ptr[src];e<this.ptr[src+1];e++)value[src]=Math.min(value[src],cost[e]+lower.at(-1)[this.g+this.dest[e]]);lower.push(value)}
 return this.prepared={key,enemy,heading,speed,minHooks,terms,byTerminal,groundTerms,lower,cost,actual:new Map(),prefix:new Map(),searches:new Map()};
};
D4SafeWorld.prototype.resolve=function(index,p){if(p.actual.has(index))return p.actual.get(index);const t=p.terms[index];let term=this.terminal(t.node,p.enemy,p.speed,t.program,t.ground);if(term){if(term.cost<t.cost-1e-9)throw Error('inadmissible terminal lower bound');let possible=false;for(let phase=0;phase<9;phase++)if(this.simulate(term.post,0,term,p.enemy,p.heading,phase).kill){possible=true;break}if(!possible)term=null}p.actual.set(index,term);return term};
D4SafeWorld.prototype.prefixAlive=function(edges,p){const key=edges.join(',');if(p.prefix.has(key))return p.prefix.get(key);const node=this.dest[edges.at(-1)],term={node,ground:false,post:[this.attach[node]],inputs:[],damage_events:[],kill_frame:0},r=this.route({edges},term),alive=this.simulate(r.path,r.arrival,term,p.enemy,p.heading).attacker_down===null;if(p.prefix.size>=16384)p.prefix.clear();p.prefix.set(key,alive);return alive};
D4SafeWorld.prototype.query=function(start,p,maxCandidates=0,maxExpansions=0){
 const position=this.ground[start],delta=sub(position,p.enemy),unknown=status=>({start,status,probability:null,complete:status!=='unresolved',probability_interval:[0,1]});
 if(Math.hypot(delta[0],delta[2])<.7&&Math.abs(delta[1])<1.7)return {start,status:'occupied',probability:null,complete:true};if(!(p.lower[3][start]<1-1e-10))return {start,status:'unreachable-in-declared-graph',probability:0,complete:true};
 const death=this.initialDeath(start,p.enemy,p.heading);if(death!==null)return {start,status:'dies-before-any-declared-route-can-move-or-kill',probability:0,complete:true,attacker_down:death};
 let state=p.searches.get(start);if(!state){const heap=new E.D4Heap();heap.push([p.lower[3][start],0,start,3,0,[],-1]);state={heap,tried:0};p.searches.set(start,state)}const heap=state.heap;let expansions=0,tried=0;
 while(heap.length){if(maxExpansions&&expansions++>=maxExpansions)return {...unknown('unresolved'),candidates:state.tried};const[bound,kind,node,left,spent,edges,index]=heap.pop();if(bound>=1-1e-10)continue;
  if(kind===2){const term=this.resolve(index,p),candidate={edges,terminal:index,cost:spent,remaining:1-spent},route=this.route(candidate,term),out=this.simulate(route.path,route.arrival,term,p.enemy,p.heading);state.tried++;tried++;
   if(out.kill){p.searches.delete(start);return {...candidate,start,probability:1,complete:true,status:'predicted-kill',program:term.program,inputs:term.inputs,hooks:edges.map(e=>this.dest[e]),...route,...out,route_events:route.events,damage_events:out.events,events:[...route.events,...out.events,{frame:out.enemy_down,event:'击倒 / 槽归零前'}].sort((a,b)=>a.frame-b.frame),program_native_verified:false,candidates:state.tried,model_scope:'contact-disjoint-whole-wave-clear'}}
   if(maxCandidates&&tried>=maxCandidates)return {...unknown('unresolved'),candidates:state.tried};continue;
  }
  if(kind===1){const term=this.resolve(index,p);if(!term)continue;const value=spent+term.cost;if(value<1-1e-10)heap.push([value,2,node,left,value,edges,index]);continue}
  if(edges.length&&!this.prefixAlive(edges,p))continue;
  for(const ti of p.byTerminal[node]){if(p.actual.has(ti)&&p.actual.get(ti)===null)continue;const value=spent+p.terms[ti].cost;if(value<1-1e-10)heap.push([value,1,node,left,spent,edges,ti])}
  if(!left)continue;for(let e=this.ptr[node];e<this.ptr[node+1];e++){const next=this.g+this.dest[e],value=spent+p.cost[e],estimate=value+p.lower[left-1][next];if(estimate<1-1e-10)heap.push([estimate,0,next,left-1,value,[...edges,e],-1])}
 }
 p.searches.delete(start);return {...unknown('no-contact-excluded-route; unrestricted-kill-unknown'),candidates:state.tried};
};
E.D4SafeWorld=D4SafeWorld;E.SafeShots=SafeShots;E.SafeMath={basis,rotate,capsule,axisDistance,trace,attackSequence};
})();
