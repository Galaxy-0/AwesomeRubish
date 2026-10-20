"""Read-only closeout audit of this window's owned sessions and resource logs."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess

from sim.parameters import ROOT,sha256
from .native import active_native


def audit(base):
    base=base.resolve();statuses=[];sessions=set();events=[]
    for path in sorted(base.glob('*/*/status.json')):
        r=json.loads(path.read_text());statuses.append(dict(path=str(path.relative_to(ROOT)),sha256=sha256(path),**r))
        if r.get('session'):sessions.add(r['session'])
        events.extend([(r['started_wall'],1),(r['ended_wall'],-1)])
    for path in base.glob('*.log'):
        for line in path.read_text(errors='replace').splitlines():
            if line.startswith('M6 session: '):sessions.add(line.split(': ',1)[1])
    resource=[]
    for session in sorted(sessions):
        path=Path(session)/'resources.jsonl'
        if not path.exists():continue
        rows=[json.loads(s) for s in path.read_text().splitlines()]
        resource.append(dict(session=session,samples=len(rows),sha256=sha256(path),
            pressure_max=max((r.get('pressure',0) for r in rows),default=0),
            new_swapout_bytes_max=max((r.get('new_swapout_bytes',0) for r in rows),default=0)))
    concurrent=peak=0
    for _,delta in sorted(events):concurrent+=delta;peak=max(peak,concurrent)
    from arena.native_runtime import default_runtime,runtime_files
    runtime=default_runtime();files=runtime_files(runtime)
    protected=subprocess.check_output(['git','diff','c0a03e4','--name-only','--','arena','rl','upstream','tools'],cwd=ROOT,text=True).splitlines()
    report=dict(schema='sim.native.window.audit.v1',budget=json.loads((base/'budget.json').read_text()),
        attempts=len(statuses),status_counts=dict(Counter(r['status'] for r in statuses)),
        statuses=statuses,owned_sessions=len(sessions),session_resource_reports=resource,
        max_overlapping_case_lifetimes=peak,active_native_at_audit=active_native(),
        resource_max=dict(pressure=max((r['pressure_max'] for r in resource),default=0),
            new_swapout_bytes=max((r['new_swapout_bytes_max'] for r in resource),default=0)),
        protected_path_changes_since_A8=protected,runtime=runtime,
        runtime_sha256={str(p.relative_to(ROOT)):sha256(p) for p in files},
        interpretation='Case lifetimes include boot/cleanup, conservatively bound native room concurrency. Collected means collection ended, not full mechanism acceptance; failed/cancelled attempts remain included.')
    (base/'audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('statuses','session_resource_reports','runtime_sha256')},indent=2))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,default=ROOT/'work/sim/window-20261021');a=p.parse_args();audit(a.directory)
