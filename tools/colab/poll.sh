#!/bin/bash
# Local: one short look at the Colab VM (never run two at once: both lose their websocket).
#   bash poll.sh SESSION setup        install + download milestones
#   bash poll.sh SESSION comfy        is ComfyUI up (last log lines, GPU memory)
#   bash poll.sh SESSION job RUN      the result of start_job.py for RUN (empty until done)
# A "RuntimeError: Connection was lost." is the poll, not the job: wait and poll again.
set -uo pipefail
[ $# -ge 2 ] || { sed -n 2,6p "$0"; exit 2; }
S=$1 WHAT=$2 RUN=${3:-}
case $WHAT in
  setup) CMD='!grep "^###" /content/setup.log | tail -n 20; cat /content/download.log 2>/dev/null | grep "^###"' ;;
  comfy) CMD='!tail -n 5 /content/comfy.log; nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader' ;;
  job)   [ -n "$RUN" ] || { echo "job needs RUN" >&2; exit 2; }
         CMD="!cat /content/job_${RUN}.log /content/job_${RUN}.json 2>/dev/null | head -c 3000; echo; grep -E '[0-9]+/8 ' /content/comfy.log | tail -n 1 | tr '\\r' '\\n' | tail -n 1" ;;
  *) echo "unknown: $WHAT" >&2; exit 2 ;;
esac
echo "$CMD" | timeout 90 colab exec -s "$S"
