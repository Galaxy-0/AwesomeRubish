"""Summarize completed limited-model queries without exporting any grid."""
import argparse,json
from collections import Counter
from pathlib import Path
from tools.zipcaster_d3r.analyze_direction import sha

def report(batch,extras=()):
 b=json.loads(batch.read_text());rows=[];entries=list(b['results'])
 for path in extras:
  q=json.loads(path.read_text());entries.append(dict(artifact=str(path),state=dict(map=q['map'],region='center')))
 for item in entries:
  path=Path(item['artifact']);q=json.loads(path.read_text());assert q['search_complete']and not q['full_d4_passed']
  assert len(q['rows'])==q['ground_nodes']and all(r['complete']for r in q['rows'])
  wins=[r for r in q['rows']if r.get('probability')==1]
  rows.append(dict(map=q['map'],region=item['state']['region'],enemy_index=q['enemy_index'],heading=q['heading_quadrant'],speed=q['speed'],
   starts=len(q['rows']),statuses=dict(Counter(r['status']for r in q['rows'])),wins_by_hooks=dict(Counter(len(r['edges'])for r in wins)),
   seconds=q['seconds'],artifact=str(path),sha256=sha(path),top2=[{k:r[k]for k in ['start','position','remaining','cost','program','hooks','exposure_frames','stealth']}for r in q['top2']]))
 return dict(schema='inklab.d4.blade-only.bank.report.v1',full_d4_passed=False,unrestricted_optimality_closed=False,completed_queries=len(rows),start_rows=sum(r['starts']for r in rows),
  all_enemy_heading_speed_queries=63328,all_queries_precomputed=False,batch_seconds=b['seconds'],summed_query_seconds=sum(r['seconds']for r in rows),queries=rows,
  original_batch_queries=len(b['results']),extra_queries=len(extras),batch_sha256=sha(batch),source_sha256=sha(__file__),scope='Fixed common enemy states with explicit headings, all declared ground starts,0..3 hooks/four programs/40f. batch_seconds covers the original9 only; summed_query_seconds includes separately closed extras, not a shared wall-clock run. Contact excluded and whole-wave clear. Not all63328 enemy-heading-speed queries. Setup-supported top2 certificates separately frozen before native trials.')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--batch',type=Path,required=True);p.add_argument('--extra',type=Path,nargs='*',default=[]);p.add_argument('--out',type=Path,required=True);a=p.parse_args();assert not a.out.exists();d=report(a.batch,a.extra);a.out.write_text(json.dumps(d,indent=2)+'\n');print(json.dumps({k:d[k]for k in ['completed_queries','start_rows','batch_seconds','summed_query_seconds']}))
