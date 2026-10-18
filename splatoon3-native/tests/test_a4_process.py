#!/usr/bin/env python3
"""The real policy worker may read public navigation, never raw game assets."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from arena.policy import OwnState,PublicPlayer,PolicyObservation
from arena.process import PolicyProcess


class PublicAtlasProcess(unittest.TestCase):
    def test_public_library_atlas_without_raw_collision_access(self):
        with tempfile.TemporaryDirectory(prefix='a4-process-',dir=ROOT/'work/tests') as folder:
            root=Path(folder)
            (root/'policy.py').write_text('''from atlas import MapAtlas
from skills import neutral
from pathlib import Path
def act(obs):
    atlas=MapAtlas.load(obs['stage_id'])
    assert len(atlas.points)>100
    assert atlas.objective()
    raw=Path(__file__).resolve().parents[3]/'work/arena/maps/Yunohana/human.npz'
    try:raw.read_bytes()
    except PermissionError:pass
    else:raise AssertionError('raw private asset readable')
    return neutral()
''')
            obs=PolicyObservation('m',10,OwnState(PublicPlayer('a',0,8000,True),(0.,3.,0.),0.,1.,1.,10),(),170.,1)
            with PolicyProcess(root,root/'worker.log',timeout=2) as child:
                result=child.act(obs)
                self.assertEqual(result['buttons'],[0]*6)


if __name__=='__main__':unittest.main()
