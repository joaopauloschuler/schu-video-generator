#!/bin/bash
# Install vidgen from /content/vidgen-src.tar.gz (this computer's working tree) on a Colab VM.
# setup_session.py uploads the archive and this script and starts it detached through
# start_setup.py with VIDGEN_HASH set; progress goes to /content/setup_vidgen.log (### lines are
# the milestones). On success it writes VIDGEN_HASH into /content/.vidgen_setup_vidgen_done.
# The system part (apt: ffmpeg, LaTeX, cairo/pango, espeak-ng; Playwright's Chromium) runs once
# (/content/.vidgen_system_done); a new hash only reinstalls vidgen into /content/vidgen-venv,
# a venv that sees Colab's packages (torch) without changing them.
# With an NVIDIA driver it adds the Vulkan and EGL vendor files Colab leaves out, and when
# Chromium's WebGL then names the GPU, writes VIDGEN_WEBGL=gpu into /content/vidgen.env (the
# environment of vidgen remote's runs); otherwise WebGL stays on SwiftShader.
set -euo pipefail
cd /content
T0=$(date +%s)
stamp() { echo "### $(date -u +%H:%M:%S) +$(( $(date +%s) - T0 ))s $*"; }
: "${VIDGEN_HASH:?VIDGEN_HASH not set}"
MARKER=/content/.vidgen_setup_vidgen_done
SYSTEM=/content/.vidgen_system_done
VENV=/content/vidgen-venv
ENVFILE=/content/vidgen.env
NV=/usr/lib64-nvidia
rm -f "$MARKER"

if [ ! -f "$SYSTEM" ]; then
  stamp "apt: ffmpeg, LaTeX, cairo/pango, espeak-ng"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq --no-install-recommends ffmpeg texlive-latex-base texlive-latex-extra \
    texlive-fonts-recommended dvisvgm libcairo2-dev libpango1.0-dev pkg-config espeak-ng >/dev/null
fi

stamp "unpack the source (code $VIDGEN_HASH)"
rm -rf /content/vidgen-src
tar -xzf /content/vidgen-src.tar.gz -C /content

command -v uv >/dev/null || pip install -q uv
if [ ! -x "$VENV/bin/python" ]; then
  stamp "venv $VENV (sees Colab's packages)"
  uv venv -q --system-site-packages "$VENV"
fi
stamp "pip install vidgen and its dependencies"
uv pip install -q --python "$VENV/bin/python" --reinstall-package schu-video-generator /content/vidgen-src
ln -sf "$VENV/bin/vidgen" /usr/local/bin/vidgen

stamp "Playwright's Chromium"
"$VENV/bin/python" -m playwright install --with-deps chromium >/dev/null
touch "$SYSTEM"

rm -f "$ENVFILE"
if command -v nvidia-smi >/dev/null && [ -f "$NV/libGLX_nvidia.so.0" ] && [ -f "$NV/libEGL_nvidia.so.0" ]; then
  stamp "WebGL on the GPU: NVIDIA Vulkan and EGL vendor files"
  mkdir -p /etc/vulkan/icd.d /etc/glvnd/egl_vendor.d
  echo '{"file_format_version": "1.0.1", "ICD": {"library_path": "'"$NV"'/libGLX_nvidia.so.0", "api_version": "1.3.0"}}' \
    > /etc/vulkan/icd.d/nvidia_icd.json
  echo '{"file_format_version": "1.0.0", "ICD": {"library_path": "'"$NV"'/libEGL_nvidia.so.0"}}' \
    > /etc/glvnd/egl_vendor.d/10_nvidia.json
  RENDERER=$(VIDGEN_WEBGL=gpu LD_LIBRARY_PATH="$NV:${LD_LIBRARY_PATH:-}" "$VENV/bin/python" -c \
    "from vidgen.browser.chromium import webgl_renderer; print(webgl_renderer())" 2>&1 | tail -n 1) || true
  if [[ "$RENDERER" == *NVIDIA* ]]; then
    printf 'VIDGEN_WEBGL=gpu\nLD_LIBRARY_PATH=%s\n' "$NV:${LD_LIBRARY_PATH:-}" > "$ENVFILE"
    stamp "WebGL: $RENDERER"
  else
    stamp "WebGL stays on SwiftShader (the GPU check gave: $RENDERER)"
  fi
fi

stamp "check"
"$VENV/bin/vidgen" --version
"$VENV/bin/python" -c "from vidgen.browser.chromium import missing_dependency as m; p = m(); assert p is None, p"
ffmpeg -version | sed -n 1p
latex --version | sed -n 1p
echo "$VIDGEN_HASH" > "$MARKER"
stamp "VIDGEN SETUP DONE"
