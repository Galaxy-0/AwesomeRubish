#!/usr/bin/env python3
"""One test room: full in seat 0, infinite in seat 1; neutral input except RS.

Build tools/build_a6_test_host.py first. This narrowly substitutes the executable
for this Session only; it never rebuilds or replaces the tournament host.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import traceback
from unittest.mock import patch

from a6_lab import ROOT,Lab,neutral
from rl.session import Session


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    alt=ROOT/'work/a6/dmhost-test-special';base=ROOT/'upstream/dm/host/dmhost'
    build=alt.with_suffix('.build.json');meta=json.loads(build.read_text())
    if sha(base)!=meta['default_sha256'] or sha(alt)!=meta['output_sha256']:
        raise AssertionError('test host/default host build identity changed')
    for name,digest in meta['source_sha256'].items():
        if sha(ROOT/name)!=digest:raise AssertionError('test host source changed')
    lab=Lab('test-special',3600)
    for path in (build,ROOT/'upstream/dm/host/hle_rl.c',ROOT/'upstream/dm/host/dm_spl3_test_special.h'):
        shutil.copy2(path,lab.out/('tested-'+path.name))
    lab.result.update(test_special_modes={'player_0':'full','player_1':'infinite'},
        test_host_build=dict(path=str(build.relative_to(ROOT)),sha256=sha(build)),
        actual_host_sha256=sha(alt),launches=[])
    (ROOT/'work/a6/test-special-driver.json').write_text(json.dumps(dict(owned_pid=os.getpid(),artifacts=str(lab.out)),indent=2)+'\n')
    original_options=Session.host_options;original_popen=subprocess.Popen

    def options(self,player):
        return dict(original_options(self,player),DM_TEST_SPECIAL=('full','infinite')[player],
                    DM_NVN_SHMAP=str(ROOT/'upstream/dm/games/0100C2500FC20000/shader_map.tsv'))

    def popen(args,*a,**kw):
        if isinstance(args,(list,tuple)) and args and str(args[0])==str(base):
            env=kw.get('env',{});assert env.get('DM_TEST_SPECIAL') in ('full','infinite')
            args=list(args);args[0]=str(alt);child=original_popen(args,*a,**kw)
            lab.result['launches'].append(dict(owned_pid=child.pid,mode=env['DM_TEST_SPECIAL'],
                actual_executable=str(alt.relative_to(ROOT)),sha256=sha(alt)))
            return child
        return original_popen(args,*a,**kw)

    def idle(label,expected):
        history=[]
        for _ in range(15):
            infos=lab.step(lab.actions(),label,6);history.append(dict(frames=6,infos=infos))
            for n,value in expected.items():
                i=infos[f'player_{n}']
                if not i['special_valid'] or abs(i['special']-value)>.001 or not i['alive']:
                    raise AssertionError('native meter not stable: '+label+repr((n,i['special'])))
        return history

    def cycle(number,players):
        before={p:lab.info(n) for n,p in enumerate(lab.env.possible_agents)};actions=lab.actions()
        for n in players:actions[f'player_{n}']['buttons'][3]=1
        history=[dict(phase='press',frames=1,infos=lab.step(actions,f'special-{number}-press',1))]
        interior={n:False for n in players}
        for _ in range(200):
            infos=lab.step(lab.actions(),f'special-{number}-active',6)
            history.append(dict(phase='active',frames=6,infos=infos))
            for n in players:
                i=infos[f'player_{n}']
                if not i['special_valid'] or not i['alive']:raise AssertionError('special lifecycle feedback unavailable')
                interior[n] |= .05<i['special']<.95
            if all(interior.values()) and lab.info(0)['special']==0. and lab.info(1)['special']==1.:
                break
        else:raise AssertionError('special did not finish/full-infinite did not diverge')
        lab.add(dict(kind='special-cycle',number=number,players=players,before=before,history=history,
                     after={p:lab.info(n) for n,p in enumerate(lab.env.possible_agents)}))

    try:
        with patch.object(Session,'host_options',options),patch.object(subprocess,'Popen',popen):
            lab.start()
            lab.add(dict(kind='initial-full-idle',history=idle('initial-full-idle',{0:1.,1:1.})))
            lab.capture('initial-full')
            cycle(1,[0,1]);lab.capture('first-ended')
            lab.add(dict(kind='after-first-idle',history=idle('after-first-idle',{0:0.,1:1.})))
            cycle(2,[1]);lab.capture('second-ended')
            lab.add(dict(kind='after-second-idle',history=idle('after-second-idle',{0:0.,1:1.})))
            lab.result.update(passed=True,probe_completed=True)
    except BaseException as error:
        lab.result['errors'].append(repr(error));lab.result['traceback']=traceback.format_exc()
    finally:
        lab.close()
    fills={}
    for n in (0,1):
        path=Path(lab.result['session'])/f'player-{n}/host.log'
        fills[f'player_{n}']=re.findall(r'A6_TEST_SPECIAL_FILL frame=(\d+) slot=(\d+) mode=(\w+) count=(\d+) old_charge=([^ ]+) remaining=(\d+) cost=([^\s]+)',path.read_text(errors='replace'))
    lab.result['host_fills']=fills
    lab.result['default_unchanged']=sha(base)==meta['default_sha256'];lab.save()
    print(lab.out,flush=True)
    return 0 if lab.result['passed'] and not lab.result['errors'] else 1


if __name__=='__main__':raise SystemExit(main())
