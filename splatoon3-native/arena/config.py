"""Coordinator-side policy manifest; policy files remain mutually inaccessible."""
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import tomllib
from rl.loadout import encode_loadout


@dataclass(frozen=True)
class PolicySpec:
    name: str
    root: Path
    loadout: dict
    step_frames: int
    step_timeout: float
    source_sha256: str

    @classmethod
    def load(cls,root):
        root=Path(root).resolve();data=tomllib.loads((root/'config.toml').read_text())
        if set(data)!={'name','weapon','step_frames','step_timeout','loadout'}:raise ValueError('policy config keys')
        if not isinstance(data['name'],str) or not data['name']:raise ValueError('policy name required')
        if data['weapon']!=8000:raise ValueError('arena requires Splatana Stamper 8000')
        if type(data['step_frames']) is not int or not 1<=data['step_frames']<=60:raise ValueError('policy cadence must be 1..60 presents')
        limit=data['step_timeout']
        if type(limit) not in (int,float) or not math.isfinite(limit) or not 0<limit<=5:raise ValueError('policy time limit must be 0..5 seconds')
        encode_loadout(data['loadout'])
        digest=hashlib.sha256()
        for p in sorted(root.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:
                digest.update(str(p.relative_to(root)).encode());digest.update(p.read_bytes())
        if not (root/'policy.py').is_file():raise ValueError('policy.py required')
        return cls(data['name'],root,data['loadout'],data['step_frames'],float(limit),digest.hexdigest())
