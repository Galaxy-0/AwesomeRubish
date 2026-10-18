# Native local RL environment

PettingZoo `ParallelEnv` wrapper for 2 or 8 native game processes. Two-player pixel/control, internal-field action correlations, a complete match and a fresh-process reset passed. Eight-player random-policy acceptance also passed; see `../notes/PROGRESS.md` for exact evidence and earlier failures.

Install dependencies with `uv pip install --python .venv/bin/python -r rl/requirements.txt`. The host, local game dump, shader cache and read-only reference save are the same prerequisites as M5. Prepare the build-checked observation gates with `.venv/bin/python tools/prepare_rl.py`, then build the host. `tests/run_all.sh --milestone m6` does both automatically. No game files are downloaded or checked in.

```python
from rl import parallel_env

env = parallel_env(players=2, frame_skip=15, mode=0, stage_id=1, weapons=[0, 0])
try:
    observations, infos = env.reset(seed=137)
    while env.agents:
        actions = {agent: env.action_space(agent).sample() for agent in env.agents}
        observations, rewards, terminated, truncated, infos = env.step(actions)
    observations, infos = env.reset()  # New room, processes and save copies.
finally:
    env.close()
```

Use `players=8` for 4v4. Team 0 contains the first half of agents, team 1 the second half. Mode indexes, stage IDs and weapon IDs follow the local M5 catalogs. `reset(options={"mode": 0, "stage_id": 1, "weapons": [...]})` selects that episode's configuration. Reset reuses M5's controller routes for startup, room configuration, weapon selection and teams. It launches fresh isolated processes after settlement; it does not navigate the same-process rematch UI. Reset during an active match raises an error; explicit `close()` cancels it.

All agents use the same action and observation spaces. Inspect them through `env.action_space(agent)` and `env.observation_space(agent)`.

| Observation | Shape / units | Source and availability |
|---|---|---|
| `pixels` | uint8 [72,128,3], RGB | Area average of the native 1280×720 crop; game texture readback with GPU completion, including headless. |
| `frame`, `phase` | int64 [1]; integer 0..3 | Completed presents; phase 0 before game, 1 InGame, 2 ResultJudge, 3 ResultWinners. |
| `position`, `heading` | float32 [3] in [-256,256]; [1] radians in [-pi,pi] | Recent own-player packet; body heading from the forward unit vector, 0 toward +Z and positive toward +X. Separate from camera yaw. |
| `hp`, `ink`, `special` | float32 [1], fraction [0,1] | Own packet. HP uses native 1000 units; special has 1% precision. HP was independently compared with live PlayerDamage through damage/recovery. |
| `remaining_time` | float32 [1], seconds [0,600] | Live timer HUD, verified native scale 60 units/second. |
| `self_slot`, `self_slot_valid` | integer 0..7 or unknown sentinel 8; bit | Native player identity obtained during own-player update. Distinct from agent order. |
| `alive`, `alive_valid` | bit; bit | Own native public HUD Normal/Down, independent of HP. Positive HP can coexist with Down. |
| `hud_status`, `hud_valid` | [8] Normal=0, Down=1, unavailable=2; [8] bits | Each observer's own public top-player HUD. No hidden opponent position or HP is merged. |
| `hud_special_ready` | [8] bits | Public HUD special-ready indicator; valid only with the corresponding `hud_valid`. |
| `hud_team`, `hud_weapon`, `team` | [8] team IDs / weapon IDs; own team 0/1 | Configured public lobby metadata joined by verified native slots; unknown slot metadata is -1. |
| `hud_downs`, `hud_counter_valid` | int64 [8] cumulative events; [8] bits | Observed Normal→Down transitions. Includes environmental deaths, without last-hit attribution. |
| `score`, `score_units`, `score_valid` | float32 [2]; 0 unknown / 1 percentage points / 2 rule counts; bit | Native final text formatter, own/enemy order. Result values remain through Winners and clear on a new match. |
| `turf_ratio`, `turf_valid` | float32 [2], fraction [0,1]; bit | Final Turf percentages divided by 100. No live paint-map coverage is provided. |

Own packet fields have separate `<field>_valid` bits. They are copied during a live native encoder call (about 10 Hz), not newly sampled from physics every render frame. Own packet, HUD states and timer expire after 120 presents and are masked outside InGame. Info includes `position_sample_frame`, `time_sample_frame`, per-slot `hud_sample_frame`, `score_sample_frame`, and the `hud_slot_agents` mapping. HUD event counters persist through results and clear on a new match. Invalid continuous values are zero with a false valid bit; zero alone must not be interpreted as a measured value.

