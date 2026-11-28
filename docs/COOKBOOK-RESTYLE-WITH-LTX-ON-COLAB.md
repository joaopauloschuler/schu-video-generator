# HOWTO: restyle a vidgen render into real-looking footage with LTX-2.3 on Colab

Take a shot vidgen rendered (here a `space` scene: a glider chased low over a rough sea), give its
**canny edges** (and optionally its **depth**) as control videos to the open video model **LTX-2.3**
with the IC-LoRA **`Lightricks/LTX-2.3-22b-IC-LoRA-Union-Control`**, with a photoreal first frame
made on the same GPU, in **ComfyUI on a Google Colab L4**, driven from your machine over SSH
(`colab ssh`). Everything downloaded is ungated on Hugging Face: no login, no token.

Scripts: [`tools/colab/`](../tools/colab/) (its [README](../tools/colab/README.md) lists them).
**local** = your machine, **VM** = the Colab machine.

> **Keep the session between experiments, stop it when you are done.** A new session's setup takes
> ~6 min and 35-85 GB of downloads; `python tools/colab/setup_session.py ltx` on a running `ltx`
> takes ~20 s. An idle L4 still bills ~1.94 units an hour, a G4 ~11.2: when the owner says you are done,
> `colab stop -s ltx` (§10).

## Recommended setup and why

- **Settings**: photoreal first frame (Qwen-Image-Edit-2511, §6.4) + **glint-masked canny**
  (`make_canny_soft.py`, §6.3), first-frame strength 1.0, seed 42, 8 steps, cfg 1, 960x512, 121 frames.
- **Inside vidgen**: the same as a shot: `videogen: {provider: comfyui, comfyui: {colab: ltx}}`,
  `model: ltx-2.3-union-control`, `guide: canny`, `first_frame: restyled`, then
  `vidgen generate inputs --guide` and `vidgen generate run --pay` ([CONFIG.md](CONFIG.md)).
- **A stylesheet with the base video** (`sheet:` + `sheet_prompt:` on the shot, `size:` / `duration:` for
  the clip, ComfyUI started with `--no-comfy-compiler`): §7.1.
- **Longer clips at 12 fps** (`fps: 12` on the shot): generated at 12 fps (2-10 s in even seconds, at most
  121 frames), doubled to 24 fps by RIFE 4.26 in the same ComfyUI job (§7.1, nodes 50 / 51). An 8 s clip is
  97 frames, the cost of a 4 s clip at 24 fps; each tick or sudden step is spread over 2 frames.
  `setup.sh` downloads the weights (`Comfy-Org/Frame-Interpolation`, ungated, 23 MB).
- **Which control video** (`guide: canny | final | depth` on the shot, each with or without a sheet, at
  12 or 24 fps). Measured once on the escapement's 8 s shot with a sheet (one seed,
  GUIDE-TEST.md in the escapement-remake project): `final`, the scene's own colour render, kept the parts
  and the lighting best and followed the camera from frame 0, but kept some of the render's look; `depth`
  invented surfaces where the render had texture and brightened; `canny` invented the most and lagged the
  camera by up to 2 s at the start. A web scene's depth needs its page to draw through
  `vidgen/three-finish` when `ctx.draw_mode` is `"depth"` (CONFIG.md, "A web scene's depth").
- **Sheets made by vidgen** (`subjects:` at the top, `subjects: [glider, sea]` on the shot): write each view
  as a `prompt:` (the picture in words); `vidgen remote NAME generate subjects` has Z-Image-Turbo draw each
  panel from the words alone on the session's ComfyUI (no picture of yours goes in; on an L4 about 25 s a
  panel, plus about 70 s for the first), all in one batch, then unloads the model, and writes
  `sheets/<subject>/contact.png`. A view made from a still (`from:` / `image:` with `text:`) is repainted by
  Qwen-Image-Edit instead (about 10 s a panel on a G4); a batch of both runs one model's panels, unloads it,
  then the other's. Look at the contact picture, then `vidgen generate subjects --approve NAME` (a shot is blocked until its panels are
  approved); `generate inputs` composes the shot's sheet from them; then `generate run --pay` as above
  (about 80 s for a 5 s clip with a sheet on a G4) ([CONFIG.md](CONFIG.md), "Subjects and a composed sheet";
  the guide's "Stylesheets").
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
| Inside vidgen | yes with `provider: comfyui` (takes, GPU units); or by hand with these scripts | yes: plan, budget, ledger, takes |
| Audio | makes its own (not used) | can take the film's sound (`audio: mix`) |

Use it to follow the render's layout and camera frame by frame, or to try ideas cheaply; use
Seedance for the paid, tracked path inside vidgen.

## 2. Prerequisites

- The **`colab` CLI** (google-colab-cli 0.8.0) installed and logged in (`colab usage` prints the
  balance); `colab skill` prints its own agent guide.
- **Compute units** on the account (an L4 is ~1.94 units an hour, a G4 ~11.2; `colab usage` shows the
  session's rate). On a G4 set `videogen.comfyui.units_per_hour: 11.2` (the default is the L4's).
- OpenSSH's client (`ssh`) and the key `~/.ssh/colab_ed25519` (`setup_session.py` creates it when
  missing). Everything goes over SSH: `setup_session.py`, `vidgen remote`, the comfyui provider and
  the hand commands below.
