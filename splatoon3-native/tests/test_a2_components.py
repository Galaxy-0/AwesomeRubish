"""Loadout validation and production constructor callback without game data."""
import os
from pathlib import Path
import subprocess
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rl.loadout import encode_loadout,uniform_loadout
from a2_metrics import full_tank_capacity


class LoadoutTest(unittest.TestCase):
    def test_full_legal_kit(self):
        self.assertEqual(encode_loadout(uniform_loadout('swim_speed_up')),','.join(['5']*12))
        gear={p:dict(main='quick_super_jump',subs=['quick_super_jump']*3) for p in ('head','clothes','shoes')};gear['head']['main']='comeback';gear['clothes']['main']='ninja_squid';gear['shoes']['main']='stealth_jump'
        self.assertEqual(encode_loadout(gear),'18,10,10,10,19,10,10,10,24,10,10,10')

    def test_reject_bad_slots_and_names(self):
        for field,value in [('main','none'),('main','invalid'),('subs',['none']*3),('subs',['none']*2),('subs',['comeback']*3),('main','stealth_jump')]:
            gear=uniform_loadout();gear['head'][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):encode_loadout(gear)
        with self.assertRaises(ValueError):encode_loadout({})

    def test_full_tank_excludes_partial_swing_and_later_refill(self):
        values=[(1,.7),(.7,.4),(.4,.1),(.1,0),(0,1),(1,.7)]
        history=[dict(cycle=i,before={'p':b},losses={'p':b-a}) for i,(b,a) in enumerate(values)]
        self.assertEqual(full_tank_capacity(history,'p')['full_cost_swings'],3)
        with self.assertRaises(AssertionError):full_tank_capacity(history[:3],'p')

    def test_production_callback_and_fail_closed(self):
        binary=ROOT/'upstream/dm/host/tests/build/t_spl3_gear'
        cases=[(None,'',True),(None,'survey',True),('original','',True),('5,5,5,5,1,1,1,1,10,10,10,10','',True),
               ('10,10,10,10,10,10,10,10,10,10,10,10','unknown',False),('10,10,10,10,10,10,10,10,10,10,10,10','missing',False),
               ('10,10,10,10,10,10,10,10,10,10,10,10','container',False)]
        cases += [(v,'',False) for v in ('0,0,0,0,0,0,0,0,0,0,0,0','','5','5,'*12,'27,'+','.join(['0']*11),
                                         '0,18,0,0,0,0,0,0,0,0,0,0','24,0,0,0,0,0,0,0,0,0,0,0')]
        for value,mode,success in cases:
            env={k:v for k,v in os.environ.items() if not k.startswith('DM_')}
            if value is not None:env['DM_GEAR']=value
            if mode=='survey':env['DM_GEAR_SURVEY']='1';mode=''
            result=subprocess.run([str(binary)]+([mode] if mode else []),env=env,capture_output=True,timeout=5)
            with self.subTest(value=value,mode=mode):self.assertEqual(result.returncode==0,success,result.stderr.decode())


if __name__=='__main__':unittest.main()
