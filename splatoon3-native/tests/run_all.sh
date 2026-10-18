#!/bin/bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
python="${PYTHON:-$root/.venv/bin/python}"
milestone=m1
if [[ "${1:-}" == --milestone ]]; then
    milestone="${2:?--milestone requires m1, m2, m25, m3, m4, m5 or m6}"
    shift 2
fi
case "$milestone" in m1|m2|m25|m3|m4|m5|m6) ;; *) echo "Unknown milestone: $milestone" >&2; exit 2 ;; esac
mkdir -p work/tests
if [[ "$milestone" == m6 ]]; then "$python" tools/prepare_rl.py; fi
make -C upstream/dm/host/tests GAME=0100C2500FC20000 build/t_hid_motion build/t_ldn_frontend build/t_account_player build/t_spl3_unlock build/t_spl3_weapon build/t_ldn_peer build/t_fs > work/tests/hid-build.log 2>&1
upstream/dm/host/tests/build/t_hid_motion > work/tests/hid-motion.log 2>&1
upstream/dm/host/tests/build/t_ldn_frontend > work/tests/ldn-frontend.log 2>&1
make -C upstream/dm/host GAME=0100C2500FC20000 dmhost > work/tests/host-build.log 2>&1
make -C upstream/dm/gfx/tests GAME=0100C2500FC20000 t_render_enable t_nvn > work/tests/gpu-build.log 2>&1
(
    cd upstream/dm/gfx/tests
    ./t_render_enable > "$root/work/tests/render-enable.log" 2>&1
    DM_HEADLESS=1 ./t_render_enable > "$root/work/tests/render-headless.log" 2>&1
    ./t_nvn > "$root/work/tests/nvn.log" 2>&1
)
upstream/dm/host/tests/build/t_fs > work/tests/fs.log 2>&1
"$python" tests/test_host_options.py
if [[ "$milestone" == m5 || "$milestone" == m6 ]]; then "$python" tests/test_m5_resources.py; fi
if [[ "$milestone" == m6 ]]; then
    make -C upstream/dm/host/tests GAME=0100C2500FC20000 build/t_rl build/t_hid_rl build/t_rl_clock > work/tests/rl-build.log 2>&1
    upstream/dm/host/tests/build/t_hid_rl > work/tests/hid-rl.log 2>&1
    upstream/dm/host/tests/build/t_rl_clock > work/tests/rl-clock.log 2>&1
    upstream/dm/host/tests/build/t_rl_clock manual >> work/tests/rl-clock.log 2>&1
    "$python" tests/test_m6_transport.py
    tail -1 work/tests/hid-rl.log
    cat work/tests/rl-clock.log
fi
tail -1 work/tests/render-enable.log
tail -1 work/tests/render-headless.log
tail -1 work/tests/nvn.log
tail -1 work/tests/hid-motion.log
tail -1 work/tests/ldn-frontend.log
if [[ "$milestone" == m3 || "$milestone" == m4 || "$milestone" == m5 || "$milestone" == m6 ]]; then
    "$python" tests/test_ldn_air.py
fi
"$python" "tests/test_$milestone.py" "$@"
