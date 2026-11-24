# RUNLOG - LTX-2.3 + IC-LoRA Union Control (depth / canny) on Colab L4, ComfyUI

Date: 2026-11-24 (UTC times below). Operator: Claude agent. Budget: L4 only, hard cap 4 h.
Goal: restyle the CG clip `render.mp4` (glider over sea) into real-looking footage with
LTX-2.3 (distilled 1.1, GGUF Q5_K_M) + `Lightricks/LTX-2.3-22b-IC-LoRA-Union-Control`, control = exact
three.js depth (run 1) and canny of the render (run 2).

## 0. Local recon (before any Colab time)

### HF repos (checked 2026-11-24 ~09:00 UTC via `https://huggingface.co/api/models/<repo>`) - all `gated: false`

| repo | sha | gated | file used | size |
|---|---|---|---|---|
| unsloth/LTX-2.3-GGUF | 96e8ed4925ead3db9ff4d0084f165ef6a74f28d0 | false | distilled-1.1/ltx-2.3-22b-distilled-1.1-Q5_K_M.gguf | 15.93 GB |
| " | " | " | vae/ltx-2.3-22b-distilled_video_vae.safetensors | 1.45 GB |
| " | " | " | vae/ltx-2.3-22b-distilled_audio_vae.safetensors | 0.36 GB |
| " | " | " | text_encoders/ltx-2.3-22b-distilled_embeddings_connectors.safetensors | 2.31 GB |
| Lightricks/LTX-2.3-22b-IC-LoRA-Union-Control | 20a580c8606c06a0988d40375a61309e0fe5893d | false | ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors | 0.654 GB |
| Comfy-Org/ltx-2 | ccde4ba417d7900669fd56dd292a883cee11ff37 | false | split_files/text_encoders/gemma_3_12B_it_fp8_scaled.safetensors | 13.2 GB |
| Lightricks/LTX-2.3 | c1521179de480464f366a98a9d9b2acc4cc097b9 | false | (not needed: no upscaler stage used) | - |

Notes:
- unsloth also has `distilled/` (v1.0) and dev GGUFs, and both `-dev_` and `-distilled_` VAE/connector files
  (same sizes). I used the `distilled_` VAE + connectors to match the distilled 1.1 transformer.
- Comfy-Org/ltx-2 also has `gemma_3_12B_it_fp4_mixed` (9.4 GB) and the full bf16 (24.4 GB).

### IC-LoRA model card (key facts)
- Union control: **Canny + Depth + Pose** in one LoRA. "Trained with downscaled reference latents by a factor of 2"
  -> `ref0.5` = the reference (control) video is used at **0.5x the output resolution**.
- In ComfyUI use **`LTXICLoRALoaderModelOnly`** (loads LoRA and outputs `latent_downscale_factor`) and
  **`LTXAddVideoICLoRAGuide`** (adds the downscaled control latent as a guide). Downscaling is done by the node:
  you feed the control at full output size.

### Official workflow `example_workflows/2.3/LTX-2.3_ICLoRA_Union_Control_Distilled.json` (UI format) - graph summary
- `CheckpointLoaderSimple(ltx-2.3-22b-dev.safetensors)` -> `LoraLoaderModelOnly(distilled-lora-384-1.1, 0.5)`
  -> `LTXICLoRALoaderModelOnly(ic-lora-union-control-ref0.5, strength 1)` -> `CFGGuider(cfg 1)`.
