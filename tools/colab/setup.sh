#!/bin/bash
# Install ComfyUI + custom nodes and download the LTX-2.3 weights on a Colab VM.
# setup_session.py uploads it with vm_state.py and starts it detached through start_setup.py;
# progress goes to /content/setup.log (lines starting with ### are the milestones) and
# /content/download.log. On success it writes /content/.vidgen_setup_ltx_done.
# Tested 2026-11-24 on a Colab L4 (Python 3.13, torch 2.14.1+cu130 preinstalled and kept).
# PIN=1 (default) checks out the commits that were tested; PIN=0 keeps the latest of each repo.
# No Hugging Face login: every repo below is ungated (check with check_hf.sh first).
# Safe to run again: existing clones are kept and hf download skips finished files.
set -x
cd /content
T0=$(date +%s)
stamp() { echo "### $(date -u +%H:%M:%S) +$(( $(date +%s) - T0 ))s $*"; }

stamp "python/torch before install"
python -V
python -c "import torch,sys;print('torch',torch.__version__,'cuda',torch.version.cuda,torch.cuda.get_device_name(0))"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
df -h /content | tail -1
free -g | head -2

stamp "pip: huggingface_hub (hf CLI + xet)"
pip install -q -U "huggingface_hub[hf_xet]" hf_transfer

# ---- downloads run in the background while ComfyUI installs ----
mkdir -p /content/hf
(
  export HF_XET_HIGH_PERFORMANCE=1
  D0=$(date +%s)
  dl() {
    local s=$(date +%s) rc
    hf download "$1" "$2" --local-dir "/content/hf/$1" >/dev/null 2>&1; rc=$?
    echo "### DL done $1/$2 in $(( $(date +%s) - s ))s rc=$rc"
  }
  dl Lightricks/LTX-2.3-22b-IC-LoRA-Union-Control ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors
  dl unsloth/LTX-2.3-GGUF vae/ltx-2.3-22b-distilled_video_vae.safetensors
  dl unsloth/LTX-2.3-GGUF vae/ltx-2.3-22b-distilled_audio_vae.safetensors
  dl unsloth/LTX-2.3-GGUF text_encoders/ltx-2.3-22b-distilled_embeddings_connectors.safetensors
  dl unsloth/LTX-2.3-GGUF distilled-1.1/ltx-2.3-22b-distilled-1.1-Q5_K_M.gguf
  dl Comfy-Org/ltx-2 split_files/text_encoders/gemma_3_12B_it_fp8_scaled.safetensors
  echo "### ALL DOWNLOADS DONE in $(( $(date +%s) - D0 ))s"
) > /content/download.log 2>&1 &
DLPID=$!

stamp "clone ComfyUI + custom nodes"
clone() { [ -d "$2/.git" ] || git clone -q "https://github.com/$1.git" "$2"; }
clone Comfy-Org/ComfyUI /content/ComfyUI
for repo in Lightricks/ComfyUI-LTXVideo city96/ComfyUI-GGUF Kosinkadink/ComfyUI-VideoHelperSuite kijai/ComfyUI-KJNodes; do
  clone "$repo" "/content/ComfyUI/custom_nodes/${repo#*/}"
done
cd /content/ComfyUI
if [ "${PIN:-1}" = "1" ]; then
  git checkout -q da8bd08e48deee74d9f6c3bc00aed365b00ec209
  git -C custom_nodes/ComfyUI-LTXVideo checkout -q ced6bad92b82f90028e1e1fd5a37527302550fc5
  git -C custom_nodes/ComfyUI-GGUF checkout -q 6ea2651e7df66d7585f6ffee804b20e92fb38b8a
  git -C custom_nodes/ComfyUI-VideoHelperSuite checkout -q 4d907bee61e92c2e65af3bd6383a4e4d356126d1
  git -C custom_nodes/ComfyUI-KJNodes checkout -q 187868f53a7d9df007dbfe85891dab41453f7933
fi
for d in . custom_nodes/*/; do echo "COMMIT $d $(git -C $d rev-parse HEAD) $(git -C $d log -1 --format=%cd --date=iso)"; done

stamp "pip install ComfyUI requirements (torch already present; keep it)"
grep -v -E '^(torch|torchvision|torchaudio)([<>=~ ]|$)' requirements.txt > /content/req_no_torch.txt
pip install -q -r /content/req_no_torch.txt
for d in custom_nodes/*/; do
  if [ -f "$d/requirements.txt" ]; then
    stamp "pip install $d"
    grep -v -E '^(torch|torchvision|torchaudio)([<>=~ ]|$)' "$d/requirements.txt" > /tmp/r.txt
    pip install -q -r /tmp/r.txt
  fi
done
python -c "import torch;print('torch after',torch.__version__)"
pip list 2>/dev/null | grep -i -E '^(torch|torchvision|torchaudio|gguf|transformers|comfy|av|opencv|numpy|safetensors|huggingface)'

stamp "waiting for downloads"
wait $DLPID
cat /content/download.log

stamp "link models into ComfyUI/models"
M=/content/ComfyUI/models
mkdir -p $M/unet $M/loras $M/vae $M/text_encoders $M/diffusion_models
ln -sf /content/hf/unsloth/LTX-2.3-GGUF/distilled-1.1/ltx-2.3-22b-distilled-1.1-Q5_K_M.gguf $M/unet/
ln -sf /content/hf/unsloth/LTX-2.3-GGUF/vae/ltx-2.3-22b-distilled_video_vae.safetensors $M/vae/
ln -sf /content/hf/unsloth/LTX-2.3-GGUF/vae/ltx-2.3-22b-distilled_audio_vae.safetensors $M/vae/
ln -sf /content/hf/unsloth/LTX-2.3-GGUF/text_encoders/ltx-2.3-22b-distilled_embeddings_connectors.safetensors $M/text_encoders/
ln -sf /content/hf/Comfy-Org/ltx-2/split_files/text_encoders/gemma_3_12B_it_fp8_scaled.safetensors $M/text_encoders/
ln -sf /content/hf/Lightricks/LTX-2.3-22b-IC-LoRA-Union-Control/ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors $M/loras/
ls -laL $M/unet $M/loras $M/vae $M/text_encoders
if python /content/vm_state.py ltx; then
  touch /content/.vidgen_setup_ltx_done
  stamp "SETUP DONE"
else
  stamp "SETUP FAILED: files missing (MISSING lines above)"
  exit 1
fi
