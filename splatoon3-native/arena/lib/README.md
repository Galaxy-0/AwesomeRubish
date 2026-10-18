# Public map and control library (A4 accepted)

Policy workers import `atlas` and `skills` directly. These modules use the
allowlisted policy JSON, public static navigation and ordinary controller input.
They have no native sockets, referee accessor or live opponent-state reader.

```python
from atlas import MapAtlas
from skills import Skills

# Instantiate once for the observation's public stage_id.
controller = Skills(MapAtlas.load(obs['stage_id']))
result = controller.move_to(obs, controller.objective())
return result.action
```

`Skills.move_to(obs, point)` follows a static directed route. `swim_to` uses
potential-swim surfaces and explicit painting, then the own submerged signal;
it cannot infer current ink ahead. Both return `SkillResult(action, done, status)`
and try one B jump after `stall_frames` without horizontal progress. If that
fails, the current directed edge is blocked temporarily (1800 frames) and the
route is replanned, at most three times before `blocked`. Vertical jumping in
place does not reset horizontal progress. `events` retains actual position,
edge, jump and replan details. Intermediate waypoints require .24 horizontal
radius and .3 height agreement; nearby bends slow with dominant-axis scaling (.65 versus .85, vector caps .85/.95)
so diagonal components remain effective in the native input range. A new target replans. `aim_at(obs, point)` rotates without walking and reports `done`
when the own view feedback aligns. `ink_at` aims and fires while aligned; its
`done` means aligned, not proof that a remote surface was painted. The caller
chooses the explicit frame budget. Low ink requests ZL refill. Missing/stale
own feedback or death returns neutral `unavailable`.

Coordinates are world (X,Y,Z), body heading and own view yaw are radians, with
zero toward +Z. `view_pitch` retains the native own-packet scalar. Its control
calibration is part of A4 native acceptance; the geometric visibility filter
continues using fixed eye heights and body heading. `objective()` returns the
experimental central Turf reference, not a game objective entity.

`MapAtlas.region(name)` provides center, west_lane, east_lane, alpha_base,
bravo_base and central_high. These are experimental geometry labels, not
community callouts. Launch/landing spawn locators and ground candidates are
separate. Center/high candidates must be graph-reachable from both spawn areas.

Build with `.venv/bin/python tools/build_arena_maps.py` after the local collision
extraction in `tools/stage_collision.py`. All generated navigation, collision
and source assets remain ignored under `work/arena/maps`. The policy sandbox
grants only the three generated navigation JSON files, not raw collision,
source assets, host logs or match truth. Static omissions and conservative
height/rise/drop/radius limits are recorded in each atlas. Current native ink,
wall swimming and moving-object routes are not inferred from that static graph.

Run `bash tests/run_all.sh --milestone a4` for the full fresh native gate,
including the deferred A1 damage comparison. Current acceptance evidence is in
`notes/PROGRESS.md`; unit/controller and graph checks alone do not accept A4.

The accepted A4 partial (`7e2ecd7`) contains the first-map skills and A1 damage
proof (both continuous/paused lost 0.550000012 HP in 1.0 HUD second). The full A4 gate passed on 2026-10-19: ten of ten preset native routes arrived
on each of the three maps, plus native aim/ink/submerged feedback. Two Yunohana
and one Yagara cases reached their goals after live jump/block/replan recovery.
The regression requirement remains at least 90% arrival per map.
Misses retain position/recovery details. Foot/knee/body lanes and cross-sections
approximate a capsule of radius .3; the conservative step threshold is .2.
Bigger discontinuities need a separately checked jump arc or are omitted.
Continuous ramps follow sampled ground support. These are approximations to
be validated by the route suite, not a complete native physics implementation.

A same-layer A* start anchor within .75 is replaced in the physical polyline by
the measured foot position; intermediate corners still require their own tight
arrival. Central lane/high labels require a return path to the central component.
One-way sinks remain in the complete static graph, without claiming wall-ink
climbing support. The accepted proof and earlier failure records are in PROGRESS.
