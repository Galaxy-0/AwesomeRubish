"""Experimental A7 game-controller startup, outside the policy process.

Only two-player Turf on the three arena maps is exposed. Native RNG seeding
and changing equipment in an existing process are not supported here.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from .session import Session, ROOT

MAPS={1:'Vss_Yunohana',2:'Vss_District00',3:'Vss_Yagara'}


def validate_runtime(host,patched):
    host=Path(host).resolve();patched=Path(patched).resolve()
    manifest=json.loads(host.with_suffix('.build.json').read_text())
    if hashlib.sha256(host.read_bytes()).hexdigest()!=manifest['output_sha256']:
        raise ValueError('A7 host identity mismatch')
    for name,digest in manifest['source_sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('A7 host source identity mismatch: '+name)
    gates={int(row.split('\t')[1]) for row in (patched/'main.obs.tsv').read_text().splitlines() if row and not row.startswith('#')}
    if not set(range(33,44))<=gates:raise ValueError('A7 scene gates missing')
    if os.environ.get('DM_TEST_SPECIAL'):raise ValueError('A7 arena startup rejects DM_TEST_SPECIAL')
    return host,patched


def write_control(path,stage,mode=0):
    if stage not in MAPS or mode!=0:raise ValueError('A7 currently supports Turf on arena maps only')
    path=Path(path);temporary=path.with_name(path.name+'.tmp')
    temporary.write_text(f'A7v1 {MAPS[stage]} {mode} 0 1\n')
    temporary.replace(path) # The native reader must never see a partial payload.


def room_ready(texts):
    states=[]
    for text in texts:
        rows=re.findall(r'LDN state=(\d+) node=(-?\d+) nodes=(\d+) session=(\w+)',text)
        roots=re.findall(r'\bA7_NET_ROOT\b[^\n]*\bstate=(\d+)',text)
        if not rows or not roots or roots[-1]!='34':return False
        states.append(rows[-1])
    return (len(states)==2 and states[0][:3]==('3','0','2') and
            states[1][:3]==('5','1','2') and states[0][3]==states[1][3])


class NativeSession(Session):
    """Session ownership/clock/protocol are unchanged; replace startup only."""
    def __init__(self,*,host,stage_id,**config):
        if config['players']!=2 or config['mode']!=0 or stage_id not in MAPS:
            raise ValueError('A7 currently supports two-player arena Turf')
        self.native_host=Path(host).resolve();self.native_stage=stage_id
        self.generation=0;self.pending_repeat=False
        super().__init__(stage_id=stage_id,**config)

    def host_command(self):return [str(self.native_host),str(self.patched)]

    def host_options(self,player):
        return super().host_options(player)|dict(DM_KEYS='',DM_SCENE_BOOT='LobbyLocal',
            DM_RL_WAIT_INGAME='1',
            DM_SCENE_UPPER='1',DM_SCENE_DIRECT='create' if player==0 else 'join',
            DM_SCENE_MATCH=str(self.out/'go'),DM_SCENE_TRACE_FLOW='1',DM_SCENE_TRACE_NETWORK='1',
            DM_PROBE='main:14f44cc@x1,main:3db55d0,main:3dcc710,main:3dd9370,main:3571e24@x21+e8',
            DM_NVN_SHMAP=str(ROOT/'upstream/dm/games/0100C2500FC20000/shader_map.tsv'))

    def texts(self):return [self.text(n) for n in (0,1)]

    def status(self):
        """Read native evidence; never derive a game phase from driver intent."""
        result=[]
        for n,process,_ in self.hosts:
            text=self.text(n)
            scenes=re.findall(r'A7_SCENE request=\d+ destination=(\S+)',text)
            phases=re.findall(r'PROBE main\+0x(3db55d0|3dcc710|3dd9370)',text)
            result.append(dict(player=n,pid=process.pid,scene=scenes[-1] if scenes else None,
                last_match_phase={'3db55d0':'ingame','3dcc710':'judge','3dd9370':'winners'}.get(phases[-1]) if phases else None))
        return dict(generation=self.generation,players=result)

    def start(self):
        if self.pending_repeat:
            self._return_and_rebuild();self.pending_repeat=False
        else:
            log=(self.out/'air.log').open('wb');self.streams.append(log)
            self.air=subprocess.Popen([sys.executable,str(ROOT/'tools/ldn/air.py'),'--socket',str(self.air_socket)],stdout=log,stderr=subprocess.STDOUT)
            self.until(self.air_socket.exists);self.spawn(0)
            self.until(lambda:'create player=0 ' in (self.out/'air.log').read_text());self.spawn(1)
        self.until(lambda:room_ready(self.texts()))
        control=self.out/('go' if not self.generation else f'go.{self.generation}')
        counts=[text.count('PROBE main+0x3db55d0') for text in self.texts()]
        fixes=self.text(0).count('A7_MATCH native_fix_complete ')
        write_control(control,self.native_stage,self.mode)
        self.until(lambda:all(f'generation={self.generation} ' in text[text.rfind('A7_MATCH configured '):] for text in self.texts()))
        Path(str(control)+'.fix').touch()
        self.until(lambda:self.text(0).count('A7_MATCH native_fix_complete ')>fixes)
        (self.out/'load-slots/active').touch();Path(str(control)+'.command').touch()
        self.until(lambda:all(text.count('PROBE main+0x3db55d0')>counts[n] for n,text in enumerate(self.texts())))

    def _return_and_rebuild(self):
        # Called only after the old clients release at paired Winners. New
        # phase evidence must follow native scene teardown/recreation.
        old=self.out/('go' if not self.generation else f'go.{self.generation}')
        Path(str(old)+'.return').touch();self.generation+=1
        self.until(lambda:all(f'A7_REPEAT returned generation={self.generation} ' in text for text in self.texts()))
        (self.out/f'go.{self.generation}.rebuild').touch()
        marker=f'A7_REPEAT returned generation={self.generation} '
        self.until(lambda:all('A7_UPPER initialize ' in text[text.rfind(marker):] for text in self.texts()))
        self.until(lambda:room_ready([text[text.rfind(marker):] for text in self.texts()]))


class NativeSessionPool:
    """One coordinator-owned reusable room; equipment changes rebuild it.

    Pass acquire/release to NativeParallelEnv. The owner must close the pool,
    including on cancellation. No session is retained on incomplete results.
    """
    def __init__(self,host,patched):
        self.host,self.patched=validate_runtime(host,patched);self.held=None
        self.identity=None;self.starts=0;self.reuses=0

    @staticmethod
    def equipment(config):
        return json.dumps({key:config.get(key) for key in ('players','mode','weapons','loadouts','clock_mode','state_dump','stall_timeout')},sort_keys=True)

    def acquire(self,**config):
        if config['players']!=2 or config['mode']!=0 or config['stage_id'] not in MAPS:
            raise ValueError('A7 currently supports two-player arena Turf')
        equipment=self.equipment(config)
        if self.held and equipment!=self.identity:self.close()
        if self.held:
            session=self.held;self.held=None;self.reuses+=1
            session.native_stage=config['stage_id'];session.pending_repeat=True
            session.started=time.monotonic();session.timeout=config['timeout']
        else:
            config['patched']=self.patched
            session=NativeSession(host=self.host,**config);self.starts+=1
        self.identity=equipment
        return session

    def release(self,session,infos):
        if (len(infos)==2 and all(info.get('phase')==3 and info.get('score_valid') for info in infos.values())
            and all(process.poll() is None for _,process,_ in session.hosts)):
            if self.held:raise RuntimeError('native room lease collision')
            self.held=session
        else:session.close()

    def close(self):
        if self.held:
            session=self.held;self.held=None;session.close()
