# Numeric tournament checkpoints

The `a5-*` JSON files contain derived per-game results, observer-local score pairs,
means/differences, HUD counter summaries, durations and provenance hashes.
They contain no game binaries/assets, collision meshes, raw player states or
screenshots. Original traces and pictures remain under ignored work/.

`a5-partial-20261019.json` preserves the original 32 valid games and reconciles
round-032 from both recorded native Winners using the approved winner-agreement
rule: 33 valid games, 0 void, 0 suspect; this is not A5 acceptance. Three old
cancelled attempts are audited separately. `--resume` validates immutable
runtime/evidence and policy hashes, then submits only missing logical fixtures.

`a5-paused-70-20261019.json` preserves the stopped 100-game run at 70 valid
games and 3 voids, including its original interrupted status. The revised A5
gate accepts at least 70 valid games with void/(valid+void) at most 10%.
`a5-accepted-70-20261019.json` is the separate acceptance audit: every round
lists the two observer-local score pairs, winning seat, `role_to_policy`,
winning policy and trace hash. It preserves the distinction between 38 wins
for player_1's seat and 61 wins for the high-ground policy after side swaps.

`proficiency/` contains the A6 black-box scorecards and readable tables for the
frozen R0 alpha/bravo revisions and public reference. Each card records declared
gear/cadence, fixture baseline poses and sample timestamps, actual distances,
HP/Down-derived metrics, input counts and provenance hashes. Raw per-present
policy/native traces and game screenshots remain ignored under `work/`.
Unsupported operations and right-censored times are explicit. The fixed-shooter
main-weapon fixture masks movement/sub/special input; these scores alone do not
establish the cause of a tournament win.

`a6-acceptance.json` indexes the hashed native research, operation dispositions,
three frozen scorecards, released T1 source and A1–A5 regression evidence.
`a6-native-20261019.json` is the passing complete gate, including independent
full/infinite test-host lifecycle audit. `a6-regression-20261019.json` records
fresh A1/A2/A3a gates, 30/30 A4 routes plus skills, the accepted A1 damage partial,
and strict accepted70 A5 audit plus two fresh swapped single-room games. It does
not claim a new 70-game run or a fresh paused/continuous damage comparison.
The default host hash is unchanged; the special-meter test binary is separate.
