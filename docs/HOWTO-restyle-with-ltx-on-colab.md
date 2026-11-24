# HOWTO: restyle a vidgen render into real-looking footage with LTX-2.3 on Colab

Take a shot vidgen rendered (here a `space` scene: a glider chased low over a rough sea), give its
**canny edges** (and optionally its **depth**) as control videos to the open video model **LTX-2.3**
with the IC-LoRA **`Lightricks/LTX-2.3-22b-IC-LoRA-Union-Control`**, with a photoreal first frame
made on the same GPU, in **ComfyUI on a Google Colab L4**, driven from your machine by the `colab`
CLI. Everything downloaded is ungated on Hugging Face: no login, no token.

Scripts: [`tools/colab/`](../tools/colab/) (its [README](../tools/colab/README.md) lists them).
**local** = your machine, **VM** = the Colab machine. The raw lab log of the tests:
[`howto/ltx-colab-runlog.md`](howto/ltx-colab-runlog.md).

> **Keep the session between experiments, stop it when you are done.** A new session's setup takes
> ~6 min and 34-80 GB of downloads; `python tools/colab/setup_session.py ltx` on a running `ltx`
> takes ~20 s. An idle L4 still bills ~1.94 units an hour: when the owner says you are done,
> `colab stop -s ltx` (§10).

## Recommended setup and why

- **Settings**: photoreal first frame (Qwen-Image-Edit-2511, §6.4) + **glint-masked canny**
  (`make_canny_soft.py`, §6.3), first-frame strength 1.0, seed 42, 8 steps, cfg 1, 960x512, 121 frames.
- **The first frame sets the look.** The CG frame 0 keeps the CG look; no first frame looks real
  but invents things (a beach, a different glider).
- **Canny holds the layout and the horizon.** Depth alone rolls the horizon: in 1 / z depth the far
  sea and the sky are both black. Masking the sun glint's edges stops LTX turning them into surf.
  Depth + canny adds nothing and is ~17 % slower.
- **Limits**: the glint mask (`GLINT`, `FEATHER`) is tuned per shot; depth stays useful for scenes
  with few edges.
- **Remaining flaw** (from the first frame, kept by LTX): the glider's twin nozzles merge into one
  dark shape and the green wing-tip light is lost.

## 1. When to use it

| | LTX-2.3 IC-LoRA on Colab (this HOWTO) | OpenRouter Seedance (`vidgen generate run`) |
|---|---|---|
| Control | exact per-frame control video (depth, canny, pose; two chained) | a reference video + prompt; the model decides how much to follow |
| Cost | Colab units: ~1.3 for 7 clips, ~1.7 for 6 stills + 4 clips | dollars per clip; OpenRouter reserves its worst case (HTTP 402 under ~$10 of credits) |
| Inside vidgen | no: by hand with these scripts | yes: plan, budget, ledger, takes |
| Audio | makes its own (not used) | can take the film's sound (`audio: mix`) |

Use it to follow the render's layout and camera frame by frame, or to try ideas cheaply; use
Seedance for the paid, tracked path inside vidgen.

## 2. Prerequisites

- The **`colab` CLI** (google-colab-cli 0.8.0) installed and logged in (`colab usage` prints the
  balance); `colab skill` prints its own agent guide.
- **Compute units** on the account (an L4 is ~1.94 units an hour).
- No SSH key, no Hugging Face login: `colab upload` / `colab download` / `colab exec`.
- Locally: `ffmpeg` / `ffprobe`, Python 3.10+ (standard library only), `curl`.
- **Ask the owner before creating a GPU session** (it spends their units).

## 3. Make the inputs with vidgen (local)

For one shot, frame-aligned: the colour render, its depth, its first frame.

1. Give the beat a `generated_shot` (never paid for on this route; vidgen only cuts its inputs).
   Render close to the LTX size: the test used `format: {width: 960, height: 544, fps: 24}`;
   **1024x576** (16:9, multiples of 64) needs no crop.
   ```yaml
   beats:
     - text: "Low over the open sea, the glider leans into a gentle turn."
       generated_shot:
         kind: establishing
         prompt: "a grey glider flies low over a rough open sea ..."
         guide: depth          # then final, see below
   ```
