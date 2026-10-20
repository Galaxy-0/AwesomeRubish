"""Explicit coordinator opt-in for A7; no changes to policy observations."""
from multiprocessing.util import Finalize
from pathlib import Path

from rl.native_start import NativeSessionPool,validate_runtime

_POOLS={}
_FINALIZER=None


def add_arguments(parser):
    parser.add_argument('--native-host',type=Path,help='A7 alternate host; requires --native-patched')
    parser.add_argument('--native-patched',type=Path,help='A7 separately rewritten modules')


def from_args(args):
    if bool(args.native_host)!=bool(args.native_patched):
        raise ValueError('--native-host and --native-patched must be supplied together')
    if args.native_host:
        host,patched=validate_runtime(args.native_host,args.native_patched)
        return dict(host=str(host),patched=str(patched))
    return None


def runtime_files(runtime):
    if runtime is None:return []
    host=Path(runtime['host']);patched=Path(runtime['patched'])
    return [host,host.with_suffix('.build.json'),*[p for p in patched.iterdir() if p.is_file()]]


def env_options(runtime):
    global _FINALIZER
    if runtime is None:return {}
    if set(runtime)!={'host','patched'}:raise ValueError('native runtime keys must be host and patched')
    key=(str(Path(runtime['host']).resolve()),str(Path(runtime['patched']).resolve()))
    if key not in _POOLS:
        _POOLS[key]=NativeSessionPool(*key)
        if _FINALIZER is None:_FINALIZER=Finalize(None,close_pools,exitpriority=10)
    pool=_POOLS[key]
    return dict(patched=pool.patched,session_factory=pool.acquire,session_releaser=pool.release)


def close_pools():
    errors=[]
    for pool in _POOLS.values():
        try:pool.close()
        except BaseException as error:errors.append(error)
    _POOLS.clear()
    if errors:raise RuntimeError('native room cleanup: '+repr(errors))
