"""Two bounded contact-shape confirmations with an isolated read-only sensor."""
import argparse
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.zipcaster_d3r.control import NativeSession, sha
from tools.zipcaster_d4 import attack_probe_v3 as probe


def main(a):
    host = a.host.resolve()
    record = json.loads(host.with_suffix('.build.json').read_text())
    assert record['contact_readonly_sensor'] and record['output_sha256'] == sha(host)
    original_options, original_lab = NativeSession.host_options, probe.new_lab

    def options(session, n):
        return original_options(session, n) | ({'DM_D4_CONTACT_SENSOR': '1'} if n == 0 else {})

    def new_lab(*args, **kwargs):
        lab = original_lab(*args, **kwargs)
        (lab.out/'contact-wrapper.json').write_text(json.dumps({
            'wrapper': str(Path(__file__).resolve()), 'sha256': sha(Path(__file__)),
            'sensor_source_sha256': sha(host.parent/'contact_sensor.h'),
            'host_sha256': sha(host), 'sensor_player': 0, 'readonly': True,
            'scope': 'Live unique controlled SaberSlash calc entry, not post-physics; actor ownership field unverified.'
        }, indent=2)+'\n')
        return lab

    with patch.object(NativeSession, 'host_options', options), patch.object(probe, 'new_lab', new_lab):
        return probe.main(a)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--group', required=True)
    p.add_argument('--fit', type=Path, default=ROOT/'work/d4/restart-v3/attack-fit-v1.json')
    p.add_argument('--host', type=Path, required=True)
    raise SystemExit(main(p.parse_args()))
