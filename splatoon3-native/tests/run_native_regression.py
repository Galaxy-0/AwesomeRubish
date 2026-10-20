#!/usr/bin/env python3
"""Run an existing native fixture on an explicit A7 host, with evidence binding.

Preserves fixture inputs/assertions. A3's scheduled full-resolution screenshots
start earlier because direct startup does not spend 14000 frames in menus.
Never builds or changes the default host/modules.
"""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
import rl
import rl.env as env_module
from rl.native_start import NativeSession,validate_runtime
from arena.runner import write_json_atomic
from arena.runner import link_load_slots


def owns_result(result,owned,known):
    refs=[result.get('session'),*result.get('sessions',[])]
    refs += [row.get('session') for row in result.get('rounds',[]) if isinstance(row,dict)]
    links=[result.get('native_evidence'),*[m.get('evidence') for m in result.get('maps',[])]]
    return any(str(x) in owned for x in refs) or any(str(x) in known for x in links)


def main(args):
    host,modules=validate_runtime(args.host,args.patched)
    record=args.record.resolve();record.parent.mkdir(parents=True,exist_ok=True)
    if record.exists():raise FileExistsError(record)
    original=rl.NativeParallelEnv;environments=[];sessions=[];children=[]
    build=json.loads(host.with_suffix('.build.json').read_text())
    entry_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    fixture_sha=hashlib.sha256(args.script.read_bytes()).hexdigest()
    runtime=[host,host.with_suffix('.build.json'),*[ROOT/name for name in build['source_sha256']],*[p for p in modules.iterdir() if p.is_file()],*list((ROOT/'rl').glob('*.py')),*list((ROOT/'arena/lib').glob('*.py'))]
    runtime += [ROOT/f'work/arena/maps/{name}/{file}' for name in ('Yunohana','District00','Yagara') for file in ('navigation.json','sight.npz','human.npz')]
    frozen={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in runtime}
    def results():return set(p for base in ('work/tests','work/a6','work/arena') for p in (ROOT/base).glob('*/result.json'))
    before=results();started=time.time()
    class RegressionSession(NativeSession):
        def start(self):
            if args.shared_load_slots:link_load_slots(self,args.shared_load_slots)
            return super().start()
        def host_options(self,player):
            options=super().host_options(player)
            if env_module.Session.__name__=='ScreenshotSession':
                options['DM_PROBE']+=',main:27f7f9c@x0+20,main:27f7fa0@x0+58'
                if player==0:
                    out=self.out/'player-0/screenshots';out.mkdir(exist_ok=True)
                    options['DM_NVN_SHOT']=','.join(str(f) for f in range(0,26011,30))+':'+str(out/'native-%d.png')
            return options
    def session_factory(**kw):
        kw['patched']=modules;s=RegressionSession(host=host,**kw);sessions.append(s);return s
    def factory(*a,**kw):
        kw.setdefault('session_factory',session_factory)
        kw.setdefault('pixels',build.get('render_mode')!='camera' or args.script.name in ('probe_a3_visibility.py','test_m6.py'))
        e=original(*a,**kw);environments.append(e);return e
    original_popen=subprocess.Popen
    def popen(command,*a,**kw):
        if isinstance(command,(list,tuple)) and len(command)>1 and Path(str(command[1])).name in ('probe_a3_visibility.py','probe_a4_routes.py'):
            child=record.with_name(record.stem+'-child-'+str(len(children))+'.json');children.append(child)
            command=[command[0],str(Path(__file__)), '--host',str(host),'--patched',str(modules),'--record',str(child),*(['--shared-load-slots',str(args.shared_load_slots)] if args.shared_load_slots else []),*command[1:]]
        return original_popen(command,*a,**kw)
    code=0;errors=[]
    sys.argv=[str(args.script),*args.script_args]
    try:
        with patch.object(rl,'NativeParallelEnv',side_effect=factory),patch.object(subprocess,'Popen',side_effect=popen):runpy.run_path(str(args.script),run_name='__main__')
    except SystemExit as e:code=e.code or 0
    except BaseException as e:code=1;errors.append(repr(e));raise
    finally:
        for e in environments:
            try:e.close()
            except BaseException as error:errors.append('cleanup: '+repr(error))
        new=sorted(results()-before)
        # Other parallel fixtures can create files too. Only claim results
        # whose recorded session belongs to an environment in this process.
        owned={str(p) for e in environments for p in e.artifacts}
        evidence=[]
        for child in children:
            if not child.exists():errors.append('missing child record '+str(child));continue
            r=json.loads(child.read_text());owned.update(r['owned_sessions']);evidence+=r['evidence']
            if not r['passed']:errors.append('child failed '+str(child))
        known={x['path'] for x in evidence}
        for p in new:
            try:r=json.loads(p.read_text())
            except (FileNotFoundError,json.JSONDecodeError):continue # unrelated parallel fixture mid-write
            if str(p) not in known and owns_result(r,owned,known):
                evidence.append(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),passed=r.get('passed'),probe_completed=r.get('probe_completed'),a1_damage_passed=r.get('a1_damage_passed'),errors=r.get('errors')))
        if not evidence:errors.append('no version-bound owned native result')
        if any(hashlib.sha256(Path(p).read_bytes()).hexdigest()!=digest for p,digest in frozen.items()):errors.append('regression runtime changed')
        if hashlib.sha256(Path(__file__).read_bytes()).hexdigest()!=entry_sha or hashlib.sha256(args.script.read_bytes()).hexdigest()!=fixture_sha:errors.append('regression entry/fixture source changed during execution')
        report=dict(schema='arena.native-regression-job.v1',passed=code==0 and not errors,exit_code=code,errors=errors,
            command=sys.argv,wall_seconds=time.time()-started,evidence=evidence,owned_sessions=sorted(owned),
            runtime_sha256=frozen,
            host_sha256=hashlib.sha256(host.read_bytes()).hexdigest(),build=json.loads(host.with_suffix('.build.json').read_text()),
            entry_sha256=entry_sha,fixture_sha256=fixture_sha)
        write_json_atomic(record,report)
    return code if code else int(bool(errors))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',type=Path,required=True);p.add_argument('--patched',type=Path,required=True);p.add_argument('--record',type=Path,required=True)
    p.add_argument('--shared-load-slots',type=Path)
    p.add_argument('script',type=Path);p.add_argument('script_args',nargs=argparse.REMAINDER)
    raise SystemExit(main(p.parse_args()))
