# Run with: colab exec -s ltx --env NAME=cannysoft --env CMD="python /content/make_canny_soft.py" \
#   --env SRC=... --env DST=... -f start_bg.py
# Starts CMD detached (environment passed through), log /content/<NAME>.log; then poll the log.
# Use it for anything over ~20 s: a foreground exec that loses its websocket kills its work.
import os
import shlex
import subprocess

name = os.environ.get("NAME", "bg")
log = open(f"/content/{name}.log", "w")
p = subprocess.Popen(shlex.split(os.environ["CMD"]), stdout=log,
                     stderr=subprocess.STDOUT, start_new_session=True)
print("started", name, "pid", p.pid)
