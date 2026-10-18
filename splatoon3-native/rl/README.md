# Native local RL environment

M6 is being implemented in layers. The host supplies internal cropped pixels, controller actions, and recent native local-player position/ink samples over a Unix domain socket. A present-based barrier and individual agent settlement replace the earlier HID/present one-to-one assumption. The two-player regression for this uncommitted revision failed on a repeated HID query in one settled frame; eight-player and full internal-state acceptance remain pending. Rewards are zero until verified paint/kill counters are available.

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

Each agent observes `pixels` (72×128×3 RGB uint8), `frame` (one int64), and `phase` (0 before game, 1 InGame, 2 ResultJudge, 3 ResultWinners). Reset returns only after all native InGame entries and attaches each controller at a completed-present boundary. Pixels are area averages of the native 1280×720 crop, read directly from the game texture with GPU completion, including in headless mode. Observations are the last completed frame before the next input sample. The environment also exposes `position` (three float32 coordinates in [-256,256]) and `position_valid`, plus `ink` (one float32 fraction in [0,1]) and `ink_valid`. These are recent local native network-state samples, copied during the live encoder call, not a new physics sample every render frame. `position_sample_frame` is available in infos; samples older than 120 present frames or outside InGame are masked to zero. `heading` is one float32 body yaw in [-pi,pi], computed from the own forward unit vector (0 toward +Z, positive toward +X), with `heading_valid`. It is separate from camera yaw and shares the packet sample/freshness rules. `remaining_time` is one float32 countdown in seconds with `time_valid` and info `time_sample_frame`. It is copied from the live native timer HUD only during InGame, uses its verified 60-units/second scale, and is masked outside InGame or after 120 presents without a fresh sample. `hp` is one float32 fraction (native 1000 units = 1) with `hp_valid`, copied from the same verified own network packet. It was compared independently with live PlayerDamage updates through PvP damage and recovery. It is not an authoritative alive flag; environmental death/respawn handling remains unmapped. `special` is one float32 charge fraction with `special_valid`, quantized to 1% by the native own packet. Own painting raised it from 0 to 49% while the neutral peer stayed at zero; the independent special HUD agreed within about one percent including sample timing. Scoring and authoritative alive fields remain pending.

Actions have `sticks[4]` = left X/Y, right X/Y in [-1,1], `gyro[3]` = controller angular rates in turns/second in [-1,1], and six binary `buttons` = ZR fire, ZL swim, R subweapon, RS special, B jump, Y camera reset. Every agent's command is sent before waiting for any acknowledgement. Invalid actions are rejected before any agent advances.

`step(k)` (the configured `frame_skip`) latches the next action at a completed-present boundary and advances exactly k native presents before returning. It does not wait for HID to count a frame. Loading, transitions and result animations can present without reading input; those frames advance normally and are counted in the per-step info `frames_without_input`. The first HID read in a frame latches the pending action; subsequent SDK queries return that same action. Backward frame numbers or reads beyond the step budget are rejected; a concurrent query at the paused budget endpoint waits for the next STEP. `input_repeats` counts repeated queries. All peers read one POSIX shared-memory monotonic clock: it runs while frames execute and while faster peers wait, pauses after every peer ACK arrives, and resumes before the next STEP batch. Policy waiting is deducted once for every peer. `guest_time_ns` is per-ACK diagnostic time; `barrier_guest_time_ns` is the common paused time after collecting all ACKs. This is a measured present boundary, not a claim of deterministic simulation, reproducible PIA packet scheduling, or a fixed 60 Hz physics tick. Setup uses M5's existing menu controller scripts before RL takes control.

Each agent terminates independently at native ResultJudge (phase 2), and is removed from `env.agents`. Submit subsequent actions for the remaining agents only. Settled processes still advance by k frames with neutral input on every step; native code also ignores their actions. `env.process_infos` contains all process ACKs, including retired agents. A match ends once all agents have settled or timed out; reset before that raises an error (explicit `close()` cancels a match). Once all agents terminate, `advance_settlement()` can advance neutral result animations until every process reports ResultWinners (phase 3). Reset then creates a fresh room and new save copies.

The wire format is platform independent: an AF_UNIX byte stream, one ASCII `STEP sequence frames buttons_hex lx ly rx ry gx gy gz\n` command, one JSON metadata line and exactly 27,648 RGB bytes per observation. Integers in the command are stick values in [-32767,32767]. The first observation has request 0 and advanced 0. The path is unique to the environment and mode 0600; an existing endpoint is never removed by another process. `RELEASE\n` releases the controller. No Nintendo or OS IP network is used.

`rl.env.turf_kill_reward` is an example for future **verified** `paint_points` and `kills` counters. It returns weighted positive deltas when both samples contain a counter, and zero for unavailable counters. It is not an estimate from image differences.

Run the pixel/control acceptance with `bash tests/run_all.sh --milestone m6 --players 2`. It must complete one random native match, check exact frame deltas despite policy delays, measure moving/camera image change against an idle baseline, then reset into a second match and advance ten steps. It does not claim a second complete result sequence. Artifacts, frame images and independent save copies stay in `work/tests/m6-*`.

M6-B passed the two-player full-match plus reset regression on 2026-10-18: 447 synchronized steps through both native Winners, followed by a fresh second match and ten steps (457 total). Own movement changed position while the neutral peer stayed fixed; firing reduced ink from 1 to 0.758284 and swimming restored it to 1. All four native hosts exited gracefully. Component checks cover repeated HID latching, missing-input presents, budget rejection, asynchronous per-agent termination and cross-process clock pause/resume. Missing-input frames were not observed in that real match; their counter is covered by the production transport fixture.

The wrapper creates the mode-0600 shared clock file and passes `DM_RL_CLOCK_FILE` to all native hosts. `rl/clock.py` builds a small C11 atomic helper from `tools/rl_clock.c` into ignored `work/build/` using the local C compiler. IPC uses POSIX files, mmap and Unix sockets; the clock helper supports macOS and Linux. A standalone socket without this file uses the original single-peer policy pause and is not the coordinated multi-agent interface.

Other internal fields and eight-player random-policy acceptance remain pending. Earlier failed experiments are preserved in the progress log; the fixed-nanoseconds-per-present clock was removed because it stalled the real game.

The real two-peer heading correlation can be run independently with `.venv/bin/python tests/test_m6_fields.py`. Each controller must turn its own heading while the neutral peer remains stable; `--survey` additionally records development-only unnamed candidate fields in ignored artifacts. This short check does not claim a complete match or reset.

`.venv/bin/python tests/test_m6_combat.py` is the longer two-peer action test for official HP damage/recovery, native camera/gyro calibration and natural results. It uses development logs to steer the test and records them only under ignored work/. Its live rerun after wiring HP is pending; the mapping itself has real PvP evidence and the production transport fixture checks the new wire field.
