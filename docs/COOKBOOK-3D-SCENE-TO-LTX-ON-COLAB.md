# Cookbook: from a 3D scene to LTX-2.3 footage on Colab

Make real-looking clips with the open video model **LTX-2.3** in **ComfyUI on a Google Colab L4**,
driven from your machine over SSH. vidgen keeps the story, the 3D scene, the stylesheet and the
assembly; LTX paints the footage. Everything downloaded is ungated on Hugging Face: no login, no token.
The paid route through OpenRouter (Seedance and others) is [COOKBOOK-3D-SCENE-TO-SEEDANCE.md](COOKBOOK-3D-SCENE-TO-SEEDANCE.md).
Settings: [CONFIG.md, Generated video](CONFIG.md#generated-video-videogen-vidgen-generate). Scripts:
[`tools/colab/`](../tools/colab/) (its [README](../tools/colab/README.md) lists them).
**local** = your machine, **VM** = the Colab machine.

**How much is known.** Every result here was measured once, with one seed (42), on 768x448 clips of
4 s at 24 fps, and judged from stills (contact sheets, crops, frame differences). Nobody has watched
the motion. The test subject was "a woman walking in a futuristic city" (projects `city-walk/` and
`starfall/` in the owner's `video-projects/`).

## The rule: first frame + stylesheet, no guide

**With LTX, give a shot a starting picture and a stylesheet, and no guide video.** That is what held
the picture, the place and the person in the one direct comparison (section 11.1). The parts:

- **The stylesheet** (section 6): up to 4 panels drawn by an image model **from text alone**, on the
  session's own GPU. Never give the image model a render, a frame or a control image. A ready-made
  picture of yours may be a panel as it is. The sheet keeps the person the same in every clip.
- **The starting picture** (section 7): the first frame of the clip. It sets the place and the look,
  and LTX holds it. An image model may paint it from a render of your 3D scene.
- **The prompt** carries the camera and the motion, because nothing else does: "The camera tracks
  steadily backwards in front of her at her pace". Short, positive words (section 6.3).

Why no guide: with a depth guide **the place comes from the guide**. It overrides the starting
picture (LTX drops it after frame 0: a cut inside the clip) and the sheet's street panel.
Blending the picture into the guide (`first_frame_in: guide`, the Seedance remedy) only turns that
cut into a 0.4 s morph. Without a guide, the camera and the motion come from the prompt alone: the
clip tracked backwards as asked, but did nothing of the blockout's planned orbit.

This differs from the Seedance cookbook's rule (a guide for every shot). There, the model decides
how much to follow a guide; here, LTX follows a depth guide frame by frame, so a guide is a strong
input that wins against the picture.

**Current limit.** vidgen cannot ask for this in `video.yaml` yet: `ltx-2.3-union-control` requires
a `guide:` (`canny`, `final` or `depth`), and `sheet:` is accepted only on that workflow. The no-guide
job is built with `tools/colab/build_noguide_workflow.py` and submitted by hand (section 8).

**When to use a guide instead** (section 9): when the layout or the camera path must be exact (an
orbit, a crane, where things stand). A blockout `type: 3d` scene sent as `guide: depth` does that,
inside vidgen, at known costs: the place follows the blockout's boxes, everything beyond the depth
range reads as open sky, and any bump on a stand-in is painted as something.

### The method in short

1. Set up the L4 session (section 3) and start the keepalive.
2. Write the panels as short prompts, make them with `vidgen remote ltx generate subjects`, approve the
   good ones, compose the sheet (section 6).
3. Make the starting picture (section 7) and look at it.
4. `/free` the GPU, then build and submit the no-guide job (section 8): **2 or 3 takes per shot**, each
   with another seed. Fetch them, look at stills, pick the best.
5. For a longer shot, start the next clip from the last frame of this one, and join the clips with
   `match_previous: true` (section 10).
6. Stop the session when the owner says you are done (section 15).

## 1. Which method

| | first frame + sheet, no guide (section 8) | blockout + depth guide + sheet (section 9) | restyle a render: canny or final guide (section 13) | Seedance on OpenRouter |
|---|---|---|---|---|
| the place | the starting picture's | the blockout's boxes, painted | the render's | the model's, from the guide and references |
| the person | the sheet | the sheet | the sheet or the first frame | the reference sheets |
| camera and motion | the prompt only | the guide, frame by frame | the guide | the guide, loosely |
| inside vidgen | no: built by hand (`build_noguide_workflow.py`) | yes (`provider: comfyui`) | yes | yes |
| cost | Colab units (about 0.26 for a 4 s clip) | about 0.30 | about 0.30 | dollars per clip |

## 2. Prerequisites

- The **`colab` CLI** (google-colab-cli 0.8.0) installed and logged in (`colab usage` prints the
  balance); `colab skill` prints its own agent guide.
- **Compute units** on the account. Set `videogen.comfyui.units_per_hour` to the rate `colab usage`
  shows for the session (vidgen's default is 1.94, the L4's; the city-walk projects used 2.33).
- OpenSSH's client (`ssh`) and the key `~/.ssh/colab_ed25519` (`setup_session.py` creates it when
  missing). Locally: `ffmpeg` / `ffprobe`, Python 3.10+, `rsync` for `vidgen remote` (without it, a tar sync).
- **Ask the owner before creating a GPU session** (it spends their units). Never create one silently:
  `colab ssh --proxy-mode -s NAME`, which every SSH call uses, creates a session that does not exist.
  Check `colab sessions` lists the session, as an L4, before you use it.

## 3. The session

### 3.1 Create and set up (local)

```bash
python tools/colab/setup_session.py ltx --gpu L4 --no-comfy-compiler --reserve-vram 10
```

From the repository root. It reuses the session `ltx` or creates it (retrying HTTP 503), creates the
SSH key when missing and checks SSH works, skips what is done, installs ComfyUI + LTX-2.3 and the image
models side by side, starts ComfyUI with `--disable-comfy-compiler --disable-dynamic-vram
--reserve-vram 10`, installs this checkout's vidgen and prints a summary. A new session takes about
6 min after it is up and downloads 35-85 GB; on a ready session it takes 10-20 s. It never stops the
session: after an error, run it again (it goes on where it stopped). Options:
[tools/colab/README.md](../tools/colab/README.md).

Why the flags, on an L4 (22.5 GB usable): a clip with a sheet ran out of memory in the first sampling
step with ComfyUI's dynamic VRAM, and in the second with `--reserve-vram 8`; with `--reserve-vram 10` it
completed at a peak of 19.2 GB. The routing node that a sheet + guide clip uses (`LTX Multi IC-LoRA`)
stalls at step 0 with ComfyUI's model compiler on, so vidgen refuses such a shot unless ComfyUI runs
with `--disable-comfy-compiler`. A re-run with other flags restarts a running ComfyUI (a job running
on it is lost). A G4 needs none of the VRAM flags.

### 3.2 When vidgen's code changed

`vidgen remote` refuses to run when the VM's vidgen differs from this checkout (also after
uncommitted edits) and prints the fix:

