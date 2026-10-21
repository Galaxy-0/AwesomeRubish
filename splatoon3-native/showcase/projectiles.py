"""Own readonly native projectile positions, exported as primitive replay data.

No resource/model/texture. Cache is ignored work/ and binds the closed host hashes.
"""
import hashlib,json,math,re
from pathlib import Path
PAT=re.compile(r'D3R_PROJECTILE frame=(\d+) kind=(\w+) object=(0x[0-9a-f]+) vtable=([0-9a-f]+) velocity=([^ ]+) p110=([^ ]+) readonly=1')
VT={'5c76df0':('full',.5),'5c75510':('light',.3),'5c79398':('gun',.285)}

def augment(root,source,clip):
    result=source(clip['evidence']['result']);run=json.loads(result.read_text());schema='showcase.projectiles.v1';tool_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest();cache=root/'work/showcase/projectile-cache'/(result.parent.name+'.json');raw=run['raw_sha256'];session=Path(run['session']);binding={str(session/f'player-{n}/host.log'):raw[str(session/f'player-{n}/host.log')]for n in[0,1]};key=dict(schema=schema,tool_sha256=tool_hash,closed_host_sha256=binding,start=clip['start_frame'],end=clip['end_frame'])
    if cache.exists()and json.loads(cache.read_text())['binding']==key:data=json.loads(source(cache).read_text())
    else:
        rows=[json.loads(line)for line in source(result.with_name('steps.jsonl')).open()];rs=next(i for i,r in enumerate(rows)if r['label'].endswith('-RS'));infos=rows[rs]['infos'];groups=[]
        for role in[0,1]:
            offset=infos['player_0']['frame']-infos[f'player_{role}']['frame'];objects={}
            with (session/f'player-{role}/host.log').open(errors='replace')as stream:
                for line in stream:
                    match=PAT.search(line)
                    if not match or match[4]not in VT:continue
                    if(role==0 and match[4]not in['5c76df0','5c75510'])or(role==1 and match[4]!='5c79398'):continue
                    frame=int(match[1])+offset
                    if not clip['start_frame']<=frame<=clip['end_frame']:continue
                    velocity=list(map(float,match[5].split(',')));position=list(map(float,match[6].split(',')))
                    if not all(math.isfinite(v)and abs(v)<1000 for v in position):continue
                    ident=(match[3],match[4]);current=objects.get(ident)
                    if current is None or frame-current['last_frame']>45:
                        own=clip['players'][role]['states']
                        pose=min(own,key=lambda s:abs(s[0]-frame))if own else None
                        if pose is None or math.dist(position,pose[2:5])>6:continue
                        current=dict(who='alpha'if role==0 else'bravo',kind=VT[match[4]][0],radius=VT[match[4]][1],first_frame=frame,last_frame=frame,states={},has_birth=False);objects[ident]=current;groups.append(current)
                    current['last_frame']=frame;current['has_birth']|=match[2]=='setter_input'and sum(v*v for v in velocity)>.5
                    # Getter after the native movement provides the newest pose
                    # of that same frame; keep the last logged own position.
                    current['states'][frame]=[frame,*[round(v,4)for v in position]]
        output=[]
        for g in groups:
            states=[g['states'][f]for f in sorted(g['states'])]
            if not g['has_birth']or len(states)<2:continue
            # Pool reuse or uninitialized non-world position must not create a
            # fake line across the map. Split at implausible per-frame jumps.
            segments=[[]]
            for s in states:
                if segments[-1]and math.dist(s[1:],segments[-1][-1][1:])>12*max(1,s[0]-segments[-1][-1][0]):segments.append([])
                segments[-1].append(s)
            for ss in segments:
                if len(ss)>=2:output.append(dict(who=g['who'],kind=g['kind'],radius=g['radius'],states=ss,provenance='readonly native getter/setter own projectile+110; no reconstructed ballistic integration'))
        data=dict(binding=key,projectiles=output,position_semantics='Per-native-frame last logged own projectile position. Normalized beta clock by constant initial controlled-frame offset. Position jumps split, never joined. Core markers are self-drawn, not native weapon models.');cache.parent.mkdir(parents=True,exist_ok=True);cache.write_text(json.dumps(data,separators=(',',':'))+'\n');source(cache)
    clip['projectiles']=data['projectiles'];clip['projectile_semantics']=data['position_semantics'];clip['evidence']['projectile_cache']=str(cache.relative_to(root))
    for p in clip['projectiles']:
        if p['who']=='alpha':clip['annotations'].append(dict(frame=p['states'][0][0],label='满蓄弹体生成'if p['kind']=='full'else'轻斩弹体生成',kind='projectile',evidence='native own projectile position/vector type'))
    full=[p for p in clip['projectiles']if p['who']=='alpha'and p['kind']=='full']
    for e in clip['annotations']:
        if e['kind']=='hit'and any(p['states'][0][0]<=e['frame']<=p['states'][-1][0]+8 for p in full):e.update(label='满蓄70窗口 / HP确认',evidence='native full projectile lifetime and target HP readback; isolated firing window')
    clip['annotations'].sort(key=lambda e:e['frame']);return clip
