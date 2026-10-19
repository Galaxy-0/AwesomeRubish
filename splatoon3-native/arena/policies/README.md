# Two intentionally weak examples

`rush/` walks toward the central Turf reference and shoots at a visible opponent.
`high-ground/` walks to the experimental central high region and paints there.
Both use Splatana Stamper (8000), complete quick-super-jump gear, and only the
shared public library. They are plumbing examples; T1 supplies real strategies.

A policy directory contains `policy.py` with `act(obs) -> action`, and
`config.toml` with name, weapon=8000, step_frames (1..60), step_timeout (0..5s),
and all head/clothes/shoes main + three legal subskills. The coordinator reads
configuration. The worker sees only its own code, the public library/navigation,
and allowlisted policy JSON; its opponent's source and native sockets are denied.

`obs['own']` has own position/heading/HP/ink/form/submergence/sample frame and
own view feedback. Enemies have public identity/team/weapon/local HUD alive,
visible position/heading or last-seen memory. Unknown fields are `None`.
`stage_id` selects the public static atlas. No pixels, enemy HP/ink, private paint,
attribution or raw host metadata enter `act`.

Return a dictionary with sticks[4], gyro[3] in [-1,1], buttons[6] binary, in order
ZR, ZL, R, RS, B, Y. The action holds until that policy's next declared cadence.
The shared match step is the GCD of both cadences; policy wall time does not
advance fixed60 game time. Exceeding the declared deadline fails the match run
and retains diagnostics rather than inventing a native victory.

T1 authors can use separate private directories. The committed example sources
are public examples; worker sandboxing does not isolate other coding sessions'
filesystem access, which the T1 director must arrange separately.

A6 adds `own.special` as an optional own-only, fresh (at most 8 presents old)
HUD meter; missing/stale feedback stays `None`. `ControlProcess` is the typed
allowlist extension used by the coordinator. It adds no enemy state. Shared
`stamper` / `stamper_data` are public; use `step_frames=1` for their shortest
release boundaries and FastTurn. See [the skill guide](../lib/stamper.md).

`tests/benchmark_a6.py --policy <directory> --scenario stationary|lateral|approach`
runs a single-room black-box proficiency fixture with the declared gear/cadence.
Its fixed-position main-weapon scores include raw/executed inputs and sample
counts. Matching source/loadout/library/evaluator cards are included in each
new tournament report; absent or stale cards remain unavailable.