2. **Depth** (`guide: depth`, `space` scenes and `web` scenes drawn through `vidgen/three-finish`;
   [CONFIG.md, generated shots](CONFIG.md)): `vidgen render`, then
   `vidgen generate inputs --guide --shot <beat id>` writes `build/videogen/<shot>/guide.depth.mp4`
   (grey = 1 / distance: near white, far dark, sky black; one range per shot) and `first_frame.png`.
3. **Colour**: set `guide: final` and run `vidgen generate inputs --guide --shot <beat id>` again:
   `guide.final.mp4` is cut from the same finished render (same frames, size, camera).
4. **Trim and crop**: LTX wants **8k+1** frames (121 = 5.04 s at 24 fps) and, with the `ref0.5`
   LoRA, width and height **multiples of 64**:
   ```bash
   bash tools/colab/prepare_inputs.sh \
     build/videogen/chase_b1/guide.final.mp4 build/videogen/chase_b1/guide.depth.mp4 \
     build/videogen/chase_b1/first_frame.png ltx-inputs 960 512 121 24
   ```
   Centre-crops (960x544 -> 960x512), keeps 121 frames, writes `render_121_960x512.mp4`,
   `depth_121_960x512.mp4`, `first_frame_960x512.png`.
5. **Canny** is made on the VM (§6.3; it has OpenCV).

Restore `video.yaml` if you changed its format for the test.

## 4. Check the Hugging Face repos (local, free)

```bash
bash tools/colab/check_hf.sh            # add --image for the models of §6.4
```
Prints `gated=False` per repo and the file sizes (`curl -sL`: a renamed repo answers with a
redirect). If a repo is gated, stop: never put a token in these scripts. By hand:
`https://huggingface.co/api/models/<repo>` (`"gated": false`).

| repo | commit | file | size |
|---|---|---|---|
| `unsloth/LTX-2.3-GGUF` | `96e8ed4925ead3db9ff4d0084f165ef6a74f28d0` | `distilled-1.1/ltx-2.3-22b-distilled-1.1-Q5_K_M.gguf` | 15.93 GB |
| " | " | `vae/ltx-2.3-22b-distilled_video_vae.safetensors` | 1.45 GB |
| " | " | `vae/ltx-2.3-22b-distilled_audio_vae.safetensors` | 0.36 GB |
| " | " | `text_encoders/ltx-2.3-22b-distilled_embeddings_connectors.safetensors` | 2.31 GB |
| `Lightricks/LTX-2.3-22b-IC-LoRA-Union-Control` | `20a580c8606c06a0988d40375a61309e0fe5893d` | `ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors` | 0.65 GB |
| `Comfy-Org/ltx-2` | `ccde4ba417d7900669fd56dd292a883cee11ff37` | `split_files/text_encoders/gemma_3_12B_it_fp8_scaled.safetensors` | 13.21 GB |

Use the `distilled_` VAE and connector files (not `dev_`) with the distilled-1.1 transformer.
`ref0.5`: trained with the control at half the output size; `LTXAddVideoICLoRAGuide` halves it, so
feed the control at full size.

## 5. Create and set up the session (local)

```bash
python tools/colab/setup_session.py ltx      # --no-image: without §6.4's models; --gpu; --latest
```
From the repository root; any name, several sessions side by side. It reuses or creates the session
(retrying HTTP 503), skips what is done, installs ComfyUI + LTX-2.3 and the image models side by
side, starts ComfyUI and prints a summary; [tools/colab/README.md](../tools/colab/README.md) has the
details. It never stops the session: after an error run it again (it goes on where it stopped).
Test VM: Python 3.13, torch 2.14.1+cu130, CUDA 13.0, L4 23 GB, 52 GB RAM, 236 GB disk.

## 6. What it installs, and the per-run steps

