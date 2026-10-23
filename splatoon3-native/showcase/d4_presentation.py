"""Copy existing query values into map-pin labels; no model or heat recalculation."""
import json
import math


def compile_presentation(root, source, d4, existing_sources):
    maps = {m['id']: m for m in d4['maps']}
    plan = json.loads(source('work/d4/restart-v4/blade-calibration-plan-v3.json').read_text())
    preferred = {}
    for point in plan['points']:
        if point['band'] not in ['top1', 'top2']:
            continue
        key = ':'.join(map(str, [point['graph'].split('-')[-1], point['enemy_index'],
                               point['heading'], point['speed']]))
        preferred.setdefault(key, {})[point['model']['start']] = 0 if point['band'] == 'top1' else 1
    rankings = {}
    for name in existing_sources:
        if 'blade-' not in name or not name.endswith('result.json'):
            continue
        path = root / name
        query = json.loads(path.read_text())
        if query.get('schema') != 'inklab.d4.blade-only.query.v1':
            continue
        if not query.get('search_complete'):
            continue
        source(path)
        m = maps[query['map']]
        enemy = query['enemy']
        key = ':'.join(map(str, [m['id'], query['enemy_index'],
                               query['heading_quadrant'], query['speed']]))
        ties = preferred.get(key, {})
        # Cost/exposure stay primary. Keep frozen selections in exactly tied slots.
        rows = [r for r in query['rows'] if r.get('complete')
                and r.get('probability') == 1 and m['ordinary_support'][r['start']]
                and not r.get('attack_uncertainties')]
        rows.sort(key=lambda r: (r['cost'], r['exposure_frames'], ties.get(r['start'], 2),
                  abs(r['position'][1] - enemy[1]), math.dist(r['position'], enemy), r['start']))
        rankings[key] = dict(complete=True, source=name,
            points=[{k: r[k] for k in ['start', 'position', 'remaining',
                     'exposure_frames', 'stealth', 'program', 'hooks']} for r in rows[:3]])
    return dict(rankings=rankings,
        scope='Existing completed queries, ordinary-supported starts; cost/exposure first, '
              'frozen selections preferred in exact ties, then height/distance/ID. '
              'Presentation labels only; no new model result, input or conclusion.')
