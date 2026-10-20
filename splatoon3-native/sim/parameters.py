"""Read local RomFS only. Extracted tables/manifests belong under ignored work/."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from tools.byml import read
from tools.stage_collision import unpack

ROOT = Path(__file__).resolve().parents[1]
ROMFS = ROOT / 'work/data/v720896/RomFS'
ENTRY = 'Component/GameParameterTable/{}.game__GameParameterTable.bgyml'


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def extract(romfs=ROMFS):
    """No invented default values are merged into serialized game parameters."""
    romfs = Path(romfs)
    pack_path = romfs / 'Pack/Params.pack.zs'
    entries = unpack(pack_path)
    tables, sources = {}, []
    for name in ('WeaponSaberNormal', 'SplPlayer'):
        entry = ENTRY.format(name)
        tables[name] = read(entries[entry])['GameParameters']
        sources.append(dict(path=str(pack_path), sha256=sha256(pack_path),
                            entry=entry, entry_sha256=hashlib.sha256(entries[entry]).hexdigest()))
    actor_path = romfs / 'Pack/Actor/SplPlayer.pack.zs'
    actor = unpack(actor_path)
    for suffix in ('SplPlayer', 'SplPlayer_ColBullet'):
        entry = f'Phive/ShapeParam/{suffix}.phive__ShapeParam.bgyml'
        tables[suffix + '_shape'] = read(actor[entry])
        sources.append(dict(path=str(actor_path), sha256=sha256(actor_path),
                            entry=entry, entry_sha256=hashlib.sha256(actor[entry]).hexdigest()))
    db_path = romfs / 'RSDB/WeaponInfoMain.Product.b30.rstbl.byml.zs'
    rows = read(subprocess.check_output(['zstd', '-dc', str(db_path)]))
    row = next(r for r in rows if r['Id'] == 8000)
    sources.append(dict(path=str(db_path), sha256=sha256(db_path)))
    return dict(schema='sim.parameters.v1', game_version='11.3.0', weapon_id=8000,
                tables=tables, weapon_info=row, sources=sources,
                missing_defaults=['human/swim acceleration and speed', 'gravity/jump impulse',
                                  'HP/ink recovery rates', 'respawn delay', 'gear AP curves',
                                  'native paintable surface masks and paint point conversion'],
                note='Sparse BYML overrides only; missing C++ defaults are not zero.')


class Parameters:
    def __init__(self, data):
        if data['schema'] != 'sim.parameters.v1' or data['weapon_id'] != 8000:
            raise ValueError('wrong simulator parameter schema/weapon')
        self.data = data
        self.weapon = data['tables']['WeaponSaberNormal']
        self.saber = self.weapon['spl__WeaponSaberParam']
        self.swing = self.saber['SwingParam']
        self.charge = self.saber['ChargeParam']
        self.target_capsule = data['tables']['SplPlayer_ColBullet_shape']['Capsule'][0]

    @classmethod
    def local(cls):
        return cls(extract())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--romfs', type=Path, default=ROMFS)
    parser.add_argument('--out', type=Path, default=ROOT / 'work/sim/parameters.json')
    args = parser.parse_args()
    out = args.out.resolve()
    if ROOT / 'work' not in out.parents:
        parser.error('extracted game parameters must stay under ignored work/')
    data = extract(args.romfs)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2) + '\n')
    print(json.dumps(dict(output=str(out), sources=len(data['sources']),
                          missing_defaults=data['missing_defaults']), indent=2))


if __name__ == '__main__':
    main()