```bash
python tools/colab/setup_session.py ltx --vidgen-only     # 36-45 s; ComfyUI and the models are not touched
```

### 3.3 Keep it alive, and check it is the right machine

Two L4 sessions were ended by Colab while in use, with all work going over SSH. When an L4 is kept
between experiments, run the keepalive beside it for as long as the session is up:

```bash
python tools/colab/keepalive.py ltx --hours 8      # one tiny `colab exec` every 7 min, skipped when another call was recent
```

It never creates or stops a session, and it stops by itself when the session is gone. When a
session vanishes during a run, an SSH retry can create a new CPU session of the same name: check
`colab sessions` shows an L4 before you trust `ltx` again. The VM's disk goes with the session:
download each clip as its run finishes.

### 3.4 The `vm` helper

The hand steps below use `vm`, a shell function that runs a command on the session over SSH with the
options vidgen uses:

```bash
vm() { ssh -F /dev/null -i ~/.ssh/colab_ed25519 -o IdentitiesOnly=yes -o LogLevel=ERROR \
  -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/dev/null \
  -o ProxyCommand="colab ssh --proxy-mode -s ltx -i ~/.ssh/colab_ed25519" root@colab "$@"; }
vm nvidia-smi                                  # a command on the VM, in /content
vm 'cat > /content/f.py' < f.py                # upload a file
vm cat /content/out.png > out.png              # download a file
```

Use `vm` only on a session that `colab sessions` lists. Calls may run in parallel. Long work runs
detached: `setsid nohup CMD > LOG 2>&1 < /dev/null & echo started $!`.

## 4. What is installed

### 4.1 The Hugging Face repos

```bash
bash tools/colab/check_hf.sh            # add --image for the image models
```

It prints `gated=False` per repo and the file sizes. If a repo is gated, stop: never put a token in
these scripts.

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

The Union-Control IC-LoRA reads a control video (depth, canny); the **Ingredients** IC-LoRA reads a
reference sheet. Use the `distilled_` VAE and connector files with the distilled-1.1 transformer.
`ref0.5` was trained with the control at half the output size: width and height must be multiples of 64.

Image models (`setup_image.sh`; skip with `--no-image`):

| repo (all `gated: false`) | file | size |
|---|---|---|
| `Comfy-Org/Z-Image-Turbo` | `z_image_turbo_bf16`, `qwen_3_4b`, `ae` (`split_files/...`) | 12.31 + 8.04 + 0.34 GB |
| `unsloth/Qwen-Image-Edit-2511-GGUF` | `qwen-image-edit-2511-Q4_K_M.gguf` | 12.84 GB |
| `lightx2v/Qwen-Image-Edit-2511-Lightning` | `Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors` | 0.85 GB |
| `Comfy-Org/Qwen-Image` | `split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors`, `split_files/vae/qwen_image_vae.safetensors` | 9.38 + 0.25 GB |
| `alibaba-pai/Z-Image-Turbo-Fun-Controlnet-Union-2.1` | `Z-Image-Turbo-Fun-Controlnet-Union-2.1-8steps.safetensors` | 6.71 GB |

Z-Image-Turbo draws stylesheet panels from text. Qwen-Image-Edit repaints a picture (the starting
picture, section 7).

### 4.2 ComfyUI and its nodes

