# Stage0 execution ledger

This is an environment implementation only; no training entry point is added.
Long remote jobs use owned tmux sessions plus .log/.exit files. SSH failures
retry after30/60/120s and do not count as scientific or engineering attempts.
Never touch the VPT venv. Reuse only pip's download cache in a private venv.

Implementation gates (keep explicit in acceptance report):
1. private CUDA installation and real tensor operation;
2. native +5 and camera geometry measurement with cloned save;
3. S1-derived movement/paint, saber/.52/projectile/Zipcaster, recovery/reward;
4. partial observation and recorder, all hot-path tensors on GPU;
5. numerical units + same-input S1 error report;
6. full180s random rollouts, showcase playback;
7. synchronized end-to-end200k env-frames/s including observations.

Benchmark count = n_envs * actualfixed60 frames, not2agents or decisions.
Unknown native mechanisms are configured approximations, not proof claims.
