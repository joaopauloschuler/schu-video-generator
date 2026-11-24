# Run with: colab exec -s ltx --env RUN=depth -f start_job.py
# (needs /content/workflow_$RUN.json and /content/run_job.py uploaded first)
# Starts run_job.py detached; it writes /content/job_$RUN.json when done.
import os
import subprocess

run = os.environ["RUN"]
log = open(f"/content/job_{run}.log", "w")
p = subprocess.Popen(["python", "/content/run_job.py", f"/content/workflow_{run}.json", run],
                     stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
print("job", run, "pid", p.pid)
