"""VM side of keepalive.py (run with ``colab exec -f``): adds its own random integer to KEEPALIVE_A."""
import json
import os
import random

a = int(os.environ["KEEPALIVE_A"])
b = random.randint(1, 10**9)
print("KEEPALIVE " + json.dumps({"b": b, "sum": a + b}), flush=True)
