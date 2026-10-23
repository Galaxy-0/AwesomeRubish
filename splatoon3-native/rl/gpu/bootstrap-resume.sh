#!/bin/sh
# Persistent owned wheelhouse: curl -C preserves partial wheels across failures.
set -eu
RL_STAGE0_ROOT=${RL_STAGE0_ROOT:-"$HOME/splatoon3-native-rl-stage0"}
cd "$RL_STAGE0_ROOT"
test -f install-uv.exit
mkdir -p wheelhouse
wheel='torch-2.12.1+cu126-cp313-cp313-manylinux_2_28_x86_64.whl'
url='https://download.pytorch.org/whl/cu126/torch-2.12.1%2Bcu126-cp313-cp313-manylinux_2_28_x86_64.whl'
n=0
while ! curl -fL -C - --connect-timeout 20 --max-time 180 --speed-limit 10240 --speed-time 30 -o "wheelhouse/$wheel.partial" "$url"; do
 n=$((n+1)); printf 'download interrupted; owned partial retained, attempt %s\n' "$n"
 if test "$n" -ge 30; then exit 2; fi
 sleep 30
done
.venv/bin/python - "$wheel" <<'PY'
from pathlib import Path
import sys,zipfile,hashlib,json
p=Path('wheelhouse')/(sys.argv[1]+'.partial')
with zipfile.ZipFile(p) as z:
 n=next(n for n in z.namelist() if n.startswith('torch-') and n.endswith('.dist-info/METADATA'))
 assert 'Version: 2.12.1+cu126\n' in z.read(n).decode()
record=dict(source='official cu126 wheel index, persistent resumed file',bytes=p.stat().st_size,sha256=hashlib.file_digest(p.open('rb'),'sha256').hexdigest())
Path('wheel-resume.json').write_text(json.dumps(record,indent=2)+'\n')
p.rename(Path('wheelhouse')/sys.argv[1]);print(json.dumps(record),flush=True)
PY
UV_HTTP_TIMEOUT=120 UV_HTTP_RETRIES=20 .venv/bin/uv pip install --python .venv/bin/python --index-url https://pypi.org/simple "wheelhouse/$wheel" 'numpy==2.2.6'
.venv/bin/python - <<'PY'
import torch,json,sys
from pathlib import Path
out=dict(torch=torch.__version__,python=sys.version,cuda_build=torch.version.cuda,cuda_available=torch.cuda.is_available())
if torch.cuda.is_available():
 x=torch.arange(1024,device='cuda',dtype=torch.float32);out.update(gpu=torch.cuda.get_device_name(),sum=float(x.square().sum().item()))
Path('cuda-verify.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out),flush=True)
assert torch.cuda.is_available() and torch.__version__=='2.12.1+cu126'
PY
