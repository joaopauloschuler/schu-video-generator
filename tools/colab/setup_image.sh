#!/bin/bash
# Download the image models for the photoreal first frame and link them into ComfyUI.
# setup_session.py starts it detached through start_setup.py (--env SCRIPT=/content/setup_image.sh)
# beside setup.sh; it waits for setup.sh's ComfyUI clone before linking. Log
# /content/setup_image.log (### milestones); on success it writes /content/.vidgen_setup_image_done.
# Every repo is ungated (check_hf.sh --image). No Hugging Face login.
set -x
cd /content
T0=$(date +%s)
stamp() { echo "### $(date -u +%H:%M:%S) +$(( $(date +%s) - T0 ))s $*"; }
export HF_XET_HIGH_PERFORMANCE=1
dl() {
  local s=$(date +%s) rc
  hf download "$1" "$2" --local-dir "/content/hf/$1" >/dev/null 2>&1; rc=$?
  stamp "DL done $1/$2 in $(( $(date +%s) - s ))s rc=$rc"
}
# Qwen-Image-Edit-2511 (Q4_K_M GGUF) + 4-step Lightning LoRA + its text encoder and VAE
dl unsloth/Qwen-Image-Edit-2511-GGUF qwen-image-edit-2511-Q4_K_M.gguf
dl lightx2v/Qwen-Image-Edit-2511-Lightning Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors
dl Comfy-Org/Qwen-Image split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors
dl Comfy-Org/Qwen-Image split_files/vae/qwen_image_vae.safetensors
# Z-Image-Turbo (bf16) + Fun ControlNet Union 2.1 (canny / depth) + its text encoder and VAE
dl Comfy-Org/Z-Image-Turbo split_files/diffusion_models/z_image_turbo_bf16.safetensors
dl Comfy-Org/Z-Image-Turbo split_files/text_encoders/qwen_3_4b.safetensors
dl Comfy-Org/Z-Image-Turbo split_files/vae/ae.safetensors
dl alibaba-pai/Z-Image-Turbo-Fun-Controlnet-Union-2.1 Z-Image-Turbo-Fun-Controlnet-Union-2.1-8steps.safetensors

stamp "waiting for ComfyUI (setup.sh clones it)"
while [ ! -f /content/ComfyUI/main.py ]; do sleep 5; done
stamp "link models into ComfyUI/models"
M=/content/ComfyUI/models
H=/content/hf
mkdir -p $M/unet $M/loras $M/vae $M/text_encoders $M/diffusion_models $M/model_patches
ln -sf $H/unsloth/Qwen-Image-Edit-2511-GGUF/qwen-image-edit-2511-Q4_K_M.gguf $M/unet/
ln -sf $H/lightx2v/Qwen-Image-Edit-2511-Lightning/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors $M/loras/
ln -sf $H/Comfy-Org/Qwen-Image/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors $M/text_encoders/
ln -sf $H/Comfy-Org/Qwen-Image/split_files/vae/qwen_image_vae.safetensors $M/vae/
ln -sf $H/Comfy-Org/Z-Image-Turbo/split_files/diffusion_models/z_image_turbo_bf16.safetensors $M/diffusion_models/
ln -sf $H/Comfy-Org/Z-Image-Turbo/split_files/text_encoders/qwen_3_4b.safetensors $M/text_encoders/
ln -sf $H/Comfy-Org/Z-Image-Turbo/split_files/vae/ae.safetensors $M/vae/
ln -sf $H/alibaba-pai/Z-Image-Turbo-Fun-Controlnet-Union-2.1/Z-Image-Turbo-Fun-Controlnet-Union-2.1-8steps.safetensors $M/model_patches/
ls -laL $M/unet $M/loras $M/vae $M/text_encoders $M/diffusion_models $M/model_patches
if python /content/vm_state.py image; then
  touch /content/.vidgen_setup_image_done
  stamp "IMAGE SETUP DONE"
else
  stamp "IMAGE SETUP FAILED: files missing (MISSING lines above)"
  exit 1
fi
