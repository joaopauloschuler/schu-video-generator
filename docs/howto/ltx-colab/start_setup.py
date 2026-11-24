# Run with: colab exec -s ltx -f start_setup.py
# (after: colab upload -s ltx setup.sh /content/setup.sh). Add --env PIN=0 for the latest commits,
# --env SCRIPT=/content/setup_image.sh to start another setup script (log /content/<name>.log).
# Starts the script detached so no exec call blocks; poll its log.
import os
import subprocess
from pathlib import Path

script = os.environ.get("SCRIPT", "/content/setup.sh")
log = open(f"/content/{Path(script).stem}.log", "w")
p = subprocess.Popen(["bash", script], stdout=log, stderr=subprocess.STDOUT,
                     start_new_session=True)
print("started", script, "pid", p.pid)
