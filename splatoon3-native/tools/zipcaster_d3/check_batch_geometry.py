"""Parity on each map, shared/zero-axis/degenerate/thin-wall segments + timing."""
import sys,time,json
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]));sys.path.insert(0,str(Path(__file__).resolve().parent))
from batch_geometry import BatchMesh
from geometry import ROOT,CollisionMesh
rng=np.random.default_rng(520321);checks=0;timings=[]
for name in ['Yunohana','District00','Yagara']:
    mesh=CollisionMesh.load(ROOT/f'work/arena/maps/{name}/sight.npz');batch=BatchMesh(mesh.triangles);tic=time.monotonic()
    for j in range(6):
        origin=rng.uniform([-30,1,-25],[30,18,25]);ends=rng.uniform([-35,0,-30],[35,20,30],(200,3));ends[:3]=origin;ends[3:10,0]=origin[0];ends[10:15,1]=origin[1];ends[15:20,2]=origin[2]
        actual=batch.clear_many(origin,ends);expected=np.array([mesh.clear(origin,p)for p in ends]);np.testing.assert_array_equal(actual,expected);checks+=len(ends)
    ends=rng.uniform([-35,0,-30],[35,20,30],(20000,3));tic=time.monotonic();batch.clear_many([0,4,8],ends);dt=time.monotonic()-tic;timings.append(dict(map=name,rays=20000,seconds=dt,rays_per_second=20000/dt))
print(json.dumps(dict(passed=True,parity_segments=checks,benchmark=timings),indent=2))
