#!/bin/bash
# Local: check that each Hugging Face repo the HOWTO uses is public and ungated (no login needed),
# and print its current commit (compare with the HOWTO's table) and the sizes of the files used.
#   bash check_hf.sh
set -uo pipefail
api() { curl -s "https://huggingface.co/api/models/$1$2"; }
for repo in unsloth/LTX-2.3-GGUF Lightricks/LTX-2.3-22b-IC-LoRA-Union-Control Comfy-Org/ltx-2 Lightricks/LTX-2.3; do
  api "$repo" "" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f\"{d.get('id')}: gated={d.get('gated')} private={d.get('private')} sha={d.get('sha')}\")"
done
sizes() { # repo, then paths
  local repo=$1 dir; shift
  dir=$(dirname "$1"); [ "$dir" = . ] && dir=""
  api "$repo" "/tree/main${dir:+/$dir}" | python3 -c "
import json, sys
want = set(sys.argv[1:])
for f in json.load(sys.stdin):
    if f['path'] in want:
        print(f\"  {f['path']}: {f['size'] / 1e9:.2f} GB\")" "$@"
}
sizes unsloth/LTX-2.3-GGUF distilled-1.1/ltx-2.3-22b-distilled-1.1-Q5_K_M.gguf
sizes unsloth/LTX-2.3-GGUF vae/ltx-2.3-22b-distilled_video_vae.safetensors vae/ltx-2.3-22b-distilled_audio_vae.safetensors
sizes unsloth/LTX-2.3-GGUF text_encoders/ltx-2.3-22b-distilled_embeddings_connectors.safetensors
sizes Comfy-Org/ltx-2 split_files/text_encoders/gemma_3_12B_it_fp8_scaled.safetensors
sizes Lightricks/LTX-2.3-22b-IC-LoRA-Union-Control ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors
