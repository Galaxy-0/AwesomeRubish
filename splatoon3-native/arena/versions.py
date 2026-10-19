"""Opaque, hash-checked policy snapshots; never lock or modify author trees."""
from pathlib import Path
import shutil
import tempfile

from .config import PolicySpec


def snapshot_policy(source,destination):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if destination==source or source in destination.parents:
        raise ValueError('snapshot must be outside author policy tree')
    if destination.exists():raise FileExistsError(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    for attempt in range(3):
        with tempfile.TemporaryDirectory(prefix='.capture-',dir=destination.parent) as temporary:
            candidate=Path(temporary)/'policy'
            before=PolicySpec.load(source)
            # Follow no author-supplied symlinks into another policy/user data.
            if any(p.is_symlink() for p in source.rglob('*')):
                raise ValueError('policy snapshot requires regular files, no symlinks')
            shutil.copytree(source,candidate,ignore=shutil.ignore_patterns('__pycache__'))
            copied=PolicySpec.load(candidate);after=PolicySpec.load(source)
            if before.source_sha256==copied.source_sha256==after.source_sha256:
                candidate.rename(destination)
                return PolicySpec.load(destination)
    raise RuntimeError('policy changed during all three snapshot attempts; retry after saving a stable version')


def loader_slots(path):
    """Shared flock inodes; each Session keeps its own activation marker."""
    path=Path(path).resolve();path.mkdir(parents=True,exist_ok=True)
    for n in range(2):(path/f'slot-{n}').touch(exist_ok=True)
    return path
