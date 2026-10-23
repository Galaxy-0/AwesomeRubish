#!/bin/sh
# Run on the explicitly authorized asuka0 user account. No game/host included.
set -eu
RL_STAGE0_ROOT=${RL_STAGE0_ROOT:-"$HOME/splatoon3-native-rl-stage0"}
mkdir -p "$RL_STAGE0_ROOT"
chmod 700 "$RL_STAGE0_ROOT"
python3 -m venv "$RL_STAGE0_ROOT/.venv"
"$RL_STAGE0_ROOT/.venv/bin/python" -m pip install \
  --timeout 120 --retries 3 --resume-retries 3 \
  'torch==2.8.0+cu128' \
  --index-url https://download.pytorch.org/whl/cu128 \
  --extra-index-url https://pypi.org/simple
"$RL_STAGE0_ROOT/.venv/bin/python" -m pip install \
  --timeout 120 --retries 3 --resume-retries 3 'numpy==2.2.6'
"$RL_STAGE0_ROOT/.venv/bin/python" - <<'PY'
import json,sys,torch
from pathlib import Path
out={'python':sys.version,'torch':torch.__version__,'cuda_build':torch.version.cuda,
     'cuda_available':torch.cuda.is_available()}
if out['cuda_available']:
    x=torch.arange(1024,device='cuda',dtype=torch.float32)
    out.update(gpu=torch.cuda.get_device_name(),sum=float(x.square().sum().item()))
print(json.dumps(out,indent=2))
Path('cuda-verify.json').write_text(json.dumps(out,indent=2)+'\n')
if not out['cuda_available']:raise SystemExit('CUDA verification failed')
PY
