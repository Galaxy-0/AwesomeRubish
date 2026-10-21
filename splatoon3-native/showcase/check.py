#!/usr/bin/env python3
"""Audit the built page against existing local evidence; no native processes."""
import hashlib
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
PAGE = ROOT / 'showcase/index.html'
text = PAGE.read_text()
match = re.search(r'<script id="showcase-data" type="application/json">(.*?)</script>', text, re.S)
assert match, 'embedded data missing'
data = json.loads(match.group(1))
checks = []


def check(label, condition):
    assert condition, label
    checks.append(label)


class ResourceAudit(HTMLParser):
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for name in ('srcset', 'poster'):
            check(f'no resource {tag}.{name}', name not in attrs)
        if 'src' in attrs:
            check('only pinned three.js CDN dependency', tag == 'script' and attrs['src'] == 'https://cdnjs.cloudflare.com/ajax/libs/three.js/0.160.0/three.min.js' and attrs.get('integrity') == 'sha384-qOkzR5Ke/XkQxuGVJ9hpFEpDlcoLtWwVYhnJf06cLIZa2vaIptSqaubivErzmD5O')
        if tag == 'link':
            check('only approved Google Fonts stylesheet/preconnect', (attrs.get('rel'), attrs.get('href')) in {('preconnect','https://fonts.googleapis.com'),('preconnect','https://fonts.gstatic.com'),('stylesheet','https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap')})
        if tag == 'a':
            check('only inline navigation links', attrs.get('href', '').startswith('#'))
        check('no embedded media/model', tag not in ('img', 'video', 'audio', 'model-viewer', 'iframe', 'object', 'embed'))


ResourceAudit().feed(text)
check('no inline CSS URL/import resources', not re.search(r'@import|url\s*\(', text))
check('no runtime network API', not re.search(r'\b(?:fetch|XMLHttpRequest|WebSocket|EventSource)\s*\(', text))
check('template resolved', '__SHOWCASE_DATA__' not in text)
check('disclaimer', '非官方研究项目，数据来自本地实验' in text)
for path, digest in data['sources'].items():
    check(f'source hash {path}', hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest)
check('three maps', [m['id'] for m in data['maps']] == ['Yunohana', 'District00', 'Yagara'])
for m in data['maps']:
    check(f"{m['id']} no raw mesh", set(m) == {'id', 'name', 'cells', 'visibility', 'points', 'spawns', 'grid', 'sample_count', 'node_count', 'bounds', 'heights','walls','ambush','geometry_method'})
    check(f"{m['id']} scalar cells", all(len(c) == 7 and c[6] in (0,1) and all(v is None or math.isfinite(v) for v in c) for c in m['cells']))
    check(f"{m['id']} LOS coverage", all(0 <= c[3] <= 100 for c in m['visibility']) and m['sample_count'] == len(m['visibility']))
    for point in m['points']:
        for side, route in enumerate(point['routes']):
            check(f"{m['id']} {point['id']} route endpoints {side}", route[0] == m['spawns'][side] and route[-1] == point['position'])
            length = sum(math.dist(a, b) for a, b in zip(route, route[1:]))
            check(f"{m['id']} {point['id']} ETA sanity {side}", abs(length / data['speed'] - point['times'][side]) < .4)
check('page under 10MB', PAGE.stat().st_size < 10_000_000)
check('preview has no download control or API', 'download-data' not in text and 'createObjectURL' not in text and '.download=' not in text)
check('scene script resolved', '__SCENE_SCRIPT__' not in text)
check('generated index ignored', '/index.html' in (ROOT/'showcase/.gitignore').read_text())
check('derived data ignored', '/data/' in (ROOT/'showcase/.gitignore').read_text())
check('R0–R9', [r['round'] for r in data['story']['rounds']] == list(range(10)))
check('R0 native baseline distinct', data['story']['rounds'][0]['wins'] == [47, 3] and data['story']['baseline']['wins'] == [9, 61])
for r in data['story']['rounds'][1:]:
    raw = json.loads((ROOT / f"work/arena/t1/round-{r['round']:03d}/summary.json").read_text())
    check(f"R{r['round']} scores/outcomes", r['wins'] == [raw['wins']['a'], raw['wins']['b']] and r['hashes'] == raw['source_hashes'])
    for i, p in enumerate(('a', 'b')):
        expected = sum(g['score_by_policy'][p] for g in raw['games']) / 3
        check(f"R{r['round']} {p} turf", abs(expected - r['turf'][i]) < .0006)
for who, tactics in data['story']['tactics'].items():
    for t in tactics:
        if t['score'] is not None:
            check(f"{who} {t['version']} card identity", t['binding'] in ('exact_source_hash', 'runtime_files_equal_directory_hash_differs') and len(t['source_hash']) == 64 and t['measured'] == t['total'] == 13)
