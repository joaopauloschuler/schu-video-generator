# HOWTO: restyle a vidgen render into real-looking footage with LTX-2.3 on Colab

This is the recipe of two test runs on 2026-11-24 (Step 404 wrote down the first; Step 405
replayed it, fixed what was wrong, and added the photoreal first frame of §6.4; the inputs came
from Steps 402 and 403). It takes a shot that vidgen rendered (here a `space` scene: a glider chased
low over a rough sea), sends its **depth** and/or **canny edges** as control videos to the
open video model **LTX-2.3** with the IC-LoRA **`Lightricks/LTX-2.3-22b-IC-LoRA-Union-Control`**,
and runs it in **ComfyUI on a Google Colab L4 GPU**, driven from your own machine by the
`colab` command-line tool. Everything it downloads is ungated on Hugging Face: no login, no token.

Every script named below is in [`tools/colab/`](../tools/colab/) (its [README](../tools/colab/README.md)
lists them). Follow the steps in order; each one says where it runs (**local** = your machine,
**VM** = the Colab machine).

> **Keep the session between experiments, stop it when you are done.** Setting up costs ~6 min
> and ~34-80 GB of downloads, so run your experiments in one session:
> `python tools/colab/setup_session.py ltx` reuses `ltx` when it runs (its weights, ComfyUI and
> outputs are still on the VM) and then takes about 20 s. An idle session still spends ~1.94 units
> an hour: when the owner says you are done, stop it (`colab stop -s ltx`, §10).

---

## 1. What it does, and when to use it

| | LTX-2.3 IC-LoRA on Colab (this HOWTO) | OpenRouter Seedance (`vidgen generate run`) |
|---|---|---|
| Control | exact per-frame control video (depth, canny, pose; two chained) | a reference video + prompt; the model decides how much to follow |
| Cost | Colab compute units (~1.3 units for 40 min of L4 covered 7 clips; ~1.7 units for 6 stills + 4 clips in run 2) | dollars per clip; OpenRouter reserves its worst case (HTTP 402 under ~$10 of credits) |
| Inside vidgen | no: done by hand with the scripts here, outside `vidgen generate` | yes: plan, budget, ledger, takes |
| Audio | generates its own (not used here) | can take the film's sound (`audio: mix`) |
| Look of the result (these tests) | run 1: real footage only **without** the CG first frame, and then it invents things; run 2: real-looking **with a photoreal first frame** (§6.4) and the layout kept (see §12) | not tried yet (credits) |

Use this route when you want the clip to follow the render's layout and camera frame by frame
and can afford some invented content, or to try ideas cheaply; use Seedance for the paid,
tracked path inside vidgen.

## 2. Prerequisites

- The **`colab` CLI** (google-colab-cli; 0.8.0 was used) installed and authenticated to the
  Colab account (`colab usage` prints the balance). Run `colab skill` once for its own agent guide.
- **Compute units** on the account (run 1 cost about 1.3, run 2 about 1.7). An L4 costs about 1.94 units
  an hour; check `colab usage` before and after.
- No SSH key and no Hugging Face login: files go up and down with `colab upload` / `colab download`,
  commands run with `colab exec`.
- Locally: `ffmpeg` / `ffprobe`, Python 3.10+ (only the standard library), `curl`.
- **Ask the owner before creating a GPU session** (it spends their units). `setup_session.py`
  reuses a running session of the same name instead of making a second one.

## 3. Make the inputs with vidgen (local)

You need, for one shot, frame-aligned: the colour render, its depth, and its first frame.

1. In the project's `video.yaml`, give the beat a `generated_shot` (it is never paid for on this
   route; vidgen only cuts its inputs). Render at a size close to what LTX will get; the test used
   `format: {width: 960, height: 544, fps: 24}`. Better: **1024x576** (16:9, both multiples of 64),
   which needs no crop (not tried).
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
3. **Colour** (`guide: final`): change the shot to `guide: final` and run
   `vidgen generate inputs --guide --shot <beat id>` again: `guide.final.mp4` is cut from the same
   finished render (no second render). Both clips have the same frames, size and camera.
4. **Trim and crop** for LTX: the frame count must be **8k+1** (121 = 5.04 s at 24 fps) and, with the
   `ref0.5` LoRA, width and height **multiples of 64** (960x544 is not: 544 / 2 / 32 is not whole).
   ```bash
   bash tools/colab/prepare_inputs.sh \
     build/videogen/chase_b1/guide.final.mp4 build/videogen/chase_b1/guide.depth.mp4 \
     build/videogen/chase_b1/first_frame.png ltx-inputs 960 512 121 24
   ```
   It centre-crops (960x544 -> 960x512: 16 px off top and bottom), keeps the first 121 frames and
   writes `render_121_960x512.mp4`, `depth_121_960x512.mp4`, `first_frame_960x512.png`.
