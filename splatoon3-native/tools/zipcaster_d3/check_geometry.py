"""Meaningful parity test: thin walls, random and adversarial grid-corner rays."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from geometry import IndexedMesh,CollisionMesh,ROOT
import numpy as np
rng=np.random.default_rng(5203);count=0
for name in ['Yunohana','District00','Yagara']:
    base=CollisionMesh.load(ROOT/f'work/arena/maps/{name}/sight.npz');fast=IndexedMesh(base.triangles)
    for _ in range(120):
        a=rng.uniform([-35,0,-30],[35,20,30]);b=rng.uniform([-35,0,-30],[35,20,30])
        x=base.hits(a,b);y=fast.hits(a,b)
        assert np.allclose(x,y),(name,a,b,x,y)
        count+=1
print(f'{count} exact hit-array parity rays passed')
