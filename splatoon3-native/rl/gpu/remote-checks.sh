#!/bin/sh
# Invoke inside an OWNED tmux/nohup job; SSH only launches/polls.
set -eu
cd "${RL_STAGE0_ROOT:-$HOME/splatoon3-native-rl-stage0}"
version=${1:?source version required}
run=${2:?fresh run label required}
case "$version:$run" in *[!a-zA-Z0-9:-]*) exit 2;; esac
test -d "$version/src/gpu"
test ! -e "checks-$run.started"
printf 'started\n' > "checks-$run.started"
export CC="$PWD/cc-zig" CXX="$PWD/cc-zig"
.venv/bin/python -c 'import torch; assert torch.cuda.is_available(); print(torch.__version__,torch.cuda.get_device_name())'
cd "$version"
export PYTHONPATH="$PWD/src" RL_STAGE0_DATA="$PWD/data" RL_STAGE0_DEVICE=cuda
../.venv/bin/python -m gpu.test_env > "../units-$run.log" 2>&1
../.venv/bin/python -m gpu.test_cuda --data data --out "../cuda-parity-$run.json" > "../cuda-parity-$run.log" 2>&1
../.venv/bin/python -m gpu.replay_s1 --reference data/s1-input-reference-v1.npz --data data --out "../s1-$run.json" > "../s1-$run.log" 2>&1
../.venv/bin/python -m gpu.run --data data --out "../bench-$run" --n-envs 1024 --steps 500 --warmup 10 --compile --fast-rays --cuda-graph --calibration data/native-camera-calibration-v1.json > "../bench-$run.log" 2>&1
