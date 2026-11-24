#!/bin/bash
# Local: make LTX-ready inputs from a vidgen shot's guide files.
#   bash prepare_inputs.sh RENDER.mp4 DEPTH.mp4 FIRST_FRAME.png OUT_DIR [W H FRAMES FPS]
# RENDER = the shot's guide.final.mp4, DEPTH = its guide.depth.mp4 (same frames and size),
# FIRST_FRAME = its first_frame.png. Defaults: 960 512 121 24.
# LTX-2.3 wants 8k+1 frames; the ref0.5 IC-LoRA wants W and H multiples of 64.
# The frames are centre-cropped (no scaling) to W x H and cut to the first FRAMES frames.
# Writes OUT_DIR/render_<F>_<W>x<H>.mp4, depth_<F>_<W>x<H>.mp4, first_frame_<W>x<H>.png.
set -euo pipefail
[ $# -ge 4 ] || { sed -n 2,8p "$0"; exit 2; }
RENDER=$1 DEPTH=$2 FIRST=$3 OUT=$4
W=${5:-960} H=${6:-512} F=${7:-121} FPS=${8:-24}
(( W % 64 == 0 && H % 64 == 0 )) || { echo "W and H must be multiples of 64" >&2; exit 2; }
(( (F - 1) % 8 == 0 )) || { echo "FRAMES must be 8k+1 (121, 97, 73 ...)" >&2; exit 2; }
mkdir -p "$OUT"
CROP="crop=$W:$H:(in_w-$W)/2:(in_h-$H)/2"
for pair in "render:$RENDER" "depth:$DEPTH"; do
  name=${pair%%:*} src=${pair#*:}
  ffmpeg -v error -y -i "$src" -vf "$CROP" -frames:v "$F" -an \
    -c:v libx264 -crf 12 -pix_fmt yuv420p -r "$FPS" "$OUT/${name}_${F}_${W}x${H}.mp4"
done
ffmpeg -v error -y -i "$FIRST" -vf "$CROP" "$OUT/first_frame_${W}x${H}.png"
n=$(ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames \
    -of csv=p=0 "$OUT/render_${F}_${W}x${H}.mp4")
echo "wrote $OUT (render has $n frames; want $F)"
