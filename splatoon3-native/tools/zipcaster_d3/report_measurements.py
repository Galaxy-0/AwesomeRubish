"""Reduce closed D3 measure rooms; preserve failures and timing limitations."""
import argparse,glob,json,math,sys,re,struct
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from native import ROOT,sha
from geometry import CollisionMesh

def reduce(cohort):
    rooms=[];shots=[];turn=[];mesh=CollisionMesh.load(ROOT/'work/arena/maps/Yunohana/sight.npz')
    for name in cohort:
        paths=sorted((ROOT/'work/a6').glob('d3-'+name+'-[0-9]*/result.json'))
        if len(paths)!=1:raise ValueError((name,len(paths)))
        p=paths[0];d=json.loads(p.read_text())
        if 'freeze_after'not in d:raise ValueError('room not closed: '+name)
        for source,digest in d.get('raw_sha256',{}).items():
            if sha(source)!=digest:raise AssertionError('changed raw record '+source)
        kits=[]
        for n,weapon in enumerate([8000,50]):
            text=(Path(d['session'])/f'player-{n}/host.log').read_text(errors='replace')
            values=re.findall(r'\[x21\+0xe8\]=([0-9a-f]{32})',text)
            kit=[struct.unpack('<4I',bytes.fromhex(v))for v in values]
            if not kit or any(k[0]!=weapon for k in kit):raise AssertionError('actual kit mismatch')
            kits.append(dict(process=n,main=kit[0][0],sub=kit[0][1],special=kit[0][2],samples=len(kit)))
        rooms.append(dict(native_kits=kits,measurement_config=d.get('measurement_config'),name=name,path=str(p.relative_to(ROOT)),sha256=sha(p),passed=d['passed'],errors=d['errors'],weapons=d.get('weapons'),weapon_setup=d.get('weapon_setup_readbacks'),loadouts=d.get('loadout_readbacks'),session=d.get('session'),owned_pids=d.get('owned_pids'),code_sha256=d.get('code_sha256'),raw_sha256=d.get('raw_sha256')))
        for trial,r in enumerate(d.get('measurements',[])):
            if r['kind']=='turn':
                yaw=[r['before']['view_yaw']]+[x['view']['view_yaw']for x in r['rows']]
                ds=np.arctan2(np.sin(np.diff(yaw)),np.cos(np.diff(yaw)));stable=ds[-40:]
                turn.append(dict(room=name,firing=r['firing'],present_frames=len(ds),stable_window=40,stable_degrees_per_second=float(np.sum(stable)/40*60*180/math.pi),first15_degrees=float(np.sum(ds[:15])*180/math.pi),view_sample_frames=[x['view']['sample_frame']for x in r['rows']]))
                continue
            first=r['before'];target_hp=first[0]['hp'];ink=first[1]['ink'];damages=[];launches=[]
            for x in r['rows']:
                hp=x['target']['hp'];current=x['shooter']['ink']
                if hp<target_hp-.01:damages.append(dict(receive_elapsed=x['frame']-r['rows'][0]['frame'],victim_present=x['target']['frame'],shooter_present=x['frame'],hp_before=target_hp*100,hp_after=hp*100,delta_hp=(target_hp-hp)*100,alive=x['target']['alive']))
                if current<ink-.007:launches.append(dict(shooter_present=x['frame'],view_sample_frame=x['view']['sample_frame'],ink_delta=ink-current))
                target_hp=hp;ink=current
            a=np.array(first[1]['position'])+[0,1.1,0];b=np.array(first[0]['position'])+[0,1.1,0]
            view=r['rows'][0]['view'];bearing=math.atan2(b[0]-a[0],b[2]-a[2]);body_error=math.atan2(math.sin(bearing-first[1]['heading']),math.cos(bearing-first[1]['heading']))
            shots.append(dict(room=name,trial=trial,requested_distance=r['requested_distance'],actual_distance=r['actual_distance'],shooter_position=first[1]['position'],target_position=first[0]['position'],height_difference=first[0]['position'][1]-first[1]['position'][1],center_ray_clear=mesh.clear(a,b),body_error_degrees=body_error*180/math.pi,view_yaw=view['view_yaw'],view_pitch=view['view_pitch'],pitch_offset=r.get('pitch_offset'),fire_frames=r['fire_frames'],launches=launches,launch_present_intervals=list(np.diff([x['shooter_present']for x in launches]).astype(int).tolist()),launch_sample_intervals=list(np.diff([x['view_sample_frame']for x in launches]).astype(int).tolist()),damage_events=damages,hit=bool(damages),target_dead=not bool(r['rows'][-1]['target']['alive'])))
    return dict(schema='inklab.d3.measurements.v1',cohort=cohort,rooms=rooms,shots=shots,turn=turn,parameters=json.loads((ROOT/'work/d3/parameters.json').read_text()),limits=['Native .52 setup uses two verified kit accessor overrides, not a persistent save write; 52HP hit provides independent behavioral evidence.','Position/camera/ink are periodically sampled; receive present is not native bullet creation or impact time.','Network delivery can coalesce victim HP decrements; observed two-hit gap is not firing cadence.','Center ray excludes ordinary static occlusion only; muzzle ray/swept body collision and spread remain possible miss causes.','A hit/miss fraction is target-hit dispersion, not a recovered angular spread distribution.','No direct native bullet coordinate sensor yet; SpawnSpeed is a parameter, not a measured effective speed.'])
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('cohort',nargs='+');p.add_argument('--out',type=Path,required=True);a=p.parse_args();r=reduce(a.cohort);a.out.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(rooms=len(r['rooms']),shots=len(r['shots']),turn=r['turn']),indent=2))
