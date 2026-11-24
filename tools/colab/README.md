# tools/colab: Colab scripts for the LTX-2.3 HOWTO

The scripts of [`docs/HOWTO-restyle-with-ltx-on-colab.md`](../../docs/HOWTO-restyle-with-ltx-on-colab.md).
`setup_session.py` sets up a session in one command; the others are the HOWTO's per-run steps.

## Set up a session

```
python tools/colab/setup_session.py NAME [--gpu L4] [--no-image] [--latest]
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
5. prints the session, GPU, what was installed or reused, the elapsed time and the next commands.

| part | script, log | what it installs |
|---|---|---|
| ComfyUI + LTX-2.3 | `setup.sh`, `/content/setup.log`, `/content/download.log` | ComfyUI and four custom nodes at the tested commits (`--latest`: their newest, `PIN=0`), their requirements without touching Colab's torch, the LTX-2.3 GGUF, VAEs, connectors, IC-LoRA and Gemma (~34 GB) |
| image models (skip with `--no-image`) | `setup_image.sh`, `/content/setup_image.log` | Qwen-Image-Edit-2511 GGUF + Lightning LoRA + text encoder + VAE, Z-Image-Turbo + Fun ControlNet (~50 GB); runs beside `setup.sh` |
| ComfyUI server | `start_comfy.py`, `/content/comfy.log` | `main.py --listen 127.0.0.1 --port 8188`, and `nvidia-smi` into `/content/vram.csv` |

The HOWTO's §4 and §6 list the repos, files and commits.

**Done markers.** On success `setup.sh` writes `/content/.vidgen_setup_ltx_done` and
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

## The other scripts

Local: `check_hf.sh`, `prepare_inputs.sh`, `build_workflow.py`, `build_image_workflow.py`,
`poll.sh`, `fetch_outputs.sh`, `make_compare.sh`. VM, started with `colab exec -f`: `start_bg.py`,
`start_job.py` + `run_job.py`, `make_canny.py`, `make_canny_soft.py`, `prep_image_inputs.py`,
`align_check.py`, `free_vram.py`, `object_info.py`, `object_info_image.py`. The HOWTO says when to
use each.
