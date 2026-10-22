"""Reconcile closed own trials after stopping only their launch coordinator."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.zipcaster_d3r.analyze_direction import sha
p=argparse.ArgumentParser();p.add_argument('--batch',type=Path,required=True);p.add_argument('--plan',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();assert not a.out.exists();manifest=json.loads((a.batch/'source-manifest.json').read_text());assert all(sha(k)==v for k,v in manifest.items());planhash=sha(a.plan);rows=[]
for path in(ROOT/'work/a6').glob('d3-r-d4-duel3-*/result.json'):
 d=json.loads(path.read_text())
 if d.get('plan_sha256')!=planhash:continue
 assert'freeze_after'in d and d['freeze_before']==d['freeze_after'];rows.append(dict(point=d['point']['id'],repeat=d['repeat'],exit_code=0 if d['passed']else 1,artifact=str(path.relative_to(ROOT)),artifact_sha256=sha(path),eligible=d['calibration_eligible']))
out=dict(schema='inklab.d4.batch.reconciled.v1',results=rows,source_manifest=manifest,source_sha256=sha(__file__),scope='Coordinator launch stopped before further trials; currently owned children finished normally. Original batch/room artifacts retained unchanged; boundary controls are auxiliary, not post-hoc voids.');a.out.write_text(json.dumps(out,indent=2)+'\n');print('RECONCILED',len(rows))
