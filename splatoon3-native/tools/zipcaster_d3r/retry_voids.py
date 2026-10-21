"""Select only fixed-cohort setup voids after the original batch closes."""
import argparse,json
from pathlib import Path

def main(a):
 if a.out.exists():raise ValueError('fresh retry plan')
 batch=json.loads(a.batch.read_text());plan=json.loads(a.plan.read_text());assert len(batch['results'])==len(plan['points'])
 invalid={(r['map'],r['point'],r['trial'])for r in batch['results']if not r['eligible']};valid={(r['map'],r['point'],r['trial'])for r in batch['results']if r['eligible']};assert not invalid&valid
 plan['points']=[p for p in plan['points']if(p['map'],p['id'],p['trial'])in invalid];plan['retry_scope']='original setup voids only; same intended source,target,heading and exact post-R battle logic. Original failures preserved.';a.out.write_text(json.dumps(plan,separators=(',',':'))+'\n');print('SETUP_VOID_RETRIES '+str(len(plan['points'])))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--batch',type=Path,required=True);p.add_argument('--plan',type=Path,required=True);p.add_argument('--out',type=Path,required=True);main(p.parse_args())
