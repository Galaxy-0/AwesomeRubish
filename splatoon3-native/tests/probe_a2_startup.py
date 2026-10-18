#!/usr/bin/env python3
"""A2 startup bisection; never accepts the full milestone or skill effects."""
import argparse
import datetime
import json
from pathlib import Path
import re
import sys
import traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from rl.session import Session
from rl.protocol import Client
from probe_a1_time import neutral,sample_hosts


class ControlSession(Session):
    def __init__(self,case,**kwargs):
        self.case=case;self.watch_room=False
        super().__init__(players=2,mode=0,stage_id=1,weapons=[8000]*2,**kwargs)

    def host_options(self,player):
        if self.case=='off':return {}
        if self.case=='survey':return {'DM_GEAR_SURVEY':'1'}
        if self.case=='original':return {'DM_GEAR':'original'}
        if self.case=='host_main_valid':return {'DM_GEAR':'10,0,0,0,10,0,0,0,10,0,0,0','DM_GEAR_LEGACY':'1'} if player==0 else {}
        values=['0,0,0,0,0,0,0,0,0,0,0,0','5,5,5,5,1,1,1,1,1,1,1,1']
        if self.case=='host_only' and player==0:return {'DM_GEAR':values[player],'DM_GEAR_LEGACY':'1'}
        if self.case=='guest_only' and player==1:return {'DM_GEAR':values[player],'DM_GEAR_LEGACY':'1'}
        return {}

    def frames(self,player,count=120):
        # Session.start has checked both peers and starts its first extra host
        # budget here. From this point a native room disconnect is a failure.
        if len(self.hosts)==2 and self.frame(1)>=4800:self.watch_room=True
        super().frames(player,count)

    def tick(self,sleep=True):
        super().tick(sleep)
        if self.watch_room:
            for n,_,_ in self.hosts:
                rows=re.findall(r'LDN state=(\d+) node=(-?\d+) nodes=(\d+) session=(\w+)',self.text(n))
                if rows and rows[-1][0] not in ('3','5'):
                    raise RuntimeError(f'player-{n}: native room closed before/after InGame: {rows[-1]}')


def main(args):
    out=ROOT/'work/tests'/datetime.datetime.now().strftime(f'a2-startup-{args.case}-%Y%m%d-%H%M%S-%f');out.mkdir(parents=True)
    result=dict(probe_completed=False,full_a2_passed=False,case=args.case,runs=[],errors=[],artifacts=str(out))
    for run in range(args.repeats):
        session=ControlSession(args.case,timeout=args.timeout);clients={};entry=dict(session=str(session.out),ingame=False,steps=[])
        result['runs'].append(entry)
        try:
            session.start();entry['ingame']=True
            for n in range(2):clients[n]=Client(session.socket_dir/f'player-{n}.sock',30)
            origins={n:clients[n].receive()[1] for n in range(2)}
            for frames in (1,7,31,15,60,120,300):
                session.clock.resume()
                for c in clients.values():c.send_step(neutral(),frames)
                infos={n:c.receive()[1] for n,c in clients.items()};session.clock.pause();session.tick(sleep=False)
                for n,info in infos.items():
                    elapsed=info['frame']-origins[n]['frame']
                    if info['guest_time_ns']-origins[n]['guest_time_ns']!=elapsed*1000000000//60:
                        raise AssertionError('default fixed60 was not precise after InGame')
                entry['steps'].append(infos)
            entry['passed']=True
        except BaseException as error:
            entry['passed']=False;entry['error']=repr(error);entry['traceback']=traceback.format_exc();result['errors'].append(repr(error))
            sample_dir=out/f'run-{run}-samples';sample_dir.mkdir();sample_hosts(session,sample_dir)
        finally:
            for c in clients.values():c.close()
            try:session.close()
            except BaseException as error:result['errors'].append('cleanup: '+repr(error))
            entry['gear_logs']={n:re.findall(r'SPL3_GEAR [^\n]+',session.text(n))[-3:] for n in range(2)}
            (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        if result['errors']:break
    result['probe_completed']=not result['errors'];(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True);return 0 if result['probe_completed'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--case',choices=['off','survey','host_only','guest_only','original','host_main_valid'],required=True)
    p.add_argument('--repeats',type=int,default=1);p.add_argument('--timeout',type=float,default=1200)
    raise SystemExit(main(p.parse_args()))
