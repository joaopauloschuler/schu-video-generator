# tools/colab: Colab sessions for vidgen and the LTX-2.3 HOWTO

`setup_session.py` sets up a Colab GPU session in one command: vidgen (for `vidgen remote`) and the
models of [`docs/HOWTO-restyle-with-ltx-on-colab.md`](../../docs/HOWTO-restyle-with-ltx-on-colab.md);
the other scripts are the HOWTO's per-run steps.

## Set up a session

```
python tools/colab/setup_session.py NAME [--gpu L4|CPU] [--high-mem] [--no-image] [--latest] [--no-vidgen | --vidgen-only] [--via exec]
```

Runs on your machine: Python 3.10+, standard library only (Windows too), and the `colab` CLI
installed and logged in (`colab usage` prints the balance). It:

1. reuses the session `NAME` when `colab sessions` lists it, or else runs `colab new -s NAME --gpu L4`
   (`--gpu` picks another; `--gpu CPU` a CPU runtime, with `--vidgen-only`; `--high-mem` a high-RAM
   shape, ignored on an L4), trying 4 times a minute apart when there is no capacity (HTTP 503);
2. creates the key `~/.ssh/colab_ed25519` when missing and checks that SSH to the session works;
3. runs `vm_state.py` on the VM to see what is done, and skips it;
4. uploads `vm_state.py`, `setup.sh` and `setup_image.sh`, starts the missing setups detached
   (`setsid nohup`), checks on the VM that each one runs, and polls their logs every 10 s,
   printing the `###` milestone lines;
5. starts ComfyUI unless it answers on 127.0.0.1:8188 (VM), and waits for it, installing this
   checkout's vidgen meanwhile unless the VM's marker holds its code hash (below);
6. prints the session, GPU, what was installed or reused, the elapsed time and the next commands.

With `--via exec` it uses the exec route (below): `start_setup.py` / `start_comfy.py`, polls every 30 s.

| part | script, log | what it installs |
|---|---|---|
| ComfyUI + LTX-2.3 | `setup.sh`, `/content/setup.log`, `/content/download.log` | ComfyUI and four custom nodes at the tested commits (`--latest`: their newest, `PIN=0`), their requirements without touching Colab's torch, the LTX-2.3 GGUF, VAEs, connectors, IC-LoRA and Gemma (~34 GB) |
| image models (skip with `--no-image`) | `setup_image.sh`, `/content/setup_image.log` | Qwen-Image-Edit-2511 GGUF + Lightning LoRA + text encoder + VAE, Z-Image-Turbo + Fun ControlNet (~50 GB); runs beside `setup.sh` |
| ComfyUI server | `start_comfy.py`, `/content/comfy.log` | `main.py --listen 127.0.0.1 --port 8188`, and `nvidia-smi` into `/content/vram.csv` |
| vidgen (skip with `--no-vidgen`; `--vidgen-only` skips the rows above) | `setup_vidgen.sh`, `/content/setup_vidgen.log` | once: apt `ffmpeg`, LaTeX (`texlive-latex-extra`, `dvisvgm`), cairo/pango, `espeak-ng`, Playwright's Chromium with its libraries; each time the code changes: `src/vidgen` of the working tree (uncommitted changes too, uploaded as `/content/vidgen-src.tar.gz`, nothing from GitHub) installed with its dependencies into `/content/vidgen-venv` (a venv that sees Colab's torch without changing it), linked as `/usr/local/bin/vidgen`; WebGL on the GPU (below) |

**WebGL on the GPU.** Colab ships the NVIDIA libraries in `/usr/lib64-nvidia` but not their vendor
files, so Chromium falls back to SwiftShader. `setup_vidgen.sh` writes
`/etc/vulkan/icd.d/nvidia_icd.json` and `/etc/glvnd/egl_vendor.d/10_nvidia.json`, starts Chromium
with `VIDGEN_WEBGL=gpu` (flags `--use-angle=vulkan --enable-features=Vulkan --ignore-gpu-blocklist`)
and, when the WebGL renderer names NVIDIA, writes `VIDGEN_WEBGL=gpu` (and `LD_LIBRARY_PATH`) into
`/content/vidgen.env`, which `vidgen remote` adds to its runs; the log shows
`### WebGL: ANGLE (NVIDIA, Vulkan 1.4.312 (NVIDIA NVIDIA L4 ...))`. Without a GPU or when the check
fails, the file is not written and WebGL stays on SwiftShader. `VIDGEN_WEBGL=gpu` is part of the
`3d`/`web` cache key, so GPU frames are their own build.

The HOWTO's §4 and §6 list the repos, files and commits.