Run the commands below from `tools/colab/`, with the inputs in `ltx-inputs/`.

### 6.1 Installed versions

`setup.sh` checks out ComfyUI and four custom nodes at these commits (`--latest`: their newest),
installs their requirements **without the torch / torchvision / torchaudio lines** (Colab's CUDA
torch must stay) and links the weights into `ComfyUI/models/`:

| repo | commit (date) | why |
|---|---|---|
| `Comfy-Org/ComfyUI` | `da8bd08e48deee74d9f6c3bc00aed365b00ec209` (2026-11-23) | the server |
| `Lightricks/ComfyUI-LTXVideo` | `ced6bad92b82f90028e1e1fd5a37527302550fc5` (2026-11-12) | IC-LoRA nodes, tiled decode |
| `city96/ComfyUI-GGUF` | `6ea2651e7df66d7585f6ffee804b20e92fb38b8a` (2026-01-12) | `UnetLoaderGGUF` |
| `Kosinkadink/ComfyUI-VideoHelperSuite` | `4d907bee61e92c2e65af3bd6383a4e4d356126d1` (2026-09-01) | `VHS_VideoCombine` (mp4 with audio) |
| `kijai/ComfyUI-KJNodes` | `187868f53a7d9df007dbfe85891dab41453f7933` (2026-11-23) | `VAELoaderKJ` (separate video / audio VAE files) |

Resulting versions: torch 2.14.1+cu130, torchvision 0.29.1, torchaudio 2.11.0, gguf 0.19.0,
transformers 5.22.1, numpy 2.4.6, av 19.0.2, safetensors 0.8.0, huggingface_hub 2.4.0,
comfyui_frontend_package 1.59.11. pip's warning that `datasets` wants hub < 2.0 is harmless.

### 6.2 ComfyUI

`bash poll.sh ltx comfy` shows the log (`/content/comfy.log`) and GPU memory (`/content/vram.csv`).
`colab exec -s ltx -f object_info.py` prints the inputs of every node used (after a node update).

### 6.3 Canny control (VM)

