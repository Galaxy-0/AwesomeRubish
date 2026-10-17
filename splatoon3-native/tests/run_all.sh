#!/bin/bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
python="${PYTHON:-$root/.venv/bin/python}"
mkdir -p work/tests
make -C upstream/dm/host GAME=0100C2500FC20000 dmhost > work/tests/host-build.log 2>&1
make -C upstream/dm/gfx/tests GAME=0100C2500FC20000 t_render_enable t_nvn > work/tests/gpu-build.log 2>&1
(
    cd upstream/dm/gfx/tests
    ./t_render_enable > "$root/work/tests/render-enable.log" 2>&1
    ./t_nvn > "$root/work/tests/nvn.log" 2>&1
)
tail -1 work/tests/render-enable.log
tail -1 work/tests/nvn.log
"$python" tests/test_m1.py "$@"
