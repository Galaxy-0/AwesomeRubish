#!/usr/bin/env python3
"""No-game two-process regression using the actual C LDN HLE and local medium."""
import datetime
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / 'work/tests' / datetime.datetime.now().strftime('ldn-air-%Y%m%d-%H%M%S-%f')
    out.mkdir(parents=True)
    cases = []
    peers = []
    service = None
    def line(p):
        # Use unbuffered binary pipes so select cannot miss Python-buffered lines.
        result = bytearray()
        with selectors.DefaultSelector() as sel:
            sel.register(p.stdout, selectors.EVENT_READ)
            deadline = time.monotonic()+6
            while time.monotonic() < deadline:
                if sel.select(max(0, deadline-time.monotonic())):
                    c = os.read(p.stdout.fileno(), 1)
                    if not c: raise RuntimeError(f'peer exited {p.poll()}')
                    result.extend(c)
                    if c == b'\n': return result.decode().strip()
        raise TimeoutError('peer response timeout')
    def start(player, path):
        env = {k:v for k,v in os.environ.items() if not k.startswith('DM_')}
        env.update(DM_PLAYER=str(player), DM_LDN_AIR=str(path))
        log = (out / f'peer-{len(peers)}.log').open('wb')
        p = subprocess.Popen([str(ROOT / 'upstream/dm/host/tests/build/t_ldn_peer')], env=env,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, bufsize=0)
        peers.append((p,log))
        return p,line(p)
    def check(name,p,command,**expected):
        p.stdin.write((command+'\n').encode())
        text = line(p)
        row = dict(re.findall(r'(\w+)=([^ ]*)',text))
        ok = all(row.get(k)==str(v) for k,v in expected.items())
        cases.append(dict(name=name,command=command,actual=row,expected=expected,passed=ok))
        if not ok: raise AssertionError(cases[-1])
        return row
    passed=False
    try:
        with tempfile.TemporaryDirectory(prefix='s3-air-') as temp:
            path=Path(temp)/'air.sock'
            with (out/'air.log').open('wb') as stream:
                service=subprocess.Popen([sys.executable,str(ROOT/'tools/ldn/air.py'),'--socket',str(path)],stdout=stream,stderr=subprocess.STDOUT)
                deadline=time.monotonic()+5
                while not path.exists():
                    if service.poll() is not None or time.monotonic()>deadline: raise RuntimeError('air not ready')
                    time.sleep(.02)
                a,ready=start(0,path);assert ready=='ready 0',ready
                b,ready=start(1,path);assert ready=='ready 0',ready
                dup,ready=start(1,path);assert ready!='ready 0',ready
                dup.stdin.write(b'QUIT\n');assert line(dup)=='bye';assert dup.wait(3)==0
                check('cannot create without AP',a,'CREATE',result=674,state=1)
                check('open AP',a,'AP',result=0,state=2)
                check('cannot open station while AP',a,'STA',result=674,state=2)
                check('close AP before service reset',a,'CLOSE_AP',result=0,state=1)
                check('reinitialize releases identity and event binding',a,'RESET',result=0,state=1)
                check('reopen AP after event reuse',a,'AP',result=0,state=2)
                check('advertise before create',a,'ADV erepo_test_beacon',result=0)
                check('create',a,'CREATE',result=0,state=3,nodes=1)
                room=check('host network',a,'INFO',result=0,advertise='erepo_test_beacon')
                check('open station',b,'STA',result=0,state=4)
                check('idle query uses LDN InvalidState',b,'INFO',result=16587,state=4)
                check('scan scene mismatch',b,'SCAN wrong',result=0,count=0)
                check('network type mismatch',b,'SCAN type',result=0,count=0)
                check('network type bitmask includes LDN',b,'SCAN alltypes',result=0,count=1)
                check('scan channel mismatch',b,'SCAN channel',result=0,count=0)
                found=check('scan exact beacon and session',b,'SCAN',result=0,count=1,advertise='erepo_test_beacon',session=room['session'])
                check('wrong passphrase',b,'JOIN wrong',result=674,state=4)
                check('reject policy',a,'POLICY 1',result=0)
                check('policy enforced',b,'JOIN',result=674,state=4)
                check('allow policy',a,'POLICY 0',result=0)
                joined=check('join',b,'JOIN',result=0,state=5,nodes=2)
                host=check('both observe same session',a,'INFO',result=0,state=3,nodes=2,session=found['session'])
                check('client same session',b,'INFO',result=0,session=host['session'])
                for p in (a,b):
                    check('host-order IPv4 and mask',p,'IP',result=0)
                    check('security parameter shares session',p,'SECURITY',result=0)
                    check('node join history',p,'HISTORY',result=0)
                    check('history is cleared on read',p,'HISTORY',result=674)
                assert int(host['events'])>=3 and int(joined['events'])>=3
                for p in (a,b):
                    check('UDP socket',p,'SOCKET',result=0)
                    check('UDP bind',p,'BIND',result=0)
                    check('SO_REUSEPORT enforced for both bindings',p,'REUSEPORT',result=0)
                    check('EventFd wakes poll and clears',p,'EVENTFD',result=0)
                check('empty poll',b,'POLL',result=674)
                check('empty recv EWOULDBLOCK',b,'RECV',result=674,errno=11)
                check('A to B frame',a,'SEND 1',result=0)
                check('readable poll',b,'POLL',result=0)
                check('B receives exact payload',b,'RECV',result=0)
                check('B to A frame',b,'SEND 0',result=0)
                check('A receives exact payload',a,'RECV',result=0)
                check('reject external destination',a,'SEND 77',result=674,errno=101)
                check('send failure is signed negative one',a,'BADSEND',result=0,errno=101)
                check('live advertise update',a,'ADV changed_beacon',result=0)
                check('client observes update',b,'INFO',result=0,advertise='changed_beacon')
                check('disconnect',b,'DISC',result=0,state=4)
                check('host sees leave',a,'INFO',result=0,nodes=1)
                check('disconnected frame cannot send',b,'SEND 0',result=674,errno=100)
                check('scan and rejoin',b,'SCAN',result=0,count=1)
                check('rejoin',b,'JOIN',result=0,state=5)
                a.stdin.write(b'QUIT\n');assert line(a)=='bye';assert a.wait(3)==0
                time.sleep(.05)
                check('host exit disconnects client',b,'STATE',result=0,state=4)
                check('host exit removes beacon',b,'SCAN',result=0,count=0)
                check('stale join fails',b,'JOIN',result=674,state=4)
                check('close station',b,'CLOSE_STA',result=0,state=1)
                b.stdin.write(b'QUIT\n');assert line(b)=='bye';assert b.wait(3)==0
                service.terminate();assert service.wait(3)==0
                assert not path.exists()
                passed=True
    finally:
        for p,log in peers:
            if p.poll() is None: p.kill();p.wait()
            log.close()
        if service and service.poll() is None:service.terminate();service.wait(3)
        (out/'result.json').write_text(json.dumps(dict(passed=passed,cases=cases),indent=2)+'\n')
        print(f'ldn-air: {len(cases)} checks, passed={passed}, artifacts={out}',flush=True)
    return not passed


if __name__=='__main__': raise SystemExit(main())