check('weapon profile', data['weapon']['damage'] == [35, 70] and data['weapon']['charge'] == [21, 26])
check('S1 holdout sizes', [r['windows'] for r in data['calibration']['rows']] == [987, 494, 243, 94])
check('Yagara directional agreement', data['calibration']['yagara']['native']['wins'] == [0, 22] and data['calibration']['yagara']['after']['wins'] == [0, 12])
check('S1 counterexample retained', data['calibration']['ranks']['R1'] == {'native': [1, 2], 'after': [16, 2]})
from arena.geometry import CollisionMesh, GeometricVision, VisionConfig
from arena.referee import PlayerTruth, RefereeSnapshot
import numpy as np
for m in data['maps']:
    check(f"{m['id']} quantized wall voxels", len(m['walls']) > 50 and all(len(w)==4 and w[0]%2==0 and w[1]%2==0 and w[2]*2==round(w[2]*2) and w[3]*2==round(w[3]*2) and w[3]>w[2] for w in m['walls']))
    mesh=CollisionMesh.load(ROOT/f"work/arena/maps/{m['id']}/sight.npz")
    vision=GeometricVision(mesh,VisionConfig(half_fov_degrees=180,body_heights=(.12,.25,.35)))
    for a in m['ambush']:
        target=next(p['position'] for p in m['points'] if p['id']==a['region'])
        check('ambush distance', 5<math.dist(a['position'],target)<=22)
        check('ambush potential swimmable', any(c[:3]==a['position'] and c[6]==1 for c in m['cells']))
        enemy=PlayerTruth('e',1,8000,True,tuple(a['threat']),0.,1.,1.,False,0,False)
        candidate=PlayerTruth('c',0,8000,True,tuple(a['position']),0.,1.,1.,True,0,True)
        witness=vision.witnesses(RefereeSnapshot('check',0,(enemy,candidate)),'e')[0]
        check('ambush static concealment witness', witness.line_clear is False)
        check('ambush standing ray to choke', mesh.clear(np.array(a['position'])+[0,1.1,0],np.array(target)+[0,.7,0]))
check('three native and two simulated clips', [t['source_kind'] for t in data['traces']].count('native_observation')==3 and [t['source_kind'] for t in data['traces']].count('simulated_state')==2)
from showcase.zipcaster import compile_zipcaster
zipdata,zipclip=compile_zipcaster(ROOT,lambda p:ROOT/p)
check('D2 presentation selection reproducible',data['zipcaster']==zipdata)
check('D2 native pose is not a static point certification',len(zipdata['verified'])==1 and '实际锚点' in zipdata['verified'][0]['caveat'])
for m in zipdata['maps']:
    for region in ('center','central_high','west_lane','east_lane'):
        check('bounded per-region selection',sum(any(t['region']==region for t in p['targets'])for p in m['candidates'])<=zipdata['per_region'])
    check('all static points remain candidates',all(p['status']=='candidate'for p in m['candidates']))
for t in data['traces']:
    if t['id']=='zipcaster-mid':
        check('D2 clip identity and inputs preserved',t==zipclip)
        from tools.zipcaster.export import trace
        raw=trace((ROOT/t['evidence']['raw_steps']).parent,'mc')
        check('D2 trace raw reconstruction',raw['players']==t['players'] and raw['start_frame']==t['start_frame'] and raw['end_frame']==t['end_frame'])
        check('D2 actual target down present',any(s[7]==0 and s[8]is False for s in t['players'][1]['states']))
        check('D2 R release edge present',any(e['type']=='R_release'for e in t['players'][0]['events']))
        continue
    n=int(t['id'][-1]);check('generic trace schema', t['schema']=='inklab.trace.v1' and t['fps']==60 and t['stride']==6 and t['end_frame']-t['start_frame']==1800)
    for player in t['players']:
        rows=player['states'];check('monotonic trace samples', len(rows)>250 and all(len(r)==10 for r in rows) and all(a[0]<b[0] for a,b in zip(rows,rows[1:])))
        if t['source_kind']=='native_observation':
            path=ROOT/f"work/arena/t1/round-{n:03d}/game-0-attempt-000/policy-{player['role'][-1]}.jsonl"
            raw={}
            with path.open() as f:
                for line in f:
                    v=json.loads(line)['observation'];raw[v['frame']]=v['own']
            for row in rows:
                v=raw[row[0]]
                check('native position preserved', max(abs(a-b)for a,b in zip(row[2:5],v['position']))<=.00501)
                check('native sample frame preserved', row[1]==v['sample_frame'])
                check('native HP preserved', (row[7] is None and v['hp'] is None) or abs(row[7]-v['hp'])<=.000501)
        else:
            path=ROOT/f"work/sim/window-20261021/route-check/R{n}-map1-side{int(n==1)}/trace-0.npz"
            with np.load(path,allow_pickle=False)as archive:
                states=archive['states'];role=int(player['role'][-1])
                for row in rows:
                    v=states[row[0],role]
                    check('sim state preserved', max(abs(a-b)for a,b in zip(row[2:5],v[:3]))<=.00501 and abs(row[7]-v[6])<=.000501)
        check('events bounded and labeled as inputs', all(t['start_frame']<=e['frame']<=t['end_frame'] and e['evidence']=='recorded_input_edge' for e in player['events']))

report = dict(passed=True, checks=len(checks), maps=[dict(name=m['id'], cells=len(m['cells']), vision_samples=m['sample_count'],wall_voxels=len(m['walls']),ambush_candidates=len(m['ambush'])) for m in data['maps']], trace_clips=len(data['traces']),trace_samples=sum(len(p['states']) for t in data['traces'] for p in t['players']),bytes=PAGE.stat().st_size, page_sha256=hashlib.sha256(PAGE.read_bytes()).hexdigest(), scope='offline data and asset audit; browser interactions verified separately')
(ROOT / 'work/showcase/check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(report, ensure_ascii=False, indent=2))
