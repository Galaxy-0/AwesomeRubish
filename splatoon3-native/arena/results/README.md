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
