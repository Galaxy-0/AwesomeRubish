#!/usr/bin/env python3
"""Both example policies execute through the production sandbox, no game claim."""
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from arena.policy import OwnState,PublicPlayer,EnemyView,PolicyObservation
from arena.process import PolicyProcess,validate_action
from arena.config import PolicySpec


class ExamplePolicyProcesses(unittest.TestCase):
    def test_two_examples_accept_only_public_observation(self):
        own=OwnState(PublicPlayer('player_0',0,8000,True),(-23.9,10.5,71.4),3.14,1.,1.,10,
                     form_squid=False,submerged=False,view_yaw=3.14,view_pitch=-.0127)
        enemy=EnemyView(PublicPlayer('player_1',1,8000,True),False)
        obs=PolicyObservation('sandbox-example',10,own,(enemy,),175.,1)
        with tempfile.TemporaryDirectory(prefix='a5-process-',dir=ROOT/'work/tests') as path:
            for name in ('rush','high-ground'):
                spec=PolicySpec.load(ROOT/'arena/policies'/name)
                with PolicyProcess(spec.root,Path(path)/(name+'.log'),timeout=spec.step_timeout) as child:
                    action=child.act(obs)
                    self.assertEqual(validate_action(action),action)


if __name__=='__main__':unittest.main()