- No Hugging Face login.
- Locally: `ffmpeg` / `ffprobe`, Python 3.10+ (standard library only), `curl`; `rsync` for
  `vidgen remote` (without it, a tar sync).
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
| `Comfy-Org/ltx-2.3` | `f20f3a54378001e5e6d642acc84719cc78addf4b` | `split_files/loras/ltx-2.3-22b-ic-lora-ingredients-0.9.safetensors` | 1.31 GB |
| `Comfy-Org/Frame-Interpolation` | `aa7009be4d1471ea0bac91d6fe4d7e4b637cbbfc` | `frame_interpolation/rife_v4.26.safetensors` (12 fps shots) | 0.02 GB |

Use the `distilled_` VAE and connector files (not `dev_`) with the distilled-1.1 transformer.
`ref0.5`: trained with the control at half the output size; `LTXAddVideoICLoRAGuide` halves it, so
feed the control at full size. The Ingredients IC-LoRA (it reads a reference sheet) is the ungated
Comfy-Org copy; it is linked into `models/loras/` under its own name.

## 5. Create and set up the session (local)

```bash
python tools/colab/setup_session.py ltx      # --no-image: without §6.4's models; --gpu; --latest
python tools/colab/setup_session.py ltx --no-comfy-compiler   # ComfyUI with its model compiler off
python tools/colab/setup_session.py cpu1 --gpu CPU --high-mem --vidgen-only   # no GPU work: renders, ffmpeg
```
From the repository root; any name, several sessions side by side. It reuses or creates the session
(retrying HTTP 503), creates the SSH key when missing and checks SSH works, skips what is done,
starts the setups detached on the VM (`setsid nohup`), installs ComfyUI + LTX-2.3 and the image
models side by side, starts ComfyUI, installs vidgen while ComfyUI loads and prints a summary.
`--high-mem` asks for a high-RAM machine (new sessions; an L4 has one shape); [tools/colab/README.md](../tools/colab/README.md) has the
details. It never stops the session: after an error run it again (it goes on where it stopped).
`--no-comfy-compiler` starts ComfyUI with `--disable-comfy-compiler` (§6.2); a re-run with or
without it restarts a running ComfyUI whose setting differs. The summary says which one runs.
Test VM: Python 3.13, torch 2.14.1+cu130, CUDA 13.0, L4 23 GB, 52 GB RAM, 236 GB disk.

## 6. What it installs, and the per-run steps

Run the commands below from `tools/colab/`, with the inputs in `ltx-inputs/`. They use `vm`, a
shell function that runs a command on the session over SSH (the options vidgen uses):
```bash
vm() { ssh -F /dev/null -i ~/.ssh/colab_ed25519 -o IdentitiesOnly=yes -o LogLevel=ERROR \
  -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/dev/null \
  -o ProxyCommand="colab ssh --proxy-mode -s ltx -i ~/.ssh/colab_ed25519" root@colab "$@"; }
vm nvidia-smi                                  # a command on the VM, in /content
vm 'cat > /content/f.py' < f.py                # upload a file
vm cat /content/out.png > out.png              # download a file
```
`colab ssh --proxy-mode -s ltx` creates a missing session: use `vm` only on a session that
`colab sessions` lists. Calls may run in parallel. Long work runs detached:
`setsid nohup CMD > LOG 2>&1 < /dev/null & echo started $!`.

### 6.1 Installed versions

`setup.sh` checks out ComfyUI and five custom nodes at these commits (`--latest`: their newest),
installs their requirements **without the torch / torchvision / torchaudio lines** (Colab's CUDA
torch must stay) and links the weights into `ComfyUI/models/`:

