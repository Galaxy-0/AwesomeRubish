#!/usr/bin/env python3
"""Audit the built page against existing local evidence; no native processes."""
import hashlib
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import sys,argparse
import base64,zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'showcase'),str(ROOT)]
parser=argparse.ArgumentParser();parser.add_argument('--page',type=Path,default=ROOT/'showcase/index.html');parser.add_argument('--report',type=Path)
args=parser.parse_args()
PAGE = args.page.resolve()
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
            check('no download attribute', 'download' not in attrs)
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
check('preview has no download control or anchor API', 'download-data' not in text and '.download=' not in text)
check('only ephemeral worker Blob URL', text.count('createObjectURL(')==1 and 'new Worker(url)'in text and 'URL.revokeObjectURL(url)'in text)
check('scene script resolved', '__SCENE_SCRIPT__' not in text and '__D3_FUNCTIONS__' not in text)
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
check('native examples and two simulated clips', [t['source_kind'] for t in data['traces']].count('native_observation')==4+len(data['zipcaster']['recommendations'])+sum(t['id'].startswith(('d3-','d3r-','d4-'))for t in data['traces']) and [t['source_kind'] for t in data['traces']].count('simulated_state')==2)
if 'd3'in data:
    d3=data['d3'];check('finite model not native certificate',d3['model_calibrated']is False)
    check('three maps and27 finite D3 tactics',len(d3['maps'])==3 and all(len(m['points'])==9 for m in d3['maps']))
    if d3['calibration']:
        check('fixed native cohort retained',d3['calibration']['native_trials']==54 and sum(p['n']for p in d3['calibration']['points'])==54)
        check('native ranking proof not manufactured',d3['calibration']['model_native_rank_proven']is False)
    for m in d3['maps']:
        for p in m['points']:
            for v in [p]+([p['corrected']]if 'corrected'in p else[]):
                check('D3 avg worst ordered',0<=v['worst']<=v['expected']<=1)
                check('D3 enemy probabilities bounded',all(len(e)==5 and 0<=e[4]<=e[3]+.000101<=1.000101 for e in v['enemy']))
                check('D3 startup-inclusive gauge bounded',0<=v['spent']<=1)
            if d3['has_corrected']:check('same finite point has corrected model', 'corrected'in p)
            if len(p['sequence'])>1:check('single-hook native not attributed to multi',p['native']is None)
from showcase.d3r import compile_d3r
rdata,rclips=compile_d3r(ROOT,lambda p:ROOT/p)
check('D3R numerical compiler reconstruction',data['d3r']==rdata)
check('D3R no manufactured native ranking',rdata['native_rank_proven']is False and rdata['calibration']['model_native_rank_proven']is False)
check('D3R fixed cohort54 valid',rdata['calibration']['native_trials']==54 and sum(p['n']for p in rdata['calibration']['points'])==54)
check('D3R setup voids separate',rdata['calibration']['void_attempts']==4)
check('D3R finite189 variants',rdata['search']['single_tactics']==18 and rdata['search']['sequence_tactics']==9 and rdata['search']['fine_variants']==189)
check('D3R four explicit operation bands',rdata['speeds']==[20,40,60,129])
for m in rdata['maps']:
    check('D3R each map9 finite tactics',len(m['points'])==9)
    for p in m['points']:
        check('D3R measured singles distinct from predicted chains',(p['native']is None)==(len(p['sequence'])>1))
        check('D3R seven legal variants',len(p['variants'])==7)
        for v in p['variants']:
            check('D3R20 full precharge not fabricated',v['speed']!=20 or(v['style']=='light3'and not v['requires_precharge']))
            check('D3R global and local probability bounds',0<=v['worst']<=v['expected']<=v['local']+1e-9<=1+1e-9 and 0<=v['local_worst']<=v['local'])
            check('D3R startup inclusive finite budget',0<v['spent']<=1)
            check('D3R conditional cells12',len(v['enemy'])==v['sampled_enemy_nodes']==12 and all(len(e)==5 and 0<=e[4]<=e[3]+.000101<=1.000101 for e in v['enemy']))
            check('D3R declared prior mass',0<v['near_prior_mass']<=1 and abs(v['expected']-v['local']*v['near_prior_mass'])<1e-8)
rlookup={t['id']:t for t in rclips}

