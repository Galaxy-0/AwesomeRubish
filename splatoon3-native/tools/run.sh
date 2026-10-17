#!/bin/bash
# run.sh <name> [secs] [VAR=val...]: boot and print the interesting tail (red lines, abort/crash with symbolized backtrace)
R="$(cd "$(dirname "$0")/.." && pwd)"; "$R/tools/boot.sh" "$@" >/dev/null 2>&1; f="$R/work/run/$1.log"
LC_ALL=C grep -a "【红】" "$f" | sort | uniq -c | sort -rn | head -25 | cut -c1-200
grep -av "绑到先装\|^\[dm\]   \|【红】\|CPU 写贴图\|^x[0-9]" "$f" | sed -n '/nnMain/,$p' | tail -${TAILN:-25} | cut -c1-220
bt=$(grep -a "^\[dm\] bt:" "$f" | tail -1 | sed 's/^\[dm\] bt: //'); [ -n "$bt" ] && "$R/.venv/bin/python" "$R/tools/nsosym.py" "$R/work/data/v720896/ExeFS" $(echo $bt | tr ' ' '\n' | grep -E '^(main|sdk)\+' | head -10)
