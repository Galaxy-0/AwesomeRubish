#!/usr/bin/env python3
"""Read local 11.3.0 Stamper parameters; extracted tables stay under work/a6."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.byml import read
from tools.stage_collision import unpack


def research():
    rom = ROOT / 'work/data/v720896/RomFS'
    source = rom / 'Pack/Params.pack.zs'
    entries = unpack(source)
    name = 'Component/GameParameterTable/WeaponSaberNormal.game__GameParameterTable.bgyml'
    weapon = read(entries[name])['GameParameters']
    main = read(subprocess.check_output([
        'zstd', '-dc', str(rom / 'RSDB/WeaponInfoMain.Product.b30.rstbl.byml.zs')]))
    row = next(r for r in main if r['Id'] == 8000)
    saber = weapon['spl__WeaponSaberParam']
    result = dict(
        build='11.3.0 / v720896', weapon_id=row['Id'],
        sub=row['SubWeapon'], special=row['SpecialWeapon'],
        special_points=row['SpecialPoint'], catalog_range=row['Range'],
        charge=saber['ChargeParam'], swing=saber['SwingParam'],
        horizontal_projectile=weapon['BulletSaberHorizontalParam'],
        vertical_projectile=weapon['BulletSaberVerticalParam'],
        horizontal_contact=weapon['BulletSaberSlashHorizontalParam'],
        vertical_contact=weapon['BulletSaberSlashVerticalParam'],
        has_keep_charge_param=any('KeepCharge' in k for k in weapon),
        source=dict(path=str(source), sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    entry=name, entry_sha256=hashlib.sha256(entries[name]).hexdigest()),
        caveats=['Parameter counters are not measured total controller startup frames.',
                 'Catalog Range is not a measured horizontal/vertical hit cutoff.',
                 'Absence of KeepCharge parameters alone does not prove cancellation.'])
    out = ROOT / 'work/a6/parameters.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + '\n')
    print(out)
    print(json.dumps(dict(weapon=8000, sub=result['sub'], special=result['special'],
                         charge=saber['ChargeParam'],
                         damage_raw={key: weapon[key]['DamageParam'] for key in (
                             'BulletSaberHorizontalParam', 'BulletSaberVerticalParam',
                             'BulletSaberSlashHorizontalParam', 'BulletSaberSlashVerticalParam')},
                         catalog_range=row['Range']), indent=2))
    return result


if __name__ == '__main__':
    research()