Upload the inputs and run the canny **detached** with `start_bg.py` (a foreground `colab exec` that
loses its websocket kills the work):
```bash
for f in ../../ltx-inputs/*; do colab upload -s ltx "$f" "/content/$(basename "$f")"; done
colab upload -s ltx start_bg.py /content/start_bg.py
colab upload -s ltx make_canny_soft.py /content/make_canny_soft.py
colab exec -s ltx -f start_bg.py --env NAME=cannysoft --env CMD="python /content/make_canny_soft.py" \
  --env SRC=/content/render_121_960x512.mp4 --env DST=/content/cannysoft_121_960x512.mp4
echo '!cat /content/cannysoft.log' | colab exec -s ltx     # "canny-soft frames 121 ..." when done (~1 min)
echo '!cp /content/depth_121_960x512.mp4 /content/cannysoft_121_960x512.mp4 /content/first_frame_960x512.png /content/ComfyUI/input/' | colab exec -s ltx
```
`make_canny_soft.py` (defaults `BLUR=0`, thresholds 92 / 200 as the official
`CannyEdgePreprocessor`, `GLINT=150`, `FEATHER=31`) removes edges where the frame blurred over 41 px
is brighter than 150: on the test shot 6.6 % edge pixels -> 3.2 %, the glider's outline and the
darker sea kept. Do not blur before the canny (`BLUR=5` loses the glider's outline). `make_canny.py`
is the plain canny (same call, `DST=/content/canny_121_960x512.mp4`; also runs locally with OpenCV).
`LoadVideo` / `LoadImage` read from `ComfyUI/input/`.

### 6.4 Photoreal first frame (VM)

Restyle frame 0 into a photo on the same VM, then give it to LTX as the first frame. Only the look
may change: position, size, attitude and outline of the subject, the horizon and the glint stay.

**Qwen-Image-Edit-2511** (GGUF Q4_K_M + 4-step Lightning LoRA) takes the frame itself as its
reference, so the layout is kept. Z-Image-Turbo + Fun ControlNet Union 2.1 (img2img 0.55-0.75)
replaces the glider with a wider F/A-18-like jet: not usable here. FLUX.1 schnell / dev / Kontext
are gated. The fp8 Qwen-Image-Edit-2511 (20.5 GB) does not fit beside its encoder in 24 GB.

| repo (all `gated: false`) | file | size |
|---|---|---|
| `unsloth/Qwen-Image-Edit-2511-GGUF` | `qwen-image-edit-2511-Q4_K_M.gguf` | 12.84 GB |
| `lightx2v/Qwen-Image-Edit-2511-Lightning` | `Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors` | 0.85 GB |
| `Comfy-Org/Qwen-Image` | `split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors` | 9.38 GB |
| " | `split_files/vae/qwen_image_vae.safetensors` | 0.25 GB |
| `Comfy-Org/Z-Image-Turbo` | `z_image_turbo_bf16`, `qwen_3_4b`, `ae` (`split_files/...`) | 12.31 + 8.04 + 0.34 GB |
| `alibaba-pai/Z-Image-Turbo-Fun-Controlnet-Union-2.1` | `Z-Image-Turbo-Fun-Controlnet-Union-2.1-8steps.safetensors` | 6.71 GB |

Commits: `check_hf.sh --image`. `setup_session.py` installs these unless `--no-image`.
```bash
for f in prep_image_inputs.py align_check.py free_vram.py; do colab upload -s ltx "$f" "/content/$f"; done
colab exec -s ltx -f prep_image_inputs.py      # ComfyUI/input/ff_up.png (frame 0 at 1440x768), ff_canny.png, ff_depth.png
python build_image_workflow.py qwen --run qwen_c --out workflow_qwen_c.json      # local
colab upload -s ltx workflow_qwen_c.json /content/workflow_qwen_c.json
colab exec -s ltx --env RUN=qwen_c -f start_job.py
bash poll.sh ltx job qwen_c                    # ~110 s the first time (load), ~25 s after
colab download -s ltx /content/ComfyUI/output/qwen_c_00001_.png qwen_c.png
```
Graph (`build_image_workflow.py qwen`): `UnetLoaderGGUF` -> `LoraLoaderModelOnly` (Lightning, 1.0)
-> `ModelSamplingAuraFlow` (shift 3.1) -> `CFGNorm`; `CLIPLoader` (`qwen_image`);
`TextEncodeQwenImageEditPlus` with `image1` = the frame and **no `vae`**, then `ReferenceLatent`
with the frame's own `VAEEncode` and `FluxKontextMultiReferenceLatentMethod` (`index_timestep_zero`);
`KSampler` seed 42, 4 steps, cfg 1, euler, simple, denoise 1.0 on that latent; saved at 1440x768
(`<run>_full_`) and at **960x512** (`<run>_00001_.png`). Frame 0 is upscaled 1.5x to 1440x768 first
(~1.1 MP, multiples of 16). Feeding the reference latent yourself keeps it on the output's grid
(through the encoder's `vae` input it is rescaled to ~1 MP and can shift).

**The prompt matters most.** "Make the sea real ocean water" keeps the CG ripples; naming them works
(the script's default, prompt C): "*Replace the regular, repeating computer-generated ripple pattern
of the water with real, irregular open-ocean waves ...*" plus "*Do not move or resize anything: the
aircraft's position, size, angle and outline, the horizon line and the bright sun glint ... must stay
exactly where they are.*" Make 2-3 candidates (seed, prompt) and keep the best.

**Alignment check.** `align_check.py` writes per candidate an overlay of the two canny maps (frame 0
red, candidate green, both yellow) and an edge F-score (3 px tolerance), whole frame and subject box:
```bash
colab exec -s ltx -f start_bg.py --env NAME=align --env CMD="python /content/align_check.py" \
  --env REF=/content/first_frame_960x512.png --env OUT=/content/align \
  --env CANDS="/content/ComfyUI/output/qwen_a_00001_.png /content/ComfyUI/output/qwen_c_00001_.png"
echo '!cat /content/align.log' | colab exec -s ltx
```
The score counts the sea's texture, so a candidate that rightly replaces the CG sea scores lower
(0.50 for the chosen `qwen_c` against 0.815 for a CG-sea candidate, both with the glider on frame 0's
outline), and the haze the model adds fools the horizon row: **check the overlay and zooms of the
subject and the horizon by eye** (`qwen_c`: within ~4 px). Then:
```bash
echo '!cp /content/ComfyUI/output/qwen_c_00001_.png /content/ComfyUI/input/photoreal_qwen_c.png' | colab exec -s ltx
colab exec -s ltx -f free_vram.py          # POST /free: unload all models
```
Switching between the image models and LTX costs a reload (~80-120 s): group runs by model.

## 7. Build and submit the workflow

### 7.1 Build the API-format graph (local)

```bash
python build_workflow.py --run pr_cannysoft --control cannysoft_121_960x512.mp4 \
  --first-frame photoreal_qwen_c.png         # the recommended setup
python build_workflow.py --run canny_noff --control canny_121_960x512.mp4 --no-first-frame
python build_workflow.py --run dc --control depth_121_960x512.mp4 \
  --second-control canny_121_960x512.mp4 --first-frame-strength 0.5 --prompt-file prompt.txt
python build_workflow.py --experiment --out-dir /some/dir      # the 7 graphs of §12's first table
```
The official `example_workflows/2.3/LTX-2.3_ICLoRA_Union_Control_Distilled.json` (ComfyUI-LTXVideo)
in API format, with GGUF loaders:

| id | node | key settings |
|---|---|---|
| 1 | `UnetLoaderGGUF` | `ltx-2.3-22b-distilled-1.1-Q5_K_M.gguf` |
| 2 | `LTXICLoRALoaderModelOnly` | union-control `ref0.5`, strength 1.0; outputs MODEL and `latent_downscale_factor` (2) |
| 3 | `DualCLIPLoader` | `gemma_3_12B_it_fp8_scaled` + `..._embeddings_connectors`, `type: ltxv` |
| 4 / 5 | `CLIPTextEncode` | prompt / negative "pc game, console game, video game, cartoon, childish, ugly" |
| 6 | `LTXVConditioning` | `frame_rate` 24 |
| 7 / 8 | `VAELoaderKJ` | video VAE / audio VAE, `main_device`, bf16 |
| 9 | `LoadImage` | the first frame |
| 10 / 11 | `LoadVideo` + `GetVideoComponents` | the control video at **full** output size |
| 12 | `EmptyLTXVLatentVideo` | 960 x 512, length 121 |
| 13 | `LTXVImgToVideoConditionOnly` | strength 1.0; **`bypass: true` = no first frame** |
| 14 | `LTXAddVideoICLoRAGuide` | frame_idx 0, strength 1.0, `latent_downscale_factor` from node 2, crop disabled, no tiled encode (256 / 64) |
| 31 | second `LTXAddVideoICLoRAGuide` | only for two controls: chained after 14 (nodes 29 / 30 load it) |
| 15 / 16 | `LTXVEmptyLatentAudio` + `LTXVConcatAVLatent` | LTX-2.3 makes video and audio together |
| 17-21 | `RandomNoise` 42, `KSamplerSelect` `euler_ancestral_cfg_pp`, `ManualSigmas` `1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0` (8 steps), `CFGGuider` cfg 1.0, `SamplerCustomAdvanced` | |
| 22-25 | `LTXVSeparateAVLatent` -> `LTXVCropGuides` -> `LTXVTiledVAEDecode` (2x2, overlap 6); `LTXVAudioVAEDecode` | |
| 26 | `VHS_VideoCombine` | 24 fps, h264 mp4, yuv420p, crf 16, with audio; prefix `ltx_<run>` |

Differences from the official workflow: the distilled-1.1 GGUF instead of the dev checkpoint +
distilled LoRA 0.5 (**do not add the distilled LoRA on top**); `DualCLIPLoader` instead of
`LTXAVTextEncoderLoader` (it wants a full checkpoint); `VAELoaderKJ`; the control prepared outside
the graph; VHS output. Single stage, no upscaler.

### 7.2 Submit, detached

```bash
for f in run_job.py workflow_pr_cannysoft.json; do colab upload -s ltx "$f" "/content/$f"; done
colab exec -s ltx --env RUN=pr_cannysoft -f start_job.py
```
`run_job.py` POSTs the graph to `/prompt`, polls `/history/<id>` every 3 s and writes
`/content/job_<run>.json` (wall time, status, outputs, peak VRAM). Jobs queue in ComfyUI.

## 8. Poll and download (local)

```bash
bash poll.sh ltx job pr_cannysoft               # empty until done; shows the step counter
bash fetch_outputs.sh ltx pr_cannysoft out      # out/pr_cannysoft_with_audio.mp4, out/pr_cannysoft.mp4, out/job_pr_cannysoft.json
```
One poller at a time, short calls (`timeout 90` built in): two `colab exec` at once drop each other.

## 9. Compare (local)

```bash
bash make_compare.sh compare.mp4 4 "CG render=ltx-inputs/render_121_960x512.mp4" \
  "photoreal + soft canny=out/pr_cannysoft.mp4" "canny, no first frame=out/canny_noff.mp4"
```
Labelled 640x340 panels, N columns, in step. Look at single frames
(`ffmpeg -i compare.mp4 -vf "select=eq(n\,60)" -frames:v 1 f60.png`): the horizon and the subject's
design. Flicker: per-frame differences with `ffmpeg -i clip.mp4 -vf "tblend=all_mode=difference,signalstats" -f null -`.

## 10. Stop the session (local)

Download everything first; the VM's disk is gone afterwards. Do this even after an error.
```bash
colab stop -s ltx          # "Session terminated."
colab sessions             # "No active sessions found on server."
colab usage                # 0.00/hr when nothing runs
```

## 11. Costs and timings (L4, 960x512, 121 frames, 8 steps)

| item | measured |
|---|---|
| session start | 8 s-3 min, plus ~3 min per HTTP 503 try |
| `setup_session.py`, new session | ~6 min setup (both parts side by side) after the session is up; up to ~23 min when `colab exec` calls hang and are retried |
| `setup_session.py`, ready session | 10-20 s |
| Qwen-Image-Edit, one 1440x768 picture, 4 steps | ~110 s with the load, ~25 s after; peak ~19.5 GB |
| Z-Image-Turbo + ControlNet, 8 steps | ~115 s with the load, ~17 s after; peak ~21.7 GB |
| first LTX run of a session | ~267 s (~75 s model load + text encode); ~316 s after the image models |
| later LTX runs, one control | ~192-195 s (~22 s a step) |
| later LTX runs, two controls | ~223-225 s (~25.7 s a step) |
| peak VRAM | ~21.3 GB of 23 GB; RAM ~5 GB + page cache |
| 7 clips | 40 min of L4, ~1.3 units |
| 6 stills + 4 clips | 54 min of L4, ~1.7 units |

## 12. Results

All: seed 42, 960x512, 121 frames, 24 fps, 8 steps, cfg 1, Q5_K_M distilled-1.1, IC-LoRA and guide
strength 1.0; all succeeded, no OOM, no flicker.

**CG first frame or none:**

| control | first frame | real footage? | horizon | subject |
|---|---|---|---|---|
| depth | CG, 1.0 | no, CG look | **rolls 15-20°** | the CG glider |
| canny | CG, 1.0 | no | level | CG glider |
| depth + canny | CG, 1.0 | no | level | CG glider |
| depth + canny | CG, 0.5 | a bit more real, still CG | level | close to CG, softened |
| depth | none | **yes** | **rolls 20-30°**, changes direction | a generic grey jet |
| canny | none | **yes**, most photographic | level | front-lit; **invents a sandy beach and surf** |
| depth + canny | none | **yes** | level | rear view, red stripe hint; same beach |

**Photoreal first frame (`qwen_c`):**

| run | control | real footage? | glider and sea | horizon |
|---|---|---|---|---|
| `pr_canny` | canny | **yes** (swells, whitecaps, haze) | glider kept (place, size, bank, outline, red stripe, wing tips); no beach; white foam-like streaks at the glint | level |
| `pr_depth_canny` | depth + canny | yes | as canny, busier white sparkle | level |
| `pr_cannysoft` | glint-masked canny | **yes, the best** | glider kept, no beach, a smooth natural glare at the glint | level |
| `pr_canny_ff07` | canny, first frame 0.7 | yes | almost as `pr_canny` | level |

The horizon sits ~4 px below the CG one, under a haze band the image model adds. The glider's
surface looks a little clean; twin nozzles and wing-tip light as in "Recommended setup".

## 13. Troubleshooting

| symptom | cause | fix |
|---|---|---|
| `colab new` fails after ~3 min: `ColabRequestError ... accelerator=L4: Service Unavailable` | no L4 capacity (HTTP 503; nothing billed) | `setup_session.py` tries 4 times a minute apart; else run it again later |
| `RuntimeError: Connection was lost.` from `colab exec` | websocket dropped (big downloads, or two `exec` at once) | the command usually finished: poll again; one poller; short calls; long work detached (`start_bg.py`, `start_job.py`) |
| the same on the **first** `exec` of a new session, or on a foreground script | dropped before or while the code ran | the code did not run or died: check (`ls /content`, the log) and run it again |
| `colab exec` keeps failing after a dropped call | the kernel is busy or reconnecting | wait ~20 s, try `echo 'print(1)' \| colab exec -s ltx` |
| `colab download` of a small file hangs | slow or dropped transfer | run it again |
| a running session is gone from `colab sessions` | Colab ended it (cause unknown) | its disk is gone: download outputs as each run finishes; `setup_session.py <name>` makes a new one |
| `colab exec` gives up after 30 s without output | its `--timeout` default | long work goes through `start_*.py` |
| `setup_session.py` stops with "... stopped before it finished" and a log tail | a download or install failed on the VM | read the tail; run it again: it starts only the unfinished part |
| guide and output sizes do not match | 960x544 with `ref0.5` (half-size guide not a whole number of latents) | multiples of 64: 960x512 or 1024x576 |
| frame count off | LTX wants 8k+1 frames | 121 (or 97, 73 ...); `prepare_inputs.sh` checks it |
| `LTXAVTextEncoderLoader` has an empty `ckpt_name` list; `CheckpointLoaderSimple` / `LTXVAudioVAELoader` unusable | they want the full checkpoint; a GGUF setup has none | `DualCLIPLoader` (`type: ltxv`), `VAELoaderKJ`, `UnetLoaderGGUF` |
| GPU torch gone after node requirements | a requirements file reinstalled torch | `setup.sh` strips the torch lines; keep Colab's torch |
| `QwenImageDiffsynthControlnet` does not take Z-Image's Fun ControlNet 2.1 | 2.1 has its own node | `ZImageFunControlnet` (`object_info_image.py` lists the inputs) |
| the image edit keeps the CG sea | the prompt only asks for "real water" | name the CG pattern (prompt C, §6.4) |
| download of `ltx_<run>_00001-audio.mp4` fails | a second run with the same prefix writes `_00002` | `colab ls -s ltx /content/ComfyUI/output` |
| a node's inputs changed | node versions moved | the pinned commits (no `--latest`) or `object_info.py` |

## Files

[`tools/colab/`](../tools/colab/) (the [README](../tools/colab/README.md) says where each runs).
The test's graphs, logs, `pip_freeze.txt`, candidates and clips stay outside the repo, in the owner's
`video-projects/footage-test/ltx-test/`; its log is [`howto/ltx-colab-runlog.md`](howto/ltx-colab-runlog.md).