**Done markers.** On success `setup.sh` writes `/content/.vidgen_setup_ltx_done`,
`setup_vidgen.sh` writes the code hash into `/content/.vidgen_setup_vidgen_done` (the hash of
`src/vidgen`'s files, `vidgen.colab.package_hash`; a new hash reinstalls vidgen only), and
`setup_image.sh` writes `/content/.vidgen_setup_image_done`, after `python /content/vm_state.py
ltx|image` found every file. A part also counts as done without its marker when all its files are
there (`vm_state.MODEL_FILES`, plus ComfyUI and its custom nodes for LTX-2.3). A part whose script
still runs is waited for, never started twice. So running the command again on a ready session
takes about 20 s, and after an error it goes on from where it stopped.

**Two routes.** `vidgen.colab.Colab` (used by `vidgen remote`, the `comfyui` provider on Colab and
this script) reaches the VM over **SSH** by default (`vidgen.colab_ssh`): `ssh` with
`colab ssh --proxy-mode` as its ProxyCommand, only the key `~/.ssh/colab_ed25519` (create it with
`ssh-keygen -t ed25519 -N "" -f ~/.ssh/colab_ed25519`), one held master per session (socket and a
per-session known_hosts file in `~/.cache/vidgen/ssh/`; `~/.ssh/config` and `~/.ssh/known_hosts`
are not used). Scripts run with `python3` on the VM, files go with `cat` over the master (SHA-256
checked); calls may run in parallel. The old route, `Colab(via="exec")`, is `colab exec` one call at
a time plus the tunnels below.

**Transfers on the exec route.** Every file between your machine and the VM goes through a
Cloudflare quick tunnel (`vidgen.colab_transfer`), never `colab upload` / `colab download`: up, your machine serves it
and the VM gets it with `curl`; down, the VM serves it (with `cloudflared` 2026.10.7, which this
script installs at `/content/bin/cloudflared` before the other parts) and your machine gets it.
Each side's tunnel opens once per command and closes when it ends. Needs `cloudflared` on your
PATH. **Security:** each tunnel serves only its own folder under a new
`secrets.token_urlsafe(32)` path, which both sides learn only through `colab exec` and which is
masked in messages; it binds to 127.0.0.1, lists nothing and answers 404 to anything else; every
file's SHA-256 is checked. A failed transfer is retried twice (a new tunnel when its address does
not resolve), then stops with an error.

**Several sessions.** Each `NAME` is its own VM; the name goes to `colab` as one argument.

**The script never stops a session**, also not after an error. Stop it yourself when you are done
(an idle L4 still bills about 1.94 compute units an hour); the VM's disk is gone afterwards:

```
colab stop -s NAME
colab sessions
```

## `vidgen remote NAME ARGS...`

Run from a project folder; it runs `vidgen ARGS` on session `NAME` (there is no default session):

```
python tools/colab/setup_session.py NAME --vidgen-only
cd my-project
vidgen remote NAME render
vidgen remote --exclude ltx-test NAME render --preview
```

1. checks that `colab sessions` lists `NAME`;
2. syncs the project to `/content/projects/<folder name>/` with rsync over SSH: files deleted here
   are deleted there; `build/`, `output/`, `exports/`, `media/`, `--exclude DIR` top folders,
   `__pycache__`, `.git` and `.vidgen-remote` are never sent or touched there;
3. checks that the VM's vidgen hash is this computer's (else it stops and prints the
   `setup_session.py ... --vidgen-only` command) and starts `vidgen ARGS` there detached (`--json`
   added for commands that have it), log in `.vidgen-remote/run.log`; it polls the log after 2 s,
   5 s, then every 10 s, printing its lines; on failure it prints the log tail and returns the exit code;
4. after a run that succeeded, rsyncs back (`--update`: a file changed here meanwhile is kept;
   nothing is deleted here) the files the JSON document names, the files the run made or changed
   outside the never-sent folders, and `build/` without the render caches (`build/*/scenes`, `web`
   clips, `frames`, `media`, `padded`, `three_d`, `audio`, `build/music`); the web captures'
   `.json` records do come back, so inputs made on the VM count here.

Without a local `rsync` (Windows), or with `--via exec` (before `NAME`), it sends the files whose
SHA-256 the VM lacks in one `.tar` (nothing on the VM is deleted) and brings back, in one `.tar`,
the named files plus `build/final/timings.json` and the run's new files outside `build/`. On the
exec route every `colab` call on a session waits for any other vidgen call on it (a lock file in
the temp folder); a `colab exec` is cut at 30 s and retried after 3, 10, 20, 30 s. Every VM step is
safe to repeat. `setup_session.py` and the `comfyui` provider use the same helpers.

Local side: `src/vidgen/remote.py` and `src/vidgen/colab.py` (shared with `setup_session.py`),
standard library only; VM side: `src/vidgen/colab_vm.py` (run with `python3` over SSH, or `colab exec -f`).
`vidgen remote` compares the hash of the `vidgen` package it runs from, so run it from this
checkout (`pip install -e .`).

## `keepalive.py` (for testing only)

```
python tools/colab/keepalive.py NAME [--every 7m] [--hours 8] [--log PATH]
```

Tests whether Colab ends idle sessions. Nothing starts it; run it by hand. Every `--every` it
skips when another call holds the session's lock, or when any call reached the session within
`--every` (vidgen's "last call" stamp next to the lock, or `~/.config/colab-cli/history/NAME.jsonl`,
which also sees `colab` calls made by hand). Otherwise it runs one `colab exec` (`keepalive_vm.py`:
a sum check). One line per round goes to stdout and the log (default
`~/.config/colab-cli/keepalive-NAME.log`): `skip-locked`, `skip-recent (Ns ago)`, `ok rtt=Ns`,
`wrong-sum`, `no-answer` or `gone`. It stops after `--hours`, when `colab sessions` no longer lists
the session (`gone`), or on Ctrl-C. It never creates or stops a session.

## The other scripts

Local: `check_hf.sh`, `prepare_inputs.sh`, `build_workflow.py` and `build_image_workflow.py` (vidgen's
graphs, `src/vidgen/videogen/ltx_graph.py` and `qwen_graph.py`),
`poll.sh`, `fetch_outputs.sh`, `make_compare.sh`. VM, started with `colab exec -f`: `start_bg.py`,
`start_job.py` + `run_job.py`, `make_canny.py`, `make_canny_soft.py`, `prep_image_inputs.py`,
`align_check.py`, `free_vram.py`, `object_info.py`, `object_info_image.py`. The HOWTO says when to
use each.

`build_workflow.py` writes the graph of vidgen's `ltx-2.3-union-control` workflow
(`src/vidgen/videogen/ltx_graph.py`, one copy). To run it on a shot from a project, use vidgen's
`comfyui` provider instead (`videogen: {provider: comfyui, comfyui: {colab: <session>}}`, docs/CONFIG.md).
