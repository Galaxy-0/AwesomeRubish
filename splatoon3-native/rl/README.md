# Native local RL environment

M6 is being implemented in layers. The first layer supplies real cropped game pixels and controller actions through a local Unix domain socket. Internal player counters are not yet supplied; rewards in this layer are zero. See `notes/PROGRESS.md` for actual acceptance status.

Install Python dependencies with `uv pip install --python .venv/bin/python -r rl/requirements.txt`.
The native host, game dump, shader cache and reference save are the same local prerequisites as M5. No game files are downloaded or checked in.

```python
from rl import parallel_env

env = parallel_env(players=2, frame_skip=15, mode=0, stage_id=1, weapons=[0, 0])
try:
    observations, infos = env.reset(seed=137)
    while env.agents:
        actions = {agent: env.action_space(agent).sample() for agent in env.agents}
        observations, rewards, terminated, truncated, infos = env.step(actions)
    observations, infos = env.reset()  # Fresh isolated native processes and save copies.
finally:
    env.close()
```

Use `players=8` for 4v4. Mode indexes, stage IDs and weapon IDs follow the local M5 catalogs. `reset(options={"mode": 0, "stage_id": 1, "weapons": [...]})` selects another configuration. A reset closes the previous room and launches a new room using the shared M5 routes, including after settlement; it does not yet navigate the native rematch UI in the same processes.

Each agent observes `pixels` (72×128×3 RGB uint8), `frame` (one int64), and `phase` (0 before game, 1 InGame, 2 ResultJudge, 3 ResultWinners). Reset returns only after all native InGame entries and attaches each controller at an input boundary. Pixels are area averages of the native 1280×720 crop, read directly from the game texture with GPU completion, including in headless mode. Observations are the last completed frame before the next input sample. Unavailable remaining time and internal state are omitted.

Actions have `sticks[4]` = left X/Y, right X/Y in [-1,1], `gyro[3]` = controller angular rates in turns/second in [-1,1], and six binary `buttons` = ZR fire, ZL swim, R subweapon, RS special, B jump, Y camera reset. Every agent's command is sent before waiting for any acknowledgement. Invalid actions are rejected before any agent advances.

`step(k)` holds that action for exactly k input/present iterations (`frame_skip`), then pauses before the following input and returns an acknowledgement of the frame difference. The guest clock freezes while waiting for Python. The host refuses skipped input/present boundaries or a change of controlling game thread. This is a measured input/render frame boundary; it is not a claim of deterministic simulation, reproducible PIA packet scheduling, or a fixed 60 Hz physics tick. Setup still uses M5's existing menu controller scripts before RL takes control.

The wire format is platform independent: an AF_UNIX byte stream, one ASCII `STEP sequence frames buttons_hex lx ly rx ry gx gy gz\n` command, one JSON metadata line and exactly 27,648 RGB bytes per observation. Integers in the command are stick values in [-32767,32767]. The first observation has request 0 and advanced 0. The path is unique to the environment and mode 0600; an existing endpoint is never removed by another process. `RELEASE\n` releases the controller. No Nintendo or OS IP network is used.

`rl.env.turf_kill_reward` is an example for future **verified** `paint_points` and `kills` counters. It returns weighted positive deltas when both samples contain a counter, and zero for unavailable counters. It is not an estimate from image differences.

Run the pixel/control acceptance with `bash tests/run_all.sh --milestone m6 --players 2`. It must complete one random native match, check exact frame deltas despite policy delays, measure moving/camera image change against an idle baseline, then reset into a second match and advance ten steps. It does not claim a second complete result sequence. Artifacts, frame images and independent save copies stay in `work/tests/m6-*`.
