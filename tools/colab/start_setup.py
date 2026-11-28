# VM side, run by setup_session.py: colab exec -s NAME --env SCRIPT=/content/setup.sh --env PIN=1 -f start_setup.py
# Starts SCRIPT (default /content/setup.sh) detached, log /content/<script name>.log, so no exec
# call blocks. --env values stay set in the kernel, so pass SCRIPT and PIN on every call.
import os
import subprocess
from pathlib import Path

script = os.environ.get("SCRIPT", "/content/setup.sh")
log = open(f"/content/{Path(script).stem}.log", "w")
p = subprocess.Popen(["bash", script], stdout=log, stderr=subprocess.STDOUT,
                     start_new_session=True)
print("started", script, "pid", p.pid)