5. **Canny** is made on the VM (it has OpenCV; step 6.3) with `make_canny.py`, thresholds 92 / 200
   like the official workflow's `CannyEdgePreprocessor`, or with `make_canny_soft.py`, which
   also removes the edges in the sun glint (better, §12). With OpenCV locally,
   `python make_canny.py SRC DST` works the same.

Restore `video.yaml` afterwards if you changed its format for the test.

## 4. Check the Hugging Face repos (local, free)

```bash
bash tools/colab/check_hf.sh            # add --image for the models of §6.4
```
prints `gated=False` for each repo and the sizes of the files used. (It uses `curl -sL`: a renamed
repo, e.g. `Comfy-Org/Qwen-Image_ComfyUI` -> `Comfy-Org/Qwen-Image`, answers with a redirect.) If a repo is gated now, stop:
the install would need a token (never put one in these scripts).

| repo | commit used | file | size |
|---|---|---|---|
| `unsloth/LTX-2.3-GGUF` | `96e8ed4925ead3db9ff4d0084f165ef6a74f28d0` | `distilled-1.1/ltx-2.3-22b-distilled-1.1-Q5_K_M.gguf` | 15.93 GB |
| " | " | `vae/ltx-2.3-22b-distilled_video_vae.safetensors` | 1.45 GB |
| " | " | `vae/ltx-2.3-22b-distilled_audio_vae.safetensors` | 0.36 GB |
| " | " | `text_encoders/ltx-2.3-22b-distilled_embeddings_connectors.safetensors` | 2.31 GB |
| `Lightricks/LTX-2.3-22b-IC-LoRA-Union-Control` | `20a580c8606c06a0988d40375a61309e0fe5893d` | `ltx-2.3-22b-ic-lora-union-control-ref0.5.safetensors` | 0.65 GB |
| `Comfy-Org/ltx-2` | `ccde4ba417d7900669fd56dd292a883cee11ff37` | `split_files/text_encoders/gemma_3_12B_it_fp8_scaled.safetensors` | 13.21 GB |

Use the `distilled_` VAE and connector files (unsloth also has `dev_` ones) to match the distilled
1.1 transformer. `ref0.5` means the LoRA was trained with the control at **half** the output size;
the `LTXAddVideoICLoRAGuide` node does the halving, so feed the control at full size.
The repos can be checked by hand at `https://huggingface.co/api/models/<repo>` (`"gated": false`).

## 5. Create and set up the session (local)

```bash
python tools/colab/setup_session.py ltx      # --no-image: without §6.4's models; --gpu G4; --latest
```
One command, run from the repository root (any session name works; several sessions can run side by
side under different names). [`tools/colab/setup_session.py`](../tools/colab/setup_session.py):
- reuses `ltx` when `colab sessions` lists it, or else runs `colab new -s ltx --gpu L4` (8 s to 3 min;
  billing starts at "Session READY"). A try can fail after ~3 min with `ColabRequestError ...
  accelerator=L4: Service Unavailable` (HTTP 503: no capacity; nothing billed): the script tries 4
  times, a minute apart;
- asks the VM what is done (`vm_state.py`) and skips it: the done markers
  `/content/.vidgen_setup_ltx_done` and `/content/.vidgen_setup_image_done`, or all the part's files
  in `ComfyUI/models` when the marker is missing, and a ComfyUI that answers on 127.0.0.1:8188;
- uploads and starts the missing setups detached, `setup.sh` and `setup_image.sh` side by side,
  checks on the VM that each one runs (the first `colab exec` of a new session can drop with
  `RuntimeError: Connection was lost.` before anything started), and prints their `###` milestones;
- starts ComfyUI (`start_comfy.py`) and waits until it answers;
- prints the session, its GPU, what it installed or reused, the elapsed time and the next commands.

It runs one `colab exec` at a time (two at once drop each other) and retries a dropped one. It never
stops the session, also not after an error: run it again to go on, or stop the session (§10). The test
VM: Python 3.13, torch 2.14.1+cu130, CUDA 13.0, L4 23 GB, 52 GB RAM, 236 GB disk.

## 6. What the setup installs, and the per-run steps (VM, started from local)

From here on, run the commands from `tools/colab/` (the scripts) with your inputs in `ltx-inputs/`
(wherever `prepare_inputs.sh` wrote; adjust the path).

### 6.1 The setup scripts

