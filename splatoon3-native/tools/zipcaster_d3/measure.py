#!/usr/bin/env python3
"""Single owned .52 room. Every damage/ink/yaw observation retained per frame."""
import argparse,json,math,sys,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from native import DuelLab,owned_options,neutral,ROOT,HOST,MODULES
from serve import fast_align

def main(args):
    lab=DuelLab(args.name,host=args.host,modules=(ROOT/'work/a7/patched-seeds-v16'if args.bullets else MODULES));report=[];capture=lab.out/'capture-bullets'
    def sample(a,label,n):
        rows=[]
        for _ in range(n):
            lab.act(1,a,label,1)
            rows.append(dict(frame=lab.info(1)['frame'],shooter=lab.info(1),target=lab.info(0),view=lab.obs(1)['own']))
        return rows
    try:
        with owned_options(bullets=args.bullets,capture=capture if args.bullets else None):
            lab.result['measurement_config']={k:str(v)if isinstance(v,Path)else v for k,v in vars(args).items()};lab.save()
            lab.start();lab.navigate({0:[0,3,8],1:[-4,3,5.5]},'measure-setup')
            print('D3_READY '+str(lab.out),flush=True)
            if args.mode=='turn':
                for firing in (False,True):
                    a=neutral();a['sticks'][2]=1;a['buttons'][0]=int(firing)
                    before=lab.obs(1)['own'];rows=sample(a,'turn-firing'if firing else'turn-human',75)
                    report.append(dict(kind='turn',firing=firing,before=before,rows=rows))
                    lab.step(lab.actions(),'turn-settle',30)
            else:
                # Flat west approach; exact native distance, height and health
                # accompany each shot. No teleports/HP writes.
                trials=[(d,o)for _ in range(args.repeats)for d in args.distances for o in (args.pitch_offsets or [args.aim_pitch_offset])]
                for distance,pitch_offset in trials:
                    lab.navigate({0:[0,3,8],1:[-distance,3,8]},'range-setup')
                    if not lab.info(0).get('alive'):raise AssertionError('target not alive')
                    lab.paint_floor(0);lab.refill(0,180)
                    if lab.info(0)['hp']<.999:raise AssertionError('full-health precondition')
                    q=lab.info(0)['position'];fast_align(lab,1,[q[0],q[1]+1.1+pitch_offset*math.dist(q,lab.info(1)['position']),q[2]],'range-align')
                    lab.refill(1,90)
                    if args.face:
                        a=neutral();a['sticks'][1]=.85;lab.act(1,a,'range-face-body',8);lab.step(lab.actions(),'range-face-settle',8)
                        q=lab.info(0)['position'];fast_align(lab,1,[q[0],q[1]+1.1+pitch_offset*math.dist(q,lab.info(1)['position']),q[2]],'range-realign')
                    if args.rest_frames:lab.step(lab.actions(),'stationary-settle',args.rest_frames)
                    before=[lab.info(n)for n in (0,1)];a=neutral();a['buttons'][0]=1
                    if args.bullets:capture.touch(exist_ok=False)
                    rows=sample(a,'range-fire',args.fire_frames)
                    rows+=sample(neutral(),'range-flight',25)
                    if args.bullets:capture.unlink()
                    report.append(dict(kind='range',pitch_offset=pitch_offset,requested_distance=distance,actual_distance=math.dist(before[0]['position'],before[1]['position']),before=before,fire_frames=args.fire_frames,rows=rows))
                    lab.result['measurements']=report;lab.save()
                    print('D3_RANGE '+json.dumps(dict(distance=distance,hp=lab.info(0)['hp'],alive=lab.info(0)['alive'])),flush=True)
            lab.result.update(passed=True,driver_completed=True,measurements=report)
    except BaseException as e:lab.result.update(errors=lab.result['errors']+[repr(e)],traceback=traceback.format_exc(),measurements=report)
    finally:lab.finish()
    print('D3_CLOSED '+str(lab.out),flush=True)
    return 0 if lab.result['passed']else 1
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--mode',choices=['turn','range'],default='range');p.add_argument('--distances',type=float,nargs='+',default=[4,8,12,15,18]);p.add_argument('--fire-frames',type=int,default=1);p.add_argument('--repeats',type=int,default=1);p.add_argument('--face',action='store_true');p.add_argument('--host',type=Path,default=HOST);p.add_argument('--bullets',action='store_true');p.add_argument('--aim-pitch-offset',type=float,default=0.);p.add_argument('--pitch-offsets',type=float,nargs='+');p.add_argument('--rest-frames',type=int,default=0);raise SystemExit(main(p.parse_args()))
