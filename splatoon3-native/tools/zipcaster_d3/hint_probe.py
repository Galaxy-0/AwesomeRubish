#!/usr/bin/env python3
"""New D3 hint cohort. Ordinary B/aim/weapon inputs; scoped test meter only.

Raw per-present state, native SuperHook/armor snapshots and source hashes are
retained. A completed command is never promoted to an observed attack/hit.
"""
import argparse,json,math,sys,traceback,re,struct
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from native import DuelLab,owned_options,neutral,ROOT,sha
from serve import fast_align
from validate_candidates import read_sensors

def main(args):
    p=next(p for p in json.loads((ROOT/'work/d2c/selection.json').read_text())['points']if p['id']==args.point)
    p['requested_anchor'][1]+=args.anchor_dy
    if args.source:p['source']=args.source
    lab=DuelLab('hint-'+args.name,p['stage']);events=[]
    lab.result.update(hint_mode=args.mode,meter_mode=args.meter,jump_enabled=args.jump,point=p,full_d3_passed=False)
    def step(label,n=1,buttons=None,sticks=None,gyro=None):
        for _ in range(n):
            a=neutral()
            if buttons is not None:a['buttons']=buttons
            if sticks is not None:a['sticks']=sticks
            if gyro is not None:a['gyro']=gyro
            lab.act(0,a,label,1)
    def mark(label):
        events.append(dict(event=label,infos=lab.env.process_infos,own=lab.obs(0)['own']));lab.result['events']=events;lab.save()
        print('HINT_EVENT '+json.dumps(dict(label=label,frame=lab.info(0)['frame'],special=lab.info(0)['special'],position=lab.info(0)['position'])),flush=True)
    try:
        with owned_options(special=True,sensors=True,meter=args.meter):
            lab.start()
            if args.mode not in ('meter','natural'):
                lab.navigate({0:p['source'],1:p['target']},'hint-place')
                fast_align(lab,0,p['requested_anchor'],'hint-hook-aim')
            mark('before-RS');step('hint-RS',1,[0,0,0,1,0,0]);step('hint-startup',30);mark('after-RS')
            if args.mode=='natural':step('hint-natural',700);mark('natural-end')
            elif args.mode=='meter':
                step('hint-idle',60);mark('idle-60')
                step('hint-light',1,[1,0,0,0,0,0]);step('hint-light-release',40);mark('light-end')
                step('hint-charge',21,[1,0,0,0,0,0]);step('hint-full-release',42);mark('full-end')
                step('hint-R',1,[0,0,1,0,0,0]);step('hint-release',90);mark('hook-end')
                step('hint-budget-exhaust',650);mark('budget-end')
            else:
                step('hint-R',1,[0,0,1,0,0,0]);step('hint-release',90);mark('arrival')
                if args.air_combo:
                    target=list(lab.info(1)['position']);target[1]+=1.1
                    fast_align(lab,0,target,'hint-preaim-combo',budget=180);mark('preaim-combo')
                if args.preaim_rehook:
                    fast_align(lab,0,args.next_anchor,'hint-preaim-second',budget=180);mark('preaim-second')
                if args.jump:step('hint-B',args.jump_frames,[0,0,0,0,1,0]);mark('after-B')
                if args.mode=='control':
                    step('hint-turn',24,sticks=[0,0,1,0]);mark('after-turn')
                    step('hint-charge',21,[1,0,0,0,0,0]);step('hint-full-release',50);mark('after-charge')
                elif args.mode=='combo':
                    target=list(lab.info(1)['position']);target[1]+=1.1
                    if not args.air_combo:
                        fast_align(lab,0,target,'hint-target-aim',budget=180);mark('aimed')
                        step('hint-face',6,sticks=[0,.85,0,0]);step('hint-face-settle',8)
                    from serve import run
                    for label,n,buttons in [('charge',21,[1,0,0,0,0,0]),('full-release',36,[0]*6),('light',1,[1,0,0,0,0,0]),('light-release',42,[0]*6)]:
                        run(lab,dict(op='track_step',label='hint-'+label,frames=n,player=0,target_player=1,offset=[0,1.1,0],buttons=buttons))
                    mark('combo-end')
                elif args.mode=='rehook':
                    # Only after the first flight has completed; no in-flight R.
                    target=list(args.next_anchor or p['requested_anchor'])
                    if not args.next_anchor:target[0]+=args.anchor_dx
                    if not args.preaim_rehook:fast_align(lab,0,target,'hint-second-aim',budget=180)
                    mark('second-aimed')
                    step('hint-R2',1,[0,0,1,0,0,0]);step('hint-release2',90);mark('second-arrival')
                step('hint-fall',60);mark('fall-end')
            if args.return_window:step('hint-return-window',args.return_window);mark('return-end')
            lab.result.update(passed=True,driver_completed=True)
    except BaseException as e:lab.result.update(errors=lab.result['errors']+[repr(e)],traceback=traceback.format_exc())
    finally:lab.finish()
    if lab.result.get('session'):
        path=lab.out/'sensors.jsonl';path.write_text(''.join(json.dumps(s)+'\n'for s in read_sensors(lab.result['session'])));lab.result['sensor_sha256']=sha(path);lab.save()
    print('HINT_CLOSED '+str(lab.out),flush=True);return 0 if lab.result['passed']else 1
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--name',required=True);ap.add_argument('--point',default='Yunohana-hook-0532');ap.add_argument('--mode',choices=['control','combo','rehook','meter','natural'],default='control');ap.add_argument('--jump',action='store_true');ap.add_argument('--jump-frames',type=int,default=1);ap.add_argument('--anchor-dy',type=float,default=0.);ap.add_argument('--return-window',type=int,default=0);ap.add_argument('--meter',choices=['full','infinite'],default='infinite');ap.add_argument('--anchor-dx',type=float,default=4.);ap.add_argument('--source',nargs=3,type=float);ap.add_argument('--next-anchor',nargs=3,type=float);ap.add_argument('--preaim-rehook',action='store_true');ap.add_argument('--air-combo',action='store_true');raise SystemExit(main(ap.parse_args()))