`setup.sh` (log `/content/setup.log`) does:
- `pip install -U "huggingface_hub[hf_xet]" hf_transfer` (hub 2.4.0; pip warns that `datasets`
  wants hub < 2.0: harmless here);
- the six downloads with `hf download <repo> <file> --local-dir /content/hf/<repo>` and
  `HF_XET_HIGH_PERFORMANCE=1`, in a background subshell while ComfyUI installs (`/content/download.log`);
- `git clone` of ComfyUI and four custom nodes (kept when already cloned), **checked out at the
  tested commits** (`setup_session.py --latest`, i.e. `PIN=0`, takes the latest instead):

  | repo | commit (date) | why |
  |---|---|---|
  | `Comfy-Org/ComfyUI` | `da8bd08e48deee74d9f6c3bc00aed365b00ec209` (2026-11-23) | the server |
  | `Lightricks/ComfyUI-LTXVideo` | `ced6bad92b82f90028e1e1fd5a37527302550fc5` (2026-11-12) | IC-LoRA nodes, tiled decode |
  | `city96/ComfyUI-GGUF` | `6ea2651e7df66d7585f6ffee804b20e92fb38b8a` (2026-01-12) | `UnetLoaderGGUF` |
  | `Kosinkadink/ComfyUI-VideoHelperSuite` | `4d907bee61e92c2e65af3bd6383a4e4d356126d1` (2026-09-01) | `VHS_VideoCombine` (mp4 with audio) |
  | `kijai/ComfyUI-KJNodes` | `187868f53a7d9df007dbfe85891dab41453f7933` (2026-11-23) | `VAELoaderKJ` (separate video / audio VAE files) |

- `pip install -r requirements.txt` for ComfyUI and each node **with the torch, torchvision and
  torchaudio lines removed**: Colab's CUDA build of torch must stay (a requirements file can pull a
  CPU or other-CUDA torch over it and break the GPU). After the install: torch 2.14.1+cu130,
  torchvision 0.29.1, torchaudio 2.11.0, gguf 0.19.0, transformers 5.22.1, numpy 2.4.6, av 19.0.2,
  safetensors 0.8.0, comfyui_frontend_package 1.59.11;
- symlinks of the weights into `ComfyUI/models/{unet,loras,vae,text_encoders}`, then
  `vm_state.py ltx` checks every file and the marker is written.

`setup_image.sh` (log `/content/setup_image.log`) downloads the image models of §6.4, waits for
`setup.sh`'s ComfyUI clone, links them and writes its marker the same way.

Timings: install ~70 s (the clone alone took 114 s once); downloads 178-186 s in all; **setup done
in ~3-5.5 min**; the image models ~4 min beside it.

### 6.2 ComfyUI

`start_comfy.py` runs `main.py --listen 127.0.0.1 --port 8188` (log `/content/comfy.log`) and
`nvidia-smi -l 1` into `/content/vram.csv` for the peak-VRAM numbers. `bash poll.sh ltx comfy` shows
the log's last lines and the GPU memory. Optional: `colab exec -s ltx -f object_info.py` prints the
input names of every node used (from `/object_info`); use it when a node's inputs changed after an
update.

### 6.3 Make the canny control (VM)

