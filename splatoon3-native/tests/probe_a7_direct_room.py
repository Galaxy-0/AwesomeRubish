#!/usr/bin/env python3
"""A7 diagnostic: native game requests create/search/join a room without HID.

This checkpoint does not accept a complete match or full A7.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rl.session import Session
from rl.loadout import uniform_loadout


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main(args):
    if os.environ.get('DM_TEST_SPECIAL'):raise ValueError('A7 room probe rejects DM_TEST_SPECIAL')
    host=args.host.resolve();patched=args.patched.resolve()
    build_path=host.with_suffix('.build.json');build=json.loads(build_path.read_text())
    if sha(host)!=build['output_sha256']:raise ValueError('host hash mismatch')
    if any(sha(ROOT/name)!=digest for name,digest in build['source_sha256'].items()):raise ValueError('host source mismatch')
    default=ROOT/'upstream/dm/host/dmhost';default_hash=sha(default)
    out=ROOT/'work/a7'/datetime.datetime.now().strftime('direct-room-%Y%m%d-%H%M%S-%f');out.mkdir(parents=True)
    session=Session(2,0,1,[8000,8000],timeout=args.timeout,loadouts=[uniform_loadout()]*2,patched=patched)
    result=dict(schema='arena.a7.direct-room.v1',passed=False,full_a7_passed=False,errors=[],
                scope='native '+('controller' if args.upper else 'game request')+' create and guest '+args.guest_action,artifacts=str(out),session=str(session.out),
                started_wall=time.time(),host_sha256=sha(host),source_sha256=build['source_sha256'],
                default_host_sha256=default_hash,menu_inputs=[],ocr_used=False)
    (ROOT/'work/a7/direct-room-current.json').write_text(json.dumps(dict(out=str(out),session=str(session.out))))
    original_popen=subprocess.Popen;original_options=Session.host_options
    def popen(command,*a,**kw):
        if str(command[0])==str(default):command=[str(host),*command[1:]]
        return original_popen(command,*a,**kw)
    def options(s,player):
        options=dict(original_options(s,player),DM_KEYS='',DM_SCENE_BOOT='LobbyLocal',
                    DM_SCENE_TRACE_FLOW='1',DM_SCENE_TRACE_NETWORK='1',DM_SCENE_TRACE_STACK='1',
                    DM_SCENE_DIRECT='create' if player==0 else args.guest_action,
                    DM_NVN_SHMAP=str(ROOT/'upstream/dm/games/0100C2500FC20000/shader_map.tsv'))
        if args.upper:options['DM_SCENE_UPPER']='1'
        return options
    def save():(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(out,flush=True);save()
    try:
        with patch('subprocess.Popen',side_effect=popen),patch.object(Session,'host_options',options):
            log=(session.out/'air.log').open('wb');session.streams.append(log)
            session.air=subprocess.Popen([sys.executable,str(ROOT/'tools/ldn/air.py'),'--socket',str(session.air_socket)],stdout=log,stderr=subprocess.STDOUT)
            session.until(session.air_socket.exists);session.spawn(0)
            session.until(lambda:'create player=0 ' in (session.out/'air.log').read_text())
            result['created_wall']=time.time();session.spawn(1)
            result['owned_host_pids']=[p.pid for _,p,_ in session.hosts];save()
            session.until(lambda:'A7_DIRECT search_complete ' in session.text(1))
            result['search_complete_wall']=time.time()
            counts=re.findall(r'A7_DIRECT search_complete count=(\d+)',session.text(1))
            result['native_search_count']=int(counts[-1]);result['passed']=result['native_search_count']>0
            if not result['passed']:result['errors'].append('native search returned no rooms')
            if result['passed'] and args.guest_action=='join':
                session.until(lambda:'join player=1 ' in (session.out/'air.log').read_text())
                def complete():
                    states=[]
                    for n in (0,1):
                        rows=re.findall(r'LDN state=(\d+) node=(-?\d+) nodes=(\d+) session=(\w+)',session.text(n))
                        states.append(rows[-1] if rows else None)
                    roots=re.findall(r'A7_NET_ROOT .*? state=(\d+)',session.text(1))
                    return (states[0] is not None and states[1] is not None and
                            states[0][:3]==('3','0','2') and states[1][:3]==('5','1','2') and
                            states[0][3]==states[1][3] and roots and roots[-1]=='34')
                session.until(complete);result['joined_wall']=time.time()
                result['native_membership']={str(n):re.findall(r'LDN state=(\d+) node=(-?\d+) nodes=(\d+) session=(\w+)',session.text(n))[-1] for n in (0,1)}
    except BaseException as error:result['errors'].append(repr(error))
    finally:
        try:session.close()
        except BaseException as error:result['errors'].append('cleanup: '+repr(error))
    result['native_events']={str(n):[x for x in session.text(n).splitlines() if any(k in x for k in ['A7_DIRECT','A7_UPPER','A7_NET_ROOT','LDN state='])]
                             for n,_,_ in session.hosts}
    for n,_,_ in session.hosts:
        text=session.text(n)
        if 'DM_HID_FIFO frame=' in text or 'DM_KEYS：' in text:result['errors'].append(f'player-{n}: unexpected HID input')
    if sha(default)!=default_hash:result['errors'].append('default host changed')
    result['owned_hosts_closed']=all(p.poll() is not None for _,p,_ in session.hosts)
    result['elapsed_wall_seconds']=time.time()-result['started_wall']
    if result['errors']:result['passed']=False
    save();print(json.dumps(result,indent=2),flush=True)
    return 0 if result['passed'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',type=Path,default=ROOT/'work/a7/dmhost-direct-v11')
    p.add_argument('--patched',type=Path,default=ROOT/'work/a7/patched-producer-v6')
    p.add_argument('--timeout',type=float,default=300)
    p.add_argument('--guest-action',choices=('scan','join'),default='join')
    p.add_argument('--upper',action='store_true',help='use native game matchmaking-controller entry points')
    raise SystemExit(main(p.parse_args()))
