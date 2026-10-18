"""Real two-peer HP correlation: gyro calibration, navigation, PvP and results."""
import sys,importlib.util,argparse,json,re,struct,math,time
from pathlib import Path
import numpy as np
from PIL import Image
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
spec=importlib.util.spec_from_file_location('field_test',root/'tests/test_m6_fields.py');test=importlib.util.module_from_spec(spec);spec.loader.exec_module(test)


def survey(env,out,result,step,observations):
    packets={};offsets={};history=[]
    def packet(n):
        p=env.session.out/f'player-{n}/host.log'
        with p.open('rb') as f:f.seek(offsets.get(n,0));data=f.read();offsets[n]=f.tell()
        matches=list(re.finditer(rb'RL_STATE frame=(\d+) sequence=\d+ data=([0-9a-f]{992})',data))
        if matches:packets[n]=bytes.fromhex(matches[-1][2].decode())
        if n not in packets:raise AssertionError('no own live packet for diagnostic')
        return packets[n]
    def camera(n):
        b=packet(n);cam=np.frombuffer(b,dtype='<f4')[23:26].astype(float)
        # The horizontal vector is encoded separately from the [-1,1] pitch scalar.
        cam[1]=struct.unpack_from('<f',b,0x68)[0];return cam
    def charge(n):return struct.unpack_from('<I',packet(n),0x80)[0]
    def run(actions,label):
        nonlocal observations
        if not env.agents:return False
        observations=step({a:actions[a] for a in env.agents},label)
        history.append(dict(label=label,infos=env.process_infos,charge={str(n):charge(n) for n in range(2)},camera={str(n):camera(n).tolist() for n in range(2)}))
        return True
    def actions():return {a:test.neutral() for a in env.agents}
    def image(label):
        for a,o in env.observations.items():Image.fromarray(o['pixels']).save(out/f'{label}-{a}.png')
    def epoch(label,fn,count):
        starts={str(n):(d/'host.log').stat().st_size for n,_,d in env.session.hosts};before=env.process_infos
        for i in range(count):
            if not env.agents:break
            if not run(fn(i),label):break
        ends={str(n):(d/'host.log').stat().st_size for n,_,d in env.session.hosts}
        result['epochs'].append(dict(label=label,log_starts=starts,log_ends=ends,before=before,after=env.process_infos))
        image(label);(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(label, {a:i['position'] for a,i in env.process_infos.items()},'charge',[charge(n) for n in range(2)],flush=True)
    def reset_view(i):
        a=actions()
        if i==0:
            for v in a.values():v['buttons'][5]=1
        return a
    epoch('reset-view',reset_view,3);before=camera(0)
    def gyro(i):
        a=actions();a['player_0']['gyro'][0]=.08;return a
    epoch('gyro-positive',gyro,3);after=camera(0)
    if abs(after[1]-before[1])<.05:raise AssertionError('gyro pitch did not change native camera vector')
    down=1 if after[1]<before[1] else -1
    result['gyro_effect']=dict(before=before.tolist(),after=after.tolist(),down_sign=down,passed=True)
    epoch('reset-view-again',reset_view,3)
    def pitch_down(i):
        a=actions();a['player_0']['gyro'][0]=down*.05;return a
    epoch('pitch-to-floor',pitch_down,2)
    def drive(n,target,paint=False,move=True):
        own=env.process_infos[f'player_{n}']['position'];dx=target[0]-own[0];dz=target[2]-own[2];distance=math.hypot(dx,dz)
        cam=camera(n);yaw=math.atan2(cam[0],cam[2]);wanted=math.atan2(dx,dz)
        error=math.atan2(math.sin(wanted-yaw),math.cos(wanted-yaw))
        a=test.neutral();a['sticks'][2]=-np.clip(error*.8,-.8,.8)
        if move and distance>6:a['sticks'][1]=1
        # Paint down during navigation. Aim at the peer's torso during PvP.
        desired=-.35 if paint else np.clip((target[1]-own[1]-.5)/max(distance,1),-.6,.6)
        a['gyro'][0]=down*np.clip((cam[1]-desired)*.15,-.12,.12)
        a['buttons'][0]=int(paint or (distance<22 and abs(error)<.3))
        return a
    def paint_route(i):
        a=actions();p=env.process_infos['player_0']['position']
        target=(-12,0,35) if p[2]>45 else (20,0,10)
        a['player_0']=drive(0,target,paint=True)
        if i%12==0:a['player_0']['buttons'][4]=1
        return a
    initial=[charge(n) for n in range(2)];initial_special={a:i["special"] for a,i in env.process_infos.items()}
    epoch('paint-route-0',paint_route,110);result['charge_after_own_paint']=dict(before=initial,after=[charge(n) for n in range(2)])
    final_special={a:i['special'] for a,i in env.process_infos.items()}
    result['special_effect']=dict(before=initial_special,after=final_special,passed=final_special['player_0']-initial_special['player_0']>.1 and abs(final_special['player_1']-initial_special['player_1'])<.01)
    if not result['special_effect']['passed']:raise AssertionError('official special did not follow own painting with neutral peer')
    result['special_passed']=True
    def use_special(i):
        a=actions();a['player_0']['buttons'][3]=int(i==0);return a
    epoch('use-special-0',use_special,8)
    epoch('reset-view-combat',reset_view,3)
    def pvp(i):
        a=actions()
        for n in range(2):
            name=f'player_{n}';other=f'player_{1-n}'
            if name not in a:continue
            target=env.process_infos[other]['position']
            a[name]=drive(n,target,paint=False,move=(n==1))
            if n==1 and i%12==0:a[name]['buttons'][4]=1
            # Relaunch after a splat when back on the high spawn platform.
            if env.process_infos[name]['position'][1]>20:a[name]['buttons'][0]=1
        return a
    epoch('pvp-approach',pvp,160)
    # Let the native game finish; never turn a comm error into termination.
    while env.agents:
        run(pvp(len(history)),'pvp-to-end')
    while not all(i['phase']==3 for i in env.process_infos.values()):env.advance_settlement()
    hp_samples={a:[row['infos'][a]['hp'] for row in history if row['infos'][a]['phase']==1 and row['infos'][a].get('hp_valid')] for a in env.possible_agents}
    result['hp_effect']={a:dict(min=min(values),max=max(values),recovered=any(0<v<.95 and max(values[i+1:],default=v)>v+.05 for i,v in enumerate(values))) for a,values in hp_samples.items()}
    if not any(v['min']<.95 for v in result['hp_effect'].values()):raise AssertionError('PvP did not reduce official own HP')
    if not any(v['recovered'] for v in result['hp_effect'].values()):raise AssertionError('official HP did not recover after damage')
    result['hp_passed']=True
    result['diagnostic_native_winners']=True;result['diagnostic_steps']=len(history)
    image('native-winners')
    (out/'diagnostic.json').write_text(json.dumps(history,indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--timeout',type=float,default=2400)
    args=parser.parse_args()
    raise SystemExit(test.main(argparse.Namespace(survey=True,timeout=args.timeout),survey_callback=survey))
