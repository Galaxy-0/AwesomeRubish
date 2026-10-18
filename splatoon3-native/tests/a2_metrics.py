"""Count complete ink deductions before the first insufficient remainder."""
import argparse
import json
from pathlib import Path
import statistics


def full_tank_capacity(history,agent):
    if len(history)<4 or history[0]['before'][agent]<.999:
        raise AssertionError('full-tank record must start full and include depletion')
    nominal=statistics.median(row['losses'][agent] for row in history[:3])
    if not .005<nominal<1:raise AssertionError('missing ordinary swing ink cost')
    count=0;spent=0
    for row in history:
        before=row['before'][agent];loss=row['losses'][agent]
        if before<nominal*.999:
            return dict(full_cost_swings=count,normal_cost=nominal,ink_spent=spent,
                        first_insufficient_cycle=row['cycle'],insufficient_remainder=before,
                        tail_positive_deductions=sum(r['losses'][agent]>.005 for r in history[row['cycle']:]))
        if abs(loss-nominal)>.002:raise AssertionError('ordinary swing had unexpected recovery or cadence')
        count+=1;spent+=loss
    raise AssertionError('record ends before insufficient ink is observed')


def verify_record(result):
    if not result.get('full_a2_passed') or len(result['rounds'])!=2 or {r['swapped'] for r in result['rounds']}!={False,True}:
        raise AssertionError('requires two completed native swapped-loadout rounds')
    output=[]
    for r in result['rounds']:
        buff='player_0' if r['swapped'] else 'player_1';base='player_1' if r['swapped'] else 'player_0'
        metrics={a:full_tank_capacity(r['air_slashes']['history'],a) for a in (base,buff)}
        if metrics[buff]['full_cost_swings']<=metrics[base]['full_cost_swings']+1:
            raise AssertionError('ink saver did not increase complete full-tank swings')
        if metrics[buff]['normal_cost']>=metrics[base]['normal_cost']*.95:
            raise AssertionError('ink saver did not reduce ordinary swing cost')
        frames=r['swim']['frames']
        if frames[buff]>=frames[base]*.97:raise AssertionError('swim speed did not reduce same-distance time')
        output.append(dict(swapped=r['swapped'],session=r['session'],ink=metrics,swim_frames=frames))
    return dict(passed=True,scope='recheck recorded native ink and swim measurements',rounds=output)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('result',type=Path)
    args=parser.parse_args();print(json.dumps(verify_record(json.loads(args.result.read_text())),indent=2))
