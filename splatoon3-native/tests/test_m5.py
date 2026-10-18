#!/usr/bin/env python3
"""M5 staged admission, real native private games, and local resource evidence."""
import argparse
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

from test_m1 import ROOT, FAILURE
from test_m2 import SAVE_SHA256
from test_m4 import enters, recognize, MODES
sys.path.insert(0, str(ROOT/'tools'))
from m5_resources import Monitor, system_sample

BUTTONS = dict(zip(('A','B','X','Y','LS','RS','L','R','ZL','ZR','Plus','Minus','Left','Up','Right','Down'),
                   (1 << n for n in range(16))))
PROBES = 'main:3db55d0,main:3dcc710,main:3dd9370,main:3571e24@x21+e8'


class Run:
    def __init__(self, args):
        self.args=args
        self.out=ROOT/'work/tests'/datetime.datetime.now().strftime(f'm5-{args.players}p-%Y%m%d-%H%M%S-%f')
        self.out.mkdir(parents=True); (self.out/'load-slots').mkdir(); print(f'M5 artifacts: {self.out}', flush=True)
        self.hosts=[]; self.streams=[]; self.fifos={}; self.air=None
        self.started=time.monotonic(); self.last_sample=0; self.last_print=0
        self.monitor=Monitor(self.out); self.result=dict(milestone='M5', players=args.players, passed=False, errors=[], requested_mode=MODES[args.mode], requested_stage_id=args.stage_id, requested_stage_row=args.stage_row)
        self.seed=ROOT/'work/save_ref/save.dat'
        self.original=ROOT.parent/'splatoon-rl-lab/saves/bis/user/save/0000000000000001/0/save.dat'

    def text(self, player): return (self.out/f'player-{player}/host.log').read_text(errors='replace')
    def frame(self, player):
        rows=re.findall(r'RESOURCE_FRAME frame=(\d+)', self.text(player))
        return int(rows[-1]) if rows else 0

    def tick(self):
        if time.monotonic()-self.started > self.args.timeout: raise TimeoutError('M5 deadline exceeded')
        for player,p,d in self.hosts:
            if p.poll() is not None or FAILURE.search(self.text(player)):
                raise RuntimeError(f'player-{player}: early exit/runtime failure {p.poll()}')
        if time.monotonic()-self.last_sample > 2:
            self.monitor.sample(self.hosts); self.last_sample=time.monotonic()
        if time.monotonic()-self.last_print > 20:
            print(f'M5 {time.monotonic()-self.started:.0f}s '+str({n:self.frame(n) for n,_,_ in self.hosts}), flush=True)
            self.last_print=time.monotonic()
        time.sleep(.5)

    def until(self, predicate):
        while not predicate(): self.tick()

    def frames(self, player, count=120):
        target=self.frame(player)+count
        self.until(lambda:self.frame(player)>=target)

    def send(self, player, button):
        self.fifos[player].write(f'{BUTTONS[button]:x} 0 0 0 0 0 0 0 0.35\n'); self.fifos[player].flush()
        with (self.out/'controller.jsonl').open('a') as f:
            f.write(json.dumps(dict(seconds=time.monotonic()-self.started, player=player, button=button, frame=self.frame(player)))+'\n')

    def press(self, player, button, settle=120):
        self.send(player,button); self.frames(player,settle)

    def spawn(self, player, sock):
        d=self.out/f'player-{player}';d.mkdir()
        for name in ('save','temp'): (d/name).mkdir()
        shutil.copyfile(self.seed,d/'save/save.dat')
        fifo=d/'controller.fifo';os.mkfifo(fifo,0o600)
        route=(ROOT/'tools/routes/m2-local-lobby.keys').read_text().strip()
        if self.args.players>1: route+=',f2700:A'+(',f3300:Y,f3900:A' if player==0 else ',f3900:A,f4500:A')
        env={k:v for k,v in os.environ.items() if not k.startswith('DM_')}
        env.update(DM_ROOT=str(ROOT/'work'), DM_ROMFS=str(ROOT/'work/data/v720896/RomFS'),
            DM_SAVE=str(d/'save'), DM_TEMP=str(d/'temp'), DM_MSL_DIR=str(ROOT/'work/build/cache/metal_shader_cache'),
            DM_FONT_DIR=str(ROOT/'work/build/font'), DM_PLAYER=str(player), DM_FULL_UNLOCK='1',
            DM_HEADLESS='1', DM_WINDOW='1', DM_OPMODE='0', DM_RESOURCE_REPORT='1',
            DM_MEM_CAP_GB='0', DM_MEMSTAT=str(d/'memory.tsv'), DM_MEMSTAT_DUMP='90', DM_KEYS=route,
            DM_PIPELINE_CACHE=str(ROOT/'work/build/cache/runtime-pipelines'), DM_LOAD_SLOTS=str(self.out/'load-slots'), DM_HID_FIFO=str(fifo), DM_PROBE=PROBES, DM_WATCH_STALL='180', DM_WATCH_SAMPLE=str(d/'stall.txt'),
            DM_NVN_SHOT=','.join(map(str,range(2400,180001,600)))+':'+str(d/'frame_%d.png'))
        if self.args.visible and player==0: env['DM_HEADLESS']='0'
        if self.args.weapons: env['DM_WEAPON']=str(self.args.weapons[player])
        if sock: env['DM_LDN_AIR']=str(sock)
        else: env['DM_LDN_FRONTEND']='1'
        (d/'input.json').write_text(json.dumps({k:v for k,v in env.items() if k.startswith('DM_')},indent=2)+'\n')
        log=(d/'host.log').open('wb');self.streams.append(log)
        p=subprocess.Popen([str(ROOT/'upstream/dm/host/dmhost'),str(ROOT/'work/build/patched_v720896')],
            cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        self.hosts.append((player,p,d))
        # Open the FIFO in nonblocking read/write mode: startup cannot hang on a
        # game that crashes before its reader starts. Only this run owns it.
        fd=os.open(fifo,os.O_RDWR|os.O_NONBLOCK)
        self.fifos[player]=os.fdopen(fd,'w',buffering=1)

    def execute(self):
        for path in (self.seed,self.original):
            if hashlib.sha256(path.read_bytes()).hexdigest()!=SAVE_SHA256: raise ValueError('reference hash mismatch')
        if self.args.players==1:
            self.spawn(0,None);self.until(lambda:self.frame(0)>=4200)
            self.frames(0,1800);self.monitor.snapshot(self.hosts,'lobby')
            self.result['lobby_only']=True;return
        with tempfile.TemporaryDirectory(prefix='s3-m5-') as tmp:
            sock=Path(tmp)/'air.sock'
            log=(self.out/'air.log').open('wb');self.streams.append(log)
            self.air=subprocess.Popen([sys.executable,str(ROOT/'tools/ldn/air.py'),'--socket',str(sock)],stdout=log,stderr=subprocess.STDOUT)
            self.until(sock.exists)
            self.spawn(0,sock)
            self.until(lambda:'create player=0 ' in (self.out/'air.log').read_text())
            self.until(lambda:self.frame(0)>=4200)
            # Launch sequentially and wait for each newcomer to finish its large
            # boot transition and join. No simultaneous cold-load peaks.
            for player in range(1,self.args.players):
                self.spawn(player,sock)
                self.until(lambda:re.search(rf'join player={player} host=0 session=(\w+) nodes={player+1}',(self.out/'air.log').read_text()))
                self.until(lambda:self.frame(player)>=4800)
                self.frames(0,300)
                self.monitor.snapshot(self.hosts,f'joined-{player+1}')
            self.frames(0,600)
            self.monitor.snapshot(self.hosts,'lobby')
            airtext=(self.out/'air.log').read_text()
            sessions=re.findall(r'create player=0 session=(\w+)',airtext)
            if not sessions:raise RuntimeError('no native room session')
            session=sessions[-1];membership=[]
            for n,_,d in self.hosts:
                states=re.findall(r'LDN state=(\d+) node=(-?\d+) nodes=(\d+) session=(\w+)',self.text(n))
                expected=(str(3 if n==0 else 5),str(n),str(self.args.players),session[:8])
                if not states or states[-1]!=expected:raise RuntimeError(f'player-{n}: membership differs from complete room')
                membership.append(dict(player=n,state=list(states[-1])))
            self.result.update(session=session,membership=membership,same_room=True)
            if self.args.admission_only: self.result['admission_only']=True;return
            # Native room settings: focused Mode, then Stage (4 columns x 3
            # rows per page; Random is the extra cell to the left).
            for _ in range(self.args.mode): self.press(0,'Right')
            self.press(0,'Down');self.press(0,'A')
            page,cell=divmod(self.args.stage_index,12);row,col=divmod(cell,4)
            for _ in range(page):self.press(0,'R')
            self.press(0,'Right')
            for _ in range(col):self.press(0,'Right')
            for _ in range(row):self.press(0,'Down')
            self.press(0,'A');self.press(0,'Down');self.press(0,'A')
            self.frames(0,600)  # The first row is not active during the team-panel transition.
            # Team rows begin Random; Right => Alpha, another Right => Bravo.
            for player in range(self.args.players):
                self.press(0,'Right')
                if player>=self.args.players//2:self.press(0,'Right')
                self.press(0,'Down')
            self.frames(0,600)
            team_shots=sorted((self.out/'player-0').glob('frame_*.png'),key=lambda p:int(p.stem.split('_')[1]))
            self.result['team_screenshot']=str(team_shots[-1])
            self.press(0,'A');self.frames(0,900)
            # Confirm all controllers together: sequential 300-frame waits for
            # eight players can exceed the native preparation deadline.
            (self.out/'load-slots/active').touch()
            for player in range(self.args.players):self.send(player,'A')
            self.frames(0,300)
            self.until(lambda:all(enters(self.text(n),'3db55d0') for n,_,_ in self.hosts))
            self.frames(0,600);self.monitor.snapshot(self.hosts,'in-game')
            self.until(lambda:all(enters(self.text(n),'3dd9370') for n,_,_ in self.hosts))
            self.frames(0,1200);self.monitor.snapshot(self.hosts,'results')
            airtext=(self.out/'air.log').read_text()
            received={str(n):max(map(int,re.findall(rf'recv player={n} frames=(\d+) session={session}',airtext)),default=0) for n,_,_ in self.hosts}
            self.result['received_frames_lower_bound']=received
            if not all(received.values()):raise RuntimeError('some peers have no actual PIA receive evidence')

    def finish(self):
        evidence=[]
        # Stop every owned host before waiting: a critical-pressure stop must
        # not leave seven peers allocating while the first host shuts down.
        for _,p,_ in self.hosts:
            if p.poll() is None:p.terminate()
        deadline=time.monotonic()+12
        for n,p,d in self.hosts:
            try:p.wait(max(0,deadline-time.monotonic()))
            except subprocess.TimeoutExpired:p.kill();p.wait();self.result['errors'].append(f'player-{n}: forced kill')
            text=self.text(n)
            if p.returncode or '优雅退出完成' not in text or FAILURE.search(text):self.result['errors'].append(f'player-{n}: unclean exit {p.returncode}')
            uid=re.findall(rf'SPL3_PLAYER_UID player={n} uid=([0-9a-f:]+)',text)
            nick=re.findall(rf'SPL3_PLAYER_NICK player={n} nickname=(\S+)',text)
            if not uid or not nick or any(v!=f'RL-{n}' for v in nick):self.result['errors'].append(f'player-{n}: native identity readback missing')
            points=[(int(f),float(t)) for f,t in re.findall(r'RESOURCE_FRAME frame=(\d+) seconds=([\d.]+)',text)]
            fps=[60/(b[1]-a[1]) for a,b in zip(points,points[1:]) if b[0]-a[0]==60 and b[1]>a[1]]
            game=enters(text,'3db55d0');judge=enters(text,'3dcc710');winners=enters(text,'3dd9370')
            evidence.append(dict(player=n,native_uid=uid,native_nick=nick,returncode=p.returncode,last_frame=self.frame(n),in_game=game,result_judge=judge,result_winners=winners,
                frame_intervals_fps=fps,headless='HEADLESS window=0 internal_render=1' in text,
                no_screen_composite='出图裁切：' not in text and '出图视口' not in text,
                crop_720p='WindowCrop 0,0 1280x720' in text,
                continued_render=bool(re.search(r'HEADLESS frame=\d+ passes=[1-9]\d* draws=[1-9]\d* screen_submits=0 composite=0',text))))
            if not self.args.admission_only and self.args.players>1 and (not game or not judge or not winners or judge[-1]-game[0]<178):
                self.result['errors'].append(f'player-{n}: missing complete native game/results')
            if self.args.weapons:
                kits=re.findall(r'PROBE main\+0x3571e24 .*?\[x21\+0xe8\]=([0-9a-f]{32})',text)
                ids=[int.from_bytes(bytes.fromhex(k)[:4],'little') for k in kits]
                evidence[-1].update(requested_weapon=self.args.weapons[n],native_weapon_ids=ids)
                if not ids or any(w!=self.args.weapons[n] for w in ids):self.result['errors'].append(f'player-{n}: native kit did not use requested weapon')
            phase_stats={}
            for phase in ('boot','lobby','loading','in_game','judging','results'):
                rows=[(r,h) for r in self.monitor.rows for h in r['hosts'] if h['player']==n and h.get('phase')==phase]
                clocks={h['clock']:h['frame'] for _,h in rows if h['clock'] is not None}
                if len(clocks)>1:
                    t0,t1=min(clocks),max(clocks)
                    steady=(rows[10:] or rows) if phase in ('lobby','in_game','results') else rows
                    phase_stats[phase]=dict(fps=(clocks[t1]-clocks[t0])/(t1-t0),
                        max_footprint_mib=max(h['memory'].get('phys_footprint',0) for _,h in steady),
                        max_rss_mib=max(h['memory'].get('rss',0) for _,h in steady),
                        max_clean_file_mib=max(h['memory'].get('clean_file_resident',0) for _,h in steady))
                    if phase in ('lobby','in_game') and phase_stats[phase]['max_footprint_mib']>6144:
                        self.result['errors'].append(f'player-{n}: steady footprint above 6 GiB in {phase}')
            evidence[-1]['phases']=phase_stats
            if not self.args.visible or n!=0:
                if not all(evidence[-1][k] for k in ('headless','no_screen_composite','continued_render','crop_720p')):self.result['errors'].append(f'player-{n}: headless/render evidence incomplete')
        if self.air and self.air.poll() is None:self.air.terminate();self.air.wait(5)
        for f in [*self.fifos.values(),*self.streams]:f.close()
        for path in (self.seed,self.original):
            if hashlib.sha256(path.read_bytes()).hexdigest()!=SAVE_SHA256:self.result['errors'].append('reference changed')
        if self.result.get('team_screenshot'):
            try:
                ocr=self.out/'vision-ocr'
                subprocess.run(['swiftc',str(ROOT/'tools/vision-ocr.swift'),'-o',str(ocr)],check=True,timeout=90)
                rows=recognize(ocr,[Path(self.result['team_screenshot'])],self.out/'teams-ocr.jsonl')
                lines=[line for row in rows for line in row['lines']]
                self.result['team_ocr']=lines
                if not any(MODES[self.args.mode].lower() in line.lower() for line in lines):self.result['errors'].append('native room UI mode does not match request')
                for team in ('Alpha Team','Bravo Team'):
                    if sum(team.lower() in line.lower() for line in lines)!=self.args.players//2:
                        self.result['errors'].append(f'native team UI does not show expected {team} count')
                # Identity is read from the actual GetUid/GetNickname output
                # buffers above; Vision confuses 0/O and 1/I/T in this font.
                self.result['identity_source']='native GetUid/GetNickname output buffers'
            except (OSError,subprocess.SubprocessError) as e:self.result['errors'].append(f'team OCR: {e}')
        try:
            cleanup=system_sample()
            cleanup['new_swapout_bytes']=max(0,cleanup['swapouts']-self.monitor.baseline['swapouts'])*cleanup['page_size']
            self.result['system_after_cleanup']=cleanup
            (self.out/'system-after-cleanup.json').write_text(json.dumps(cleanup,indent=2)+'\n')
            if cleanup['pressure']>=4 or cleanup['new_swapout_bytes']>2*2**30:self.result['errors'].append('resource limit exceeded during cleanup')
        except (OSError,subprocess.SubprocessError) as e:self.result['errors'].append(f'cleanup resource sample: {e}')
        uid_set={h['native_uid'][-1] for h in evidence if h['native_uid']}
        if len(uid_set)!=len(self.hosts):self.result['errors'].append('native player UIDs are not unique')
        self.result.update(hosts=evidence,resources=self.monitor.summary())
        if len(self.hosts)!=self.args.players:self.result['errors'].append('requested process count not reached')
        if self.args.players>1 and not self.result.get('same_room'):self.result['errors'].append('complete room membership not observed')
        self.result['phase_passed']=not self.result['errors']
        self.result['passed']=self.args.players==8 and not self.args.admission_only and self.result['phase_passed']
        (self.out/'result.json').write_text(json.dumps(self.result,indent=2)+'\n')
        print(json.dumps({k:v for k,v in self.result.items() if k not in ('hosts','resources')},indent=2),flush=True)
        return not self.result['phase_passed']


def main(args):
    run=Run(args)
    try:run.execute()
    except Exception as e:run.result['errors'].append(f'{type(e).__name__}: {e}')
    except KeyboardInterrupt:run.result['errors'].append('interrupted')
    return run.finish()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--players',type=int,choices=(1,2,4,8),default=8)
    p.add_argument('--timeout',type=float,default=2400)
    p.add_argument('--mode',type=int,choices=range(5),default=0)
    stage=p.add_mutually_exclusive_group()
    stage.add_argument('--stage-index',type=int,choices=range(25),default=0)
    stage.add_argument('--stage-id',type=int,help='local VersusSceneInfo catalog ID')
    p.add_argument('--admission-only',action='store_true')
    p.add_argument('--visible',action='store_true')
    p.add_argument('--weapons',type=lambda s:[int(x) for x in s.split(',')],help='one Versus catalog ID per player')
    args=p.parse_args()
    from byml import read as read_byml
    stages=read_byml(subprocess.check_output(['zstd','-dc',str(ROOT/'work/data/v720896/RomFS/RSDB/VersusSceneInfo.Product.b30.rstbl.byml.zs')]))
    stages=sorted((r for r in stages if r['IsDisplayInStageList']),key=lambda r:r['DisplayOrder'])
    if args.stage_id is not None:
        matches=[i for i,r in enumerate(stages) if r['Id']==args.stage_id]
        if not matches:p.error('--stage-id is not a displayed private-battle stage')
        args.stage_index=matches[0]
    args.stage_id=stages[args.stage_index]['Id'];args.stage_row=stages[args.stage_index]['__RowId']
    if args.weapons:
        table=ROOT/'work/data/v720896/RomFS/RSDB/WeaponInfoMain.Product.b30.rstbl.byml.zs'
        rows=read_byml(subprocess.check_output(['zstd','-dc',str(table)]))
        valid={r['Id'] for r in rows if r['Type']=='Versus'}
        if len(args.weapons)!=args.players or any(w not in valid for w in args.weapons):p.error('--weapons must give one valid Versus kit per player')
    raise SystemExit(main(args))
