import unittest
import numpy as np
from tools.zipcaster_d4.geometry import Mesh
from tools.zipcaster_d4.attack_geometry import basis
from tools.zipcaster_d4.attack_batch import trace_batch as full
from tools.zipcaster_d4.attack_batch_v2 import trace_batch as coalesced


class CoalescingTests(unittest.TestCase):
    def test_body_first_and_collinear_field_preserve_first_hits(self):
        wall=Mesh([[[-4,-2,5],[4,-2,5],[-4,5,5]],[[4,-2,5],[4,5,5],[-4,5,5]]])
        col=dict(CoreIndex=0,OffsetArray=[dict(X=0,Y=0,Z=0),dict(X=1,Y=0,Z=0)],
                 ParamArray=[dict(InitRadiusForField=.2,EndRadiusForField=.3,InitRadiusForPlayer=.4)]*2)
        rng=np.random.default_rng(281007)
        for gravity in [False,True]:
            angles=np.linspace(-.7,.7,60);rot=np.array([basis(0,e)for e in angles])
            age=np.r_[-1.,np.arange(27)]
            # Launch speed changes but stays collinear. The gravity tail
            # changes spatial direction and must never be collapsed.
            distance=np.r_[0.,1.4+np.arange(27)*.8]
            points=np.array([np.array([0,1,0])+distance[:,None]*r[:,2]for r in rot])
            if gravity:points[:,:,1]-=.0027*np.maximum(age-22,0)*(np.maximum(age-22,0)+1)/2
            enemy=np.array([[[rng.uniform(-1,1),rng.uniform(-2,3),rng.uniform(2,11)]]*len(age)for _ in angles])
            for bound in ['initial','end']:
                a=full(wall,points,age,enemy,rot,col,bound)
                b=coalesced(wall,points,age,enemy,rot,col,bound)
                for name in ['hit','core_hit','assembly_uncertain']:
                    np.testing.assert_array_equal(a[name],b[name])
                np.testing.assert_allclose(a['body_times'],b['body_times'],atol=1e-10)
                np.testing.assert_allclose(a['field_times'][b['field_queried']],b['field_times'][b['field_queried']],atol=1e-8)
                self.assertTrue((~b['field_queried']).any())


if __name__=='__main__':unittest.main()
