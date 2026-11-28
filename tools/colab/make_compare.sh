#!/bin/bash
# Local: a labelled grid of clips, played in step (each panel 640x340 at 24 fps).
#   bash make_compare.sh OUT.mp4 COLUMNS "label 1=clip1.mp4" "label 2=clip2.mp4" ...
# e.g.  bash make_compare.sh compare.mp4 4 "CG render=inputs/render_121_960x512.mp4" \
#         "depth + first frame=out/depth.mp4" "canny, no first frame=out/canny_noff.mp4"
# Missing clips are skipped; the last row may be short. Labels must not contain ' or : or =.
set -euo pipefail
[ $# -ge 3 ] || { sed -n 2,6p "$0"; exit 2; }
OUT=$1 COLS=$2; shift 2
FONT=${FONT:-/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf}
args=(); fc=""; layout=(); k=0
for pair in "$@"; do
  label=${pair%%=*} file=${pair#*=}
  [ -f "$file" ] || { echo "skip (missing): $file" >&2; continue; }
  args+=(-i "$file")
  fc+="[$k:v]scale=640:340,setsar=1,fps=24,drawtext=fontfile=$FONT:text='$label':x=8:y=8:fontsize=18:fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=5[v$k];"
  layout+=("$(( (k % COLS) * 640 ))_$(( (k / COLS) * 340 ))")
  k=$((k + 1))
done
[ "$k" -gt 0 ] || { echo "no clips" >&2; exit 1; }
if [ "$k" -eq 1 ]; then
  fc+="[v0]null[out]"
else
  ins=""; for ((i = 0; i < k; i++)); do ins+="[v$i]"; done
  fc+="${ins}xstack=inputs=$k:layout=$(IFS='|'; echo "${layout[*]}"):fill=black[out]"
fi
ffmpeg -v error -y "${args[@]}" -filter_complex "$fc" -map "[out]" -shortest \
  -c:v libx264 -crf 18 -pix_fmt yuv420p "$OUT"
echo "wrote $OUT ($k clips)"
