"""Version-pinned arena host selection; no changes to policy observations."""
from multiprocessing.util import Finalize
from pathlib import Path
import json
import hashlib

from rl.native_start import NativeSessionPool,validate_runtime

_POOLS={}
_FINALIZER=None
DEFAULT_RUNTIME=Path(__file__).resolve().parent/'default-runtime.json'


def default_runtime(*,require_accepted=True):
    record=json.loads(DEFAULT_RUNTIME.read_text())
    root=DEFAULT_RUNTIME.parent.parent
    host,patched=validate_runtime(root/record['host'],root/record['patched'])
    if hashlib.sha256(host.read_bytes()).hexdigest()!=record['host_sha256']:
        raise ValueError('default arena host differs from the selected revision')
    if {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in patched.iterdir() if p.is_file()}!=record['patched_sha256']:
        raise ValueError('default arena patched modules differ from the selected revision')
    build=json.loads(host.with_suffix('.build.json').read_text())
    if build.get('test_only') or build.get('experimental_hdr') or build.get('copy_mode','none')!='none' or build['render_mode']!='camera':
        raise ValueError('default arena host must be the selected camera-only production build')
    if require_accepted:
        certificate=root/record['acceptance']
        if not certificate.is_file():
            raise ValueError('A8 default is not activated: final regression acceptance is missing; use an explicit native runtime for diagnostics')
        accepted=json.loads(certificate.read_text())
        if not (accepted.get('passed') and accepted.get('full_a8_passed') and accepted.get('comparison',{}).get('equivalence_passed') and accepted.get('host_build',{}).get('output_sha256')==record['host_sha256']):
            raise ValueError('A8 default acceptance is invalid or belongs to another host')
    return dict(host=str(host),patched=str(patched))


def add_arguments(parser):
    parser.add_argument('--native-host',type=Path,help='Override the pinned default arena host; requires --native-patched')
    parser.add_argument('--native-patched',type=Path,help='A7 separately rewritten modules')
    parser.add_argument('--legacy-menu',action='store_true',help='Explicit diagnostic fallback to the original menu host')


def from_args(args):
    if getattr(args,'legacy_menu',False):
        if args.native_host or args.native_patched:raise ValueError('--legacy-menu cannot override an explicit native runtime')
        return None
    if bool(args.native_host)!=bool(args.native_patched):
        raise ValueError('--native-host and --native-patched must be supplied together')
    if args.native_host:
        host,patched=validate_runtime(args.native_host,args.native_patched)
        return dict(host=str(host),patched=str(patched))
    return default_runtime()


def runtime_files(runtime):
    if runtime is None:return []
    host=Path(runtime['host']);patched=Path(runtime['patched'])
    return [DEFAULT_RUNTIME,host,host.with_suffix('.build.json'),*[p for p in patched.iterdir() if p.is_file()]]


def env_options(runtime):
    global _FINALIZER
    if runtime is None:return {}
    if set(runtime)!={'host','patched'}:raise ValueError('native runtime keys must be host and patched')
    key=(str(Path(runtime['host']).resolve()),str(Path(runtime['patched']).resolve()))
    if key not in _POOLS:
        _POOLS[key]=NativeSessionPool(*key)
        if _FINALIZER is None:_FINALIZER=Finalize(None,close_pools,exitpriority=10)
    pool=_POOLS[key]
    build=json.loads(Path(runtime['host']).with_suffix('.build.json').read_text())
    return dict(patched=pool.patched,session_factory=pool.acquire,session_releaser=pool.release,pixels=build.get('render_mode')!='camera')


def close_pools():
    errors=[]
    for pool in _POOLS.values():
        try:pool.close()
        except BaseException as error:errors.append(error)
    _POOLS.clear()
    if errors:raise RuntimeError('native room cleanup: '+repr(errors))
