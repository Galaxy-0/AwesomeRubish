# A5 tournament runner (native acceptance pending)

```sh
bash tests/run_all.sh --milestone a5 --games 4 --parallel 4
bash tests/run_all.sh --milestone a5 --games 100 --parallel 4 --fallback-three --resume arena/results/a5-partial-20261019.json
```

The four-game smoke phase does not sign A5. The formal gate requires 100 valid
native games, all reaching Winners with both observers agreeing on the winner,
and void/(valid+void) <= 10%. Four concurrent 1v1 rooms (eight hosts) are the
default. A documented three-room fallback is authorized for excessive voids.
With `--fallback-three`, after at least 12 settled attempts a four-room void
rate above 10% stops new submissions while current rooms finish; remaining
fixtures resume in three rooms. `four_room_comparison` retains separate
statistics for the first parallel setting. Already valid fixtures are never
rerun; each segment records its room count and native overlap evidence.

Every adjacent logical fixture pair exchanges policy roles/teams/spawn sides
on the same map; pairs cycle through the three selected maps. Each policy
retains its declared loadout on either side. Each attempt uses fresh isolated
processes/save copies. Only rush and high-ground weak examples are provided.

A native `FATAL RL_STALL` or peer winner disagreement makes an attempt void.
Its owned room is cleaned
and the same logical map/role fixture is retried in a new attempt directory.
Other rooms continue. Arbitrary policy, integrity or setup errors are not
silently voided. Cleanup errors from the expected watchdog SIGABRT are retained.
Attempts are stored as `round-NNN-attempt-NNN`; only one successful attempt per
logical fixture counts. Above the feasible void budget, current rooms drain
before stopping. Voids remain outside the win/loss/draw denominator.

Raw game data stay under ignored `work/arena/tournament-*`. `native-barriers.jsonl`
contains referee metadata at synchronized ACKs, with actual native sample
frames. `inputs-per-present.jsonl` records exact held inputs for each present
interval. Positions are not interpolated into invented per-present state.
Separate policy allowlist observations/actions, periodic, Down-event and
Winners images (128x72) are retained. Policy/runtime, public atlas/visibility
hashes and per-session resource/cleanup evidence accompany each run.

Victory requires the two native observer-local score pairs to name the same
winner (or both a draw), reversing peer one's own/enemy order. The score is
their arithmetic mean. Both raw pairs, aligned differences and observer winners
are retained. A maximum difference strictly above 2 percentage points adds
`suspect` but still counts if winners agree. Suspect rate uses valid games;
void rate uses valid+void attempts. Small score differences never cancel
other rooms. Temporary 1v1 metrics use each observer's
own HUD enemy/self Down counters, including unknown causes. Position-classified
falls below the playable floor or outside static bounds are listed separately
with actual classification positions. Unknown causes stay unknown. No attacker
or weapon attribution is synthesized; A3b paint/knockdowns remain unknown.
Final Turf percentages are settlement values, not live world paint coverage.

Statistics use two-sided 95% Clopper-Pearson exact binomial intervals on decided
games, with draws separate. Superiority requires a lower bound > 0.5; 60/100
has lower bound about 0.4972 and 61/100 about 0.5073. `statistics.by_policy`
reports HUD down/environment subsets, native score distributions and valid-game
wall/controlled durations. HUD non-environment subsets are not asserted to be
exact last-hit kills. Tournament elapsed wall time and void rate are separate.

`concurrency_windows` uses controlled start to the last successful native ACK,
with distinct host PIDs (eight for four rooms, six for three). A stalled room's
watchdog delay cannot inflate the windows. Merely selecting workers does not
satisfy the actual concurrent-room check. Partial runs are not A5 acceptance.

`--resume` validates policy hashes, paired fixture identities, evidence hashes
and immutable native/skill/map runtime hashes. Completed fixtures are excluded
before submission. Cancelled attempts remain separately audited. Wall time
sums active run segments, excluding the human pause between sessions.
`arena/results/` contains numeric summaries and provenance hashes only.
The original 32-game result plus round-032 was reconciled from native traces
without modifying any old result file:

```sh
.venv/bin/python -m arena.checkpoint --legacy work/arena/tournament-20261019-021200-165802/result.json --out arena/results/a5-partial-20261019.json
```
