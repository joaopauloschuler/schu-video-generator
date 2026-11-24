# Run with: colab exec -s ltx -f start_setup.py
# (after: colab upload -s ltx setup.sh /content/setup.sh). Add --env PIN=0 for the latest commits.
# Starts setup.sh detached so no exec call blocks; poll /content/setup.log.
import subprocess

log = open("/content/setup.log", "w")
p = subprocess.Popen(["bash", "/content/setup.sh"], stdout=log, stderr=subprocess.STDOUT,
                     start_new_session=True)
print("setup pid", p.pid)
