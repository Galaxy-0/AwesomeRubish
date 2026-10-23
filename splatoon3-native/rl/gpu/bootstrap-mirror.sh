#!/bin/sh
# Main torch wheel stays from the official cu126 index. Dependency mirror files
# MUST match SHA256 values obtained independently from official PyPI metadata.
set -eu
RL_STAGE0_ROOT=${RL_STAGE0_ROOT:-"$HOME/splatoon3-native-rl-stage0"}
cd "$RL_STAGE0_ROOT"
test -f install-resume.exit
.venv/bin/python - <<'PY'
import json,zipfile,email,hashlib,re
from pathlib import Path
rows=json.loads(Path('dependency-hashes.json').read_text());local={}
for p in Path('wheelhouse').glob('*.whl'):
 with zipfile.ZipFile(p) as z:
  name=next(k for k in z.namelist() if k.endswith('.dist-info/METADATA'));meta=email.message_from_bytes(z.read(name));key=meta['Name'].lower().replace('_','-')
 local[key]=(p,meta['Version'],hashlib.file_digest(p.open('rb'),'sha256').hexdigest())
torch,version,h=local['torch'];assert version=='2.12.1+cu126'
assert h==json.loads(Path('wheel-resume.json').read_text())['sha256']
lines=[f'{torch} --hash=sha256:{h}']
for row in rows:
 key=row['name'].lower().replace('_','-');found=local.get(key)
 if found and found[1]==row['version']:
  path,version,h=found;assert h in row['hashes'];lines.append(f'{path} --hash=sha256:{h}')
 else:lines.append(row['name']+'=='+row['version']+' '+' '.join('--hash=sha256:'+h for h in row['hashes']))
Path('requirements-verified.txt').write_text('\n'.join(lines)+'\n');print('torch official wheel + official-hash-bound dependencies; private local wheels preferred',flush=True)
PY
UV_HTTP_TIMEOUT=120 UV_HTTP_RETRIES=20 UV_CONCURRENT_DOWNLOADS=4 .venv/bin/uv pip install --python .venv/bin/python --require-hashes --index-url https://pypi.tuna.tsinghua.edu.cn/simple -r requirements-verified.txt
.venv/bin/python - <<'PY'
import json,sys,torch
from pathlib import Path
out=dict(torch=torch.__version__,python=sys.version,cuda_build=torch.version.cuda,cuda_available=torch.cuda.is_available())
if torch.cuda.is_available():
 x=torch.arange(1024,device='cuda',dtype=torch.float32);out.update(gpu=torch.cuda.get_device_name(),sum=float(x.square().sum().item()))
Path('cuda-verify.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out),flush=True)
assert torch.cuda.is_available() and torch.__version__=='2.12.1+cu126'
PY
