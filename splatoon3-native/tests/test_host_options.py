#!/usr/bin/env python3
"""Fresh-process checks for process identity and guarded runtime ownership cuts."""
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def main():
    out = ROOT / 'work/tests/host-options'
    out.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith('DM_')}
    cases = []
    identities = []
    def run(name, binary, options=None, arg=None, reject=False):
        local = env | (options or {})
        p = subprocess.run([str(ROOT / 'upstream/dm/host/tests/build' / binary)] + ([arg] if arg else []),
                           env=local, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
        (out / (name + '.log')).write_bytes(p.stdout)
        passed = p.returncode != 0 and b'FATAL' in p.stdout if reject else p.returncode == 0 and b'0 failed' in p.stdout
        cases.append(dict(name=name, returncode=p.returncode, passed=passed))
        if not passed:
            raise RuntimeError(f'{name}: see {out / (name + ".log")}')
        return p.stdout.decode(errors='replace')
    run('identity-default', 't_account_player')
    run('identity-nickname', 't_account_player', {'DM_NICK': 'Researcher'})
    for player in range(8):
        text = run(f'identity-{player}', 't_account_player', {'DM_PLAYER': str(player), 'DM_NICK': 'ignored'})
        identities.append(text.split('uid=')[-1].strip())
    assert len(set(identities)) == 8
    for player in ('-1', '8', 'x', ''):
        run('identity-reject-' + (player or 'empty'), 't_account_player', {'DM_PLAYER': player}, reject=True)
    run('identity-build-guard', 't_account_player', {'DM_PLAYER': '0'}, 'unknown', reject=True)
    for flag in (None, '0', '1'):
        run('unlock-' + str(flag), 't_spl3_unlock', {} if flag is None else {'DM_FULL_UNLOCK': flag})
    run('unlock-build-guard', 't_spl3_unlock', {'DM_FULL_UNLOCK': '1'}, 'unknown', reject=True)
    run('unlock-signature-guard', 't_spl3_unlock', {'DM_FULL_UNLOCK': '1'}, 'mismatch', reject=True)
    run('unlock-option-guard', 't_spl3_unlock', {'DM_FULL_UNLOCK': 'yes'}, reject=True)
    run('weapon-default', 't_spl3_weapon')
    for weapon in ('0', '2040', '8001', '65535'):
        run('weapon-'+weapon, 't_spl3_weapon', {'DM_WEAPON': weapon})
    for weapon in ('-1', '65536', 'x', ''):
        run('weapon-reject-'+(weapon or 'empty'), 't_spl3_weapon', {'DM_WEAPON': weapon}, reject=True)
    for guard in ('unknown','mismatch'):
        run('weapon-'+guard, 't_spl3_weapon', {'DM_WEAPON': '8001'}, guard, reject=True)
    (out / 'result.json').write_text(json.dumps(dict(passed=True, cases=cases, identities=identities), indent=2) + '\n')
    print(f'host-options: {len(cases)} process cases passed')

if __name__ == '__main__':
    main()
