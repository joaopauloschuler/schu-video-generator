"""Orbital mechanics without manim (Phase X, DESIGN §98): Kepler's equation for every conic
(:mod:`.kepler`), two-body orbits from classical elements or state vectors and their derived
quantities — vis-viva, period, energy, angular momentum, apsides, time of flight
(:mod:`.elements`), bodies and preset orbits with their sources (:mod:`.bodies`), values with
units (:mod:`.values`), systems of bodies moved by Kepler's laws and the video's clock
(:mod:`.system`), and n-body motion on Phase W's integrators (:mod:`.nbody`). The ``orbit``
scene type draws them. Exported by ``vidgen.api`` as the module ``orbits``."""

from .bodies import ALIASES as PRESET_ALIASES, BODIES, GM_EARTH, GM_SUN, ORBITS, R_EARTH, SIDEREAL_DAY, Body, OrbitPreset, body_preset, orbit_preset, preset_key
from .elements import Elements, circular_speed, escape_speed, period, semi_major_axis, specific_energy, vis_viva
from .kepler import PARABOLIC_TOLERANCE, eccentric_anomaly, hyperbolic_anomaly, kind_of, mean_from_true, mean_motion, parabolic_anomaly, true_from_mean, wrap_angle
from .nbody import METHOD_ALIASES, METHODS, NBodyRun, default_step, method_name, simulate
from .system import Orbiter, Playback, System, swept_area
from .values import AU, DAY, G, YEAR, length_unit, speedup_text, time_unit, value_si

__all__ = [
    "AU",
    "BODIES",
    "DAY",
    "G",
    "GM_EARTH",
    "GM_SUN",
    "METHODS",
    "METHOD_ALIASES",
    "ORBITS",
    "PARABOLIC_TOLERANCE",
    "PRESET_ALIASES",
    "R_EARTH",
    "SIDEREAL_DAY",
    "YEAR",
    "Body",
    "Elements",
    "NBodyRun",
    "OrbitPreset",
    "Orbiter",
    "Playback",
    "System",
    "body_preset",
    "circular_speed",
    "default_step",
    "eccentric_anomaly",
    "escape_speed",
    "hyperbolic_anomaly",
    "kind_of",
    "length_unit",
    "mean_from_true",
    "mean_motion",
    "method_name",
    "orbit_preset",
    "parabolic_anomaly",
    "period",
    "preset_key",
    "semi_major_axis",
    "simulate",
    "specific_energy",
    "speedup_text",
    "swept_area",
    "time_unit",
    "true_from_mean",
    "value_si",
    "vis_viva",
    "wrap_angle",
]
