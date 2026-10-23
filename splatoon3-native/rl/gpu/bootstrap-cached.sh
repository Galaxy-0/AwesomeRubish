#!/bin/sh
# Fallback after a terminated/failed pip run. Reuses its completed official
# cu126 torch wheel, then installs dependencies from PyPI using uv in tmux.
set -eu
RL_STAGE0_ROOT=${RL_STAGE0_ROOT:-"$HOME/splatoon3-native-rl-stage0"}
cd "$RL_STAGE0_ROOT"
test -f install-cu126.exit
.venv/bin/python -m pip install --index-url https://pypi.org/simple --timeout 30 --retries 5 uv
.venv/bin/python - <<'PY'
from pathlib import Path
import zipfile,os,json,hashlib
root=Path.cwd();wheels=root/'wheelhouse';wheels.mkdir(exist_ok=True)
target=wheels/'torch-2.12.1+cu126-cp313-cp313-manylinux_2_28_x86_64.whl'
if not target.exists():
    for p in (Path.home()/'.cache/pip').rglob('*.body'):
        if p.stat().st_size<700_000_000:continue
        try:
            with zipfile.ZipFile(p) as z:
                metadata=next(n for n in z.namelist() if n.endswith('.dist-info/METADATA') and n.startswith('torch-'))
                text=z.read(metadata).decode()
                if 'Version: 2.12.1+cu126\n' not in text:continue
            os.link(p,target);break
        except (zipfile.BadZipFile,StopIteration):continue
    else:raise SystemExit('Completed official cu126 wheel not present; do not redownload implicitly')
record=dict(path=str(target),bytes=target.stat().st_size,sha256=hashlib.file_digest(target.open('rb'),'sha256').hexdigest(),source='completed official cu126 pip HTTP cache from preceding run')
(root/'wheel-cache.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record),flush=True)
PY
UV_HTTP_TIMEOUT=120 UV_HTTP_RETRIES=10 .venv/bin/uv pip install --python .venv/bin/python \
 --index-url https://pypi.org/simple 'wheelhouse/torch-2.12.1+cu126-cp313-cp313-manylinux_2_28_x86_64.whl' 'numpy==2.2.6'
.venv/bin/python - <<'PY'
import torch,json,sys
from pathlib import Path
out=dict(torch=torch.__version__,python=sys.version,cuda_build=torch.version.cuda,cuda_available=torch.cuda.is_available())
if torch.cuda.is_available():
 x=torch.arange(1024,device='cuda',dtype=torch.float32);out.update(gpu=torch.cuda.get_device_name(),sum=float(x.square().sum().item()))
Path('cuda-verify.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out),flush=True)
assert torch.cuda.is_available() and torch.__version__=='2.12.1+cu126'
PY
