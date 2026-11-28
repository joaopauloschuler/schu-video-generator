#!/bin/bash
# Local: check that each Hugging Face repo the LTX cookbook uses is public and ungated (no login needed),
# and print its current commit (compare with the cookbook's tables, section 4) and the sizes of the files used.
#   bash check_hf.sh            the LTX-2.3 repos
#   bash check_hf.sh --image    also the image models for the photoreal first frame (cookbook section 4.1)
# curl -L: a renamed repo answers with a redirect ("Temporary Redirect"), not JSON.
set -uo pipefail
api() { curl -sL "https://huggingface.co/api/models/$1$2"; }
repos=(unsloth/LTX-2.3-GGUF Lightricks/LTX-2.3-22b-IC-LoRA-Union-Control Comfy-Org/ltx-2 Comfy-Org/ltx-2.3 Lightricks/LTX-2.3
  Comfy-Org/Frame-Interpolation)
IMAGE=0; [ "${1:-}" = --image ] && IMAGE=1
[ $IMAGE = 1 ] && repos+=(unsloth/Qwen-Image-Edit-2511-GGUF lightx2v/Qwen-Image-Edit-2511-Lightning
  Comfy-Org/Qwen-Image Comfy-Org/Z-Image-Turbo alibaba-pai/Z-Image-Turbo-Fun-Controlnet-Union-2.1)
for repo in "${repos[@]}"; do
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
sizes Comfy-Org/ltx-2.3 split_files/loras/ltx-2.3-22b-ic-lora-ingredients-0.9.safetensors
sizes Comfy-Org/Frame-Interpolation frame_interpolation/rife_v4.26.safetensors
if [ $IMAGE = 1 ]; then
  sizes unsloth/Qwen-Image-Edit-2511-GGUF qwen-image-edit-2511-Q4_K_M.gguf
  sizes lightx2v/Qwen-Image-Edit-2511-Lightning Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors
  sizes Comfy-Org/Qwen-Image split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors
  sizes Comfy-Org/Qwen-Image split_files/vae/qwen_image_vae.safetensors
  sizes Comfy-Org/Z-Image-Turbo split_files/diffusion_models/z_image_turbo_bf16.safetensors
  sizes Comfy-Org/Z-Image-Turbo split_files/text_encoders/qwen_3_4b.safetensors
  sizes Comfy-Org/Z-Image-Turbo split_files/vae/ae.safetensors
  sizes alibaba-pai/Z-Image-Turbo-Fun-Controlnet-Union-2.1 Z-Image-Turbo-Fun-Controlnet-Union-2.1-8steps.safetensors
fi
