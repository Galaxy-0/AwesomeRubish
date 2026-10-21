"""Presentation selection over D2 results. Does not recompute collision or vision."""
import json
import math

REGIONS = ('center', 'central_high', 'west_lane', 'east_lane')
PER_REGION = 8


def compile_zipcaster(root, source):
    layers = json.loads(source('showcase/data/zipcaster-layer.json').read_text())
    evidence = json.loads(source('work/d2/measurements.json').read_text())
    report = json.loads(source('notes/d2-20261021.json').read_text())
    clips = json.loads(source('showcase/data/zipcaster-traces.json').read_text())
    clip = next(c for c in clips if c['label'] == '原生飞索 · mc')
    clip.update(id='zipcaster-mid', label='飞索实测 · 中路蓄斩接轻斩', short_label='飞索连招',
                description='静止满血靶：挂墙 → 开始蓄斩 → 下落命中70 → 转身轻斩击倒。蓄力起始至首次观测倒下150帧，含重瞄，非最短连招。QS57AP。')
    source(clip['evidence']['raw_steps']); source(clip['evidence']['result'])
    before = evidence['mid_combo']['statuses']['mc-before']['player_0']
    hanging = evidence['mid_combo']['statuses']['mc-before-charge']
    native = dict(id='native-mid-wall', status='verified', map='Yunohana', region='center',
                  label='中路夹具 · 实测挂墙姿态', position=hanging['player_0']['position'],
                  start=before['position'], target=hanging['player_1']['position'],
                  combo='full-light', damage=105, frames=150, clip_id=clip['id'],
                  caveat='标记是原生人物挂墙位置，实际锚点/命中面尚未读取；只验证本夹具，不认证附近候选。')
    b = json.loads(source('notes/d2b-20261021.json').read_text())
    high = json.loads(source('work/d2b/traces/high-side.json').read_text())[0]
    high.update(id='zipcaster-high',label='飞索实测 · 侧角上台接两刀',short_label='高台连招',
                description='从侧角挂索落格栅，满蓄70接轻斩击倒高台满血靶。首次KO观测75帧，非最短；QS57AP。')
    source(high['evidence']['raw_steps']);high_run=json.loads(source(high['evidence']['result']).read_text())
    high_start=next(c['after']['player_0']['position']for c in high_run['cases']if c['kind']=='high-side-before')
    anchor=b['native_anchors'][-1]
    verified=[native,dict(id='native-high-side',status='verified',map='Yunohana',region='central_high',
        label='侧角上台 · 两刀收高台',position=anchor['anchor_world'],anchor=anchor['anchor_world'],
        normal=anchor['hit_normal_world'],start=high_start,
        landing=b['high_combo']['before']['player_0']['position'],target=b['high_combo']['before']['player_1']['position'],
        combo='full-light',damage=105,frames=75,clip_id=high['id'],
        caveat='B原生1次：精确锚点和法线已读取；侧角上索后落格栅，两刀命中，非空中挂墙连招或实战安全保证。')]
    batch_path=root/'work/d2c/results.json'
    summaries=[];recommendations=[];extra_clips=[]
    if batch_path.exists():
        batch=json.loads(source('work/d2c/results.json').read_text());summaries=batch['maps'];recommendations=batch['recommendations']
        extra_clips=json.loads(source(batch['trace_output']['path']).read_text())
        for c in extra_clips:source(c['evidence']['raw_steps']);source(c['evidence']['result'])
        for p in batch['points']:
            verified.append(dict(id=p['id'],status=p['display_status'],map=p['map'],region=p['region'],
                label=p['label'],position=p['anchor']if p['display_status']=='verified'else p['requested_anchor'],
                anchor=p['anchor'],normal=p['normal'],start=p['source'],target=p['target'],
                landing=p['landing'],arrival_pose=p['arrival_pose'],post_sword_position=p['post_sword_position'],combo='full-light',damage=105,frames=p['frames'],arrival_frames=p['arrival_to_ko_frames'],
                attempts=p['attempts'],outcome=p['outcome'],sample_scope=p['sample_scope'],clip_id=p.get('clip_id'),
                caveat=p['caveat']))
    maps = []
    for m in layers['maps']:
        candidates = {}
        for region in REGIONS:
            pairs = [t for t in m['targets'] if t[1] == region and t[3] is not None]
            pairs.sort(key=lambda t: (not t[6], not t[5], -(m['anchors'][t[0]][14] or 0), t[3], t[0]))
            chosen = []
            for t in pairs:
                a = m['anchors'][t[0]]
                if any(math.dist(a[1:4], m['anchors'][i][1:4]) < 3 for i in chosen):
                    continue
                chosen.append(t[0])
                item = candidates.setdefault(a[0], dict(id=a[0], status='candidate', position=a[1:4],
                    attach=a[7:10], landing=a[10:13], view=a[14], targets=[],
                    start=None, approach_range=None))
                item['targets'].append(dict(region=region, position=m['target_positions'][region]['position'],
                    distance=t[3], line_clear=t[5], full_light=t[6],
                    bomb_full_geometry=bool(t[5] and t[3] <= 22)))
                approaches = [v for v in m['approaches'] if v[0] == t[0]]
                best = min(approaches, key=lambda v: v[2])
                item.update(start=m['starts'][best[1]], approach_range=best[2])
                if len(chosen) == PER_REGION:
                    break
        tested={p['id']for p in verified if p['map']==m['id']}
        maps.append(dict(id=m['id'], total=len(m['anchors']), candidates=[p for p in candidates.values()if p['id']not in tested]))
    return dict(schema='showcase.zipcaster.v2', maps=maps, verified=verified, per_region=PER_REGION,
                summaries=summaries,recommendations=recommendations,
                mechanisms=report['native'],
                selection='每个命名目标区域最多8点；按现有几何连招条件、落点潜在视域、距离排序，3u内去重。非成功率排名。',
                limits='空心环是静态候选；蓝色为指定夹具两刀成功、红色为有效试验失败、灰色为前置或连招未完成。每点1–2次，不代表实战成功率；天花板、护甲倍率仍未定。'), [clip,high,*extra_clips]
