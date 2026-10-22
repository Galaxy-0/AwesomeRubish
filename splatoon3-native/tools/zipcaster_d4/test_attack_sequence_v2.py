import unittest
import numpy as np
from tools.zipcaster_d4.attack_sequence_v2 import sequence


class FixtureShots:
    def __init__(self,contact=True):self.allow_contact=contact;self.targets=[]
    def best_contact(self,source,target,style):return dict(yaw=0.,native_pitch=0.,hit=self.allow_contact)
    def contact(self,source_path,target_path,style,yaw,pitch,receiver='ColBullet'):
        return dict(hit=self.allow_contact,first_age=0,damage=140 if style=='full'else 20)
    def best(self,source,target,style):
        self.targets.append(np.array(target));return dict(yaw=0.,native_pitch=0.,lifetime=26 if style=='full'else 6)
    def evaluate(self,*args):
        style=args[2];return dict(hit=True,assembly_uncertain=False,player_contact_age=2,damage=70 if style=='full'else 35)


class SequenceTests(unittest.TestCase):
    def profiles(self):
        p={k:dict(frames=[0,4,48],distance=[0,.1,.7],measured_until=48)for k in ['full','light','light_contact_then_projectile']}
        p['light_contact_then_projectile']['joint_hp_ages']=[dict(age=0,drop=20),dict(age=4,drop=35)]
        return p
    def test_full_contact_kills_without_second_cast(self):
        r=sequence(FixtureShots(),np.zeros((180,3)),[0,0,4],[(40,'full'),(76,'light')],self.profiles())
        self.assertEqual(r['kill_frame'],48)
        self.assertEqual([e['damage']for e in r['damage_events']],[140])
        self.assertEqual(len(r['casts']),1)
    def test_light_contact_and_blade_are_separate_native_events(self):
        shots=FixtureShots()
        r=sequence(shots,np.zeros((180,3)),[0,0,2.6],[(20,'light'),(50,'light')],self.profiles())
        self.assertEqual([e['damage']for e in r['damage_events']],[20,35,20,35])
        self.assertEqual([e['due']for e in r['damage_events']],[33,37,63,67])
        self.assertEqual(r['kill_frame'],67)
        self.assertGreater(shots.targets[1][2],shots.targets[0][2])
        self.assertEqual(r['uncertainties'],[])
    def test_remote_only_full_light_keeps70_plus35(self):
        r=sequence(FixtureShots(False),np.zeros((180,3)),[0,0,8],[(40,'full'),(76,'light')],self.profiles())
        self.assertEqual([e['damage']for e in r['damage_events']],[70,35])
        self.assertEqual(r['kill_frame'],93)


if __name__=='__main__':unittest.main()