| repo | commit (date) | why |
|---|---|---|
| `Comfy-Org/ComfyUI` | `da8bd08e48deee74d9f6c3bc00aed365b00ec209` (2026-11-23) | the server |
| `Lightricks/ComfyUI-LTXVideo` | `ced6bad92b82f90028e1e1fd5a37527302550fc5` (2026-11-12) | IC-LoRA nodes, tiled decode |
| `city96/ComfyUI-GGUF` | `6ea2651e7df66d7585f6ffee804b20e92fb38b8a` (2026-01-12) | `UnetLoaderGGUF` |
| `Kosinkadink/ComfyUI-VideoHelperSuite` | `4d907bee61e92c2e65af3bd6383a4e4d356126d1` (2026-09-01) | `VHS_VideoCombine` (mp4 with audio) |
| `kijai/ComfyUI-KJNodes` | `187868f53a7d9df007dbfe85891dab41453f7933` (2026-11-23) | `VAELoaderKJ` (separate video / audio VAE files) |
| `hashu786/comfyui-hrnodes` | `1f91974824c7e4e190d59aae9b38cd9cdd39a590` (2026-07-30) | `LTXMultiICLoRA` ("LTX Multi IC-LoRA": several IC-LoRAs at once, each on its own guide's tokens; no requirements) |

Resulting versions: torch 2.14.1+cu130, torchvision 0.29.1, torchaudio 2.11.0, gguf 0.19.0,
transformers 5.22.1, numpy 2.4.6, av 19.0.2, safetensors 0.8.0, huggingface_hub 2.4.0,
comfyui_frontend_package 1.59.11. pip's warning that `datasets` wants hub < 2.0 is harmless.

### 6.2 ComfyUI

`vm 'tail -n 5 /content/comfy.log; nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader'`
shows the log and GPU memory (also sampled into `/content/vram.csv`).
`vm python3 - < object_info.py` prints the inputs of every node used (after a node update).

ComfyUI 0.46's model compiler is on by default. With it on, `LTXMultiICLoRA` stalls at step 0
(one CPU core busy, the GPU idle); ComfyUI started with `--disable-comfy-compiler`
(`setup_session.py NAME --no-comfy-compiler`) runs it. The running ComfyUI's flags:
`vm "pgrep -af 'main.py'"`.

**On an L4** (22.5 GB usable), a clip with a sheet needs ComfyUI started for a small card:
`python tools/colab/setup_session.py NAME --gpu L4 --no-comfy-compiler --reserve-vram 10` (ComfyUI gets
`--disable-comfy-compiler --disable-dynamic-vram --reserve-vram 10`; a running one with other flags is
restarted by its PID). Then sheet clips of 97 frames complete: 4 s at 24 fps, or 8 s with `fps: 12`.
Measured on shot `04_escapement_2_b1` (768x448, text encoder on the CPU, 2026-11-26): peak 19.2 GB, about
26 s a sampling step, the text step on the CPU about 150 s, about 7 min in ComfyUI; the 4 s clip at 12 fps
(49 frames) peaked at 18.5 GB in 345 s. With dynamic VRAM (no flags) the first sampling step ran out of
memory, with `--reserve-vram 8` the second; tiled encode is not needed. 121 frames on an L4 were not
tried. A G4 needs none of this.
Render web scenes on the L4 with software WebGL: `VIDGEN_WEBGL=swiftshader vidgen remote NAME generate inputs
--guide ...` (`vidgen remote` passes this computer's `VIDGEN_WEBGL` to the run, over the VM's `gpu`). The L4's GPU
WebGL (Chromium, ANGLE on Vulkan) left black holes in gilded and reflective parts (up to 61 % of a frame in the
first frames of the escapement film's cathedral scene, 2026-11-26); SwiftShader had none, at about 1.2-1.7 min
a scene on the VM's CPU. A render made with the other backend is drawn again, not reused.

### 6.3 Canny control (VM)

Upload the inputs and run the canny detached:
```bash
tar cf - -C ../../ltx-inputs . | vm 'tar xf - -C /content'
vm 'cat > /content/make_canny_soft.py' < make_canny_soft.py
vm 'cd /content || exit 3; SRC=render_121_960x512.mp4 DST=cannysoft_121_960x512.mp4 \
  setsid nohup python3 make_canny_soft.py > cannysoft.log 2>&1 < /dev/null & echo started $!'
vm cat /content/cannysoft.log      # "canny-soft frames 121 ..." when done (~1 min)
vm 'cd /content && cp depth_121_960x512.mp4 cannysoft_121_960x512.mp4 first_frame_960x512.png ComfyUI/input/'
```
`make_canny_soft.py` (defaults `BLUR=0`, thresholds 92 / 200 as the official
`CannyEdgePreprocessor`, `GLINT=150`, `FEATHER=31`) removes edges where the frame blurred over 41 px
is brighter than 150: on the test shot 6.6 % edge pixels -> 3.2 %, the glider's outline and the
darker sea kept. Do not blur before the canny (`BLUR=5` loses the glider's outline). `make_canny.py`
is the plain canny (same call, `DST=canny_121_960x512.mp4`; also runs locally with OpenCV).
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
tar cf - prep_image_inputs.py align_check.py run_job.py | vm 'tar xf - -C /content'
vm 'cd /content && python3 prep_image_inputs.py'   # ComfyUI/input/ff_up.png (frame 0 at 1440x768), ff_canny.png, ff_depth.png
python build_image_workflow.py qwen --run qwen_c --out workflow_qwen_c.json      # local
vm 'cat > /content/workflow_qwen_c.json' < workflow_qwen_c.json
vm 'cd /content || exit 3; setsid nohup python3 run_job.py workflow_qwen_c.json qwen_c > job_qwen_c.log 2>&1 < /dev/null & echo started $!'
vm cat /content/job_qwen_c.json                # missing until done: ~110 s the first time (load), ~25 s after
vm cat /content/ComfyUI/output/qwen_c_00001_.png > qwen_c.png
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
vm 'cd /content || exit 3; REF=/content/first_frame_960x512.png OUT=/content/align \
  CANDS="/content/ComfyUI/output/qwen_a_00001_.png /content/ComfyUI/output/qwen_c_00001_.png" \
  setsid nohup python3 align_check.py > align.log 2>&1 < /dev/null & echo started $!'
vm cat /content/align.log
```
The score counts the sea's texture, so a candidate that rightly replaces the CG sea scores lower
(0.50 for the chosen `qwen_c` against 0.815 for a CG-sea candidate, both with the glider on frame 0's
outline), and the haze the model adds fools the horizon row: **check the overlay and zooms of the
subject and the horizon by eye** (`qwen_c`: within ~4 px). Then:
```bash
vm cp /content/ComfyUI/output/qwen_c_00001_.png /content/ComfyUI/input/photoreal_qwen_c.png
vm python3 - < free_vram.py                # POST /free: unload all models
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
| 3 | `DualCLIPLoader` | `gemma_3_12B_it_fp8_scaled` + `..._embeddings_connectors`, `type: ltxv`, `device: cpu` (vidgen's `videogen.comfyui.text_encoder: gpu` gives `default`) |
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

**With a stylesheet** (a shot's `sheet:` + `sheet_prompt:`, [CONFIG.md](CONFIG.md); trial run T2c of
2026-11-25, `video-projects/sheet-trial-2026-11-25/trial2/`), the same graph with these changes, node for node:

| id | node | key settings |
|---|---|---|
| 2 | `LTXMultiICLoRA` (comfyui-hrnodes) | `ic_lora_count` 2, `noisy_blend` 1.0; LoRA a `ltx-2.3-22b-ic-lora-ingredients-0.9`, strength 1.0, guide 0; LoRA b union-control `ref0.5`, strength 1.0, guide 1; outputs MODEL and one `latent_downscale_factor` per guide |
| 40 / 41 | `LoadImage` + `RepeatImageBatch` | the sheet at the output size, repeated to the clip's frame count |
| 42 | `LTXAddVideoICLoRAGuide` | the sheet: frame_idx 0, strength 1.0, `latent_downscale_factor` from node 2 output 1; fed by node 6 and node 13 |
| 14 | `LTXAddVideoICLoRAGuide` | the control, chained after 42, `latent_downscale_factor` from node 2 output 2 |

**At 12 fps** (a shot's `fps: 12`): frame rate 12 on nodes 6 and 15, the frame count (`duration x 12 + 1`)
on 12, 15 and 41, and after the decode:

| id | node | key settings |
|---|---|---|
| 50 | `FrameInterpolationModelLoader` (core) | `rife_v4.26.safetensors` in `models/frame_interpolation/` |
| 51 | `FrameInterpolate` (core) | images from node 24, multiplier 2: n frames become 2n - 1 |
| 26 | `VHS_VideoCombine` | images from node 51, 24 fps |

On an L4 the interpolation took 3-4 s and about 550 MiB of VRAM (FPS12.md, 2026-11-26).

The prompt starts `Reference sheet: <the panels>. Generated video: `. ComfyUI must run with
`--disable-comfy-compiler` (§6.2): vidgen checks it before sending such a shot and refuses otherwise.
The stock loaders (no routing) put the sheet's panels into the clip; only the routing node keeps them
apart. Inside vidgen, `vidgen generate run --pay` unloads the models (`POST /free`) once before its first job.

### 7.2 Submit, detached

```bash
vm 'cat > /content/run_job.py' < run_job.py
vm 'cat > /content/workflow_pr_cannysoft.json' < workflow_pr_cannysoft.json
vm 'cd /content || exit 3; setsid nohup python3 run_job.py workflow_pr_cannysoft.json pr_cannysoft \
  > job_pr_cannysoft.log 2>&1 < /dev/null & echo started $!'
```
`run_job.py` POSTs the graph to `/prompt`, polls `/history/<id>` every 3 s and writes
`/content/job_<run>.json` (wall time, status, outputs, peak VRAM). Jobs queue in ComfyUI.

## 8. Poll and download (local)

```bash
vm "cat /content/job_pr_cannysoft.json; grep -E '[0-9]+/8 ' /content/comfy.log | tail -n 1 | tr '\\r' '\\n' | tail -n 1"
mkdir -p out                                    # when job_pr_cannysoft.json is there:
vm cat /content/ComfyUI/output/ltx_pr_cannysoft_00001-audio.mp4 > out/pr_cannysoft_with_audio.mp4
vm cat /content/job_pr_cannysoft.json > out/job_pr_cannysoft.json
ffmpeg -v error -y -i out/pr_cannysoft_with_audio.mp4 -an -c copy out/pr_cannysoft.mp4
```
The job file is missing until the job ends; the `grep` shows the step counter. A second run of the
same graph writes `_00002`: `vm ls /content/ComfyUI/output`.

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
| `setup_session.py`, new session | ~6 min setup (both parts side by side) after the session is up |
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
| `setup_session.py` stops with "SSH to session NAME does not work" | `ssh` missing, the key refused, or `colab ssh` failing | check `vm echo ok`; or the exec route (below) |
| `vm` made a new session | `colab ssh --proxy-mode -s NAME` creates a missing one | check `colab sessions` first; stop the unwanted one |
| a `vm` call ends with exit 255 | the SSH connection dropped | run it again (detached work keeps running) |
| a running session is gone from `colab sessions` | Colab ended it (cause unknown) | its disk is gone: download outputs as each run finishes; `setup_session.py <name>` makes a new one |
| `setup_session.py` stops with "... stopped before it finished" and a log tail | a download or install failed on the VM | read the tail; run it again: it starts only the unfinished part |
| guide and output sizes do not match | 960x544 with `ref0.5` (half-size guide not a whole number of latents) | multiples of 64: 960x512 or 1024x576 |
| frame count off | LTX wants 8k+1 frames | 121 (or 97, 73 ...); `prepare_inputs.sh` checks it |
| `LTXAVTextEncoderLoader` has an empty `ckpt_name` list; `CheckpointLoaderSimple` / `LTXVAudioVAELoader` unusable | they want the full checkpoint; a GGUF setup has none | `DualCLIPLoader` (`type: ltxv`), `VAELoaderKJ`, `UnetLoaderGGUF` |
| GPU torch gone after node requirements | a requirements file reinstalled torch | `setup.sh` strips the torch lines; keep Colab's torch |
| `QwenImageDiffsynthControlnet` does not take Z-Image's Fun ControlNet 2.1 | 2.1 has its own node | `ZImageFunControlnet` (`object_info_image.py` lists the inputs) |
| the image edit keeps the CG sea | the prompt only asks for "real water" | name the CG pattern (prompt C, §6.4) |
| download of `ltx_<run>_00001-audio.mp4` fails | a second run with the same prefix writes `_00002` | `vm ls /content/ComfyUI/output` |
| a node's inputs changed | node versions moved | the pinned commits (no `--latest`) or `object_info.py` |

## The colab exec route (`--via exec`)

The other route: `colab exec` one call at a time, files through Cloudflare quick tunnels (needs
`cloudflared` on your PATH), no SSH key. Pick it per command with `--via exec`:
```bash
python tools/colab/setup_session.py ltx --via exec
vidgen remote --via exec ltx render             # before the session name
vidgen generate run --pay --via exec --shot ID  # the comfyui provider on Colab
```
`tools/colab/README.md` ("Two routes") has the details. The hand scripts `poll.sh` and
`fetch_outputs.sh`, and the `colab exec -f` header lines of the VM scripts, use this route.

## Files

[`tools/colab/`](../tools/colab/) (the [README](../tools/colab/README.md) says where each runs).
The test's graphs, logs, `pip_freeze.txt`, candidates and clips stay outside the repo, in the owner's
`video-projects/footage-test/ltx-test/`.