from showcase.zipcaster import compile_zipcaster
zipdata,zipclips=compile_zipcaster(ROOT,lambda p:ROOT/p)
check('D2 presentation selection reproducible',data['zipcaster']==zipdata)
check('D2 legacy native pose is not a static point certification','实际锚点' in zipdata['verified'][0]['caveat'])
check('D2B native anchor is explicit',next(p for p in zipdata['verified']if p['id']=='native-high-side')['anchor']is not None)
check('measured failures remain failures',all(p['status']in ['verified','failed','partial','incomplete']for p in zipdata['verified']))
for m in zipdata['maps']:
    for region in ('center','central_high','west_lane','east_lane'):
        check('bounded per-region selection',sum(any(t['region']==region for t in p['targets'])for p in m['candidates'])<=zipdata['per_region'])
    check('all static points remain candidates',all(p['status']=='candidate'for p in m['candidates']))
if data.get('d4',{}).get('schema')=='showcase.d4.v2':
    from showcase.d4 import code as d4_code,center_query
    d4=data['d4'];runtime=data['d4_runtime']
    check('D4 limited scope is not full acceptance',d4['full_d4_passed'] is False)
    check('D4 safe numerical runtime selected',runtime['safe_model']['schema']=='showcase.d4.safe-model.v1')
    check('D4 independent browser model embedded','class D4SafeWorld' in text and 'Contact-disjoint' in text)
    check('D4 no unexpanded worker marker','/* __D4_SAFE_WORKER__ */'not in text)
    batch=json.loads((ROOT/'work/d4/restart-v4/blade-common-full-v1/batch.json').read_text())
    paths=[Path(x['artifact'])for x in batch['results']]+[center_query(ROOT,name)for name in ['Yunohana','Yagara']]
    complete=0;start_rows=0
    for m in d4['maps']:
        packed=zlib.decompress(base64.b64decode(m['codes']))
        check('D4 packed matrix exact size',len(packed)==math.ceil(m['g']*16*m['g']/2))
        for p in paths:
            p=p if p.is_absolute()else ROOT/p;q=json.loads(p.read_text())
            if q['map']!=m['id']:continue
            check('D4 heat source bound',str(p.relative_to(ROOT))in data['sources'])
            complete+=q['search_complete'];start_rows+=len(q['rows'])
            for r in q['rows']:
                i=(q['enemy_index']*16+q['heading_quadrant']*4+d4['speeds'].index(q['speed']))*m['g']+r['start']
                value=(packed[i//2]>>(4*(i%2)))&15
                check('D4 exact limited query grade',value==d4_code(r))
                if r['status']=='no-contact-excluded-route; unrestricted-kill-unknown':
                    check('D4 outside-scope miss stays unknown',r['probability'] is None and value==13)
    check('D4 full heat queries separate from prefix certificates',d4['counts']['complete']==complete and complete>=9 and d4['counts']['unresolved']==len(paths)-complete)
    check('D4 computed start rows disclosed',d4['counts']['start_rows']==start_rows)
    check('D4 historical core bank not bound',not any('/all-full-v' in p or '/common-full-v3/'in p for p in data['sources']))
    if d4.get('native'):
        n=d4['native'];observed=sum(b['n']for s in n['by_state']for b in s['bands'].values())
        check('D4 native counts use a distinct denominator',observed==n['valid']and n['planned']==216)
        check('D4 native repetition is not full acceptance',n['full_d4_passed']is False and n['old12_reused']is False and n['counter_capacity']==540)
        if n['complete_new216']:
            check('D4 completed cohort exactly8 each',n['valid']==216 and n['stop_reason']is None and len(n['by_state'])==9 and all(set(s['bands'])=={'top1','top2','control'}and all(b['n']==8 for b in s['bands'].values())for s in n['by_state']))

for t in data['traces']:
    if t['id'].startswith('d4-'):
        from showcase.d3 import native_trace
        from showcase.projectiles import augment
        path=Path(t['evidence']['result']);run=json.loads((ROOT/path).read_text());expected=native_trace(ROOT,lambda p:ROOT/p,path.parent,t['id'],t['label']);augment(ROOT,lambda p:ROOT/p,expected)
        check('D4 raw own-state reconstruction',t['players']==expected['players']and t['start_frame']==expected['start_frame']and t['end_frame']==expected['end_frame'])
        check('D4 readonly projectile reconstruction',t['projectiles']==expected['projectiles'])
        check('D4 fixed logical FOV disclosed',t['enemy_fov_degrees']==180 and abs(t['enemy_fov_heading']-run['point']['heading']*math.pi/2)<1e-12)
        check('D4 visibility history exact',t['logical_visibility']==[[h['frame'],h['visible'],h['in_range']]for h in run['defender_history']])
        check('D4 annotated timeline bounded',all(t['start_frame']<=e['frame']<=t['end_frame']for e in t['annotations']))
        check('D4 native clocks and map',t['map']==run['point']['graph'].split('-')[-1]and t['fps']==60)
        check('D4 ideal fixture explicit',t['ideal_operation_fixture']is True)
        continue
    if t['id'].startswith('d3r-'):
        check('D3R native trace reconstruction',t==rlookup[t['id']])
        check('D3R ideal fixture disclosed',t['ideal_operation_fixture']is True)
        check('D3R annotated timeline bounded',all(t['start_frame']<=e['frame']<=t['end_frame']for e in t['annotations']))
        check('D3R own-state columns',all(len(s)==10 for p in t['players']for s in p['states']))
        for p in t['players']:
            check('D3R finite aim samples',all(len(s)==3 and all(math.isfinite(v)for v in s)and t['start_frame']<=s[0]<=t['end_frame']for s in p['aim_states']))
        for p in t['projectiles']:
            check('D3R owner and weapon type',p['kind']in(['full','light']if p['who']=='alpha'else['gun']))
            check('D3R readonly projectile finite positions',all(len(s)==4 and t['start_frame']<=s[0]<=t['end_frame']and all(math.isfinite(v)and abs(v)<1000 for v in s[1:])for s in p['states']))
            check('D3R pooled projectile jumps not joined',all(a[0]<b[0]and math.dist(a[1:],b[1:])<=12*(b[0]-a[0])for a,b in zip(p['states'],p['states'][1:])))
        continue
    if t['id'].startswith('d3-'):
        from showcase.d3 import native_trace
        path=Path(t['evidence']['result']).parent
        expected=native_trace(ROOT,lambda p:ROOT/p,path,t['id'],t['label'])
        check('D3 native trace reconstruction',t==expected)
        check('D3 annotated timeline bounded',all(t['start_frame']<=e['frame']<=t['end_frame']for e in t['annotations']))
        check('D3 has native hook/charge markers',any(e['kind']in('hook','hook_input')for e in t['annotations']))
        check('D3 own-state columns',all(len(s)==10 for p in t['players']for s in p['states']))
        continue
    if t['id']=='zipcaster-mid':
        check('D2 clip identity and inputs preserved',t==zipclips[0])
        from tools.zipcaster.export import trace
        raw=trace((ROOT/t['evidence']['raw_steps']).parent,'mc')
        check('D2 trace raw reconstruction',raw['players']==t['players'] and raw['start_frame']==t['start_frame'] and raw['end_frame']==t['end_frame'])
        check('D2 actual target down present',any(s[7]==0 and s[8]is False for s in t['players'][1]['states']))
        check('D2 R release edge present',any(e['type']=='R_release'for e in t['players'][0]['events']))
        continue
    if t['id']=='zipcaster-high':
        from tools.zipcaster.export import trace
        raw=trace((ROOT/t['evidence']['raw_steps']).parent,'high-side')
        check('D2B high clip identity',t==zipclips[1])
        check('D2B high trace raw reconstruction',raw['players']==t['players']and raw['start_frame']==t['start_frame']and raw['end_frame']==t['end_frame'])
        check('D2B high actual KO',any(s[7]==0 and s[8]is False for s in t['players'][1]['states']))
        continue
    if t['id'].startswith('zipcaster-batch-'):
        from tools.zipcaster.export import trace
        raw=trace((ROOT/t['evidence']['raw_steps']).parent,'c')
        check('D2C recommended trace raw reconstruction',raw['players']==t['players']and raw['start_frame']==t['start_frame']and raw['end_frame']==t['end_frame'])
        check('D2C target KO retained',any(s[7]==0 and s[8]is False for s in t['players'][1]['states']))
        check('D2C clip has a measured successful point',any(p.get('clip_id')==t['id']and p['status']=='verified'for p in zipdata['verified']))
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

report = dict(passed=True, checks=len(checks), maps=[dict(name=m['id'], cells=len(m['cells']), vision_samples=m['sample_count'],wall_voxels=len(m['walls']),ambush_candidates=len(m['ambush'])) for m in data['maps']], trace_clips=len(data['traces']),trace_samples=sum(len(p['states']) for t in data['traces'] for p in t['players']),page=str(PAGE),bytes=PAGE.stat().st_size, page_sha256=hashlib.sha256(PAGE.read_bytes()).hexdigest(), scope='offline data and asset audit; browser interactions verified separately')
target=args.report or ROOT/'work/showcase/check.json'
if args.report:assert not target.exists(),'fresh explicit audit report required'
target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(report, ensure_ascii=False, indent=2))