Upload the inputs, then run the canny **detached** with `start_bg.py` (a foreground `colab exec` that
loses its websocket kills the work with it: run 2 lost a canny that way):
```bash
for f in ../../ltx-inputs/*; do colab upload -s ltx "$f" "/content/$(basename "$f")"; done
colab upload -s ltx start_bg.py /content/start_bg.py
colab upload -s ltx make_canny_soft.py /content/make_canny_soft.py
colab exec -s ltx -f start_bg.py --env NAME=cannysoft --env CMD="python /content/make_canny_soft.py" \
  --env SRC=/content/render_121_960x512.mp4 --env DST=/content/cannysoft_121_960x512.mp4
echo '!cat /content/cannysoft.log' | colab exec -s ltx     # "canny-soft frames 121 ..." when done (~1 min)
echo '!cp /content/depth_121_960x512.mp4 /content/cannysoft_121_960x512.mp4 /content/first_frame_960x512.png /content/ComfyUI/input/' | colab exec -s ltx
```
(The plain canny of run 1: the same with `make_canny.py` and `DST=/content/canny_121_960x512.mp4`.)
`LoadVideo` / `LoadImage` read from `ComfyUI/input/`. A sun-glint sea gives a lot of edges (6.6 %
of pixels in the middle frame) that LTX reads as surf. `make_canny_soft.py` (defaults `BLUR=0`,
92 / 200, `GLINT=150`, `FEATHER=31`) removes the edges where the frame, blurred over 41 px, is
brighter than 150: 3.2 % left, the glider's outline and the darker sea kept, the glint empty. Do not
blur before the canny (`BLUR=5` lost most of the glider's outline in run 2).

### 6.4 Make a photoreal first frame (VM; run 2, recommended)

With the CG frame 0 as the first frame, LTX keeps the CG look; without one, it invents (§12). The fix
that worked: restyle frame 0 into a photo with an image-editing model **on the same VM**, then give
that picture to LTX as the first frame. Only the look must change: the subject's position, size,
attitude and outline, the horizon and the glint must stay where they are.

**Model: Qwen-Image-Edit-2511** (GGUF Q4_K_M) with the 4-step Lightning LoRA. An edit model takes the
frame itself as its reference, so the layout is kept by construction; with the Lightning LoRA it is
4 steps. The other family tried, Z-Image-Turbo + Fun ControlNet Union 2.1 (canny or depth) as
img2img, gave a real sea but **replaced the glider** with a wider F/A-18-like jet (denoise 0.55-0.75):
not usable here. FLUX.1 schnell / dev / Kontext are gated (`"gated": "auto"`): not used.

| repo (all `gated: false`) | file | size |
|---|---|---|
| `unsloth/Qwen-Image-Edit-2511-GGUF` | `qwen-image-edit-2511-Q4_K_M.gguf` | 12.84 GB |
| `lightx2v/Qwen-Image-Edit-2511-Lightning` | `Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors` | 0.85 GB |
| `Comfy-Org/Qwen-Image` | `split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors` | 9.38 GB |
| " | `split_files/vae/qwen_image_vae.safetensors` | 0.25 GB |
| `Comfy-Org/Z-Image-Turbo` (tried, not chosen) | `z_image_turbo_bf16`, `qwen_3_4b`, `ae` (`split_files/...`) | 12.31 + 8.04 + 0.34 GB |
| `alibaba-pai/Z-Image-Turbo-Fun-Controlnet-Union-2.1` (tried) | `Z-Image-Turbo-Fun-Controlnet-Union-2.1-8steps.safetensors` | 6.71 GB |

(Commits on 2026-11-24 in `check_hf.sh --image`'s output; the fp8 Qwen-Image-Edit-2511 is 20.5 GB,
too big beside its text encoder on 24 GB, hence the GGUF.)
`setup_session.py` installed these models (unless `--no-image`). Steps:
```bash
for f in prep_image_inputs.py align_check.py free_vram.py; do colab upload -s ltx "$f" "/content/$f"; done
colab exec -s ltx -f prep_image_inputs.py      # ComfyUI/input/ff_up.png (frame 0 at 1440x768), ff_canny.png, ff_depth.png
python build_image_workflow.py qwen --run qwen_c --out workflow_qwen_c.json      # local
colab upload -s ltx workflow_qwen_c.json /content/workflow_qwen_c.json
colab exec -s ltx --env RUN=qwen_c -f start_job.py
bash poll.sh ltx job qwen_c                    # ~110 s the first time (load), ~25 s after
colab download -s ltx /content/ComfyUI/output/qwen_c_00001_.png qwen_c.png
```
The graph (`build_image_workflow.py qwen`): `UnetLoaderGGUF` -> `LoraLoaderModelOnly` (Lightning, 1.0)
-> `ModelSamplingAuraFlow` (shift 3.1) -> `CFGNorm`; `CLIPLoader` (`qwen_image`); the prompt through
`TextEncodeQwenImageEditPlus` with `image1` = the frame and **no `vae`**, then `ReferenceLatent` with the
frame's own `VAEEncode` and `FluxKontextMultiReferenceLatentMethod` (`index_timestep_zero`); `KSampler`
seed 42, 4 steps, cfg 1, euler, simple, denoise 1.0 on that same latent; decode, save at 1440x768
(`<run>_full_`) and scaled to **960x512** (`<run>_00001_.png`). Frame 0 is upscaled to 1440x768 first
(1.5x, same 15:8 aspect, ~1.1 MP, multiples of 16). Feeding the reference latent yourself keeps it on
the output's grid: through the encoder's `vae` input it is rescaled to ~1 MP and can shift.

**The prompt matters most.** "Make the sea real ocean water" (prompt A) kept the CG ripple pattern; naming
it worked (prompt C, the script's default): "*Replace the regular, repeating computer-generated ripple
pattern of the water with real, irregular open-ocean waves ...*", together with "*Do not move or resize
anything: the aircraft's position, size, angle and outline, the horizon line and the bright sun glint
... must stay exactly where they are.*" Make 2-3 candidates (seed, prompt) and keep the best.

**Alignment check.** `align_check.py` (VM, or locally with OpenCV) writes, for each candidate, an
overlay of the two canny maps (frame 0 red, candidate green, both yellow) and an edge F-score (3 px
tolerance) for the whole frame and the subject's box:
```bash
colab exec -s ltx -f start_bg.py --env NAME=align --env CMD="python /content/align_check.py" \
  --env REF=/content/first_frame_960x512.png --env OUT=/content/align \
  --env CANDS="/content/ComfyUI/output/qwen_a_00001_.png /content/ComfyUI/output/qwen_c_00001_.png"
echo '!cat /content/align.log' | colab exec -s ltx
```
Read it with care: the score counts the sea's texture too, so the candidate that rightly replaces the
CG sea scores lower (run 2: 0.815 for the CG-sea qwen_a, 0.50 for the chosen qwen_c, while the glider's
outline sits on frame 0's in both). The automatic horizon row is fooled by the haze the model adds:
**check the overlay, a zoom of the subject and of the horizon by eye** (run 2: within ~4 px).
Then put the chosen frame where LTX reads it and free the image models before LTX:
```bash
echo '!cp /content/ComfyUI/output/qwen_c_00001_.png /content/ComfyUI/input/photoreal_qwen_c.png' | colab exec -s ltx
colab exec -s ltx -f free_vram.py          # POST /free: unload all models
```
Switching between the image models and LTX in one ComfyUI costs a reload (~80-120 s): group the runs
by model.

## 7. Build and submit the workflow

### 7.1 Build the API-format graph (local)

```bash
python build_workflow.py --experiment --out-dir /some/dir      # the 7 graphs of the test
python build_workflow.py --run canny_noff --control canny_121_960x512.mp4 --no-first-frame
python build_workflow.py --run dc --control depth_121_960x512.mp4 \
  --second-control canny_121_960x512.mp4 --first-frame-strength 0.5 --prompt-file prompt.txt
python build_workflow.py --run pr_cannysoft --control cannysoft_121_960x512.mp4 \
  --first-frame photoreal_qwen_c.png         # run 2's best: photoreal first frame, glint-masked canny
```
`--experiment` writes the seven graphs byte for byte as they were run (checked in Step 404).
The graph is the official `example_workflows/2.3/LTX-2.3_ICLoRA_Union_Control_Distilled.json`
(ComfyUI-LTXVideo) translated to API format, with GGUF loaders:

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
| 13 | `LTXVImgToVideoConditionOnly` | strength 1.0 (0.5 tried); **`bypass: true` = no first frame** |
| 14 | `LTXAddVideoICLoRAGuide` | frame_idx 0, strength 1.0, `latent_downscale_factor` from node 2, crop disabled, no tiled encode (256 / 64) |
| 31 | second `LTXAddVideoICLoRAGuide` | only for two controls (depth + canny): chained after 14 (nodes 29 / 30 load it) |
| 15 / 16 | `LTXVEmptyLatentAudio` + `LTXVConcatAVLatent` | LTX-2.3 makes video and audio together |
| 17-21 | `RandomNoise` 42, `KSamplerSelect` `euler_ancestral_cfg_pp`, `ManualSigmas` `1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0` (8 steps), `CFGGuider` cfg 1.0, `SamplerCustomAdvanced` | |
| 22-25 | `LTXVSeparateAVLatent` -> `LTXVCropGuides` -> `LTXVTiledVAEDecode` (2x2, overlap 6); `LTXVAudioVAEDecode` | |
| 26 | `VHS_VideoCombine` | 24 fps, h264 mp4, yuv420p, crf 16, with audio; prefix `ltx_<run>` |

Differences from the official workflow: the distilled-1.1 GGUF in place of the dev checkpoint +
distilled LoRA 0.5 (**do not add the distilled LoRA on top**); `DualCLIPLoader` in place of
`LTXAVTextEncoderLoader` (that one wants a full checkpoint, which a GGUF setup does not have);
`VAELoaderKJ`; the control prepared outside the graph; VHS output in place of `CreateVideo` /
`SaveVideo`. Single stage, no upscaler.

### 7.2 Submit, detached

```bash
for f in run_job.py workflow_canny_noff.json; do colab upload -s ltx "$f" "/content/$f"; done
colab exec -s ltx --env RUN=canny_noff -f start_job.py
```
`start_job.py` starts `run_job.py` in the background: it POSTs the graph to `/prompt`, polls
`/history/<id>` every 3 s, and writes `/content/job_<run>.json` (wall time, status, outputs, peak
VRAM from `vram.csv`). Jobs queue in ComfyUI, so several can be started one after another.

## 8. Poll and download (local)

```bash
bash poll.sh ltx job canny_noff                 # empty until done; shows the step counter
bash fetch_outputs.sh ltx canny_noff out        # out/canny_noff_with_audio.mp4, out/canny_noff.mp4, out/job_canny_noff.json
```
One poller at a time, short calls (`timeout 90` is built in): a background wait loop and a manual
look at the same time drop each other's websocket (hit in run 2). The first run of a session takes
~75 s longer (loading the models and encoding the prompt).

## 9. Make a comparison video (local)

```bash
bash make_compare.sh compare.mp4 4 "CG render=ltx-inputs/render_121_960x512.mp4" \
  "canny, no first frame=out/canny_noff.mp4" "depth+canny, no first frame=out/depth_canny_noff.mp4"
```
Labelled 640x340 panels in a grid of N columns, played in step. Look at single frames too
(`ffmpeg -i compare.mp4 -vf "select=eq(n\,60)" -frames:v 1 f60.png`): watch the horizon and the
subject's design. Flicker: `ffmpeg -i clip.mp4 -vf "tblend=all_mode=difference,signalstats" -f null -`
style per-frame differences; no run of the test had spikes.

## 10. Stop the session when you are done (local)

Between experiments, leave it running (see the note at the top): reuse it with `colab sessions` and
`-s ltx`. When the owner says you are done:
```bash
colab stop -s ltx          # "Session terminated."
colab sessions             # "No active sessions found on server."
colab usage                # balance and current rate (0.00/hr when nothing runs)
```
Do this even after an error. Download everything you need first; the VM's disk is gone afterwards.

## 11. Costs and timings (L4, 960x512, 121 frames, 8 steps)

| item | measured |
|---|---|
| session start | 8 s-3 min (plus a 503 retry: hit in both runs) |
| setup (install + 34 GB of downloads) | ~3-5.5 min |
| `setup_session.py` on a ready session (everything skipped) | 10-20 s |
| `setup_session.py` on a new session (2026-11-24) | 23 min: one 503 and the session ~5 min, the first uploads ~3 min, both setups 4 min 45 s side by side, ComfyUI 6 min 40 s (most of it `colab exec` calls that hung and were retried) |
| image models (§6.4: 50 GB more, in parallel) | ~4 min |
| Qwen-Image-Edit, one 1440x768 picture, 4 steps | ~110 s with the model load, ~25 s after; peak ~19.5 GB |
| Z-Image-Turbo + ControlNet, 8 steps | ~115 s with the load, ~17 s after; peak ~21.7 GB |
| first LTX run after the image models | ~316 s (LTX load again) |
| first run of a session | ~267 s (incl. ~75 s model load + text encode) |
| later runs, one control | ~192-195 s (~22 s a step) |
| later runs, two controls | ~223-225 s (~25.7 s a step, +17 %) |
| peak VRAM (nvidia-smi, device) | ~21.3 GB of 23 GB; RAM ~5 GB + page cache |
| whole test (7 runs) | 40 min of L4, about **1.3 compute units** (balance showed -1.14 right after the stop) |
| run 2 (6 stills + 4 clips) | 54 min of L4 to the last download, about **1.7 units** (session then left running) |

## 12. Results of the tests (honest)

### Run 1: CG first frame or none

All 7 runs: seed 42, 960x512, 121 frames, 24 fps, 8 steps, cfg 1, GGUF Q5_K_M distilled-1.1, IC-LoRA
and guide strength 1.0. All succeeded; no OOM; **no flicker in any run**.

| run | first frame | real footage? | camera / horizon | subject |
|---|---|---|---|---|
| depth | CG, 1.0 | no, keeps the CG look | **horizon rolls 15-20°** by the end | the CG glider, almost exact |
| canny | CG, 1.0 | no (slightly more photographic sea) | level, matches | CG glider |
| depth + canny | CG, 1.0 | no | level, matches | CG glider |
| depth + canny | CG, 0.5 | a bit more real, still reads CG | level, matches | close to CG, softened |
| depth | none | **yes** (foam, haze, motion blur) | **camera roll swings 20-30°**, changes direction | a generic grey jet |
| canny | none | **yes, the most photographic** | level, stable | front-lit look; **invents a sandy beach and surf on the right** |
| depth + canny | none | **yes** | level, stable | rear view right, red stripe hint; same invented beach |

**Verdict.** With the CG first frame the result keeps the CG look (0.5 helps only a little).
Without it the result looks like real footage, and with canny or depth + canny the horizon is level
and stable, **but** the model invents a beach on the right (it reads the sun-glint edges as surf)
and changes the glider's design. Depth alone does not hold the camera: in 1 / z depth the far sea
and the sky are both black, so there is no horizon line and the model invents its own bank.
Nothing here is usable as-is for the film; the route works and is cheap.

### Run 2: a photoreal first frame (§6.4)

First frame: Qwen-Image-Edit-2511's `qwen_c` (prompt C, seed 42), first-frame strength 1.0 unless
said; otherwise the same settings as run 1. All succeeded; no OOM; no flicker (no spikes in the
per-frame difference; it is about twice the render's because real, high-contrast waves move).

| run | control | real footage? | glider and sea | horizon |
|---|---|---|---|---|
| `pr_canny` | canny | **yes** (open ocean, swells, whitecaps, haze) | glider kept (place, size, bank, outline, red stripe and wing tips); **no beach**; white foam-like streaks where the glint edges were | level, stable |
| `pr_depth_canny` | depth + canny | yes | as canny, busier white sparkle patches | level, stable |
| `pr_cannysoft` | glint-masked canny (`make_canny_soft.py`) | **yes, the best** | glider kept, **no beach**, a smooth natural glare where the glint is | level, stable |
| `pr_canny_ff07` | canny, first frame 0.7 | yes | almost the same as `pr_canny` | level, stable |

**Verdict.** The photoreal first frame is what was missing: every run looks like real aerial footage,
keeps our glider and the open sea (no invented beach) and a level horizon (~4 px below the CG one,
under a haze band the image model added). Best: **photoreal first frame + glint-masked canny**. Still
not perfect: the glider's surface looks a little clean/plastic, and its twin nozzles merged into one
dark shape and the green wing-tip light went missing (already in the photoreal frame, so LTX kept
that). Depth adds nothing over canny here. Strength 0.7 changes little.

**Next ideas (untested):**
- keep the subject's details in the photoreal frame: edit only the background (a mask) or paste the
  CG subject back and let the edit blend it;
- a photoreal frame for the **last** frame too, for long shots;
- a sparse canny of only the subject and the horizon with the depth;
- a **depth convention that keeps the horizon visible** (e.g. a floor so the far sea is not black like
  the sky, or a gamma; `vidgen.web.depth` normalises per shot, the place to add it).

## 13. Troubleshooting

"hit" = it happened in the test; "avoided" = found in the workflow or the node specs before it could.

| symptom | cause | fix |
|---|---|---|
| (hit) `colab new` fails after ~3 min: `ColabRequestError ... accelerator=L4: Service Unavailable` | no L4 capacity (HTTP 503) | `setup_session.py` tries 4 times a minute apart; if all fail, run it again later (nothing billed) |
| (hit, twice) `RuntimeError: Connection was lost.` from `colab exec` | the websocket dropped under heavy network use (big downloads) or two `exec` calls at once | the remote command usually finished: poll again; one poller only; keep calls short (`timeout 90`); start long work detached (`Popen(..., start_new_session=True)`) |
| (hit, run 2) the same error on the **first** `exec` of a new session, or on a foreground script | the websocket dropped before or while the code ran | the code did **not** run, or died with the connection: check (`ls /content`, the log) and run it again (`setup_session.py` does this for the setup); run anything over ~20 s with `start_bg.py` |
| (hit, run 2) `colab exec` keeps failing right after a dropped call | the kernel is still busy or reconnecting | wait ~20 s and try `echo 'print(1)' \| colab exec -s ltx` before the next call |
| (hit, run 2) `colab download` of a small file hangs past its timeout | a slow or dropped transfer | run it again |
| (hit, 2026-11-24) a session that was running is gone from `colab sessions` | Colab ended it on its side (no `colab stop` was sent; the cause is not known) | its disk is gone: download outputs as soon as a run finishes; `setup_session.py <name>` makes a new one |
| (hit, run 2) `check_hf.sh` prints a JSON error for a repo | `curl -s` got "Temporary Redirect" (the repo was renamed) | fixed: `curl -sL` |
| (hit, run 2) `QwenImageDiffsynthControlnet` for Z-Image's Fun ControlNet 2.1 | the 2.1 patch has its own node | `ZImageFunControlnet` (`object_info_image.py` lists the inputs) |
| (hit, run 2) the image edit keeps the CG sea | the prompt only asked for "real water" | name the CG pattern and ask to replace it (prompt C, §6.4) |
| (avoided) `colab exec` gives up after 30 s without output (its `--timeout` default) | long work in the foreground | everything long goes through `start_*.py` (detached) |
| (avoided) guide and output sizes do not match | 960x544 with the `ref0.5` LoRA (the half-size guide is not a whole number of latents) | width and height multiples of 64: crop to 960x512 or render 1024x576 |
| (avoided) frame count off | LTX wants 8k+1 frames | 121 (or 97, 73 ...); `prepare_inputs.sh` checks it |
| (hit, in `/object_info`) `LTXAVTextEncoderLoader` has an empty `ckpt_name` list; `CheckpointLoaderSimple` / `LTXVAudioVAELoader` unusable | they want the full LTX checkpoint; a GGUF setup has none | `DualCLIPLoader` (`type: ltxv`), `VAELoaderKJ` for both VAEs (needs KJNodes), `UnetLoaderGGUF` |
| (avoided) GPU torch gone after installing node requirements | a requirements file reinstalled torch | `setup.sh` strips the torch / torchvision / torchaudio lines; keep Colab's torch |
| `setup_session.py` stops with "... stopped before it finished" and a log tail | a download or install failed on the VM | read the tail; run `setup_session.py` again: it keeps what is there and starts only the unfinished part |
| (hit, warning) pip: `datasets 4.8.5 requires huggingface-hub<2.0` | upgrading the hub for `hf download` + xet | harmless here (datasets is not used) |
| (possible) download of `ltx_<run>_00001-audio.mp4` fails | a second run with the same prefix writes `_00002` | `colab ls -s ltx /content/ComfyUI/output` |
| (possible) a node's inputs changed after an update | node versions moved | the tested commits (`setup_session.py` without `--latest`) or `object_info.py` to read the new names |

## 14. Scaling to the G4 (96 GB) — untested

`python tools/colab/setup_session.py ltx-g4 --gpu G4` (RTX PRO 6000, 96 GB; check its rate with `colab usage`) could run the
model unquantized and the official workflow almost unchanged:
- `Lightricks/LTX-2.3` (ungated): `ltx-2.3-22b-distilled-1.1.safetensors` (46.15 GB), or
  `ltx-2.3-22b-dev.safetensors` (46.15 GB) + `ltx-2.3-22b-distilled-lora-384-1.1.safetensors`
  (7.61 GB) at 0.5 as in the official graph; the full checkpoint also lets `LTXAVTextEncoderLoader`
  and `CheckpointLoaderSimple` be used;
- the full Gemma: `Comfy-Org/ltx-2` `split_files/text_encoders/gemma_3_12B_it.safetensors` (24.38 GB);
- a second stage with `ltx-2.3-spatial-upscaler-x2-1.1.safetensors` (1.00 GB) for twice the size
  (also there: `-x1.5-1.0`, 1.09 GB, and `ltx-2.3-temporal-upscaler-x2-1.0.safetensors`, 0.26 GB).
None of this was run: sizes from the Hugging Face API on 2026-11-24; the download alone is ~75 GB.

## 15. As a service later (Cloudflare quick tunnel) — untested

To let vidgen call the VM like a video API: start `cloudflared tunnel --url http://127.0.0.1:<port>`
on the VM (a `trycloudflare.com` address, no account) in front of a small HTTP wrapper, not ComfyUI
itself:
- **submit and poll**: `POST /jobs` (graph or inputs) returns a job id at once; `GET /jobs/<id>`
  returns the state and, when done, the result's URL. A quick tunnel cuts a request after about
  **100 s** and does not carry server-sent events reliably, so no long request and no SSE / websocket
  progress;
- a **bearer token** on every request (the address is public); generate it per session, never commit it;
- uploads of the control videos as files, results fetched with a GET;
- stop the tunnel with the session.
vidgen already uses quick tunnels for Seedance inputs (`videogen.host: quick_tunnel`); Step 402 saw
two tries fail on DNS of a new address before it resolved: retry the resolve before using it.

## Files

[`tools/colab/`](../tools/colab/): `setup_session.py`, `check_hf.sh`, `prepare_inputs.sh` (local);
`vm_state.py`, `setup.sh`, `setup_image.sh`, `start_setup.py`, `start_bg.py`, `start_comfy.py`,
`object_info.py`, `object_info_image.py`, `make_canny.py`, `make_canny_soft.py`,
`prep_image_inputs.py`, `align_check.py`, `free_vram.py`, `run_job.py`, `start_job.py` (VM, started
with `colab exec`); `build_workflow.py`, `build_image_workflow.py`, `poll.sh`, `fetch_outputs.sh`,
`make_compare.sh` (local).
The full log of both tests (`RUNLOG.md`, run 2 in its "Run 2 (photoreal first frame)" section), their
graphs (`colab/`, `colab2/`), logs, `pip_freeze.txt`, the candidates and the clips (`out/`, `out2/`) stay
outside the repo, in the owner's `video-projects/footage-test/ltx-test/`.
