"""Owned D3 native fixture, with independent weapon truth and full rendering."""
import hashlib,json,re,sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'tools/zipcaster')]
from a6_lab import Lab,neutral
from rl.native_start import NativeSession,validate_runtime
from arena.referee_api import RefereeAPI
import rl.session as session_module
HOST=ROOT/'work/d2b/round2-world-build/dmhost-sensors'
MODULES=HOST.parent/'modules'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
class DuelLab(Lab):
    def __init__(self,name,stage=1,host=HOST,modules=MODULES):
        host,patched=validate_runtime(host,modules)
        super().__init__('d3-'+name,1800,stage,native_runtime=dict(host=str(host),patched=str(patched)))
        self.env.config.update(weapons=[8000,50],pixels=True)
        self.result.update(schema='inklab.d3.native.v1',weapons=[8000,50],pixels=True,clock='fixed60',host_sha256=sha(host),driver_sha256=sha(__file__))
    def start(self):
        super().start()
        self.api=RefereeAPI(self.out.name,self.origins,dict(zip(self.env.possible_agents,[8000,50])),dict(zip(self.env.possible_agents,[0,1])),ROOT/f"work/arena/maps/{self.atlas.data['name']}/sight.npz",stage_id=self.stage)
        self.api.update(self.env.process_infos)
        self.result['weapon_setup_readbacks']=[]
        for n,weapon in enumerate([8000,50]):
            line=re.findall(r'SPL3_WEAPON requested=(\d+) local_kit_reads=(\d+) save_writes=(\d+)',self.env.session.text(n))
            if not line or tuple(map(int,line[-1]))!=(weapon,2,0):raise AssertionError('native weapon setup gate missing')
            self.result['weapon_setup_readbacks'].append(line[-1])
        self.save();return self
    def finish(self):
        self.close()
        self.result['raw_sha256']={str(self.out/'steps.jsonl'):sha(self.out/'steps.jsonl')}
        for n in (0,1):
            p=Path(self.result.get('session',''))/f'player-{n}/host.log'
            if p.is_file():self.result['raw_sha256'][str(p)]=sha(p)
        self.save()
@contextmanager
def owned_options(special=False,sensors=False,bullets=False,capture=None,meter='infinite'):
    if meter not in ('full','infinite'):raise ValueError('invalid fixture meter')
    original=NativeSession.host_options;original_env=session_module.host_environment
    def options(self,player):
        return original(self,player)|{'DM_RL_STALL_SECONDS':'120'}|({'DM_D2B_SENSOR':'1'}if sensors and player==0 else{})|({'DM_TEST_SPECIAL':meter}if special and player==0 else{})|({'DM_D3_BULLET':'1'}if bullets and player==1 else{})|({'DM_D3_BULLET_CAPTURE':str(capture)}if capture and player==1 else{})
    def environment(*a,**kw):
        result=original_env(*a,**kw);result.pop('DM_WATCH',None);result.pop('DM_WATCH_STALL',None);return result
    with patch.object(NativeSession,'host_options',options),patch.object(session_module,'host_environment',environment):yield
