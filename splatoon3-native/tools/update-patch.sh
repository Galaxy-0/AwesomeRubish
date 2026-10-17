#!/bin/bash
# Capture source/profile changes, excluding locally extracted shader tables.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
git -C "$root/upstream" diff --binary -- . \
    ':(exclude)dm/games/0100C2500FC20000/shader_*' \
    ':(exclude)dm/games/0100C2500FC20000/c1_full.tsv' \
    > "$root/patches/0001-splatoon3.diff"
git -C "$root/upstream" diff --check -- . \
    ':(exclude)dm/games/0100C2500FC20000/shader_*' \
    ':(exclude)dm/games/0100C2500FC20000/c1_full.tsv'
