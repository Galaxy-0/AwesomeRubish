"""Proficiency sandbox: canonical skills plus optional staging, no native logs."""
import json
from pathlib import Path
import selectors
import subprocess
import sys

from .process import PolicyProcess, sandbox_profile, ROOT
from .control_process import ControlProcess


def profile(policy_root):
    baseline = sandbox_profile(policy_root)
    original = '(literal '+json.dumps(str(ROOT/'arena/policy_worker.py'))+')'
    replacement = ('(literal '+json.dumps(str(ROOT/'arena/proficiency_worker.py'))+') '
                   '(subpath '+json.dumps(str(ROOT/'arena/lib_a6'))+')')
    if original not in baseline:
        raise RuntimeError('policy sandbox layout changed')
    return baseline.replace(original, replacement)


class ProficiencyProcess(ControlProcess):
    def __init__(self, policy_root, log, timeout=.25, startup_timeout=10.):
        if sys.platform != 'darwin' or timeout <= 0:
            raise RuntimeError('requires macOS sandbox and positive timeout')
        self.timeout = timeout
        self.buffer = b''
        self.selector = selectors.DefaultSelector()
        self.closed = False
        self.log = Path(log).open('wb')
        policy_root = Path(policy_root).resolve()
        self.child = subprocess.Popen(
            ['/usr/bin/sandbox-exec', '-p', profile(policy_root), sys.executable, '-I', '-u',
             str(ROOT/'arena/proficiency_worker.py'), str(policy_root),
             str(ROOT/'arena/lib'), str(ROOT/'arena/lib_a6')],
            cwd=policy_root, env={'PATH':'/usr/bin:/bin', 'LANG':'en_US.UTF-8'},
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log, close_fds=True)
        self.selector.register(self.child.stdout, selectors.EVENT_READ)
        try:
            if self._receive(startup_timeout) != {'ready':True}:
                raise RuntimeError('policy worker handshake')
        except BaseException:
            self.close()
            raise
