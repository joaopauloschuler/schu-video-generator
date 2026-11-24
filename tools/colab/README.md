# tools/colab: Colab sessions for vidgen and the LTX-2.3 HOWTO

`setup_session.py` sets up a Colab GPU session in one command: vidgen (for `vidgen remote`) and the
models of [`docs/HOWTO-restyle-with-ltx-on-colab.md`](../../docs/HOWTO-restyle-with-ltx-on-colab.md);
the other scripts are the HOWTO's per-run steps.

## Set up a session

```
python tools/colab/setup_session.py NAME [--gpu L4] [--no-image] [--latest] [--no-vidgen | --vidgen-only]
```

Runs on your machine: Python 3.10+, standard library only (Windows too), and the `colab` CLI
installed and logged in (`colab usage` prints the balance). It:

1. reuses the session `NAME` when `colab sessions` lists it, or else runs `colab new -s NAME --gpu L4`
   (`--gpu` picks another), trying 4 times a minute apart when there is no capacity (HTTP 503);
2. runs `vm_state.py` on the VM to see what is done, and skips it;
3. uploads `vm_state.py`, `setup.sh` and `setup_image.sh` and starts the missing setups detached
   (`start_setup.py`), checks on the VM that each one runs, and polls their logs every 30 s,
   printing the `###` milestone lines;
4. starts ComfyUI (`start_comfy.py`) unless it answers on 127.0.0.1:8188 (VM), and waits for it;
5. installs this checkout's vidgen unless the VM's marker holds its code hash (below);
6. prints the session, GPU, what was installed or reused, the elapsed time and the next commands.

| part | script, log | what it installs |
|---|---|---|
| ComfyUI + LTX-2.3 | `setup.sh`, `/content/setup.log`, `/content/download.log` | ComfyUI and four custom nodes at the tested commits (`--latest`: their newest, `PIN=0`), their requirements without touching Colab's torch, the LTX-2.3 GGUF, VAEs, connectors, IC-LoRA and Gemma (~34 GB) |
| image models (skip with `--no-image`) | `setup_image.sh`, `/content/setup_image.log` | Qwen-Image-Edit-2511 GGUF + Lightning LoRA + text encoder + VAE, Z-Image-Turbo + Fun ControlNet (~50 GB); runs beside `setup.sh` |
| ComfyUI server | `start_comfy.py`, `/content/comfy.log` | `main.py --listen 127.0.0.1 --port 8188`, and `nvidia-smi` into `/content/vram.csv` |
| vidgen (skip with `--no-vidgen`; `--vidgen-only` skips the rows above) | `setup_vidgen.sh`, `/content/setup_vidgen.log` | once: apt `ffmpeg`, LaTeX (`texlive-latex-extra`, `dvisvgm`), cairo/pango, `espeak-ng`, Playwright's Chromium with its libraries; each time the code changes: `src/vidgen` of the working tree (uncommitted changes too, uploaded as `/content/vidgen-src.tar.gz`, nothing from GitHub) installed with its dependencies into `/content/vidgen-venv` (a venv that sees Colab's torch without changing it), linked as `/usr/local/bin/vidgen` |

The HOWTO's §4 and §6 list the repos, files and commits.

**Done markers.** On success `setup.sh` writes `/content/.vidgen_setup_ltx_done`,
`setup_vidgen.sh` writes the code hash into `/content/.vidgen_setup_vidgen_done` (the hash of
`src/vidgen`'s files, `vidgen.colab.package_hash`; a new hash reinstalls vidgen only), and
`setup_image.sh` writes `/content/.vidgen_setup_image_done`, after `python /content/vm_state.py
ltx|image` found every file. A part also counts as done without its marker when all its files are
there (`vm_state.MODEL_FILES`, plus ComfyUI and its custom nodes for LTX-2.3). A part whose script
still runs is waited for, never started twice. So running the command again on a ready session
takes about 20 s, and after an error it goes on from where it stopped.

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

1. checks that `colab sessions` lists `NAME`, and that the VM's vidgen hash is this computer's
   (else it stops and prints the `setup_session.py ... --vidgen-only` command);
2. syncs the project to `/content/projects/<folder name>/`: the files whose SHA-256 differs, in one
   `.tar.gz`; `build/`, `output/`, `exports/`, `media/` and `--exclude DIR` top folders are never
   sent, and nothing on the VM is deleted;
3. starts `vidgen ARGS` there detached (`--json` added for commands that have it), log in
   `.vidgen-remote/run.log`, and polls it (one `colab exec` at a time, each cut at 60 s and
   retried), printing its lines; on failure it prints the log tail and returns the exit code;
4. brings back the files the JSON document names inside the project outside `build/` (for
   `render`: the MP4, SRT, chapters, thumbnail) plus the render's `build/final/timings.json`,
   and the files the run made or changed outside the never-sent folders (e.g. `audio/` of `tts`).
   The rest of `build/` stays on the VM as a cache for the next run.

Local side: `src/vidgen/remote.py` and `src/vidgen/colab.py` (shared with `setup_session.py`),
standard library only; VM side: `src/vidgen/colab_vm.py` (run with `colab exec -f`).
`vidgen remote` compares the hash of the `vidgen` package it runs from, so run it from this
checkout (`pip install -e .`).

## The other scripts

Local: `check_hf.sh`, `prepare_inputs.sh`, `build_workflow.py`, `build_image_workflow.py`,
`poll.sh`, `fetch_outputs.sh`, `make_compare.sh`. VM, started with `colab exec -f`: `start_bg.py`,
`start_job.py` + `run_job.py`, `make_canny.py`, `make_canny_soft.py`, `prep_image_inputs.py`,
`align_check.py`, `free_vram.py`, `object_info.py`, `object_info_image.py`. The HOWTO says when to
use each.
