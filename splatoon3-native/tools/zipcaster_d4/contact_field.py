"""Diagnostic solid box/finite cylinder against actual field triangles.

No sphere damage proxy. SAT is exact up to the declared epsilon. Cylinder
intersection clips the triangle to the axial slab, then tests its projected
convex polygon against the circular cross section. Closest witnesses are
geometric constructions, not claims about a native contact notification.
"""
import math
import numpy as np
from tools.zipcaster_d4.attack_geometry import xyz

EPS=1e-8


def triangle_box(triangle, center, half):
    t=np.asarray(triangle,float)-center
    edges=np.roll(t,-1,axis=0)-t
    axes=[*np.eye(3),np.cross(edges[0],edges[1])]
    axes.extend(np.cross(edge,axis)for edge in edges for axis in np.eye(3))
    for axis in axes:
        length=np.linalg.norm(axis)
        if length<1e-12:continue
        axis=axis/length
        p=t@axis;extent=float(np.abs(axis)@half)
        if p.min()>extent+EPS or p.max()<-extent-EPS:return False
    return True


def clip(poly, axis, maximum):
    out=[]
    for a,b in zip(poly,np.roll(poly,-1,axis=0)):
        da,db=float(a@axis-maximum),float(b@axis-maximum)
        if da<=EPS:out.append(a)
        if (da<0<db)or(db<0<da):out.append(a+(b-a)*(da/(da-db)))
    return np.array(out).reshape(-1,3)


def triangle_cylinder(triangle, ca, cb, radius):
    axis=np.asarray(cb,float)-ca;length=np.linalg.norm(axis)
    if length<1e-12:raise ValueError('nondegenerate finite cylinder required')
    axis/=length;center=(np.asarray(ca)+cb)/2
    poly=clip(np.asarray(triangle,float)-center,axis,length/2)
    if not len(poly):return False
    poly=clip(poly,-axis,length/2)
    if not len(poly):return False
    radial=poly-(poly@axis)[:,None]*axis
    # Projection may collapse to a line; edge distances handle that case.
    nearest=math.inf;crosses=[]
    for a,b in zip(radial,np.roll(radial,-1,axis=0)):
        delta=b-a;den=float(delta@delta)
        q=a+delta*(np.clip(-a@delta/den,0,1)if den>1e-20 else 0.)
        nearest=min(nearest,float(q@q))
        crosses.append(float(np.cross(a,b)@axis))
    area=sum(crosses)
    contains=abs(area)>1e-12 and(all(c>=-EPS for c in crosses)or all(c<=EPS for c in crosses))
    return contains or nearest<=(radius+EPS)**2


def shape_field(triangles, origin, rotation, shape):
    center=xyz(shape['BoxCenter']);half=xyz(shape['BoxHalfExtents'])
    corners=np.array([center+half*[x,y,z]for x in [-1,1]for y in [-1,1]for z in [-1,1]])
    world=corners@rotation.T+origin;low,high=world.min(axis=0),world.max(axis=0)
    if shape['HasCylinderShape']:
        ca,cb=xyz(shape['CylinderCenterA']),xyz(shape['CylinderCenterB'])
        axis=rotation@(cb-ca);length=np.linalg.norm(axis);axis/=length
        c=origin+rotation@((ca+cb)/2)
        extent=np.abs(axis)*length/2+shape['CylinderRadius']*np.sqrt(np.maximum(0,1-axis**2))
        low=np.minimum(low,c-extent);high=np.maximum(high,c+extent)
    ids=np.flatnonzero((triangles.max(axis=1)>=low-EPS).all(axis=1)&(triangles.min(axis=1)<=high+EPS).all(axis=1))
    hits=[]
    for index in ids:
        triangle=triangles[index];local=(triangle-origin)@rotation
        box=triangle_box(local,center,half)
        cylinder=bool(shape['HasCylinderShape']and triangle_cylinder(local,ca,cb,shape['CylinderRadius']))
        if not(box or cylinder):continue
        normal=np.cross(triangle[1]-triangle[0],triangle[2]-triangle[0]);normal/=max(np.linalg.norm(normal),1e-15)
        hits.append(dict(field_triangle=int(index),box=box,cylinder=cylinder,normal=normal.tolist(),
                         surface_kind='floor-like'if abs(normal[1])>.9 else'wall-like'if abs(normal[1])<.2 else'slope',
                         plane_offset=float(normal@triangle[0])))
    return hits


def closest_witness(origin, rotation, shape, enemy):
    """Nearest solid-shape point to receiver axis; overlap need not be unique."""
    a=rotation.T@(np.asarray(enemy)+[0,.35,0]-origin)
    b=rotation.T@(np.asarray(enemy)+[0,1.3,0]-origin)
    center,half=xyz(shape['BoxCenter']),xyz(shape['BoxHalfExtents'])
    def box(p):return center+np.clip(p-center,-half,half)
    projectors=[('box',box)]
    if shape['HasCylinderShape']:
        ca,cb=xyz(shape['CylinderCenterA']),xyz(shape['CylinderCenterB'])
        axis=cb-ca;length=np.linalg.norm(axis);axis/=length;c=(ca+cb)/2
        def cylinder(p):
            d=p-c;axial=float(d@axis);radial=d-axial*axis
            return c+axis*np.clip(axial,-length/2,length/2)+radial*min(1,shape['CylinderRadius']/max(np.linalg.norm(radial),1e-15))
        projectors.append(('cylinder',cylinder))
    rows=[]
    for name,project in projectors:
        def sq(t):
            p=a+(b-a)*t;delta=p-project(p);return float(delta@delta)
        left,right=0.,1.;phi=(math.sqrt(5)-1)/2
        for _ in range(72):
            x=right-phi*(right-left);y=left+phi*(right-left)
            if sq(x)<=sq(y):right=y
            else:left=x
        t=min([0.,1.,(left+right)/2],key=sq);p=a+(b-a)*t;q=project(p)
        rows.append(dict(shape=name,distance=math.sqrt(sq(t)),axis_point=(origin+rotation@p).tolist(),
                         shape_point=(origin+rotation@q).tolist(),nonunique_overlap=sq(t)<1e-14))
    return min(rows,key=lambda row:row['distance'])
