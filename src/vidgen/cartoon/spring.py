"""A damped spring for parts that lag and wobble behind what carries them (antennae, ears, tails,
hair, hanging signs; DESIGN.md §69.15), worked out in closed form without manim.

A part on a spring of unit mass follows a target ``s``: ``x'' = stiffness·(s − x) − damping·x'``.
:meth:`Spring.follow` gives ``x`` at any time as a pure function of the target's history (the
spring's step response as a weighting of the past), so the result is the same at every frame
rate and does not depend on which frames were drawn before. Times are in seconds.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

#: How many of the spring's decay times (``1 / decay_rate``) of the past :meth:`Spring.follow`
#: weighs; what is older weighs less than e^−6 (0.25 %) and is taken as the oldest value weighed.
_WINDOW_DECAYS = 6.0
#: Slices per radian of the spring's natural frequency, and the bounds on their number.
_SLICES_PER_RADIAN = 8.0
_MIN_SLICES = 32
_MAX_SLICES = 512
#: Damping ratios this close to 1 count as critical (``tuned(f, 1.0)`` lands within rounding of 1).
_CRITICAL_BAND = 1e-9


@dataclass(frozen=True)
class Spring:
    """A damped spring of unit mass: ``stiffness`` (1/s², the square of its natural angular
    frequency) and ``damping`` (1/s). :meth:`tuned` makes one from a frequency and a damping
    ratio, the easier numbers to choose."""

    stiffness: float
    damping: float

    def __post_init__(self) -> None:
        if not (self.stiffness > 0 and self.damping > 0):
            raise ValueError(f"a spring needs stiffness > 0 and damping > 0, not {self.stiffness}, {self.damping}")

    @classmethod
    def tuned(cls, frequency_hz: float, damping_ratio: float) -> Spring:
        """A spring that wobbles ``frequency_hz`` times a second when undamped, with
        ``damping_ratio``: below 1 it overshoots and wobbles (0.5: about 16 % past), 1 (critical)
        is the fastest without overshoot, above 1 creeps in slower."""
        omega = 2.0 * math.pi * frequency_hz
        return cls(omega * omega, 2.0 * damping_ratio * omega)

    @property
    def angular_frequency(self) -> float:
        """Its natural angular frequency ω (radians per second)."""
        return math.sqrt(self.stiffness)

    @property
    def damping_ratio(self) -> float:
        """ζ = damping / (2ω): below 1 under-damped (wobbles), 1 critical, above 1 over-damped."""
        return self.damping / (2.0 * self.angular_frequency)

    @property
    def is_critical(self) -> bool:
        """Whether it is critically damped (ζ = 1, within rounding)."""
        return abs(self.damping_ratio - 1.0) < _CRITICAL_BAND

    @property
    def decay_rate(self) -> float:
        """How fast (1/s) its slowest motion dies away: ζω, or ω(ζ − √(ζ² − 1)) over-damped."""
        omega, zeta = self.angular_frequency, self.damping_ratio
        return omega * (zeta - math.sqrt(zeta * zeta - 1.0)) if zeta > 1.0 and not self.is_critical else zeta * omega

    def step_response(self, seconds: float) -> float:
        """Where the spring is ``seconds`` after its target jumps from 0 to 1, starting at rest at
        0 (0 before; tends to 1; past 1 only when under-damped)."""
        if seconds <= 0:
            return 0.0
        omega, zeta = self.angular_frequency, self.damping_ratio
        if self.is_critical:
            return 1.0 - math.exp(-omega * seconds) * (1.0 + omega * seconds)
        if zeta < 1.0:
            root = math.sqrt(1.0 - zeta * zeta)
            wobble = omega * root * seconds
            return 1.0 - math.exp(-zeta * omega * seconds) * (math.cos(wobble) + zeta / root * math.sin(wobble))
        root = math.sqrt(zeta * zeta - 1.0)
        slow, fast = omega * (zeta - root), omega * (zeta + root)
        return 1.0 - (fast * math.exp(-slow * seconds) - slow * math.exp(-fast * seconds)) / (fast - slow)

    def overshoot(self) -> float:
        """How far past a jump of 1 its step response goes at most: e^(−πζ/√(1 − ζ²)), 0 when
        critically or over-damped."""
        zeta = self.damping_ratio
        return 0.0 if zeta >= 1.0 or self.is_critical else math.exp(-math.pi * zeta / math.sqrt(1.0 - zeta * zeta))

    def settle_seconds(self, tolerance: float = 0.02) -> float:
        """Seconds after a jump of its target from which the spring stays within ``tolerance``
        (a share of the jump) of it."""
        if not 0 < tolerance < 1:
            raise ValueError(f"tolerance must be between 0 and 1, not {tolerance}")

        def outside(seconds: float) -> bool:
            return abs(1.0 - self.step_response(seconds)) > tolerance

        zeta = self.damping_ratio
        if zeta < 1.0 and not self.is_critical:
            # its k-th turning point is at kπ/ω_d, e^(−ζω kπ/ω_d) from 1: the last one outside
            # the band and the first inside bracket the moment it enters the band for good
            half_cycle = math.pi / (self.angular_frequency * math.sqrt(1.0 - zeta * zeta))
            inside = math.ceil(math.log(1.0 / tolerance) / (self.decay_rate * half_cycle))
            low, high = (inside - 1) * half_cycle, inside * half_cycle
        else:
            low, high = 0.0, 1.0 / self.decay_rate
            while outside(high):
                high *= 2.0
        for _ in range(60):  # between two turning points the distance to 1 only shrinks: bisect
            middle = 0.5 * (low + high)
            low, high = (middle, high) if outside(middle) else (low, middle)
        return high

    def follow(self, target: Callable[[float], float], seconds: float) -> float:
        """Where a part on this spring is at ``seconds`` while it follows ``target`` (a function
        of seconds from 0), the part at rest at ``target(0)`` before 0. Pure: the same at every
        frame rate. ``target`` is not read before 0 (unless ``seconds`` is)."""
        span = min(max(seconds, 0.0), _WINDOW_DECAYS / self.decay_rate)
        slices = min(_MAX_SLICES, max(_MIN_SLICES, math.ceil(span * self.angular_frequency * _SLICES_PER_RADIAN)))
        step = span / slices
        total, weighed = 0.0, 0.0
        for k in range(slices):  # each slice weighs the impulse response's integral over it
            reached = self.step_response((k + 1) * step)
            total += target(seconds - (k + 0.5) * step) * (reached - weighed)
            weighed = reached
        return total + target(seconds - span) * (1.0 - weighed)


__all__ = ["Spring"]
