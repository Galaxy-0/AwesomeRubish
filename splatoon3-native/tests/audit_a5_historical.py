#!/usr/bin/env python3
"""Reaudit accepted A5 traces against their exact historical source snapshots.

A changed current adapter must not resume an old frozen tournament. Restore
only old source into ignored evidence storage and redirect the archive audit's
hash reads there; all trace/score/HUD checks and every expected hash stay intact.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from arena import checkpoint,a5_audit


def main(args):
    data=json.loads(args.checkpoint.read_text());directory=args.out.parent/'historical-sources';directory.mkdir(parents=True,exist_ok=True)
    mappings={};resolved=[]
    for name,expected in data['immutable_runtime_sha256'].items():
        actual=checkpoint.path_at_root(name)
        if checkpoint.sha256(actual)==expected:continue
        if not name.endswith('.py'):raise AssertionError('non-source frozen input changed: '+name)
        target=directory/name;target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists() or checkpoint.sha256(target)!=expected:
            git_path='splatoon3-native/'+name
            commits=subprocess.check_output(['git','log','--format=%H','--',git_path],cwd=ROOT.parent,text=True).splitlines()
            for commit in commits:
                value=subprocess.run(['git','show',commit+':'+git_path],cwd=ROOT,capture_output=True)
                if value.returncode:continue
                import hashlib
                if hashlib.sha256(value.stdout).hexdigest()==expected:
                    target.write_bytes(value.stdout);break
            else:raise AssertionError('exact historical source not available: '+name)
        assert checkpoint.sha256(target)==expected
        mappings[name]=target;resolved.append(dict(original=name,snapshot=str(target),sha256=expected))
    original=checkpoint.path_at_root
    def historical(path):return mappings.get(str(path),original(path))
    with patch.object(checkpoint,'path_at_root',side_effect=historical):report=a5_audit.audit_checkpoint(args.checkpoint)
    report['source_scope']='Accepted historical runtime and native traces, not current-runtime resumability. No hash was bypassed.'
    report['restored_source_snapshots']=resolved
    args.out.write_text(json.dumps(report,indent=2)+'\n');print(report['accepted'],report['valid_rounds'],resolved)
    return 0 if report['accepted'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--checkpoint',type=Path,default=ROOT/'arena/results/a5-paused-70-20261019.json');p.add_argument('--out',type=Path,required=True)
    raise SystemExit(main(p.parse_args()))
