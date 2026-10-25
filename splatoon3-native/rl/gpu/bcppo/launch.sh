#!/bin/sh
# Run only on asuka0 inside this project's private directory, never the VPT venv.
set -eu
umask 077
cd "${BCPPO_ROOT:-$HOME/splatoon3-native-rl-stage0/bcppo81-r3}"
export PYTHONPATH="$PWD/src"
export CC="$HOME/splatoon3-native-rl-stage0/cc-zig"
export CXX="$HOME/splatoon3-native-rl-stage0/cc-zig"
echo $$ > launcher.pid
exec timeout --signal=INT --kill-after=120s 25h ../.venv/bin/python -u -m gpu.bcppo.train \
  --bc bc.pt --data data --calibration data/native-camera-calibration-v1.json \
  --contract data/contract.npz --mask-bank data/mask-bank.npz \
  --history ../stage1-round1-r1/checkpoints/u000100.pt \
  --history ../stage1-round1-r1/checkpoints/u000245.pt \
  --out "${BCPPO_OUT:-train-r1}" --hours "${BCPPO_HOURS:-24}" \
  --n-envs 128 --eval-envs 32 --critic-episodes 2 --seed 81 \
  --rollout 128 --sequence 32 --minibatch 16 --epochs 3 --lr .0001 \
  --eval-hours 1 --health-eval-minutes 30 --zero-damage-hours 6 --save-minutes 15 "$@"
