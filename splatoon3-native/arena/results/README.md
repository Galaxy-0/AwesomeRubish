# Numeric tournament checkpoints

These JSON files contain derived per-game results, observer-local score pairs,
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