`setup.sh` checks out ComfyUI and five custom nodes at these commits (`--latest`: their newest),
installs their requirements **without the torch lines** (Colab's CUDA torch must stay) and links
the weights into `ComfyUI/models/`:

| repo | commit (date) | why |
|---|---|---|
| `Comfy-Org/ComfyUI` | `da8bd08e48deee74d9f6c3bc00aed365b00ec209` (2026-11-23) | the server (0.46) |
| `Lightricks/ComfyUI-LTXVideo` | `ced6bad92b82f90028e1e1fd5a37527302550fc5` (2026-11-12) | IC-LoRA nodes, tiled decode |
| `city96/ComfyUI-GGUF` | `6ea2651e7df66d7585f6ffee804b20e92fb38b8a` (2026-01-12) | `UnetLoaderGGUF` |
| `Kosinkadink/ComfyUI-VideoHelperSuite` | `4d907bee61e92c2e65af3bd6383a4e4d356126d1` (2026-09-01) | `VHS_VideoCombine` (mp4) |
| `kijai/ComfyUI-KJNodes` | `187868f53a7d9df007dbfe85891dab41453f7933` (2026-11-23) | `VAELoaderKJ` |
| `hashu786/comfyui-hrnodes` | `1f91974824c7e4e190d59aae9b38cd9cdd39a590` (2026-07-30) | `LTXMultiICLoRA` (several IC-LoRAs, each on its own guide) |

Test VM: Python 3.13, torch 2.14.1+cu130, CUDA 13.0, L4 23 GB, 52 GB RAM, 236 GB disk.
`vm "pgrep -af 'main.py'"` shows the running ComfyUI's flags; `vm python3 - < tools/colab/object_info.py`
prints the inputs of every node used (after a node update).

## 5. GPU memory: one model at a time

Batch all the work of one model, then unload it. Never interleave image and video jobs. Before
every LTX job, unload everything and check the card is nearly empty:

```bash
vm python3 - < tools/colab/free_vram.py        # POST /free to ComfyUI on 8188
vm nvidia-smi --query-gpu=memory.used --format=csv,noheader
```

Measured on `ltx`: 0.7 GB in use before each job; after a clip ComfyUI still held 3.3-10.4 GB, and
after a batch of panels it kept Z-Image (7.5 GB) loaded. `/free` brought it back to 0.4-0.7 GB each
time. `vidgen generate run --pay` posts `/free` once before its first job; a hand job does not.

**Two ComfyUIs on one card.** vidgen talks to the ComfyUI on port 8188, which runs with the L4 flags of
section 3.1. Those flags are for LTX; image models run on that same ComfyUI at 27 s a Z-Image-Turbo
picture (1440x768, 8 steps). The `ltx` session also has a second ComfyUI on port 8189 with default
flags, a separate checkout at the same commit (`/content/ComfyUI-img`, its own `models/` of
symlinks); `setup_session.py` does not make it. Both share the card's memory, so `/free` **both**
before an LTX job:

```bash
for p in 8188 8189; do vm "curl -s -X POST -H 'Content-Type: application/json' \
  -d '{\"unload_models\": true, \"free_memory\": true}' http://127.0.0.1:$p/free"; done
```

## 6. The stylesheet

### 6.1 Panels from text alone

Each panel is a picture an image model drew **from words only**. No render, no frame of a clip, no
canny or depth picture, no still of your scene goes into the image model: the image model's own
design is the look the video model follows, and the 3D scene carries only layout and motion. Panels
from repainted renders were judged very poor by the owner; panels from text were not.

In `video.yaml`, each panel is a subject view with only `prompt:` (from city-walk's `make_yaml.py`):

```yaml
subjects:
  back_d:
    look: the woman
    seed: 61
    views:
      - {name: v, prompt: "Full-body photo of a slim young East Asian woman with straight shoulder-length dark brown hair, wearing a white sleeveless top, black high-waisted shorts and black high heels, carrying a black handbag, walking away from the camera, seen from directly behind, mid-stride. Plain neutral grey studio background, soft even light, photoreal film still."}
  street_b:
    look: the futuristic city street
    location: true
    seed: 17
    views:
      - {name: v, prompt: "A wide futuristic city boulevard seen along its length at eye level: tall grey glass skyscrapers with curved balconies and warm white light strips, wet grey stone paving with soft reflections, a pale hazy dusk sky between the towers. Empty street, clean facades, cinematic film still, photoreal, anamorphic lens."}
```

```bash
vidgen remote ltx generate subjects .                      # Z-Image-Turbo, 1440x768, 8 steps, all panels in one batch
vidgen generate subjects . --approve back_d --approve street_b
```

To try several seeds, write the same view once per seed under different subject names, make them in
one batch, and approve the best. Look at every candidate at full size, corners too (stray marks, text).

### 6.2 What image models draw well

- **Subjects the image model knows from many real photos work**: people, cities, streets,
  landscapes. Seven words ("beautiful woman walking on a futuristic city") gave a picture the owner
  used as a panel as it was.
- **Original invented objects do not**: three rounds of text-only spaceship panels (90 candidates) gave
  aircraft with canopies, sea battleships with towers, literal objects (a tuning fork on a table) and
  drifts towards famous film ships. Exact machinery fails the same way, in the video model too: at
  768x448 LTX invents parts (extra springs, a bar, a plate) and on a mechanism every invention reads as
  a mistake. Pick bold, forgiving subjects.
- **Faces**: the first round of face panels did not look like the woman in the owner's picture; naming
  her look closer ("East Asian", "straight shoulder-length dark brown hair") in round 2 did.

### 6.3 Short, positive prompts

- **At most about 75 words.** The 52-68 word ship prompts followed shape far better than the long
  ones, and a 230-word prompt confused Z-Image-Turbo. The city-walk panels are 40-55 words.
- **Say what you want, never "no X".** Z-Image-Turbo runs at cfg 1, where a negative prompt does
  nothing, and a named negation adds the thing: "no canopy", "no tower", "not a wedge" gave canopies,
  towers and wedges. Write "a crescent moon carved from ivory", not "not an aircraft". "Fighter" and
  "pilot" bring a cockpit.
- **Share wording.** Write the person once (`WOMAN` = "a slim young East Asian woman with ... carrying
  a black handbag") and use the same words in every panel, the sheet prompt and the shot prompt.
- The same rules hold for the LTX shot prompt: the no-guide clip's prompt was 71 words, all positive.

### 6.4 Other image models (measured once, text only, on the L4)

`setup_session.py` installs only Z-Image-Turbo and Qwen-Image-Edit. On twelve short ship prompts with
the same seeds (`starfall/candidates_models/MODELS.md`): Z-Image-Turbo (ComfyUI, 8 steps, cfg 1) took
27 s a picture and was the most photographic; ERNIE-Image (bf16, a second ComfyUI, 50 steps, cfg 4)
followed the written shape best, with true black, a bit CG, at 165 s; HiDream-O1-Image (GGUF through
stable-diffusion.cpp, 50 steps, cfg 5) took 44-49 s and drew toy-like product shots on a green studio
backdrop. Licences: Apache-2.0 and MIT. Z-Image-Turbo stays the default for exploring; ERNIE-Image
when a shape must come out as written.

### 6.5 Compose the sheet

At most **4 panels** per sheet, in the grid that shows them largest (2x2 at 768x448), on black, no text.
The sheet must have the clip's aspect ratio. Two ways:

- **From approved subjects** (`subjects: [back_d, face_e, street_b]` on a shot): `vidgen generate inputs`
  composes `build/videogen/<shot>/sheet.png` and its sheet prompt. This works only on a guided shot.
- **By hand**, when a ready-made picture must be a panel as it is, or for the no-guide job. A subject
  view made from a picture file (`image:`) is always repainted by Qwen-Image-Edit, so a picture that must
  stay as it is cannot be a subject. Compose with vidgen's own layout (city-walk's
  `scripts/compose_sheet.py`, run with `PYTHONPATH=<repo>/src`):

```python
from pathlib import Path
from vidgen.videogen.sheet_layout import SheetPanel, compose_sheet, sheet_prompt

panels = [SheetPanel(Path("user/woman_city_user.png"), "the woman, walking across a stone plaza in a futuristic city"),
          SheetPanel(Path("sheets/back_d/v.png"), "the same woman seen from behind"),
          SheetPanel(Path("sheets/face_e/v.png"), "the same woman's face"),
          SheetPanel(Path("sheets/street_b/v.png"), "the futuristic city street")]
columns, rows = compose_sheet(panels, 768, 448, Path("sheet/citywalk_sheet.png"))
print(sheet_prompt(panels, columns, rows))   # "top left, ...; top right, ...; bottom left, ...; bottom right, ..."
```

The sheet prompt city-walk used: "top left, WOMAN, walking across a stone plaza in a futuristic city;
top right, the same woman seen from behind; bottom left, the same woman's face; bottom right, the
futuristic city street" (WOMAN written out). On a guided shot, use the file as `sheet:
sheet/citywalk_sheet.png` with that `sheet_prompt:`; a `sheet:` you supply needs no approval.

**The background.** LTX carries the sheet's brightness into the clip. `sheet_background: location`
keeps an indoor, lamp-lit scene lit; `black` suits daylight outdoor shots and dark scenes
([CONFIG.md](CONFIG.md), "Subjects and a composed sheet").

### 6.6 What the sheet does in the clip

In all four variants of section 11.1 the woman kept the sheet's face, white top, black shorts, heels
and handbag for the whole clip, and over 12 s of chained clips she did not drift. The hair drifted
when a depth guide was used (longer, wavy, wind-blown instead of the sheet's straight, neat hair); in
the no-guide clip it stayed as in the sheet.

## 7. The starting picture

The first frame of the first clip. Unlike panels, it may be painted from a render of your scene.

- **A picture file** you made (an image model, a photo you may use): fit it to the clip's size.
- **A repainted blockout frame** (`first_frame: restyled`, comfyui provider): `vidgen remote ltx
  generate inputs . --guide` renders the scene, and Qwen-Image-Edit-2511 repaints its first frame
  (about 112 s with the model load, 0.073 units) into `build/videogen/<shot>/first_frame.restyled.png`.
  `first_frame_prompt:` is the edit instruction. The one city-walk used, first attempt accepted:

  > Turn this computer-graphics picture into a real photograph of the same street, keeping the camera,
  > the street, the buildings and every position exactly as they are. The pale grey capsule standing in
  > the street is WOMAN: paint her standing upright exactly where the capsule is and as tall, facing the
  > camera, full body from her head to her heels, starting a step. The city: CITY. A cinematic 35 mm
  > film still with natural skin texture.

  This needs a guided shot in `video.yaml` (any `guide:`), because the shot must be valid; the clip
  itself can then be made without a guide (section 8). Check `overlay.png` (the picture over the
  guide's first frame): the figure sat exactly on the capsule. But Qwen also moved the buildings back,
  lowered the horizon and left out a bridge, and the overlay does not make background changes obvious.
  With no guide this does not matter. With a guide it is what made LTX drop the picture (section 11.1).

Fit a picture to the clip (cover, centre crop, Lanczos), as vidgen does:

```bash
ffmpeg -v error -y -i start.png -vf "scale=768:448:force_original_aspect_ratio=increase:flags=lanczos,crop=768:448,setsar=1" \
  -frames:v 1 start_768x448.png
```

## 8. First frame + sheet, no guide (`build_noguide_workflow.py`)

### 8.1 The graph

`tools/colab/build_noguide_workflow.py` writes the ComfyUI API graph of vidgen's
`ltx-2.3-union-control` workflow with a sheet, with the control video taken out. Compared with the graph
vidgen sends for a sheet shot:

| id | node | in vidgen's sheet + guide graph | in the no-guide graph |
|---|---|---|---|
| 2 | IC-LoRA loader | `LTXMultiICLoRA`: Ingredients (guide 0) + Union-Control (guide 1) | `LTXICLoRALoaderModelOnly`: the Ingredients IC-LoRA alone, strength 1.0 |
| 10 / 11 | `LoadVideo` + `GetVideoComponents` | the control video | removed |
| 14 | `LTXAddVideoICLoRAGuide` | the control, chained after 42 | removed |
| 9 -> 13 | `LoadImage` -> `LTXVImgToVideoConditionOnly` | the first frame, strength 1.0 | the same |
| 40 -> 41 -> 42 | `LoadImage` -> `RepeatImageBatch` -> `LTXAddVideoICLoRAGuide` | the sheet, repeated to the frame count, frame 0, strength 1.0 | the same; its downscale factor from node 2 output 1 |
| 16, 20, 23 | latent concat, `CFGGuider`, `LTXVCropGuides` | read node 14 | read node 42 |

Everything else is unchanged: the distilled-1.1 Q5_K_M GGUF (node 1), Gemma fp8 + connectors on the CPU
(node 3), 8 steps (`ManualSigmas`), cfg 1, sampler `euler_ancestral_cfg_pp`, seed 42, the negative "pc game,
console game, video game, cartoon, childish, ugly", tiled decode, `VHS_VideoCombine` h264 at crf 16, no
audio. The prompt is `Reference sheet: <sheet prompt>. Generated video: <prompt>`.

### 8.2 Commands

From the repository root, with the fitted starting picture and the sheet at the clip's size (both
768x448 here) and `vm` from section 3.4:

```bash
python tools/colab/build_noguide_workflow.py --run walk1 \
  --first-frame start_768x448.png --sheet citywalk_sheet.png \
  --sheet-prompt "top left, ...; top right, ...; bottom left, ...; bottom right, the futuristic city street" \
  --prompt-file prompt.txt --width 768 --height 448 --frames 97 --fps 24 --seed 42
#   writes workflow_walk1.json; output prefix ltx_walk1. File names are names in ComfyUI/input/ on the VM.
vm 'cat > /content/ComfyUI/input/start_768x448.png' < start_768x448.png
vm 'cat > /content/ComfyUI/input/citywalk_sheet.png' < citywalk_sheet.png
vm 'cat > /content/workflow_walk1.json' < workflow_walk1.json
vm 'cat > /content/run_job.py' < tools/colab/run_job.py
vm python3 - < tools/colab/free_vram.py                       # and 8189 too, if it runs (section 5)
vm 'cd /content || exit 3; setsid nohup python3 run_job.py workflow_walk1.json walk1 > job_walk1.log 2>&1 < /dev/null & echo started $!'
vm cat /content/job_walk1.json                                 # missing until the job ends (about 7 min on an L4)
vm cat /content/ComfyUI/output/ltx_walk1_00001.mp4 > walk1.mp4
vm python3 - < tools/colab/free_vram.py                        # after the last job
```

`run_job.py` posts the graph to `/prompt`, polls `/history` every 3 s and writes
`/content/job_<run>.json` (wall time, status, outputs, peak VRAM). Jobs queue in ComfyUI. A second run
with the same prefix writes `_00002`: `vm ls /content/ComfyUI/output`.

The prompt of the measured clip (71 words; the sheet prompt goes before it):

> Establishing shot: Tracking shot, full body: the young woman in the white sleeveless top and black
> shorts walks towards the camera down a futuristic city street with a natural relaxed stride, her
> handbag in one hand. The camera tracks steadily backwards in front of her at her pace, keeping her
> centred and full body in frame. Glass skyscrapers with warm light strips, wet stone paving, soft hazy
> dusk light, cinematic 35 mm film.

Name the camera move in plain words; it is the only thing that sets it. Lengths: 8k+1 frames (97 = 4 s
at 24 fps, 121 = 5 s at most); width and height multiples of 64.

### 8.3 What it gives, and what vidgen does not do for it

Measured (section 11.1, variant A): 396 s of GPU, 0.257 units, peak 13.3 GB. Frame 0 is the picture
(mean absolute difference 4.0), no cut, no morph; the place and the woman are the picture's and the
sheet's for the whole 4 s. The camera tracked backwards at her pace with a small sideways sway.

A hand job has no take, no QA, no ledger line and no cache. Check it yourself: stills every 0.5 s, and
`ffmpeg -i walk1.mp4 -vf "select='gt(scene,0.08)',showinfo" -f null -` for cuts inside the clip
(variant A had no scene change above 0.08). To use it in a film, play it as a `video_clip` (section 10.2).

### 8.4 Two or three takes per shot

A video model does not do equally well on every run of the same prompt. Make **2 or 3 takes of each
shot**, each with another seed, judge them from stills, keep the best, and start the next clip of a
chain from the picked take's last frame. One bad take says nothing against the method. With the tool,
give each take its own `--seed` and `--run` name (the run name is the output prefix):

```bash
for s in 42 43 44; do
  python tools/colab/build_noguide_workflow.py --run walk1_s$s --seed $s \
    --first-frame start_768x448.png --sheet citywalk_sheet.png --sheet-prompt "..." --prompt-file prompt.txt \
    --width 768 --height 448 --frames 97 --fps 24
done
```

Submit the three graphs one after the other (they queue in ComfyUI; about 7 min each on an L4). On a
shot inside vidgen, `seed:` on the `generated_shot` does the same: another seed is another request, a
new take in `takes/<shot>/`, and `vidgen generate pick` chooses the one shown.

## 9. Blockout + depth guide (inside vidgen)

When the camera path or the layout must be exact. A plain `type: 3d` scene of primitives (boxes as
buildings, cylinders as lamps, flat colours, no textures or labels) goes to LTX as `guide: depth`; the
look comes from the sheet and the prompt.

```yaml
videogen: {provider: comfyui, comfyui: {colab: ltx, units_per_hour: 2.33}, budget_usd: 0}
scenes:
  - id: medium_capsule
    type: 3d
    params:
      background: "#c9c4bd"
      camera: {position: [1.3, 1.3, -37.0], look_at: [-0.6, 1.05, -40.0], fov: 40}
      floor: {size: 700, color: "#6b7077"}
      guide_passes: depth
      depth_range: [2, 120]
      objects:
        # ... the street: boxes and cylinders ...
        - {id: her, shape: standin, size: [0.45, 1.7, 0.4], position: [-0.6, 0.85, -40.0], color: "#e8e4de"}
    beats:
      - text: "Tick."
        pause: 3.6                    # the beat = 4.00 s
        actions:
          - {object_move: her, at: 0, by: [0, 0, 5.8], run_time: 4.0, easing: linear}
          - {action: camera_move, at: 0, to: [1.3, 1.3, -31.2], look_at: [-0.6, 1.05, -34.2], run_time: 4.0, easing: linear}
        generated_shot:
          kind: establishing
          model: ltx-2.3-union-control
          guide: depth
          audio: none
          line: false
          first_frame: none
          size: 768x448
          duration: 4
          fps: 24
          prompt: "Medium tracking shot, full body: WOMAN, walking towards the camera ..."
          sheet: sheet/citywalk_sheet.png
          sheet_prompt: "top left, WOMAN, walking across a stone plaza in a futuristic city; top right, ..."
```

```bash
vidgen validate .
VIDGEN_WEBGL=swiftshader vidgen remote ltx generate inputs . --guide       # about 50 s on the VM, no GPU job
#   look at build/videogen/<shot>/guide.depth.mp4 (frames 5, 45, 85) before paying
vidgen remote ltx generate run . --pay --shot medium_capsule_b1            # about 438 s of GPU, 8 min door to door
vidgen generate takes . --shot medium_capsule_b1
vidgen generate pick . --shot medium_capsule_b1 --take 1
```

Render with `VIDGEN_WEBGL=swiftshader` on the L4: its GPU WebGL left black holes in some renders. A
scene rendered with one backend is drawn again with the other. Use `first_frame: none` with a depth
guide (section 11.1).

**What the guide costs you.**

- **The place follows the blockout's boxes.** The sheet's tall-tower street became the guide's
  concrete plaza with a footbridge. Build the silhouettes you want: with depth only, outlines come
  from the primitives (a fighter kept its straight bar wings), surfaces and colour from the sheet.
- **Everything beyond `depth_range` reads as open sky.** Depth is linear in distance and clamped at
  the far end: with `[2, 40]` the right half of a street became sky over a plaza; with `[2, 120]` it
  had buildings on both sides. Keep the far end past the farthest building that must stay a building,
  or close the street within it. A very wide range costs contrast near the figure: with `[3, 260]` the
  stand-in nearly vanished into the floor.
- **Every bump is painted.** `standin` has a facing marker (its nose) that cannot be hidden; once the
  camera circled, the depth guide carried it and LTX painted a pale arm-like shape beside her shoulder
  for 5 s. For a guide, build a plain capsule from primitives (city-walk `continuous/testB`):

  ```yaml
  - {id: her, shape: group, position: [-0.6, 0.85, -40.0]}
  - {id: her_body, shape: cylinder, parent: her, size: [0.45, 1.3, 0.4], position: [0, 0, 0], color: "#e8e4de"}
  - {id: her_top, shape: sphere, parent: her, size: [0.45, 0.4, 0.4], position: [0, 0.65, 0], color: "#e8e4de"}
  - {id: her_foot, shape: sphere, parent: her, size: [0.45, 0.4, 0.4], position: [0, -0.65, 0], color: "#e8e4de"}
  ```

- **A built figure over-controls the person.** A figure of spheres and cylinders with swinging limbs
  (timed `object_rotate` on hip and shoulder pivots) gave the stride in the guide, but froze the legs
  in one wide split from 1 s to 4 s (a glide, seen only in dense crops). The plain capsule gave a real
  stepping cycle; the owner preferred it.
- **A starting picture fights the guide** unless it agrees with it exactly (section 11.1).
- `camera_orbit: her` with `run_time:` moves the camera round a moving figure in one action. A beat
  action's `at` counts only the beat's spoken words, not its `pause:`, so timed keyframes cannot be
  placed inside a silent beat's pause.

## 10. Longer shots: chained clips and the join

### 10.1 Start each clip from the last frame of the one before

`first_frame: last_of:<shot>` on the next shot. `vidgen generate inputs` cuts the last frame of the
take that shot shows into `build/videogen/<next shot>/last_of.<shot>.<take>.png`; pick the take you want
first. A beat longer than LTX's longest clip (5 s at 24 fps) is split by vidgen into `<beat>_p1`,
`_p2` ... of equal length, and each later part starts from the part before in the same way. Make them
in order: a run never pays for a clip and the clip it starts from in one pass.

```bash
vidgen remote ltx generate run . --pay --shot walk_p1
vidgen generate pick . --shot walk_p1 --take 2
VIDGEN_WEBGL=swiftshader vidgen remote ltx generate inputs . --guide --shot walk_p2
vidgen remote ltx generate run . --pay --shot walk_p2
```

**The frame holds when it agrees with what the model is otherwise told.** With a depth guide and the
sheet, parts 2 and 3 of the 12 s walk opened with a match of 0.992 each and no cut warning: a frame
from LTX's own previous clip agrees with the guide. A repainted picture that did not agree was dropped
(section 11.1). For no-guide clips, cut the last frame of the picked take by hand and give it to the tool as
`--first-frame`:

```bash
ffmpeg -v error -y -sseof -0.1 -i walk1.mp4 -update 1 -frames:v 1 walk1_last.png
```

Each later clip's frame 0 is a copy of that picture: drop it when joining (below), so 3 clips of 97
frames cover exactly 288 frames (12.00 s).

### 10.2 The join: a `video_clip` film

Put the picked takes in a separate config, one `video_clip` per clip, with `trim:` dropping frame 0 of
each later clip and `match_previous: true` on each clip that continues the one before (city-walk
`continuous/film_match.yaml`, written by `make_film.py`):

```yaml
title: City walk, continuous 12 s
output: continuous_match
format: {width: 768, height: 448, fps: 24}
preview: {width: 768, height: 448, fps: 24}
transition: cut
scenes:
  - {id: clip1, type: video_clip, duration: 4.0, params: {path: takes/walk_p1/2.mp4, region: bleed, fit: cover, fade: false, mute: true, trim: [0.0, 4.0]}}
  - {id: clip2, type: video_clip, duration: 4.0, params: {path: takes/walk_p2/1.mp4, region: bleed, fit: cover, fade: false, mute: true, trim: [0.041667, 4.041667], match_previous: true}}
  - {id: clip3, type: video_clip, duration: 4.0, params: {path: takes/walk_p3/1.mp4, region: bleed, fit: cover, fade: false, mute: true, trim: [0.041667, 4.041667], match_previous: true}}
```

```bash
vidgen render film_match.yaml --preview                               # 62 s locally
ffmpeg -i output/continuous_match_preview.mp4 -an -c:v copy continuous_12s.mp4   # the render adds a silent track
```

A hand-made clip (section 8) joins the same way: give its path. `match_previous` gives the clip's first
frame the brightness and colour of the previous clip's last frame and eases the correction out over
1 s. `match_previous: {dissolve: 3}` also mixes the first 3 frames with the previous last frame; use it
only if a jump still shows. Rendering the beat in the main project instead would draw its placeholder
caption and voice, hence the separate film.

Measured on the 12 s walk (no dissolve):

| cut | mean level before | after | frame-to-frame change at the cut | the same next to it |
|---|---|---|---|---|
| clip 1 to 2 | 99.8 | 99.9 (+0.1 %) | 6.96 | 5.8-6.8 |
| clip 2 to 3 | 75.0 | 75.1 (+0.1 %) | 7.80 | 6.5-7.1 |

Neither join shows in the stills: her position, pose, size, the bag, the lamp posts and the paving
continue with no jump; render warnings: none. The change across each cut is only a little above the
change around it, which is high because the camera moves all the time.

## 11. What was measured

All: LTX-2.3 distilled Q5_K_M on the L4 `ltx`, 97 frames, 768x448, 24 fps, seed 42, the city-walk sheet
and sheet prompt, `depth_range [2, 120]` where a guide was used. **Once each, one seed, judged from
stills only.**

### 11.1 Which inputs LTX follows (the first 4 s of the walk)

| variant | inputs | the place | the woman | opening | camera | faults |
|---|---|---|---|---|---|---|
| **A** | starting picture as first frame + sheet (Ingredients only), **no control video**, a 71-word prompt carrying the motion | **the picture's** glass-tower boulevard (curved balconies, warm light strips, wet tiles), close to the sheet's street panel | as the sheet, hair straight and neat too | **holds**: frame 0 = the picture (diff 4.0), no cut, no morph | tracks backwards at her pace, small sway; **no orbit** (nothing of the blockout's path) | none of the blockout's layout (bridge, kerbs, lamp posts) |
| **B** | sheet + depth guide (plain capsule), `first_frame: none` | partly the panel's look, but the guide's walls make it a plaza with a footbridge | as the sheet; hair a bit longer, wind-blown | clean, no cut | follows the guide, starts to swing round her | none seen |
| C | starting picture as first frame + sheet + depth guide | after frame 0, the guide's concrete plaza | as the sheet; hair longer, wavy | **fails**: the picture for 1 frame, then a cut (QA: abrupt change at 0.04 s) | follows the guide | the cut |
| D | starting picture blended into the guide (`first_frame_in: guide`) + sheet + depth guide | after 0.4 s, the concrete plaza | as C | **fails**: a version of the picture (diff 34.3) that morphs into the plaza over 0.4 s | follows the guide | the morph; yellow lines painted on the paving |

So: **with a depth guide the place comes from the guide** (B, C and D give the same kind of plaza;
B gives it without any picture). **Without a guide the first frame is held**, and the camera does only
what the prompt says. The sheet keeps her the same in all four. B is the cleanest of the guided
openings: there is no picture to fight the guide.

### 11.2 The 12 s continuous walk (guided, chained)

Three clips with a depth guide and the sheet, clip 1 as D above, clips 2 and 3 from `last_of` (opening
0.992 each). The same face, hair and clothes for 12 s; the place, a grey concrete plaza with LED lamp
posts and glass shopfronts, does not drift between clips. Clip 3 is darker (level 75 against 100) as the
camera turns to a darker facade. Faults: the 0.4 s opening morph; the place is less "futuristic city"
than the sheet; the stand-in's nose painted as a pale limb from 6.5 s (section 9); the handbag merges
with her leg near the end.

### 11.3 Blockout shots (single 4 s clips, depth guide, sheet, no first frame)

- City, wide, plain stand-in from behind, `[3, 80]` (514 s GPU): the woman right, no capsule look, the
  towers as the sheet; past 80 m open sky, the street ending at a horizon like a rooftop edge.
- City, medium (432-438 s each): the built figure gave a woman close to the sheet but legs that glide;
  the plain capsule a real stepping cycle, hair less like the sheet, and a skin-coloured flap on her
  shorts (cause unknown).
- Space, ships and fighters of primitives (428 / 442 s): the ships took the sheet's look (ivory
  spindles, teal lines) and the blockout's proportions; the fighters kept the blockout's straight bar wings.

## 12. 8 s in one clip: `fps: 12` + RIFE

A clip is at most 121 frames (5 s at 24 fps). With `fps: 12` on a guided shot vidgen generates at 12 fps
(2, 4, 6, 8 or 10 s), fits the guide at 12 fps and doubles the clip to 24 fps with RIFE 4.26 in the same
ComfyUI job (`FrameInterpolationModelLoader` + `FrameInterpolate`, nodes 50 / 51; n frames become
2n - 1). An 8 s clip is 97 frames, the GPU time of a 4 s clip at 24 fps; on an L4 the interpolation took
3-4 s and about 550 MiB. Each tick or sudden step is spread over 2 frames, so keep `fps: 24` for fast
motion with fine detail. `tools/colab/setup.sh` downloads the RIFE weights. The no-guide tool has no RIFE step: it writes the clip at
`--fps`; use `fps: 12` on guided shots.

## 13. Reference: restyling a render with a canny or final guide

These exist in vidgen and the tools, for keeping a render's layout and lighting when the render
already looks right.

- **Which control video** (`guide: canny | final | depth`, each with or without a sheet, at 12 or 24
  fps). Measured once on an 8 s clockwork shot with a sheet: `final` (the scene's colour render) kept
  the parts and the lighting best and followed the camera from frame 0, but kept some of the render's
  look; `depth` invented surfaces where the render had texture; `canny` invented the most and lagged
  the camera by up to 2 s. On a space film the owner, watching, preferred `depth` to `final` (rings, a
  nebula or "no sun" went into the prompt). A web scene's depth needs its page to draw through
  `vidgen/three-finish` (CONFIG.md, "A web scene's depth").
- **Canny with a glint mask**: `canny: {low: 92, high: 200, glint: 150}` drops the edges in bright areas
  (a sun glint LTX paints as surf); by hand `make_canny_soft.py` on the VM (`GLINT=150`, `FEATHER=31`),
  `make_canny.py` the plain canny. On a glider over the sea, canny held the horizon level where 1 / z
  depth rolled it 15-30°; a CG first frame kept the CG look; no first frame looked real but invented a beach.
- **A repainted first frame by hand**: `prep_image_inputs.py` (VM), `build_image_workflow.py qwen`
  (local), `run_job.py`; Qwen-Image-Edit-2511 takes the frame as its own reference, so the layout is
  kept (about 110 s with the load, 25 s after, peak 19.5 GB). Name the CG pattern in the prompt
  ("replace the regular, repeating computer-generated ripple pattern of the water with real, irregular
  open-ocean waves") and say what must not move; `align_check.py` overlays the edges of frame 0 and the
  candidate: check it by eye. Inside vidgen: `first_frame: restyled` (section 7).
- **Graphs by hand**: `build_workflow.py` writes vidgen's graph for given inputs (`--control`,
  `--second-control`, `--first-frame` or `--no-first-frame`, size, frames, fps, seed);
  `prepare_inputs.sh` trims to 8k+1 frames and crops to multiples of 64; `make_compare.sh` lays clips
  side by side. The graph's source, node by node: `src/vidgen/videogen/ltx_graph.py`. Do not add the
  distilled LoRA on top of the distilled GGUF.

## 14. Costs and timings (L4)

| item | measured |
|---|---|
| session start | 8 s-3 min, plus about 3 min per HTTP 503 try |
| `setup_session.py`, new session / ready session | about 6 min / 10-20 s |
| `setup_session.py ltx --vidgen-only` | 36-45 s |
| `vidgen remote ... generate inputs --guide` (one 4 s 3D shot, software WebGL, no GPU job) | about 50 s |
| Z-Image-Turbo panel, 1440x768, 8 steps (ComfyUI 8188 with the L4 flags) | about 106 s for the first (load), 27 s each after |
| Qwen-Image-Edit starting picture, with the model load | 112 s, 0.073 units |
| no-guide clip, 97 frames 768x448 (first frame + sheet) | 396 s GPU, 0.257 units, about 7 min 20 s; peak 13.3 GB |
| depth guide + sheet clip, 97 frames 768x448 | 428-514 s GPU, 0.28-0.33 units, 7.5-9 min door to door |
| sheet clip, 97 frames, peak VRAM | 19.2 GB (about 26 s a sampling step, text step on the CPU about 150 s) |
| the 12 s walk: 1 picture + 4 clips | 1 935 s GPU (32 min), 1.25 units |

Units at 2.33 an hour (what the projects set). An idle L4 still bills: stop it when you are done.

## 15. Stop the session (local)

Download everything first; the VM's disk is gone afterwards. Stop the keepalive too. An L4 kept between
experiments is stopped when the owner says so; any other GPU, when the work is done.

```bash
colab stop -s ltx          # "Session terminated."
colab sessions             # "No active sessions found on server."
colab usage                # 0.00/hr when nothing runs
```

## 16. Troubleshooting

| symptom | cause | fix |
|---|---|---|
| a guided clip shows the starting picture for one frame, then another place (QA: abrupt change at 0.04 s) | the picture disagrees with the depth guide | no guide (section 8), or `first_frame: none` with the guide |
| the place is a plaza or a box street, not the sheet's | the depth guide sets the place | no guide, or build the blockout as the place you want |
| open sky at the end of a street | beyond `depth_range` | widen the far end, or close the street within it |
| a pale limb beside a figure | the `standin` nose in the depth guide | a plain capsule of primitives (section 9) |
| `vidgen remote` refuses: the VM's vidgen differs | this checkout changed | `setup_session.py NAME --vidgen-only` |
| `vm` or a retry made a new session | `colab ssh --proxy-mode` creates a missing one | `colab sessions`; stop the unwanted one; check `ltx` is an L4 |
| a running session is gone | Colab ended it | run the keepalive; download outputs as each run finishes; `setup_session.py ltx` makes a new one |
| out of memory in the first sampling steps | dynamic VRAM, or another model still loaded | `--reserve-vram 10` (section 3.1); `/free` both ComfyUIs (section 5) |
| a sheet shot is refused before sending | ComfyUI runs with its model compiler on | `setup_session.py NAME --no-comfy-compiler` |
| download of `ltx_<run>_00001.mp4` fails | a second run with the same prefix writes `_00002` | `vm ls /content/ComfyUI/output` |

## The colab exec route (`--via exec`)

The other route, `colab exec` one call at a time with files through Cloudflare quick tunnels, is
picked per command with `--via exec` ([tools/colab/README.md](../tools/colab/README.md), "Two routes").
It never restarts ComfyUI and refuses `--no-comfy-compiler` and `--reserve-vram`, so it cannot set up
the L4 recipe of section 3.1.

## Files

[`tools/colab/`](../tools/colab/) (the [README](../tools/colab/README.md) says where each script runs).
The projects these results come from stay outside the repo, in the owner's `video-projects/`:
`city-walk/` (the walk, its sheet, the four-variant test in `continuous/testA` and `testB`, the join),
`starfall/` (text-only panels, the blockout test, the image-model comparison), `escapement-remake/`
(guide choice, 12 fps, the L4 memory fit), `footage-test/ltx-test/` (the canny and first-frame tests).
