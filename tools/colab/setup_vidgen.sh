#!/bin/bash
# Install vidgen from /content/vidgen-src.tar.gz (this computer's working tree) on a Colab VM.
# setup_session.py uploads the archive and this script and starts it detached through
# start_setup.py with VIDGEN_HASH set; progress goes to /content/setup_vidgen.log (### lines are
# the milestones). On success it writes VIDGEN_HASH into /content/.vidgen_setup_vidgen_done.
# The system part (apt: ffmpeg, LaTeX, cairo/pango, espeak-ng; Playwright's Chromium) runs once
# (/content/.vidgen_system_done); a new hash only reinstalls vidgen into /content/vidgen-venv,
# a venv that sees Colab's packages (torch) without changing them.
set -euo pipefail
cd /content
T0=$(date +%s)
stamp() { echo "### $(date -u +%H:%M:%S) +$(( $(date +%s) - T0 ))s $*"; }
: "${VIDGEN_HASH:?VIDGEN_HASH not set}"
MARKER=/content/.vidgen_setup_vidgen_done
SYSTEM=/content/.vidgen_system_done
VENV=/content/vidgen-venv
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

stamp "check"
"$VENV/bin/vidgen" --version
"$VENV/bin/python" -c "from vidgen.browser.chromium import missing_dependency as m; p = m(); assert p is None, p"
ffmpeg -version | sed -n 1p
latex --version | sed -n 1p
echo "$VIDGEN_HASH" > "$MARKER"
stamp "VIDGEN SETUP DONE"
