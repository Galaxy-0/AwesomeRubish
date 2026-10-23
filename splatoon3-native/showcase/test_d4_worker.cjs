/* Presentation dispatcher regression; no game data, browser, or numeric model needed. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/d4_worker.js','utf8');
const dispatcher=source.slice(source.indexOf("if(typeof self!=='undefined'"));
async function run(initialRows=[],cancel=false){
 const calls=[],messages=[];
 const ground=[[0,0,0],[3,0,0],[6,0,0],[9,0,0]];
 const result=i=>({probability:i===1?1:null,complete:i!==2,remaining:i===1?.5:undefined,stealth:i===1,status:i===1?'predicted-kill':i===2?'unresolved':'excluded-from-native-setup-domain',exposure_frames:i===1?0:undefined});
 const world={g:4,map:{id:'fixture'},ground,prepare:()=>({}),query:(i,p,candidates,expansions)=>{calls.push({i,candidates,expansions});return result(i)}};
 const self={postMessage:m=>{messages.push(m);if(cancel&&m.type==='progress'&&m.rows?.length)self.onmessage({data:{type:'cancel'}})}};
 vm.runInNewContext(dispatcher,{self,D4Engine:{D4SafeWorld:{create:async()=>world}},performance,setTimeout});
 await self.onmessage({data:{type:'init',id:0,runtime:{safe_model:true,maps:[world.map]}}});
 await self.onmessage({data:{type:'heat',id:1,map:'fixture',enemy:0,heading:0,speed:40,ordinary:[false,true,false,true],initialRows}});
 return {calls,messages,result};
}
(async()=>{
 const full=await run(),final=full.messages.find(m=>m.type==='heat');
 assert.deepEqual(full.calls.map(c=>c.i),[1,3,0,2],'ordinary supported first, then distance');
 assert(full.calls.every(c=>c.candidates===100&&c.expansions===1000),'model search budgets unchanged');
 assert.deepEqual(Array.from(final.rows,r=>r.start),[0,1,2,3],'final rows retain original grid indices');
 assert.equal(final.rows[2].complete,false,'bounded unresolved remains unresolved');
 assert.equal(final.rows[0].probability,null,'excluded scope stays unknown');
 const chunks=full.messages.filter(m=>m.type==='progress');
 assert.equal(chunks[0].done,0);assert.equal(chunks.at(-1).done,4);
 assert.deepEqual(chunks.flatMap(m=>Array.from(m.rows,r=>r.start)),[1,3,0,2],'every row streams once');
 assert(chunks.some(m=>m.ordinary_done&&m.done===2),'ordinary phase is exposed before extra heights');
 const resume=await run([final.rows[1]]);
 assert(!resume.calls.some(c=>c.i===1),'cached row is not recomputed');
 assert.deepEqual(JSON.parse(JSON.stringify(resume.messages.find(m=>m.type==='heat').rows)),JSON.parse(JSON.stringify(final.rows)),'resumed pass preserves all row results');
 const cancelled=await run([],true);
 assert(!cancelled.messages.some(m=>m.type==='heat'),'cancelled pass cannot publish a final heatmap');
 assert(cancelled.messages.some(m=>m.type==='cancelled'));
 console.log('D4 presentation dispatcher: priority, progressive rows, budgets, unknowns, cache resume, cancellation passed');
})().catch(e=>{console.error(e);process.exitCode=1});
