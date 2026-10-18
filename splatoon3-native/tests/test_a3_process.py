#!/usr/bin/env python3
"""Production policy worker white-list, filesystem/socket denial and deadline."""
from pathlib import Path
import socket
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from arena.process import PolicyProcess
from arena.visibility import PolicyProjector
from test_a3_components import snapshot


class ChildBoundary(unittest.TestCase):
    def test_actual_child_denied_truth_socket_and_other_policy(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work/tests',prefix='a3-process-') as tmp:
            path=Path(tmp);policy=path/'own';policy.mkdir();(path/'opponent').mkdir()
            secret=path/'truth.json';secret.write_text('private-live-position')
            other=path/'opponent/policy.py';other.write_text('private-strategy')
            sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);address=str(path/'raw.sock');sock.bind(address);sock.listen()
            try:
                (policy/'policy.py').write_text('''import socket, os
def act(obs):
    denied=0
    for name in '''+repr([str(secret),str(other)])+''':
        try:open(name).read()
        except PermissionError:denied+=1
    try:
        s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.connect('''+repr(address)+''')
    except PermissionError:denied+=1
    clean=obs['schema']=='arena.policy.v1' and obs['enemies'][0]['position'] is None and 'hp' not in obs['enemies'][0] and not any(k.startswith('DM_') for k in os.environ)
    return dict(sticks=[0]*4,gyro=[0]*3,buttons=[int(denied==3 and clean)]+[0]*5)
''')
                with PolicyProcess(policy,path/'worker.log',timeout=2) as child:
                    with self.assertRaises(TypeError):child.act(snapshot())
                    action=child.act(PolicyProjector('match').observe(snapshot(),'a'))
                    self.assertEqual(action['buttons'][0],1,(path/'worker.log').read_text())
            finally:sock.close()

    def test_deadline_kills_busy_policy(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work/tests',prefix='a3-process-') as tmp:
            path=Path(tmp);(path/'policy.py').write_text('def act(obs):\n    while True:pass\n')
            with PolicyProcess(path,path/'worker.log',timeout=.1) as child:
                with self.assertRaises(TimeoutError):child.act(PolicyProjector('match').observe(snapshot(),'a'))
                self.assertIsNotNone(child.child.poll())


if __name__=='__main__':unittest.main()