The current runtime field evidence covers Turf War on Scorch Gorge. Other M5 modes/maps/weapons are configurable; non-Turf score formatting has static and production-transport coverage, and other-mode/overtime state readings still need their own real matches. Turf scores come from actual percentage text arguments, not bar areas normalized against each other. Actual per-agent `paint_points` and last-hit `kills` are unavailable.

| Action | Definition |
|---|---|
| `sticks` | float32 [4] in [-1,1]: left X/Y, right X/Y. |
| `gyro` | float32 [3] angular rates in turns/second in [-1,1]. |
| `buttons` | Six bits: ZR fire, ZL swim, R subweapon, RS special, B jump, Y camera reset. |

Every process receives its command before any acknowledgement is awaited. Invalid actions are rejected before any process advances. `step` applies the next action and advances exactly `frame_skip` completed native presents. The first HID read in each frame latches the action; subsequent SDK queries return it unchanged. Presents without HID reads count normally, with per-step info `frames_without_input`. Backward frame numbers or reads beyond the budget are rejected; concurrent polling at the paused budget endpoint waits for the next STEP. `input_repeats` counts normal same-frame repeated queries.

Peers share one POSIX mmap monotonic clock. It runs while frames execute and while faster peers wait, pauses once all ACKs arrive, and resumes before the next command batch. Policy waiting is deducted once for every peer. `guest_time_ns` is diagnostic per-ACK time and `barrier_guest_time_ns` is the common paused time. Exact present counting does not promise a fixed 60 Hz physics tick, deterministic PIA scheduling or reproducible simulation. Setup uses the original M5 clock until RL attaches.

Agents terminate individually at ResultJudge and leave `env.agents`; submit actions only for remaining agents. Retired processes continue advancing with neutral input. `env.process_infos` contains every process ACK. After all agents terminate, `advance_settlement()` can advance neutral result animations until every process reports ResultWinners. A timeout truncates remaining agents and permits reset.

`turf_kill_reward` is the default adjustable example. It adds `0.001 × positive special-charge percentage-point gain` as painting shaping and one per newly observed public enemy Down event. Charge gain is not exact painted area; enemy Down includes environmental deaths without personal kill attribution. Ally downs are excluded and unavailable signals give zero. If verified `paint_points` / `kills` are supplied to the helper, it uses their positive deltas instead. Pass `reward_fn=None` for zero reward or a custom `(previous_observation, current_observation) -> float` callable.

The wire protocol uses an AF_UNIX mode-0600 stream: `STEP sequence frames buttons_hex lx ly rx ry gx gy gz\n`, followed by one JSON metadata line and exactly 27,648 RGB bytes in the response. Stick command integers are in [-32767,32767]. The initial response has request/advanced 0. `RELEASE\n` releases control. A process never removes another environment's existing endpoint. `rl/clock.py` builds `tools/rl_clock.c` into ignored `work/build/` and passes `DM_RL_CLOCK_FILE` to every host. IPC uses POSIX files, mmap and sockets; clock code supports macOS and Linux. Standalone sockets without the shared file use the single-peer pause fallback and do not coordinate multiple agents. No Nintendo or OS IP network is used.

Run acceptance with:

```sh
bash tests/run_all.sh --milestone m6 --players 2 --timeout 2400
.venv/bin/python tests/test_m6_combat.py --reset-check
bash tests/run_all.sh --milestone m6 --players 8 --timeout 7200
```

The two-player main test runs one random match through both Winners, then resets into a second match for ten steps. It checks varying frame skips/policy delays, pixels against an idle baseline, own movement/heading, ink use/recovery and observation spaces. The longer combat test verifies gyro, painting/special charge, HP damage/recovery, native HUD Down and final observer-relative percentages; `--reset-check` adds a fresh second match. Optional `--inspect-results` releases RL only after every agent terminates, then uses M5's menu driver to inspect later UI. It never sends actions to retired STEP agents. `test_m6_fields.py` is a shorter heading/time test; `--survey` stores development candidates only in ignored work/ logs.

M6-B passed 447 synchronized first-match steps plus ten after reset. The expanded HUD/score regression passed 426 first-match steps plus ten after reset, four graceful exits and no new swapouts. Both native slots were public to both observers; both had one Down event, including positive-HP Down samples. Final Turf scores were [4.0,2.0] and [2.0,4.0]. Missing-input presents are covered by the production fixture; no missing-input frame was observed in the M6-B real match. The separate eight-player formal run passed 186 synchronized steps through all native Winners, with all eight public HUD slots valid, matching own/enemy result scores [4.4,4.0] / [4.0,4.4], eight graceful exits and no new swapouts. Artifacts, pixels and independent save copies remain under ignored `work/tests/m6-*`.