- Text: `LTXAVTextEncoderLoader(gemma, ckpt)` -> 2x `CLIPTextEncode` (negative: "pc game, console game, video game,
  cartoon, childish, ugly") -> `LTXVConditioning(frame_rate = video fps)`.
- Control video: `LoadVideo` -> `GetVideoComponents` -> `ResizeImageMaskNode(scale shorter dim 544)` ->
  annotator (`CannyEdgePreprocessor 92/200 @512`, or Video-Depth-Anything, or DWPose) ->
  `ResizeImageMaskNode(scale to multiple, multiple = latent_downscale_factor*32 = 64)` -> `GetImageSize` gives
  W/H/length for `EmptyLTXVLatentVideo` and `LTXVEmptyLatentAudio`.
  => output size must be a multiple of 64 because the guide is half size (544/2/32 is not whole). 960x544 is NOT ok.
- First frame: `LoadImage` -> resize longer side 1536 -> `LTXVImgToVideoConditionOnly(strength 1, bypass)`; the
  example has bypass=True (pure v2v/t2v).
- `LTXAddVideoICLoRAGuide` widgets `[0, 1, 1, 'disabled', False, 256, 64]` (names read from the node source on Colab, see below).
- Audio + video latents concatenated (`LTXVConcatAVLatent`), `SamplerCustomAdvanced` with `RandomNoise(42 fixed)`,
  `KSamplerSelect(euler_ancestral_cfg_pp)`, `ManualSigmas("1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0")` = 8 steps,
  then `LTXVSeparateAVLatent` -> `LTXVCropGuides` -> `LTXVTiledVAEDecode(2,2,6,...)` -> `CreateVideo` -> `SaveVideo`.
- Single stage, no upscaler.
- The unsloth GGUF repo's `unsloth_flowers.mp4` embeds a GGUF workflow: `UnetLoaderGGUF`, `VAELoaderKJ` (KJNodes)
  for both video and audio VAE from `models/vae`, `DualCLIPLoaderGGUF(gemma gguf, embeddings_connectors, type ltxv)`.
  I used that pattern for the loaders (with the safetensors fp8 gemma via core `DualCLIPLoader`).

### Input preparation (local, ffmpeg)
`depth.mp4`/`render.mp4` are 960x544, 127 frames. LTX needs 8k+1 frames and (for ref0.5) W,H multiples of 64:
```
for f in render depth; do ffmpeg -v error -y -i $f.mp4 -vf "crop=960:512:0:16" -frames:v 121 \
  -c:v libx264 -crf 12 -pix_fmt yuv420p -r 24 colab/inputs/${f}_121_960x512.mp4; done
ffmpeg -v error -y -i first_frame.png -vf "crop=960:512:0:16" colab/inputs/first_frame_960x512.png
```
=> 960x512 (centre crop, 16 px off top and bottom), 121 frames, 24 fps. Canny is made on Colab with OpenCV
(no cv2 locally).

## 1. Colab session
All scripts are in `ltx-test/colab/`. Commands are run from that folder.

### 1.1 Create the session
```
colab new -s ltx --gpu L4      # 09:03:31 -> FAILED after ~3 min: ColabRequestError ... /tun/m/assign?...&accelerator=L4: Service Unavailable
colab sessions                 # "No active sessions" -> nothing billed
colab new -s ltx --gpu L4      # 09:07:04 -> "Session READY" 09:08:41   <- billing starts here
```
Pitfall: the first L4 request returned HTTP 503 (capacity). A plain retry a minute later worked.

VM: Python 3.13.16, torch 2.14.1+cu130 (preinstalled, kept), CUDA 13.0, NVIDIA L4 23034 MiB, driver 580.82.07,
52 GB RAM, 236 GB disk.

### 1.2 Install + download (detached)
```
colab upload -s ltx setup.sh /content/setup.sh
for f in inputs/*; do colab upload -s ltx $f /content/$(basename $f); done
colab exec -s ltx -f start_setup.py          # Popen(bash setup.sh, start_new_session=True) -> /content/setup.log
echo '!grep "^###" /content/setup.log; cat /content/download.log' | colab exec -s ltx    # poll
```
`setup.sh`: `pip install -U "huggingface_hub[hf_xet]" hf_transfer`; downloads with `hf download <repo> <file> --local-dir
/content/hf/<repo>` (HF_XET_HIGH_PERFORMANCE=1) in a background subshell while ComfyUI installs; git clone ComfyUI +
4 custom nodes; `pip install -r requirements.txt` for each with torch/torchvision/torchaudio lines removed (keeps Colab's
CUDA torch); then symlinks the weights into `ComfyUI/models/{unet,loras,vae,text_encoders}`.

Timings (setup started 09:09:44):
- huggingface_hub upgrade: 2.4.0 (pip warns `datasets 4.8.5 requires huggingface-hub<2.0` - harmless here).
- ComfyUI + node requirements: 09:10:24 -> 09:11:36 (~70 s). torch unchanged (2.14.1+cu130); torchvision 0.29.1, torchaudio 2.11.0.
- Downloads (all from Colab, no login): IC-LoRA 0.65 GB 5 s; video VAE 1.45 GB 5 s; audio VAE 4 s; connectors 2.3 GB 9 s;
  **GGUF Q5_K_M 15.9 GB 118 s**; **gemma fp8 13.2 GB 37 s**. All downloads 178 s total. SETUP DONE at +187 s (09:12:51).

Git commits:
| repo | commit | date |
|---|---|---|
| Comfy-Org/ComfyUI | (see 1.3) | |
| city96/ComfyUI-GGUF | 6ea2651e7df66d7585f6ffee804b20e92fb38b8a | 2026-01-12 |
| kijai/ComfyUI-KJNodes | 187868f53a7d9df007dbfe85891dab41453f7933 | 2026-11-23 |
| Lightricks/ComfyUI-LTXVideo | ced6bad92b82f90028e1e1fd5a37527302550fc5 | 2026-11-12 |
| Kosinkadink/ComfyUI-VideoHelperSuite | 4d907bee61e92c2e65af3bd6383a4e4d356126d1 | 2026-09-01 |

KJNodes is extra (not in the task list): needed for `VAELoaderKJ` to load the separate video/audio VAE files.

### 1.3 Canny control (OpenCV on Colab)
`colab exec -s ltx -f make_canny.py` -> `cv2.Canny(gray, 92, 200)` per frame (the workflow's CannyEdgePreprocessor
thresholds; frames are already 512 px tall = its resolution). White edges on black, 121 frames; 6.6 % edge pixels at frame
60 (the sun-glint sea makes a lot of edges). Downloaded to `colab/inputs/canny_121_960x512.mp4` and `canny_f60.png`.
Pitfall: an `exec` poll in the same call lost its websocket ("RuntimeError: Connection was lost.") while big downloads
ran; the command had finished, just retry the poll. Wrap polls in `timeout 90`.

### 1.4 ComfyUI server + node specs
```
colab exec -s ltx -f start_comfy.py     # python main.py --listen 127.0.0.1 --port 8188 (detached) + nvidia-smi -l 1 > /content/vram.csv
colab exec -s ltx -f object_info.py > object_info_out.txt   # input specs of every node used, from /object_info
```
Findings from /object_info (see `object_info_out.txt`):
- `LTXAddVideoICLoRAGuide` inputs: frame_idx, strength, latent_downscale_factor, crop (disabled|center), use_tiled_encode,
  tile_size, tile_overlap (+ optional use_streaming, tile_frames). The UI widgets `[0, 1, 1, 'disabled', False, 256, 64]` map in that order.
- `LTXVImgToVideoConditionOnly`: strength, optional bypass.
- Core `DualCLIPLoader` has `type: ltxv` and accepts gemma fp8 safetensors + embeddings_connectors -> no GGUF text encoder needed.
- `LTXAVTextEncoderLoader` wants a full checkpoint for `ckpt_name` (empty list here) -> not usable with GGUF-only files.

### 1.5 API-format graph
`python3 build_workflow.py` (local) writes `workflow_depth.json`, `workflow_canny.json`, `workflow_depth_noff.json`.
Inputs are copied into `/content/ComfyUI/input/` (LoadVideo / LoadImage read from there).
```
for f in run_job.py workflow_*.json; do colab upload -s ltx $f /content/$f; done
colab upload -s ltx inputs/canny_121_960x512.mp4 /content/ComfyUI/input/canny_121_960x512.mp4
echo '!cp /content/depth_121_960x512.mp4 /content/first_frame_960x512.png /content/ComfyUI/input/' | colab exec -s ltx
colab exec -s ltx --env RUN=depth -f start_job.py     # detached run_job.py: POST /prompt, poll /history, write /content/job_depth.json
```

ComfyUI commit: `da8bd08e48deee74d9f6c3bc00aed365b00ec209` (2026-11-23).

## 2. Runs

All runs: seed 42 (`RandomNoise`), 960x512, 121 frames, 24 fps, sampler `euler_ancestral_cfg_pp`, 8 steps via
`ManualSigmas`, CFG 1.0, IC-LoRA strength 1.0, guide strength 1.0, frame_idx 0, crop disabled, first-frame strength 1.0.
Timings from `run_job.py` (POST -> history success) and peak VRAM = max of `nvidia-smi -l 1` samples during the run
(device-level, includes the CUDA context and ComfyUI's cache; `torch.cuda.max_memory_allocated` is not reachable from
outside the server process).

### Run 1 - depth (with first frame)   `workflow_depth.json`
- submitted 09:15:20; finished 09:19:47. **Wall 267 s** (ComfyUI "Prompt executed in 266.20 seconds"), **peak 21226 MiB**.
- Breakdown (comfy.log): loading GGUF + text encoder (fp8 gemma, "14784MB Staged", dynamic VRAM loading) + encode ~70 s;
  transformer "loaded completely; 18816.84 MB usable, 15459.03 MB loaded, full load: True"; sampling **8 steps at ~22 s/step
  (~3 min)**; tiled VAE decode 2x2 (tiles 11x18 latents) a few s.
- Output: `ltx_depth_00001.mp4` (no audio) and `ltx_depth_00001-audio.mp4` (with the generated audio track); 121 frames.
  Downloaded with `colab download -s ltx /content/ComfyUI/output/ltx_depth_00001-audio.mp4 out/depth_with_audio.mp4`,
  `out/depth.mp4` = same with audio stripped (`ffmpeg -i ... -an -c copy`).
- RAM: ~5 GB used + 32 GB page cache. No OOM, no errors.

### Run 2 - canny (with first frame)   `workflow_canny.json`
- submitted 09:21:30 (queued straight after run 1; models already loaded). **Wall 192 s**, **peak 21258 MiB**.
  ~75 s faster than run 1 = the one-off model load/text encode cost.
- Pitfall: two `colab exec` polls at the same time (a background poll loop + a manual one) made both lose their
  websocket ("Connection was lost."). Run one poller at a time.

### Run 3 - depth, NO first frame   `workflow_depth_noff.json` (LTXVImgToVideoConditionOnly bypass=True)
- submitted 09:25:14. **Wall 195 s**, **peak 21260 MiB**.

### Run 4 - depth + canny, with first frame   `workflow_depth_canny.json`
Two `LTXAddVideoICLoRAGuide` nodes chained (node 14 depth -> node 31 canny; same settings); CFGGuider and
LTXVCropGuides take node 31's conditioning, LTXVConcatAVLatent takes node 31's latent. Not in the official workflow -
an experiment (the union LoRA was trained with one control at a time).
- submitted 09:29:05. Sampling ~25.7 s/step (vs 22 s: the second half-res guide adds tokens).

Added after looking at run 3 (much more "real" without the CG first frame, but the camera roll drifts):
### Run 5 - canny, NO first frame  `workflow_canny_noff.json`
### Run 6 - depth + canny, NO first frame  `workflow_depth_canny_noff.json`

### Run results (all `success`, seed 42)
| run | workflow | first frame | wall s | peak VRAM MiB (nvidia-smi) |
|---|---|---|---|---|
| 1 depth | workflow_depth.json | 1.0 | 267.4 (includes ~75 s model load + text encode) | 21226 |
| 2 canny | workflow_canny.json | 1.0 | 192.3 | 21258 |
| 3 depth_noff | workflow_depth_noff.json | bypass | 195.2 | 21260 |
| 4 depth_canny | workflow_depth_canny.json | 1.0 | 225.2 | 21258 |
| 5 canny_noff | workflow_canny_noff.json | bypass | 192.1 | 21260 |
| 6 depth_canny_noff | workflow_depth_canny_noff.json | bypass | 225.2 | 21258 |
| 7 depth_canny_ff05 | workflow_depth_canny_ff05.json | strength 0.5 | 222.6 | 21258 |

Sampling: ~22 s/step with one guide, ~25.7 s/step with two (8 steps). After the first run the models stay loaded
(between runs nvidia-smi shows ~17.1 GB held by ComfyUI). No OOM, no errors, no node problems in any run.
Each run also writes audio (LTX-2.3 is audio+video): `*_with_audio.mp4`; the plain `out/<run>.mp4` files are video only.

### Download and stop
```
colab download -s ltx /content/ComfyUI/output/ltx_<run>_00001-audio.mp4 out/<run>_with_audio.mp4
ffmpeg -v error -y -i out/<run>_with_audio.mp4 -an -c copy out/<run>.mp4
colab download -s ltx /content/job_<run>.json colab/job_<run>.json
# logs: colab/logs_comfy.log, logs_setup.log, logs_download.log, logs_vram.csv, logs_object_info.json, pip_freeze.txt
colab stop -s ltx        # 09:49:05 -> "Session terminated."
colab sessions           # "No active sessions found on server."
colab usage              # balance 1797.45 (was 1798.59) -> 1.14 units shown; usage rate 0.00/hr
```
**L4 time: 09:08:41 -> 09:49:05 = 40 min** (about 1.3 units at 1.94/h; the balance showed a 1.14 drop right after the stop,
which may still be catching up).

## 3. Final node graph (API format, `build_workflow.py`)
```
1  UnetLoaderGGUF            ltx-2.3-22b-distilled-1.1-Q5_K_M.gguf
2  LTXICLoRALoaderModelOnly  (1) ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors, strength 1.0 -> MODEL, latent_downscale_factor (=2)
3  DualCLIPLoader            gemma_3_12B_it_fp8_scaled + ltx-2.3-22b-distilled_embeddings_connectors, type ltxv
4/5 CLIPTextEncode           prompt (README) / "pc game, console game, video game, cartoon, childish, ugly"
6  LTXVConditioning          frame_rate 24
7  VAELoaderKJ               ltx-2.3-22b-distilled_video_vae, main_device, bf16
8  VAELoaderKJ               ltx-2.3-22b-distilled_audio_vae, main_device, bf16
9  LoadImage                 first_frame_960x512.png
10/11 LoadVideo + GetVideoComponents   control video (960x512, 121 f) -- fed at FULL size; node 14 halves it
12 EmptyLTXVLatentVideo      960 x 512, length 121
13 LTXVImgToVideoConditionOnly  vae 7, image 9, latent 12, strength 1.0 (0.5 in run 7), bypass = no-first-frame runs
14 LTXAddVideoICLoRAGuide    pos/neg 6, vae 7, latent 13, image 11, frame_idx 0, strength 1.0,
                             latent_downscale_factor <- 2.1, crop disabled, use_tiled_encode false (256/64)
  [31 second LTXAddVideoICLoRAGuide (canny, same settings) chained after 14 in the depth+canny runs; 29/30 load it]
15 LTXVEmptyLatentAudio      121 frames, 24 fps, audio_vae 8
16 LTXVConcatAVLatent        video 14(or 31).latent + audio 15
17 RandomNoise 42 | 18 KSamplerSelect euler_ancestral_cfg_pp | 19 ManualSigmas 1.0,0.99375,0.9875,0.98125,0.975,0.909375,0.725,0.421875,0.0
20 CFGGuider                 model 2, cfg 1.0
21 SamplerCustomAdvanced
22 LTXVSeparateAVLatent -> 23 LTXVCropGuides -> 24 LTXVTiledVAEDecode (2x2 tiles, overlap 6, last_frame_fix false)
25 LTXVAudioVAEDecode
26 VHS_VideoCombine          24 fps, video/h264-mp4, yuv420p, crf 16, audio 25
```
Differences from the official workflow: GGUF distilled-1.1 transformer instead of dev + distilled LoRA 0.5; DualCLIPLoader
instead of LTXAVTextEncoderLoader; VAELoaderKJ; control prepared outside the graph; VHS output instead of CreateVideo/SaveVideo.

## 4. Visual verdict (frames in `out/frames/`, grids in `out/compare.mp4`, `out/compare_all.mp4`)
Flicker metric = mean |frame(n) - frame(n-1)| luma (0-255) over the clip (ffmpeg tblend+signalstats); no run has
single-frame spikes, so no flicker in the classic sense.

| run | mean / max diff | real footage? | layout + camera | glider |
|---|---|---|---|---|
| render | 8.54 / 9.00 | - | - | - |
| depth + FF | 9.29 / 10.83 | No. Still looks like the CG; the sea keeps the CG ripple pattern, slightly sharper | Glider placement holds; **the horizon rolls away by ~15-20 deg** by the end (camera banks that the render does not) | Kept the CG model almost exactly (stripe, nav lights, nozzles) |
| canny + FF | 6.67 / 7.65 | No, slightly more photographic sea (whitecap streaks) | Very good: level horizon, motion matches | Same CG glider |
| depth+canny + FF | 7.36 / 7.72 | Like canny + FF | Very good | Same CG glider |
| depth+canny + FF 0.5 | 6.92 / 8.20 | A bit more real (bluer sea, whitecaps), still reads CG | Very good | Close to CG, slightly softened |
| depth, no FF | 8.28 / 15.03 | **Yes**: green-grey sea, big foam, haze, motion blur | Glider silhouette holds; **camera roll swings strongly (tilted 20-30 deg, changes direction)**; looks lower and faster than the render | Turned into a generic plain grey jet, no stripe/lights/nozzles |
| canny, no FF | 4.95 / 5.67 | **Yes, most photographic** (drone-footage look) | Level, stable horizon; layout holds | Silhouette holds but shading reads like a front view (nose to camera); **invents a sandy beach + surf on the right** (the sun-glint edges became surf); sun glare lost |
| depth+canny, no FF | 5.42 / 6.12 | **Yes**, very photographic | Level and stable | Rear view correct with a red stripe hint; same invented beach |

Main lessons:
1. **The CG first frame dominates** the look: with FF strength 1.0 every run stays CG-looking; 0.5 helps only a little.
   Without it the result looks like real footage but the content drifts (beach, glider design).
2. **Depth alone does not fix the horizon / camera roll**: in a 1/z map the far sea fades to the same black as the sky, so
   there is no horizon line; the model invents its own bank. Canny (sea texture lines) pins the camera much better.
3. Canny of a sun-glint sea is mostly glint noise; the model reads it as surf. A cleaner canny (blur first, higher
   thresholds, mask out the glint) or depth + a sparse canny is the next thing to try. A real-looking first frame
   (e.g. an image model restyle of frame 0) is the other lever.
4. Union control accepts two chained guides (depth + canny) without errors; cost +17 % per step.

## 5. Pitfalls (for the HOWTO)
- `colab new --gpu L4` can fail with 503 Service Unavailable; retry.
- Output size must be a multiple of 64 with the ref0.5 LoRA (960x544 is not); crop to 960x512 (or resize to 1024x576).
- Frames 8k+1 (121). Feed the control at full output size; LTXAddVideoICLoRAGuide downsizes it using the factor from LTXICLoRALoaderModelOnly.
- With GGUF files there is no full checkpoint, so LTXAVTextEncoderLoader / CheckpointLoaderSimple / LTXVAudioVAELoader cannot be used:
  use DualCLIPLoader(type ltxv), VAELoaderKJ (needs ComfyUI-KJNodes) for both VAEs, UnetLoaderGGUF.
- Use the distilled 1.1 GGUF with the workflow's 8 manual sigmas and cfg 1; do not add the distilled LoRA on top.
- Keep Colab's torch: strip torch lines from requirements files before pip install.
- `colab exec` websockets drop ("Connection was lost.") under heavy network use or when two execs run at once: one poller,
  short calls, `timeout 60`, everything long detached with Popen(start_new_session=True).
- Gemma fp8 + Q5_K_M fit on the L4 (peak ~21.3 GB device) with ComfyUI's dynamic VRAM loading; RAM use stayed low (~5 GB + cache).

---

# Run 2 (photoreal first frame) - 2026-11-24, 11:40-12:41 UTC

Goal: make frame 0 photoreal with an image model on the same L4 (same composition), then run LTX-2.3 +
Union-Control again with that picture as the first frame. Operator: Claude agent, following
`docs/HOWTO-restyle-with-ltx-on-colab.md` (Step 404) as its first real test. L4 only; no paid API.
Scripts and API graphs of this run: `colab2/`. Outputs: `out2/`.

## R2.0 Image models: repos checked (`https://huggingface.co/api/models/<repo>`, 11:40 UTC)

| repo | gated | sha | file used | size |
|---|---|---|---|---|
| unsloth/Qwen-Image-Edit-2511-GGUF | false | 52838251db242ddd8e8d0118de36c71006d7c397 | qwen-image-edit-2511-Q4_K_M.gguf | 12.84 GB |
| lightx2v/Qwen-Image-Edit-2511-Lightning | false | 107d238d68b8387e32843d0b4a2e24ceb0d3ad86 | Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors | 0.85 GB |
| Comfy-Org/Qwen-Image (old name Qwen-Image_ComfyUI redirects) | false | 1f12b17be14c89b026c51a91d67c32f84bb047bc | split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors | 9.38 GB |
| " | " | " | split_files/vae/qwen_image_vae.safetensors | 0.25 GB |
| Comfy-Org/Z-Image-Turbo (old name z_image_turbo redirects) | false | 6fc90a3b1b653e935a0d175e260736de25b84df5 | split_files/diffusion_models/z_image_turbo_bf16.safetensors | 12.31 GB |
| " | " | " | split_files/text_encoders/qwen_3_4b.safetensors | 8.04 GB |
| " | " | " | split_files/vae/ae.safetensors | 0.34 GB |
| alibaba-pai/Z-Image-Turbo-Fun-Controlnet-Union-2.1 | false | 5155fc56d17821007d6f62ac192c09e0f0e72016 | Z-Image-Turbo-Fun-Controlnet-Union-2.1-8steps.safetensors | 6.71 GB |

Checked, not used: Qwen/Qwen-Image-Edit-2511 false; Comfy-Org/Qwen-Image-Edit false (fp8 2511 is 20.5 GB: too big for
24 GB with the encoder, so the GGUF); QuantStack/Qwen-Image-Edit-2509-GGUF false; QuantStack/Qwen-Image-Edit-2511-GGUF:
401 (does not exist / private); InstantX/Qwen-Image-ControlNet-Union false; Comfy-Org/Qwen-Image-InstantX-ControlNets false;
Tongyi-MAI/Z-Image-Turbo false; alibaba-pai/Z-Image-Turbo-Fun-Controlnet-Union false;
**black-forest-labs/FLUX.1-schnell, FLUX.1-dev, FLUX.1-Kontext-dev: `gated: "auto"`** (need a login + accepting terms: excluded).
Note: `curl -s` on a renamed repo returns "Temporary Redirect ..." (not JSON): use `curl -sL`. `check_hf.sh` fixed.

Why Qwen-Image-Edit-2511: an instruction edit model takes the frame itself as the reference latent at the output
size, so the layout is kept by construction; the GGUF Q4_K_M + fp8 encoder fit the L4; the Lightning LoRA makes it 4 steps.
Z-Image-Turbo + Fun ControlNet Union 2.1 as the second family (img2img + canny/depth control).

## R2.1 Session and setup (following the HOWTO)

```
colab sessions; colab usage            # 11:40 no sessions; balance 1797.29
colab new -s ltx --gpu L4              # 11:43:26 -> 11:46:43 ColabRequestError ... accelerator=L4: Service Unavailable (503), nothing billed
colab new -s ltx --gpu L4              # 11:47:03 -> Session READY 11:47:11 (8 s)
colab upload -s ltx setup.sh /content/setup.sh; colab upload -s ltx setup_image.sh /content/setup_image.sh
colab exec -s ltx -f start_setup.py    # 11:47:30 RuntimeError: Connection was lost.  -> setup had NOT started (no /content/setup.log)
colab exec -s ltx -f start_setup.py                                       # 11:48:47 retry: started
colab exec -s ltx --env SCRIPT=/content/setup_image.sh -f start_setup.py  # image models, in parallel
colab upload ... render/depth/canny_121_960x512.mp4, first_frame_960x512.png   # inputs from colab/inputs/
```
`start_setup.py` now takes `SCRIPT` (log `/content/<script stem>.log`). `setup_image.sh` downloads the 8 image files, waits for
`/content/ComfyUI/main.py`, then links them (`model_patches/` for the ControlNet).
- LTX downloads: 186 s in all (as before). Image downloads: 231 s (GGUF 66 s, Qwen VL fp8 48 s, Z-Image bf16 57 s, ControlNet 22 s).
- setup.sh: clone took **114 s** this time (was fast before), pip ~3 min; **SETUP DONE 11:54:04 (~5.3 min)**, not ~3 min.
- `colab exec -f start_comfy.py` 11:54:30; "To see the GUI" within ~40 s. VM: same image as before (Python 3.13, torch 2.14.1+cu130).
- `object_info_image.py`: all image nodes present at the pinned ComfyUI commit. Z-Image Fun ControlNet 2.1 uses
  **`ZImageFunControlnet`** (model, model_patch, vae, strength, image, inpaint_image, mask, start/end_percent), not
  `QwenImageDiffsynthControlnet` (first draft used that; switched before running).

## R2.2 Photoreal frame 0 (image models, ComfyUI)

Inputs on the VM (`prep_image_inputs.py`, OpenCV): `ff_up.png` = frame 0 Lanczos-upscaled to **1440x768** (same 15:8 as
960x512, ~1.1 MP, multiples of 16), `ff_canny.png` (canny 92/200 after a 5 px blur, glint masked), `ff_depth.png` (depth frame 0).
Every output is saved at 1440x768 (`*_full_*`) and scaled back to **960x512** (Lanczos) for LTX.

Qwen graph (`build_image_workflow.py qwen`): UnetLoaderGGUF(qwen-image-edit-2511-Q4_K_M) -> LoraLoaderModelOnly(Lightning 4-step, 1.0)
-> ModelSamplingAuraFlow(3.1) -> CFGNorm(1.0); CLIPLoader(qwen_2.5_vl_7b_fp8_scaled, type qwen_image); VAELoader(qwen_image_vae);
TextEncodeQwenImageEditPlus(prompt, image1 = ff_up, **no vae**) -> ReferenceLatent(VAEEncode(ff_up)) ->
FluxKontextMultiReferenceLatentMethod(index_timestep_zero); negative = same with "" ; KSampler(seed, 4 steps, cfg 1, euler, simple,
latent = VAEEncode(ff_up), denoise 1.0). Feeding the reference latent ourselves (not through the encoder's `vae` input, which rescales
it to ~1 MP) keeps the reference and output at the same 1440x768 grid: the layout cannot drift by a resize.
Z-Image graph (`build_image_workflow.py zimage`): UNETLoader(z_image_turbo_bf16) -> ZImageFunControlnet(model_patch Union-2.1-8steps,
control image, strength) -> ModelSamplingAuraFlow(3.0); CLIPLoader(qwen_3_4b, lumina2); VAELoader(ae); KSampler(8 steps, cfg 1,
res_multistep, simple, latent = VAEEncode(ff_up), denoise D).

| cand | model / settings | exec (ComfyUI) | peak VRAM | edge F all / glider box (3 px) | look |
|---|---|---|---|---|---|
| qwen_a | Qwen-Edit-2511 Q4 + Lightning, seed 42, prompt A | 111.7 s (first: load + encode) | 19.5 GB | **0.815 / 0.877** | real metal glider, haze; **sea still the CG ripple pattern** |
| qwen_b | same, seed 7 | 26.8 s | 19.4 GB | 0.800 / 0.856 | like a, plus odd spray blobs by the glider |
| qwen_c | same, seed 42, prompt C ("replace the regular CG ripple pattern with real irregular ocean waves ...") | 107.4 s (reload after Z-Image) | 19.2 GB | 0.499 / 0.683 (the sea texture changed on purpose) | **most photographic**: real open-ocean waves, whitecaps, haze; glider in place, same outline, panel lines; nozzle detail merged |
| zi_canny | Z-Image + canny 0.8, denoise 0.7 | 118.3 s (load) | 21.7 GB | 0.734 / 0.787 | real sea, but the glider became an **F/A-18-like jet, wider**; red streak artefacts |
| zi_depth | Z-Image + depth 0.8, denoise 0.75 | 17.4 s | 21.3 GB | 0.716 / 0.758 | same problem, three nozzles |
| zi_canny2 | Z-Image + canny 1.0, denoise 0.55 | 114.0 s (reload) | 21.7 GB | 0.730 / 0.771 | glider shape closer but still CG-ish; sea between CG and real |

Alignment check (`align_check.py`, overlays `out2/cands/*_overlay.png`; red = frame 0 edges, green = candidate, yellow = both):
the glider outline of qwen_a/c sits on frame 0's (zoom crop `out2/cands/glider_crops.png`); the horizon by eye
(`out2/cands/hz_crops.png`) is within ~4 px for qwen_a and qwen_c (the model adds a haze band above it). The automatic horizon
row (largest sky->sea luma drop, left half) says 106 -> 115 (a) / 146 (c): fooled by the soft haze and by c's whitecaps - **check
the horizon by eye**. The edge F-score counts the sea texture, so it rewards keeping the CG sea: read it on the glider box and the overlay.
**Chosen: qwen_c** (`out2/photoreal_first_frame_qwen_c.png`, staged as `ComfyUI/input/photoreal_qwen_c.png`). qwen_a is the
best-aligned but keeps the CG sea, i.e. it would hand LTX the same CG look as before.
Model switching costs ~80-90 s each time (Qwen <-> Z-Image reload): group runs by model.
Before LTX: `colab exec -f free_vram.py` (POST /free unload_models) -> 200.

## R2.3 Glint-masked canny (`make_canny_soft.py`)
- v1 (BLUR=5, 92/200, GLINT=150): edge fraction 1.46 % (was 6.6 %) but the blur **erased most of the glider's outline**
  (`out2/canny_vs_cannysoft_v1_blur5_rejected_f60.png`): rejected.
- v2 (**BLUR=0**, 92/200, edges removed where the 41 px-blurred luma > 150, mask feathered 31 px): 3.16 %, glider outline and the
  left sea lines kept, the glint area empty (`out2/cannysoft_f60.png`). Used for run (c).
- A foreground `colab exec -f make_canny_soft.py` lost its websocket and the work died with it (no output): run it with
  `start_bg.py` (detached). The HOWTO's step 6.3 had it in the foreground.

## R2.4 LTX-2.3 runs with the photoreal first frame
Same graph and settings as run 1 (`build_workflow.py`): seed 42, 960x512, 121 frames, 24 fps, 8 steps, cfg 1, IC-LoRA and guide 1.0,
first frame `photoreal_qwen_c.png`.
```
python build_workflow.py --run pr_canny       --control canny_121_960x512.mp4 --first-frame photoreal_qwen_c.png
python build_workflow.py --run pr_depth_canny --control depth_121_960x512.mp4 --second-control canny_121_960x512.mp4 --first-frame photoreal_qwen_c.png
python build_workflow.py --run pr_cannysoft   --control cannysoft_121_960x512.mp4 --first-frame photoreal_qwen_c.png
python build_workflow.py --run pr_canny_ff07  --control canny_121_960x512.mp4 --first-frame photoreal_qwen_c.png --first-frame-strength 0.7
colab exec -s ltx --env RUN=<run> -f start_job.py     # all four queued at 12:14
bash fetch_outputs.sh ltx <run> ../out2
```
| run | exec (ComfyUI) | peak VRAM | mean / max frame diff, max jump |
|---|---|---|---|
| pr_canny | 316.3 s (incl. LTX load after the image models) | 21.2 GB | 13.63 / 15.11, 0.76 |
| pr_depth_canny | 225.3 s | 21.3 GB | 14.82 / 16.71, 0.71 |
| pr_cannysoft | 193.2 s | 21.3 GB | 13.82 / 15.12, 0.61 |
| pr_canny_ff07 | 193.0 s | 21.3 GB | 13.13 / 15.98, 1.51 |
| (render) | | | 7.33 / 7.73, 0.20 |
| (old depth+canny, no FF) | | | 4.66 / 5.25, 0.20 |
All four done 12:29:59. No errors, no OOM. The higher mean difference is the real, high-contrast waves moving, not flicker:
no spikes, consecutive frames (`out2/frames/consec_crops.png`) are coherent.

Comparison: `out2/compare.mp4` (CG | old depth+canny no FF | 4 new runs), stills `out2/frames/compare_f{0,60,120}.png`,
glider zoom `out2/frames/glider_crops_f120.png`.

## R2.5 Verdict (honest)
- **Real footage?** Yes, much more than any run-1 clip with a first frame: a real open ocean with swells, whitecaps and sun
  glare, haze on the horizon. Still a little "too clean" (glider surface slightly plastic) and the glare on the right is drawn
  as bright streaks in the plain-canny runs.
- **Glider and sea kept, no beach?** Yes in all four: no beach, no surf line. The glider keeps its position, size, bank,
  outline, red stripe and red wing tips over the whole clip; the twin nozzles become one dark blob (lost already in qwen_c) and
  the green nav light is gone.
- **Horizon:** level and stable in all four, ~4 px below the CG one with a haze band (from the photoreal frame).
- **Flicker:** none.
- Per run: **pr_cannysoft (glint masked) is the best** - smoothest, most natural glare, no streaks; pr_canny good but white
  foam-like streaks where the glint edges were; pr_depth_canny adds more white sparkle patches (busier), no gain over canny;
  pr_canny_ff07 is almost the same as 1.0 (the photoreal frame is already what we want).
- Usable for the film? Close: the best yet. Next: keep the nozzle detail in the photoreal frame (a crop-and-paste of the
  CG nozzles, or a mask so the edit leaves the aircraft alone), and the glint-masked canny + depth.

## R2.6 Times and units
- Session READY 11:47:11; work done 12:41 (~54 min); balance 1797.29 -> 1795.60 at 12:41 (**~1.7 units** so far, 1.94/h).
- The session `ltx` is **left running** (owner's instruction): ComfyUI up with LTX loaded (17.1 GB held), all weights on disk.
- Logs: `colab2/logs_{comfy,setup,setup_image,download,cannysoft2}.log`, `colab2/logs_vram.csv`, `colab2/job_*.json`, `out2/job_pr_*.json`.

## R2.7 HOWTO problems found (fixed in the repo)
1. First `colab exec -f start_setup.py` lost its websocket and the setup never started: check that `/content/setup.log` exists, retry.
2. Setup took ~5.3 min (clone 114 s), not ~3 min.
3. Step 6.3 ran `make_canny.py` in the foreground: a dropped websocket kills the work -> `start_bg.py`.
4. Two `colab exec` at once (a background waiter + a manual look) drop each other: one at a time, always.
5. `check_hf.sh` used `curl -s`: renamed repos answer with a redirect, not JSON -> `curl -sL`; `--image` added.
6. "Always stop the session" -> keep it running between experiments (check `colab sessions`, reuse `ltx`); stop when done.
7. `start_setup.py` could only run `setup.sh` -> `SCRIPT` env.
8. `colab download` of a small JSON once hung > 120 s (retry worked).
9. Model switches in one ComfyUI (image <-> LTX) cost a reload (~80-120 s); `/free` between stages.
