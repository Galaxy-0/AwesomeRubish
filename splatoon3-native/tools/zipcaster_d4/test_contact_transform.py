import unittest
import numpy as np
from tools.zipcaster_d4.audit_contact_transform import bind_calls


class TransformOwnershipTests(unittest.TestCase):
    def test_equal_numeric_matrix_is_not_an_owner_witness(self):
        engine=0x10000
        position=np.array([-8.4,4.2,-2.8],dtype='<f4')
        rotation=np.eye(3,dtype='<f4')
        blobs={'d4_transform_source':position.tobytes(),
               'd4_transform_rotation':rotation.tobytes()}
        engines={engine:[dict(frame=81,position=position,rotation=rotation)]}
        calls=[dict(frame=80,source=engine+0x25c,rotation=engine+0x268,blobs=blobs),
               dict(frame=81,source=engine+0x25c,rotation=engine+0x300,blobs=blobs),
               dict(frame=81,source=engine+0x125c,rotation=engine+0x1268,blobs=blobs)]
        rows=bind_calls(calls,engines)
        self.assertEqual(len(rows),1)
        self.assertTrue(rows[0]['same_engine_source_and_rotation_pointers'])
        self.assertEqual(rows[0]['position_error'],0)
        self.assertEqual(rows[0]['rotation_max_error'],0)


if __name__=='__main__':unittest.main()
