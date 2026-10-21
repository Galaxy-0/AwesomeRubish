#!/usr/bin/env python3
"""Run the existing D2 lab with its isolated read-only sensor derivative."""
import argparse
from pathlib import Path
from unittest.mock import patch
import serve
from probe import NativeSession,ROOT


def main(args):
    original=NativeSession.host_options
    def options(self,player):return original(self,player)|dict(DM_D2B_SENSOR='1')
    with patch.object(NativeSession,'host_options',options):return serve.main(args)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--name',required=True);p.add_argument('--commands',type=Path,required=True)
    p.add_argument('--stage',type=int,choices=(1,2,3),default=1);p.add_argument('--host',type=Path,required=True);p.add_argument('--patched',type=Path,required=True)
    p.add_argument('--timeout',type=float,default=7200);p.add_argument('--meter',choices=('full','infinite'),default='infinite');raise SystemExit(main(p.parse_args()))
