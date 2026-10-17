#!/bin/bash
# Keep the gpt-6.1-sol session pushing GOAL.md: whenever it is not running, resume it with a nudge. Check every ${INTERVAL:-1200}s.
R="$(cd "$(dirname "$0")/.." && pwd)"; SID=${SID:?session id}; L="$R/work/codex"; n=1
while true; do
  if ! pgrep -f "codex exec.*$R" >/dev/null; then
    n=$((n+1)); echo "[$(date '+%F %T')] resume #$n" >> "$L/supervisor.log"
    if grep -q "ALL MILESTONES DONE" "$L/last.md" 2>/dev/null; then echo "done" >> "$L/supervisor.log"; exit 0; fi
    codex exec resume "$SID" -m gpt-6.1-sol -c model_reasoning_effort=high --dangerously-bypass-approvals-and-sandbox -o "$L/last.md" \
      "继续按 GOAL.md 推进当前里程碑。先看 notes/PROGRESS.md 和 git log 确认做到哪了；阶段性节点 commit + push。实在卡住按 GOAL.md 只读问 Astra。M6 全部完成时最后一句写 ALL MILESTONES DONE。" \
      > "$L/run$n.log" 2>&1
  fi
  sleep "${INTERVAL:-1200}"
done
