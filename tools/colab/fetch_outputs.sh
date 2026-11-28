#!/bin/bash
# Local: download a finished run from the Colab VM.
#   bash fetch_outputs.sh SESSION RUN OUT_DIR
# Gets ltx_<RUN>_00001-audio.mp4 (video + LTX's generated audio) as OUT_DIR/<RUN>_with_audio.mp4,
# writes OUT_DIR/<RUN>.mp4 without the audio (stream copy), and the run record job_<RUN>.json.
# The output name is the VHS_VideoCombine prefix (ltx_<RUN>) + _00001; a second run of the same
# graph writes _00002: list /content/ComfyUI/output with `colab ls` if the download fails.
set -euo pipefail
[ $# -eq 3 ] || { sed -n 2,7p "$0"; exit 2; }
S=$1 RUN=$2 OUT=$3
mkdir -p "$OUT"
timeout 300 colab download -s "$S" "/content/ComfyUI/output/ltx_${RUN}_00001-audio.mp4" "$OUT/${RUN}_with_audio.mp4"
ffmpeg -v error -y -i "$OUT/${RUN}_with_audio.mp4" -an -c copy "$OUT/${RUN}.mp4"
timeout 120 colab download -s "$S" "/content/job_${RUN}.json" "$OUT/job_${RUN}.json"
python3 -c "import json,sys; d=json.load(open(sys.argv[1], encoding='utf-8')); print(d['run'], d['status'].get('status_str'), d['wall_s'], 's, peak', d['peak_vram_mib_nvidia_smi'], 'MiB')" "$OUT/job_${RUN}.json"
