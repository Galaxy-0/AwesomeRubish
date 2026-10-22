"""Audit closed compressed queries; retain exporter failure separately."""
import argparse,gzip,json,sys,collections
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.analyze_direction import sha

def main(a):
 if a.out.exists():raise ValueError('fresh audit output')
 source=json.loads((a.bank/'source-manifest.json').read_text());assert all(sha(p)==h for p,h in source.items());rows=[];counts=collections.Counter();pairs=collections.Counter();ids=set()
 for p in sorted(a.bank.glob('*.json.gz')):
  d=json.loads(gzip.decompress(p.read_bytes()));assert d['key']not in ids;ids.add(d['key']);counts[d['status']]+=1;q=d['result'];result=q.get('rows',[])
  if d['status']=='complete':
   assert q['search_complete']and len(result)==q['ground_nodes'];assert len({r['start']for r in result})==len(result)
  for r in result:
   assert not(r['probability']==0 and not r['complete']),r
   if r['probability']==1:assert r['remaining']>0 and len(r['hooks'])<=3 and r['kill_frame']>=r['arrival_frame']
   pairs[r['status']]+=1
  rows.append(dict(key=d['key'],status=d['status'],seconds=d['seconds'],bytes=p.stat().st_size,sha256=sha(p),artifact=str(p.resolve().relative_to(ROOT))))
 out=dict(schema='inklab.d4.enumeration.audit.v1',passed=True,queries=len(rows),statuses=dict(counts),pair_statuses=dict(pairs),seconds_sum=sum(r['seconds']for r in rows),seconds_max=max(r['seconds']for r in rows),gzip_bytes=sum(r['bytes']for r in rows),results=rows,source_sha256=sha(__file__),scope='Audits complete-vs-unknown/coverage/resource invariants, not independent proof of every combat prediction. Common9 enemy cells ×4headings×4speeds; not all-map enemy enumeration. Original v1 exporter completed gzip files then failed relative-path progress metadata; this audit reconstructs metadata without changing originals.')
 a.out.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:out[k]for k in['queries','statuses','pair_statuses','seconds_sum','seconds_max','gzip_bytes']},indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--bank',type=Path,required=True);p.add_argument('--out',type=Path,required=True);main(p.parse_args())
