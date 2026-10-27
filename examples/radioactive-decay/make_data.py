"""Write the example's two data files (standard library only, seeded: the same files every run).

    python make_data.py

- assets/counts.csv: a simulated measurement of barium-137m (half-life 2.552 min, eluted from a
  caesium-137 generator): the counts in each 30-second interval for 15 minutes, drawn from a
  Poisson distribution around the expected number (background neglected).
- assets/nuclei.csv: a Monte Carlo of the decay itself: 1000 nuclei and 20 nuclei, each with its
  own random decay time (exponentially distributed), the share still undecayed every 0.05 min,
  beside the exponential law exp(-lambda * t).

These are illustrative numbers, not a real measurement; the video says so on screen.
"""

import math
import random
from pathlib import Path

HALF_LIFE = 2.552                    # min, barium-137m (NNDC)
LAMBDA = math.log(2) / HALF_LIFE     # per minute
HERE = Path(__file__).resolve().parent


def poisson(rng: random.Random, mean: float) -> int:
    """A Poisson draw: the arrivals of a unit-rate process within ``mean``."""
    t, n = 0.0, -1
    while t <= mean:
        t += -math.log(1.0 - rng.random())
        n += 1
    return n


def counts(rng: random.Random) -> str:
    rate0 = 1500.0                   # decays counted per minute at t = 0
    width = 0.5                      # min: each interval
    rows = ["# simulated counts of barium-137m (half-life 2.552 min), Poisson noise, seed 227",
            "time (min),counts"]
    for i in range(30):
        t = i * width
        expected = rate0 / LAMBDA * (math.exp(-LAMBDA * t) - math.exp(-LAMBDA * (t + width)))
        rows.append(f"{t:.1f},{poisson(rng, expected)}")
    return "\n".join(rows) + "\n"


def nuclei(rng: random.Random) -> str:
    big = sorted(-math.log(1.0 - rng.random()) / LAMBDA for _ in range(1000))
    small = sorted(-math.log(1.0 - rng.random()) / LAMBDA for _ in range(20))
    rows = ["# Monte Carlo decay of 1000 and of 20 barium-137m nuclei (seed 227): the share left, and the exponential law",
            "time (min),N1000,N20,law"]
    for i in range(241):
        t = i * 0.05
        n_big = sum(1 for d in big if d > t)
        n_small = sum(1 for d in small if d > t)
        rows.append(f"{t:.2f},{n_big / 1000:.3f},{n_small / 20:.2f},{math.exp(-LAMBDA * t):.4f}")
    return "\n".join(rows) + "\n"


def main() -> None:
    rng = random.Random(227)
    (HERE / "assets").mkdir(exist_ok=True)
    (HERE / "assets" / "counts.csv").write_text(counts(rng), encoding="utf-8")
    (HERE / "assets" / "nuclei.csv").write_text(nuclei(rng), encoding="utf-8")


if __name__ == "__main__":
    main()
