"""Batch implementation of the v3 finite aim scan; contact not yet certified."""
import math
import numpy as np
from tools.zipcaster_d4.attack_model_v3 import Shots as ScalarShots
from tools.zipcaster_d4.attack_geometry import basis, xyz, contact_overlap
from tools.zipcaster_d4.attack_batch import (trace_batch, capsule_axis_distance,
    segment_box_distances,segment_cylinder_distances)
from tools.zipcaster_d4.contact_shape import native_shape


class Shots(ScalarShots):
    def contact(self,source_path,target_path,style,yaw,pitch,receiver='ColBullet'):
        source_path,target_path=map(lambda x:np.asarray(x,float),(source_path,target_path))
        if len(source_path)!=4 or len(target_path)!=4:raise ValueError('exact4-frame contact interval')
        if receiver=='ColBullet':body=(.35,.35,1.30)
        elif receiver=='Body-candidate':body=(.6,.6,1.30)
        else:raise ValueError('explicit receiver')
        key='vertical'if style=='full'else'horizontal'
        shape=native_shape(self.parameters[key+'_contact']['ShapeParam'])
        offset=xyz(self.parameters['swing']['ShotSlashOffset_Vertical'if style=='full'else'ShotSlashOffset_L'])
        _,elevation=self.direction(yaw,pitch,style)
        rotation=basis(yaw,elevation)
        origin=source_path[0]+basis(yaw,0)@offset
        frames=[dict(age=t,**contact_overlap(origin,rotation,shape,target,*body))
                for t,target in enumerate(target_path)]
        return dict(hit=any(r['hit']for r in frames),first_age=next((r['age']for r in frames if r['hit']),None),
                    damage=140 if style=='full' else 20,receiver=receiver,frames=frames,
                    shape='box+finite-cylinder'if shape['HasCylinderShape']else'box',
                    native_local_shape_verified=True,native_origin_verified=True,
                    native_transform_verified=True,
                    scope='Read native local shape and physics-fed direction rotation; static born shape over4frames. Airborne follow/no-follow remains a validation target.')

    def best_contact(self,source,target,style,step=.01):
        source,target=np.asarray(source,float),np.asarray(target,float)
        yaw=math.atan2(target[0]-source[0],target[2]-source[2])
        pitches=np.linspace(-.85,.85,round(1.7/step)+1)
        coeff=self.fit['elevation'][style]['coefficients']
        rotations=np.array([basis(yaw,coeff[0]*p+coeff[1])for p in pitches])
        offset=xyz(self.parameters['swing']['ShotSlashOffset_Vertical'if style=='full'else'ShotSlashOffset_L'])
        origin=source+basis(yaw,0)@offset
        shape=native_shape(self.parameters[('vertical'if style=='full'else'horizontal')+'_contact']['ShapeParam'])
        a=np.einsum('pji,j->pi',rotations,target+[0,.35,0]-origin)
        b=np.einsum('pji,j->pi',rotations,target+[0,1.30,0]-origin)
        distance=segment_box_distances(a,b,xyz(shape['BoxCenter']),xyz(shape['BoxHalfExtents']))
        if shape['HasCylinderShape']:
            distance=np.minimum(distance,segment_cylinder_distances(a,b,xyz(shape['CylinderCenterA']),xyz(shape['CylinderCenterB']),shape['CylinderRadius']))
        margin=.35-distance
        i=max(range(len(pitches)),key=lambda j:(margin[j],-abs(pitches[j])))
        return dict(yaw=yaw,native_pitch=float(pitches[i]),hit=bool(margin[i]>=0),
                    clearance=float(margin[i]),damage=140 if style=='full'else 20,
                    contact=True,native_transform_verified=True)

    def best(self, source, target, style, step=.01):
        source, target = np.asarray(source,float), np.asarray(target,float)
        yaw = math.atan2(target[0]-source[0],target[2]-source[2])
        pitches = np.linspace(-.85,.85,round(1.7/step)+1)
        coeff = self.fit['elevation'][style]['coefficients']
        elevations = coeff[0]*pitches+coeff[1]
        rotations = np.array([basis(yaw,e) for e in elevations])
        directions = rotations[:,:,2]
        if style == 'full':
            launch = np.repeat((source+[0,2.2,0])[None,:],len(pitches),axis=0)
            origins = launch+basis(yaw,0)[:,2]*.8
        else:
            launch = source+rotations[:,:,1]
            origins = launch+directions*1.4
        life,speed = (26,.8) if style == 'full' else (6,2.82)
        age = np.arange(life+1,dtype=float)
        points = origins[:,None,:]+age[None,:,None]*directions[:,None,:]*speed
        if style == 'full':
            points[:,:,1] -= .0027*np.maximum(age-22,0)*(np.maximum(age-22,0)+1)/2
        points = np.concatenate([launch[:,None,:],points],axis=1)
        frames = np.r_[-1.,age]
        enemies = np.broadcast_to(target,points.shape)
        collision = self.parameters[('vertical' if style=='full' else 'horizontal')+'_projectile']['CollisionParam']
        initial = trace_batch(self.world.field,points,frames,enemies,rotations,collision)
        end = trace_batch(self.world.field,points,frames,enemies,rotations,collision,'end')
        offsets = np.einsum('pij,kj->pki',rotations,np.array([xyz(o) for o in collision['OffsetArray']]))
        a = points[:,:-1,None,:]+offsets[:,None,:,:]-target
        b = points[:,1:,None,:]+offsets[:,None,:,:]-target
        distance = np.min(capsule_axis_distance(a,b),axis=1)
        radii = np.array([r['InitRadiusForPlayer'] for r in collision['ParamArray']])
        margins = .35+radii-distance
        chosen = initial['damage_sphere']
        ids = np.arange(len(pitches))
        time_stop = np.minimum(initial['field_times'][ids,chosen],initial['field_times'][:,collision['CoreIndex']])
        clearance = np.minimum(margins[ids,chosen],(np.minimum(life,time_stop)-np.maximum(initial['body_time'],0))*speed)
        # Same miss score as scalar: body penetration, limited by a preceding
        # field contact only if a body-contact time exists for that ball.
        all_stops = np.minimum(initial['field_times'],initial['field_times'][:,collision['CoreIndex'],None])
        limited = np.isfinite(initial['body_times']) & np.isfinite(all_stops)
        gap = np.zeros_like(all_stops)
        np.subtract(all_stops,initial['body_times'],out=gap,where=limited)
        miss_margin = np.max(np.where(limited,np.minimum(margins,gap*speed),margins),axis=1)
        clearance = np.where(initial['hit'],clearance,miss_margin)
        field_margin = np.zeros(len(pitches))
        good = np.flatnonzero(initial['hit'])
        if len(good):
            ball_indices = np.stack([np.full(len(good),collision['CoreIndex']),chosen[good]],axis=1)
            picked = offsets[good[:,None],ball_indices]
            starts = np.stack([launch[good,None,:]+picked,origins[good,None,:]+picked],axis=2)
            endpoint = origins[good]+directions[good]*speed*np.maximum(initial['body_time'][good,None],0)
            ends = np.stack([origins[good,None,:]+picked,endpoint[:,None,:]+picked],axis=2)
            lengths = np.linalg.norm(ends-starts,axis=-1)
            d = (ends-starts)/np.maximum(lengths[...,None],1e-15)
            field_radii = np.array([r['InitRadiusForField'] for r in collision['ParamArray']])[ball_indices]
            low, high = np.zeros(len(good)),np.maximum(clearance[good],0)
            for _ in range(9):
                middle = (low+high)/2
                rr = np.broadcast_to(field_radii[:,:,None]+middle[:,None,None],lengths.shape)
                hit,_,_ = self.world.field.sphere(starts.reshape(-1,3),d.reshape(-1,3),rr.reshape(-1),np.maximum(lengths.reshape(-1),1e-12))
                blocked = (hit.reshape(lengths.shape)>=0).any(axis=(1,2))
                high = np.where(blocked,middle,high)
                low = np.where(blocked,low,middle)
            field_margin[good] = low
            clearance[good] = np.minimum(clearance[good],low)
        uncertain = initial['assembly_uncertain'] | end['assembly_uncertain'] | (initial['hit'] != end['hit'])
        i = max(range(len(pitches)),key=lambda j:(initial['hit'][j] and not uncertain[j],clearance[j],-abs(pitches[j])))
        result = self.evaluate(source,target,style,yaw,float(pitches[i]))
        result.update(clearance=float(clearance[i]),field_margin=float(field_margin[i]),
                      radius_bound_uncertain=bool(initial['hit'][i] != end['hit'][i]),
                      assembly_uncertain=bool(uncertain[i]),batch_scan=True)
        return result
