# Public map and control library (A4 in progress)

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
and stop with `blocked` after bounded no-progress/total frame counts. A new
target replans. `aim_at(obs, point)` rotates without walking and reports `done`
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

The revised native gate passed all first-map skills and the deferred A1 damage
comparison: both continuous/paused trials lost 0.550000012 HP in 1.0 HUD second.
A4 is currently stopped, unaccepted, on a new District00 route obstruction.
The walk controller reaches about (-3.9, 8.38, -27.05) but cannot reach its next
waypoint (-5, 9, -27). Low foot-level collision segments are blocked while the
current high-plane edge test passes. Early corner advancement and rise/capsule
clearance remain hypotheses; see the PROGRESS blocker and ignored native trace.
Yagara native acceptance and the A5 tournament have not run. Guest waits have no
absolute wall deadline; the configurable 120-second no-progress watchdog excludes
policy pauses and passed the component regressions.
