"""Flight in the air of a world (Step 385), beside :mod:`vidgen.orbits`: a
flight described in words (:mod:`.spec`: a start, then legs — straight, turns, climbs, speed
changes, terrain following, curves through waypoints, circling a place, a landing, a re-entry from
orbit) becomes smooth position, velocity and attitude on the world's sphere (:mod:`.plan`), checked
never to come under the ground (:mod:`.terrain`: ``vidgen/space-land``'s heights ported to numpy,
a level ground, the sea, a flat world), in the scene's local frame, which :mod:`.frames` ties to the
world-fixed frame and to the orbit bridge's ecliptic frame. :mod:`.worlds` holds the radius,
gravity and air of each world; :mod:`.reentry` the shaped descent from orbit. Exported by
``vidgen.api`` as the module ``flight``; a ``web`` scene's ``flight_data:`` hands it to the page as
``ctx.flight``."""

from .frames import LocalFrame, spin_local, spin_vector
from .plan import MAX_STEP, FlightContext, FlightRun, LegRecord
from .reentry import HEAT_DENSITY, HEAT_SPEED, EntryProfile, entry_profile, heating
from .spec import Circle, Climb, Flight, Follow, Landing, Leg, Place, Reentry, Speed, Start, Turn, Waypoints
from .terrain import FlatGround, Ground, LandGround, SeaGround, SphereGround, hash2, height_of, macro_at, noise, relief_at
from .worlds import AIRS, WORLDS, Air, World, world

__all__ = [
    "AIRS", "Air", "Circle", "Climb", "EntryProfile", "FlatGround", "Flight", "FlightContext", "FlightRun", "Follow", "Ground",
    "HEAT_DENSITY", "HEAT_SPEED", "Landing", "LandGround", "Leg", "LegRecord", "LocalFrame", "MAX_STEP", "Place", "Reentry",
    "SeaGround", "Speed", "SphereGround", "Start", "Turn", "WORLDS", "Waypoints", "World", "entry_profile", "hash2", "heating",
    "height_of", "macro_at", "noise", "relief_at", "spin_local", "spin_vector", "world",
]
