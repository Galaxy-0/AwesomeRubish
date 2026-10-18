"""Own exactly one native room and its processes; reuse M5's tested routes."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

from tools.private_battle import BUTTONS, host_environment, configure_room, prepare_match
from tools.m5_resources import Monitor
from .clock import SharedClock

ROOT = Path(__file__).resolve().parents[1]
SAVE_HASH = '89286f20dcf3305017dac3575e20ae094808d97fe8261d4e40a41e67fa21f1cd'
FAILURE = re.compile(r'CRASH|FATAL|GPU.*(?:执行错误|execution error)|内存看门狗')


def catalogs():
    # Local BYML package already used by M4/M5. No remote catalog or game data.
    from tools.byml import read
    def table(name):
        return read(subprocess.check_output(['zstd','-dc',str(ROOT/f'work/data/v720896/RomFS/RSDB/{name}.Product.b30.rstbl.byml.zs')]))
    stages = sorted((r for r in table('VersusSceneInfo') if r['IsDisplayInStageList']),key=lambda r:r['DisplayOrder'])
    return stages, {r['Id'] for r in table('WeaponInfoMain') if r['Type'] == 'Versus'}


class Session:
    def __init__(self, players, mode, stage_id, weapons, timeout=2400, patched=None, state_dump=False):
        if players not in (2,8): raise ValueError('M6 supports 2 or 8 players')
        if mode not in range(5): raise ValueError('mode must be 0..4')
        stages, weapon_ids = catalogs()
        matches = [i for i,r in enumerate(stages) if r['Id'] == stage_id]
        if not matches: raise ValueError('stage_id is not a displayed local Versus stage')
        if len(weapons) != players or any(w not in weapon_ids for w in weapons): raise ValueError('one Versus weapon ID required per player')
        self.players,self.mode,self.stage_index,self.weapons = players,mode,matches[0],weapons
        self.timeout=timeout;self.started=time.monotonic();self.last_sample=0;self.last_print=0
        self.state_dump=state_dump
        self.out=ROOT/'work/tests'/datetime.datetime.now().strftime(f'm6-{players}p-%Y%m%d-%H%M%S-%f')
        self.out.mkdir(parents=True);(self.out/'load-slots').mkdir()
        self.tmp=tempfile.TemporaryDirectory(prefix='s3-rl-')
        self.socket_dir=Path(self.tmp.name);self.air_socket=self.socket_dir/'air.sock'
        self.clock=SharedClock(self.socket_dir/'clock.bin')
        self.patched=Path(patched) if patched else ROOT/'work/build/patched_v720896'
        self.hosts=[];self.streams=[];self.fifos={};self.air=None;self.closed=False
        self.monitor=Monitor(self.out)
        self.seed=ROOT/'work/save_ref/save.dat'
        self.original=ROOT.parent/'splatoon-rl-lab/saves/bis/user/save/0000000000000001/0/save.dat'
        self.check_saves()
        print(f'M6 session: {self.out}',flush=True)

    def check_saves(self):
        for path in (self.seed,self.original):
            if hashlib.sha256(path.read_bytes()).hexdigest()!=SAVE_HASH: raise RuntimeError(f'reference hash changed: {path}')

    def text(self, player): return (self.out/f'player-{player}/host.log').read_text(errors='replace')

    def frame(self, player):
        rows=re.findall(r'RESOURCE_FRAME frame=(\d+)',self.text(player))
        return int(rows[-1]) if rows else 0

    def tick(self, sleep=True):
        if time.monotonic()-self.started>self.timeout: raise TimeoutError('M6 session deadline exceeded')
        if self.air and self.air.poll() is not None: raise RuntimeError('local air service exited')
        for player,process,_ in self.hosts:
            if process.poll() is not None or FAILURE.search(self.text(player)):
                raise RuntimeError(f'player-{player}: early exit/runtime failure {process.poll()}')
        now=time.monotonic()
        if now-self.last_sample>2:
            self.monitor.sample(self.hosts);self.last_sample=now
        if now-self.last_print>30:
            print(f'M6 {now-self.started:.0f}s frames='+str({n:self.frame(n) for n,_,_ in self.hosts}),flush=True);self.last_print=now
        if sleep: time.sleep(.1)

    def until(self, predicate):
        while not predicate():self.tick()

    def frames(self, player, count=120):
        target=self.frame(player)+count;self.until(lambda:self.frame(player)>=target)

    def send(self, player, button):
        self.fifos[player].write(f'{BUTTONS[button]:x} 0 0 0 0 0 0 0 0.35\n');self.fifos[player].flush()

    def press(self, player, button):self.send(player,button);self.frames(player)

    def spawn(self, player):
        directory=self.out/f'player-{player}';directory.mkdir()
        for name in ('save','temp'):(directory/name).mkdir()
        shutil.copyfile(self.seed,directory/'save/save.dat')
        os.mkfifo(directory/'controller.fifo',0o600)
        env=host_environment(ROOT,self.out,directory,player,self.players,self.air_socket,self.weapons)
        env.update(DM_RL_SOCKET=str(self.socket_dir/f'player-{player}.sock'),DM_RL_CLOCK_FILE=str(self.clock.path),DM_HID_TRACE='1',
                   DM_PROBE='main:3db55d0,main:3dcc710,main:3dd9370,main:3571e24@x21+e8')
        if self.state_dump:
            env['DM_RL_STATE_DUMP']='1'
            env['DM_PROBE']+=',main:3ef6930@x0+140,main:292075c@x0+88,main:2920760@x0+f00,main:3f2d700@x0+4c,main:3f71a6c@x19+c10'
        (directory/'input.json').write_text(json.dumps({k:v for k,v in env.items() if k.startswith('DM_')},indent=2)+'\n')
        log=(directory/'host.log').open('wb');self.streams.append(log)
        process=subprocess.Popen([str(ROOT/'upstream/dm/host/dmhost'),str(self.patched)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        self.hosts.append((player,process,directory))
        self.fifos[player]=os.fdopen(os.open(directory/'controller.fifo',os.O_RDWR|os.O_NONBLOCK),'w',buffering=1)

    def start(self):
        log=(self.out/'air.log').open('wb');self.streams.append(log)
        self.air=subprocess.Popen([sys.executable,str(ROOT/'tools/ldn/air.py'),'--socket',str(self.air_socket)],stdout=log,stderr=subprocess.STDOUT)
        self.until(self.air_socket.exists);self.spawn(0)
        airtext=lambda:(self.out/'air.log').read_text()
        self.until(lambda:'create player=0 ' in airtext());self.until(lambda:self.frame(0)>=4200)
        for player in range(1,self.players):
            self.spawn(player)
            self.until(lambda:re.search(rf'join player={player} host=0 session=(\w+) nodes={player+1}',airtext()))
            self.until(lambda:self.frame(player)>=4800);self.frames(0,300)
        self.frames(0,600)
        sessions=re.findall(r'create player=0 session=(\w+)',airtext());session=sessions[-1]
        for n,_,_ in self.hosts:
            states=re.findall(r'LDN state=(\d+) node=(-?\d+) nodes=(\d+) session=(\w+)',self.text(n))
            expected=(str(3 if n==0 else 5),str(n),str(self.players),session[:8])
            if not states or states[-1]!=expected:raise RuntimeError(f'player-{n} incomplete native room')
        configure_room(self,self.players,self.mode,self.stage_index);prepare_match(self,self.players)
        self.until(lambda:all('PROBE main+0x3db55d0' in self.text(n) for n,_,_ in self.hosts))

    def close(self):
        if self.closed:return
        self.closed=True;errors=[]
        self.clock.resume()
        for _,p,_ in self.hosts:
            if p.poll() is None:p.terminate()
        deadline=time.monotonic()+12
        for n,p,_ in self.hosts:
            try:p.wait(max(0,deadline-time.monotonic()))
            except subprocess.TimeoutExpired:p.kill();p.wait();errors.append(f'player-{n}: forced kill')
            if p.returncode or '优雅退出完成' not in self.text(n):errors.append(f'player-{n}: unclean exit {p.returncode}')
        if self.air and self.air.poll() is None:self.air.terminate();self.air.wait(5)
        for stream in [*self.fifos.values(),*self.streams]:stream.close()
        self.check_saves()
        (self.out/'resources-summary.json').write_text(json.dumps(self.monitor.summary(),indent=2)+'\n')
        self.clock.close()
        self.tmp.cleanup()
        if errors:raise RuntimeError('; '.join(errors))
