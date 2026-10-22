"""Explicit D4 fallback: projectile-only feasible routes, no contact credit.

A conservative enclosing bound only REJECTS possible-contact routes. It never
awards a hit. Both unknown140/20 branches disappear only when native contact
shapes are guaranteed disjoint from either candidate receiver for all4frames.
This does not close contact rules, clipping or the unrestricted optimum.
"""
import numpy as np
from tools.zipcaster_d4.attack_geometry import xyz
from tools.zipcaster_d4.contact_shape import native_shape
from tools.zipcaster_d4.attack_model_safe import Shots as BaseShots
from tools.zipcaster_d4.attack_sequence_v2 import sequence as base_sequence


def contact_exclusion(parameters,source_path,target_path,style,receiver_radius=.6):
    source,target=map(lambda x:np.asarray(x,float),(source_path,target_path))
    if source.shape!=(4,3)or target.shape!=(4,3):raise ValueError('four native contact frames required')
    key='vertical'if style=='full'else'horizontal'
    shape=native_shape(parameters[key+'_contact']['ShapeParam'])
    box=np.linalg.norm(np.abs(xyz(shape['BoxCenter']))+xyz(shape['BoxHalfExtents']))
    cylinder=max(np.linalg.norm(xyz(shape[k]))for k in ['CylinderCenterA','CylinderCenterB'])+shape['CylinderRadius']if shape['HasCylinderShape']else 0.
    offset=xyz(parameters['swing']['ShotSlashOffset_Vertical'if style=='full'else'ShotSlashOffset_L'])
    # Read native contact birth is yaw-only foot+offset. Allow every shape
    # orientation, not just the rejected engine-matrix hypothesis. Ignoring
    # height is conservative for arbitrary target capsule axis height.
    bound=max(box,cylinder)+np.linalg.norm(offset[[0,2]])+receiver_radius+1e-4
    distance=np.linalg.norm((source-target)[:,[0,2]],axis=1)
    return dict(certified_disjoint=bool(np.all(distance>bound)),horizontal_bound=float(bound),
                minimum_horizontal_distance=float(distance.min()),margin=float(distance.min()-bound),
                contact_damage_interval=[0,140 if style=='full'else 20],frames=4,
                predicate='Orientation-independent enclosing bound used only to reject uncertain-contact routes.')


class Shots(BaseShots):
    def best_contact(self,source,target,style,step=.01):
        # Native executor uses one projectile aim throughout this fallback.
        # This result never grants or optimizes contact damage.
        aim=self.best(source,target,style,step)
        return dict(yaw=aim['yaw'],native_pitch=aim['native_pitch'],hit=False,
                    contact=True,damage=0,unknown_native_damage=True)

    def contact(self,source_path,target_path,style,yaw,pitch,receiver='ColBullet'):
        exclusion=contact_exclusion(self.parameters,source_path,target_path,style)
        return dict(hit=False,first_age=None,damage=0,receiver=receiver,
                    excluded_from_planning=True,exclusion=exclusion,
                    unknown_native_damage=not exclusion['certified_disjoint'],
                    frames=[dict(age=i,hit=False)for i in range(4)])


def sequence(shots,source_path,enemy,inputs,recoil,receive_delay=4):
    result=base_sequence(shots,source_path,enemy,inputs,recoil,receive_delay)
    proofs=[c['contact']['exclusion']for c in result['casts']]
    unsafe=any(not p['certified_disjoint']for p in proofs)
    if unsafe:result['uncertainties'].append('possible contact: native140/20 and knockback branches unclosed; route rejected')
    result.update(contact_exclusion_certified=bool(proofs and not unsafe),contact_exclusion=proofs,
                  eligible_feasible_route=bool(proofs and not unsafe and not result['uncertainties']),
                  native_contact_verified=False,
                  scope='Projectile-only feasible route. Contact is unknown, not native0; any possible contact makes route ineligible. Full D4 and global optimum unclosed.')
    return result
