#!/usr/bin/env python3
"""Summarize local A3 diagnostics without accepting candidate field meanings."""
import argparse
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]


def main(path):
    path = path.resolve()
    if not path.is_relative_to(ROOT/'work'):
        raise ValueError('raw diagnostic reports belong under ignored work/')
    result = json.loads(path.read_text())
    session = Path(result['session']).resolve()
    if not session.is_relative_to(ROOT/'work'):
        raise ValueError('native diagnostic session must be under work/')
    logs = {f'player_{n}': (session/f'player-{n}/host.log').read_text(errors='replace')
            for n in range(2)}
    states = {agent: {int(f): bytes.fromhex(h) for f, h in
                     re.findall(r'RL_STATE frame=(\d+).*?data=([0-9a-f]{992})', text)}
              for agent, text in logs.items()}
    rows = []
    for sample in result['samples']:
        label = sample['label']
        owner = label.split('-')[0] if label.startswith('player_') else 'player_0'
        info = sample['infos'][owner]
        frame = info['position_sample_frame']
        data = states[owner][frame]
        rows.append(dict(label=label, owner=owner, host_sample_frame=frame,
                         position=struct.unpack_from('<3f', data, 0x20),
                         candidate_contact_94=struct.unpack_from('<I', data, 0x94)[0],
                         candidate_form_f8=struct.unpack_from('<I', data, 0xf8)[0],
                         candidate_form_payload_e8_f0=data[0xe8:0xf0].hex(),
                         native_slot=info['self_slot']))
    cameras = {}
    for agent, text in logs.items():
        phase = text.find('PROBE main+0x3db55d0 ')
        cameras[agent] = {}
        for offset in ('28f9e8c', '28f9e90', '28f9e94'):
            hits = list(re.finditer(r'PROBE main\+0x'+offset+r' #[^\n]+', text))
            cameras[agent][offset] = dict(installed=('探针 main+0x'+offset+'（') in text,
                ingame_seen=phase >= 0, total=len(hits),
                after_ingame=sum(phase >= 0 and m.start() > phase for m in hits),
                last_records=[m.group() for m in hits[-3:]])
    report = dict(full_a3_passed=False, diagnostic_completed=result['probe_completed'],
                  errors=result['errors'], session=str(session), samples=rows,
                  camera_candidates=cameras,
                  note='Candidate bytes and probe hits do not certify submerged state or camera pose.')
    output = path.parent/'candidate-fields.json'
    output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(report=str(output), diagnostic_completed=report['diagnostic_completed'],
                         samples=len(rows), camera_candidates=cameras, full_a3_passed=False), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('result', type=Path)
    main(parser.parse_args().result)
