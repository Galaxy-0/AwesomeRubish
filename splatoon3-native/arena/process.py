"""Bounded, sandboxed policy process. Only encode_policy output crosses stdin."""
import json
import math
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time
from .policy import encode_policy

ROOT=Path(__file__).resolve().parents[1]


def _literal(path):return json.dumps(str(Path(path).resolve()))


def sandbox_profile(policy_root):
    # Protect user data (including session logs), temporary native clocks and
    # sockets, game dumps and opposing policy sources. System runtime reads
    # remain available; only this policy/runtime/public skills are exceptions.
    read_dirs=[sys.prefix,sys.base_prefix,policy_root,ROOT/'arena/lib']
    reads=' '.join('(subpath '+_literal(p)+')' for p in read_dirs)
    worker=_literal(ROOT/'arena/policy_worker.py')
    allowed='(require-any '+reads+' (literal '+worker+'))'
    private='(require-any (subpath '+_literal(Path.home())+') (subpath "/private/var/folders") (subpath "/private/tmp"))'
    protected='(require-all '+private+' (require-not '+allowed+'))'
    return ('(version 1)(allow default)(deny network*)(deny process-fork)'
            '(deny file-read-data '+protected+')'
            '(deny file-map-executable '+protected+')'
            '(deny file-write* (require-not (subpath "/dev")))')


def validate_action(action):
    if type(action) is not dict or set(action)!={'sticks','gyro','buttons'}:raise ValueError('policy action keys')
    for key,count in [('sticks',4),('gyro',3),('buttons',6)]:
        value=action[key]
        if type(value) is not list or len(value)!=count:raise ValueError('policy action shape')
        if not all(type(v) in (int,float,bool) and math.isfinite(v) and -1<=v<=1 for v in value):raise ValueError('policy action range')
        if key=='buttons' and any(v not in (0,1) for v in value):raise ValueError('policy button range')
    return action


class PolicyProcess:
    def __init__(self,policy_root:Path,log:Path,timeout=.25,startup_timeout=10.):
        if sys.platform!='darwin':raise RuntimeError('policy filesystem/network sandbox currently requires macOS')
        if timeout<=0:raise ValueError('policy timeout must be positive')
        self.timeout=timeout;self.buffer=b'';self.selector=selectors.DefaultSelector();self.closed=False
        self.log=Path(log).open('wb');policy_root=Path(policy_root).resolve()
        env={'PATH':'/usr/bin:/bin','LANG':'en_US.UTF-8'}
        self.child=subprocess.Popen(['/usr/bin/sandbox-exec','-p',sandbox_profile(policy_root),
                                     sys.executable,'-I','-u',str(ROOT/'arena/policy_worker.py'),
                                     str(policy_root),str(ROOT/'arena/lib')],
                                    cwd=policy_root,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                    stderr=self.log,close_fds=True)
        self.selector.register(self.child.stdout,selectors.EVENT_READ)
        try:
            if self._receive(startup_timeout)!={'ready':True}:raise RuntimeError('policy worker handshake')
        except BaseException:self.close();raise

    def _receive(self,timeout):
        deadline=time.monotonic()+timeout
        while b'\n' not in self.buffer:
            remaining=deadline-time.monotonic()
            if remaining<=0 or not self.selector.select(remaining):raise TimeoutError('policy step deadline')
            chunk=os.read(self.child.stdout.fileno(),4096)
            if not chunk:raise RuntimeError('policy process exited')
            self.buffer+=chunk
            if len(self.buffer)>65536:raise ValueError('policy output too large')
        line,self.buffer=self.buffer.split(b'\n',1)
        return json.loads(line)

    def act(self,observation):
        # Type rejection happens before any data is written to the child.
        payload=encode_policy(observation)
        try:
            self.child.stdin.write(payload);self.child.stdin.flush()
            return validate_action(self._receive(self.timeout))
        except BaseException:self.close();raise

    def close(self):
        if self.closed:return
        self.closed=True
        if self.child.poll() is None:
            self.child.terminate()
            try:self.child.wait(1)
            except subprocess.TimeoutExpired:self.child.kill();self.child.wait(1)
        self.selector.close();self.child.stdin.close();self.child.stdout.close();self.log.close()

    def __enter__(self):return self
    def __exit__(self,*args):self.close()
