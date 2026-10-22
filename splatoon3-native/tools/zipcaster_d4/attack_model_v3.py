"""Finite native-informed shot model, independent of route search.

First body/field/lifetime comparison; explicit multi-sphere assembly and exact
four-frame contact box/cylinder. Model uncertainty is returned, never P=0.
"""
import json,math,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d4.attack_geometry import basis,muzzle,trace_contacts,contact_overlap,xyz
from tools.zipcaster_d4.model_v2 import segment_distance

class Shots:
    def __init__(self,world,fit):
        self.world=world
        self.fit=json.loads(Path(fit).read_text())if isinstance(fit,(str,Path))else fit
        self.parameters=json.loads((ROOT/'work/a6/parameters.json').read_text())
        for key in ['ShotSlashOffset_Vertical','ShotSlashOffset_L']:
            xyz(self.parameters['swing'][key])
        for key in ['vertical_contact','horizontal_contact']:
            if self.parameters[key]['MoveParam']['AliveFrame']!=4:
                raise ValueError('unsupported contact lifetime; requires4-frame11.3.0 fixture')

    def direction(self,yaw,pitch,style):
        coeff=self.fit['elevation'][style]['coefficients']
        elevation=coeff[0]*pitch+coeff[1]
        return basis(yaw,elevation)[:,2],elevation

    def evaluate(self,source,target,style,yaw,pitch,target_positions=None):
        source,target=np.asarray(source,float),np.asarray(target,float)
        if abs(pitch)>.85:raise ValueError('outside accepted direct-aim fixture')
        direction,elevation=self.direction(yaw,pitch,style)
        origin,launch=muzzle(source,yaw,elevation,style)
        life=26 if style=='full'else 6
        speed=.8 if style=='full'else 2.82
        age=np.arange(life+1,dtype=float)
        points=origin+age[:,None]*direction*speed
        if style=='full':points[:,1]-=.0027*np.maximum(age-22,0)*(np.maximum(age-22,0)+1)/2
        points=np.concatenate([[launch],points]);frames=np.r_[-1.,age]
        enemies=np.repeat(target[None,:],len(points),axis=0)if target_positions is None else np.asarray(target_positions,float)
        collision=self.parameters[('vertical'if style=='full'else'horizontal')+'_projectile']['CollisionParam']
        clipped=trace_contacts(self.world.field,points,frames,enemies,yaw,elevation,collision)
        uncut=trace_contacts(self.world.field,points,frames,enemies,yaw,elevation,collision,side_policy='core_lifetime')
        core=trace_contacts(self.world.field,points,frames,enemies,yaw,elevation,collision,True)
        radius=collision['ParamArray'][clipped['damage_sphere']]['InitRadiusForPlayer']if clipped['hit']else None
        body_margin=-math.inf
        if clipped['hit']:
            offset=basis(yaw,elevation)@xyz(collision['OffsetArray'][clipped['damage_sphere']])
            distances=[segment_distance(a+offset-ea,b+offset-eb,np.array([0.,.35,0.]),np.array([0.,1.30,0.]))for a,b,ea,eb in zip(points,points[1:],enemies,enemies[1:])]
            body_margin=.35+radius-min(distances)
            sphere=clipped['side_events'][clipped['damage_sphere']]
            ends=[float(life)]
            if sphere['field_time']is not None:ends.append(sphere['field_time'])
            if clipped['core_field_time']is not None:ends.append(clipped['core_field_time'])
            clearance=min(body_margin,(min(ends)-max(0.,clipped['body_time']))*speed)
        else:
            clearance=-math.inf
            for j,shape in enumerate(collision['ParamArray']):
                offset=basis(yaw,elevation)@xyz(collision['OffsetArray'][j])
                distance=min(segment_distance(a+offset-ea,b+offset-eb,np.array([0.,.35,0.]),np.array([0.,1.30,0.]))for a,b,ea,eb in zip(points,points[1:],enemies,enemies[1:]))
                penetration=.35+shape['InitRadiusForPlayer']-distance
                event=clipped['side_events'][j]
                if event['body_time']is not None:
                    walls=[t for t in [clipped['core_field_time'],event['field_time']]if t is not None]
                    if walls:penetration=min(penetration,(min(walls)-event['body_time'])*speed)
                clearance=max(clearance,penetration)
        return dict(style=style,yaw=float(yaw),native_pitch=float(pitch),elevation=elevation,
                    origin=origin.tolist(),launch_start=launch.tolist(),core=core,
                    independent=clipped,core_lifetime=uncut,
                    hit=clipped['hit'],assembly_uncertain=clipped['hit']!=uncut['hit'],
                    clearance=float(clearance),body_margin=float(body_margin),
                    player_contact_age=max(0.,clipped['body_time'])if clipped['hit']else None,
                    damage=70 if style=='full'else 35,lifetime=life)

    def best(self,source,target,style,step=.01):
        yaw=math.atan2(target[0]-source[0],target[2]-source[2])
        rows=[self.evaluate(source,target,style,yaw,float(p))for p in np.linspace(-.85,.85,round(1.7/step)+1)]
        # A ray barely clearing a ledge is not robust simply because its
        # first wall collision is far away. Inflate field spheres up to the
        # first body contact to measure actual geometric clearance.
        collision=self.parameters[('vertical'if style=='full'else'horizontal')+'_projectile']['CollisionParam']
        for row in rows:
            if not row['hit']:continue
            direction,elevation=self.direction(yaw,row['native_pitch'],style)
            origin,launch=muzzle(source,yaw,elevation,style)
            end=origin+direction*(.8 if style=='full'else 2.82)*row['player_contact_age']
            rotation=basis(yaw,elevation);ids={collision['CoreIndex'],row['independent']['damage_sphere']}
            starts=[];ends=[];radii=[]
            for index in ids:
                offset=rotation@xyz(collision['OffsetArray'][index])
                starts.extend([launch+offset,origin+offset]);ends.extend([origin+offset,end+offset])
                radii.extend([collision['ParamArray'][index]['InitRadiusForField']]*2)
            starts,ends,radii=map(np.asarray,(starts,ends,radii));delta=ends-starts;lengths=np.linalg.norm(delta,axis=1);directions=delta/np.maximum(lengths[:,None],1e-15)
            low,high=0.,max(0.,row['clearance'])
            for _ in range(9):
                middle=(low+high)/2
                hits,_,_=self.world.field.sphere(starts,directions,radii+middle,np.maximum(lengths,1e-12))
                if np.any(hits>=0):high=middle
                else:low=middle
            row['field_margin']=low
            row['clearance']=min(row['clearance'],low)
        return max(rows,key=lambda r:(r['hit']and not r['assembly_uncertain'],r['clearance'], -abs(r['native_pitch'])))

    def contact(self,source_path,target_path,style,yaw,pitch,receiver='ColBullet'):
        """Four actual pose transforms, box+enabled cylinder union.

        Body-candidate is diagnostic until character-controller world transform
        is verified; it is never silently substituted for ColBullet.
        """
        source_path,target_path=map(lambda p:np.asarray(p,float),(source_path,target_path))
        if len(source_path)!=4 or len(target_path)!=4:raise ValueError('exact4-frame contact interval')
        _,elevation=self.direction(yaw,pitch,style)
        rotation=basis(yaw,elevation)
        key='vertical'if style=='full'else'horizontal'
        shape=self.parameters[key+'_contact']['ShapeParam']
        offset=xyz(self.parameters['swing']['ShotSlashOffset_Vertical'if style=='full'else'ShotSlashOffset_L'])
        if receiver=='ColBullet':radius,low,high=.35,.35,1.30
        elif receiver=='Body-candidate':radius,low,high=.6,.6,1.30
        else:raise ValueError('explicit receiver')
        frames=[]
        for t,(source,target)in enumerate(zip(source_path,target_path)):
            frames.append(dict(age=t,**contact_overlap(source+rotation@offset,rotation,shape,target,radius,low,high)))
        return dict(hit=any(r['hit']for r in frames),first_age=next((r['age']for r in frames if r['hit']),None),
                    damage=140 if style=='full'else 20,receiver=receiver,frames=frames,
                    shape='box+finite-cylinder'if shape['HasCylinderShape']else'box',
                    native_transform_verified=False)
