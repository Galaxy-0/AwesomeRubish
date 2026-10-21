"""Derived presentation geometry and conditional ambush candidates (offline only)."""
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from arena.geometry import CollisionMesh, GeometricVision, VisionConfig
from arena.lib.atlas import MapAtlas
from arena.referee import PlayerTruth, RefereeSnapshot


def enrich_map(data, root, source):
    path = root / 'work/arena/maps' / data['id']
    nav = source(path / 'navigation.json')
    sight = source(path / 'sight.npz')
    script = source(Path(__file__))
    key = hashlib.sha256((hashlib.sha256(nav.read_bytes()).hexdigest() +
          hashlib.sha256(sight.read_bytes()).hexdigest() + hashlib.sha256(script.read_bytes()).hexdigest()).encode()).hexdigest()[:16]
    cache = root / f'work/showcase/derived-3d-{data["id"]}-{key}.json'
    if cache.exists():
        extra = json.loads(cache.read_text())
        data.update(extra)
        return data
    atlas = MapAtlas(json.loads(nav.read_text()))
    buckets = {}
    for i, (x, y, z) in enumerate(atlas.points):
        buckets.setdefault((round(x/2)*2, round(z/2)*2), []).append(i)
    cells = []
    for c in data['cells']:
        candidates = buckets[(c[0], c[2])]
        i = min(candidates, key=lambda i: abs(atlas.points[i][1]-c[1]))
        cells.append(c[:6] + [int(atlas.swimmable[i])])
    # Collapse vertical collision faces into 2-unit XZ wall voxels. No original
    # triangle topology/vertices are serialized. Clip decorative height to 12u
    # above nearby walkable floors to keep the tactical model readable.
    mesh = CollisionMesh.load(sight)
    floors = {(c[0],c[2]):c[1] for c in cells}
    walls = {}
    for tri in mesh.triangles:
        normal = np.cross(tri[1]-tri[0], tri[2]-tri[0])
        length = np.linalg.norm(normal)
        if length < 1e-8 or abs(normal[1])/length > .35 or np.ptp(tri[:,1]) < 1.5:
            continue
        pairs = [(a,b) for a in range(3) for b in range(a+1,3)]
        a,b = max(pairs,key=lambda ab: np.linalg.norm(tri[ab[0],[0,2]]-tri[ab[1],[0,2]]))
        count = max(1,int(np.linalg.norm(tri[a,[0,2]]-tri[b,[0,2]])/1.2))
        for t in np.linspace(0,1,count+1):
            p = tri[a]*(1-t)+tri[b]*t
            x,z = round(p[0]/2)*2,round(p[2]/2)*2
            nearby = [floors[(x+dx,z+dz)] for dx,dz in [(0,0),(2,0),(-2,0),(0,2),(0,-2)] if (x+dx,z+dz) in floors]
            if not nearby:
                continue
            base = min(nearby)
            low = round(max(float(tri[:,1].min()),base)*2)/2
            high = round(min(float(tri[:,1].max()),base+12)*2)/2
            if high-low < 1:
                continue
            old = walls.get((x,z),(low,high))
            walls[(x,z)] = (min(old[0],low),max(old[1],high))
    voxels = [[int(x),int(z),lo,hi] for (x,z),(lo,hi) in sorted(walls.items())]
    conceal = GeometricVision(mesh, VisionConfig(half_fov_degrees=180,body_heights=(.12,.25,.35)))
    ambush = []
    for region in data['points']:
        target = region['position']
        for side, route in enumerate(region['routes']):
            if len(route)<3:
                continue
            threat = min(route[:-1],key=lambda p:abs(math.dist(p,target)-18))
            if math.dist(threat,target)<8:
                continue
            enemy = PlayerTruth('enemy',1,8000,True,tuple(threat),0.,1.,1.,False,0,False)
            choices = []
            for c in cells[::2]:
                pos = c[:3]
                distance = math.dist(pos,target)
                if not c[6] or not 5<distance<=22 or abs(c[1]-target[1])>3.5:
                    continue
                if math.dist(pos,threat)>100:
                    continue
                # Must cover the choke with an unobstructed standing body ray;
                # projectile volume, exact floor ink and emergence are unknown.
                if not mesh.clear(np.array(pos)+[0,1.1,0],np.array(target)+[0,.7,0]):
                    continue
                hidden = PlayerTruth('candidate',0,8000,True,tuple(pos),0.,1.,1.,True,0,True)
                w = conceal.witnesses(RefereeSnapshot('ambush-offline',0,(enemy,hidden)),'enemy')[0]
                if w.line_clear is not False:
                    continue
                choices.append((abs(distance-15), c, distance))
            chosen=[]
            for _,c,distance in sorted(choices,key=lambda v:v[0]):
                if any(math.hypot(c[0]-p[0],c[2]-p[2])<8 for p in chosen):
                    continue
                chosen.append(c)
                ambush.append(dict(position=c[:3],region=region['id'],label=region['label'],
                    threat=threat,approach_side='A' if side==0 else 'B',distance=round(distance,1),
                    light=distance<=19,full=True,hidden='static_squid_body_occluded',swimmable=True))
                if len(chosen)==2:
                    break
    extra=dict(cells=cells,walls=voxels,ambush=ambush,
               geometry_method='2u top reachable floor tiles + vertical-collision wall voxels; y quantized .5u; decorative walls capped 12u above nearby floor')
    cache.write_text(json.dumps(extra,ensure_ascii=False,separators=(',',':'),allow_nan=False))
    print(f"  3D {data['name']}: {len(cells)} floor tiles / {len(voxels)} wall voxels / {len(ambush)} conditional ambush candidates",flush=True)
    data.update(extra)
    return data
