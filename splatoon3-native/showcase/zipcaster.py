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
        maps.append(dict(id=m['id'], total=len(m['anchors']), candidates=list(candidates.values())))
    return dict(schema='showcase.zipcaster.v1', maps=maps, verified=[native], per_region=PER_REGION,
                mechanisms=report['native'],
                selection='每个命名目标区域最多8点；按现有几何连招条件、落点潜在视域、距离排序，3u内去重。非成功率排名。',
                limits='候选为静态射线分析；挂面、枪口偏移、动态物体和实际命中待原生验证。炸弹组合只做伤害算术，大招内炸弹输入未验证。'), clip
