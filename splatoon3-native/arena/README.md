# Explainable arena — A3a accepted / deferred A3b

`referee.py` holds private match snapshots, paint and knockdown records.
`policy.py` defines an independent allowlisted observation schema and wire encoder.
`visibility.py` projects truth into that schema and maintains per-observer last-seen
memory. Hidden enemies have no current position, heading or sample timestamp;
enemy HP/ink, private paint and attribution never enter the policy schema.
`native_referee.py` joins each host's verified own position/heading/HP/ink/alive
into a private snapshot and converts each host's different startup frame offset
to a common controlled-frame count. Public enemy alive status is taken from
that observer's own HUD; private remote alive state cannot substitute for it.
Unmapped A3 fields remain unavailable.

Visibility requires a fresh referee-side geometric witness for that observer,
target, sample and match. `geometry.py` uses position + fixed human/squid eye
height, body-heading horizontal FOV/range and foot/waist/head collision segments;
one clear sample is enough. Stationary own-ink squid are hidden; movement
splashes and jumps are visible exceptions. Ninja Squid can suppress splashes.
The numerical defaults are in `VisionConfig`. Native Scorch Gorge screenshots
were checked for open/front, squid observer, back/return, wall, raised platform
and stationary submerged targets, plus jump/movement exceptions. This validates
the authorized geometric approximation, not pixel-exact game-camera reconstruction
or equivalent native scene coverage on all three maps.
Missing evidence hides the target. Unknown paint/attribution are `None`, distinct
from a measured empty grid/event list. Frames must be match-relative controlled
presents; native host frame counters have different startup offsets.

Run interface fixtures with `.venv/bin/python tests/test_a3_components.py`.
They test information leakage and memory behavior only. A3a covers geometric
visibility and the allowlisted subprocess boundary. A3b (live paint and attributed
deaths) is deferred until after A5. These private fields stay `None`; tests reject
fabricating them from HUD counts, final scores or configuration. The observed
paint atlas still needs a verified world mapping. Candidate directions are second
render-mesh UV mapping or empirical known-position ink calibration. Native death
network events remain the direction for attribution. A4/A5 do not wait on A3b.
`process.py` runs the independent `policy_worker.py` over bounded stdio,
with the policy wire encoder, no inherited native descriptors, and a macOS
sandbox denying private user/temp files, the opposing policy and all sockets.
Run `.venv/bin/python tests/test_a3_process.py` for actual subprocess denial and
deadline tests. The policy may read its own code, public skills and interpreter
runtime; this is not a claim to defend against OS vulnerabilities.
Do not pass the existing `rl/` observations or
`process_infos` directly to a strategy: that API is for the coordinator/referee.
`tools/stage_collision.py` builds the authorized static approximation from local
Turf Cmn/Pnt collision meshes and actor transforms, writing assets/manifests only
under `work/arena/maps`. Dynamic omissions are explicit in each manifest.
`tests/probe_a3_fields.py` records native field diagnostics in ignored
`work/` and always reports `full_a3_passed=false`.
`tests/analyze_a3_fields.py <result.json>` summarizes candidate bytes/probe hits;
`tests/probe_a3_replay.py <steps.jsonl>` checks the adapter against a real saved
trace. Both write diagnostic summaries under ignored `work/` and leave the full
A3 acceptance flag false.

`referee_api.py` separates coordinator-only `state()` from
`policy_observation(observer)`. The latter alone can enter `PolicyProcess.act`.
`tests/probe_a3_policy_replay.py <result.json>` checks this actual subprocess
path using recorded native scenes; it does not drive a complete policy match.
`bash tests/run_all.sh --milestone a3a` runs the fresh native geometry gate,
actual policy-process replay and explicit deferred-field unknown checks.
`--native-evidence` is diagnostic replay and cannot sign fresh acceptance.
The arena will use final scores for winners and observer HUD enemy Down counts
for 1v1; position-classified environmental deaths are recorded separately. These
counts are not the deferred native last-hit/weapon attribution.
