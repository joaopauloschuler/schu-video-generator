# How to get to Mars

An orbital-mechanics explainer (seven scenes, about 3 min 43 s with Kokoro narration) built on the
`orbit` scene type with two `calculation` scenes (DESIGN §98). Every number on screen is computed
by the scenes from their model, and the narration says the same numbers (`vidgen lint`'s
`orbit_*` and `calc_*` rules check it). The craft: [the orbits cookbook](../../docs/COOKBOOK-ORBITS.md).

```
vidgen validate examples/mars-transfer           # the short (9:16) variant too
vidgen lint examples/mars-transfer [--variant short]   # incl. the orbit_* and calc_* rules
vidgen storyboard examples/mars-transfer --per-beat 2
vidgen tts examples/mars-transfer                # Kokoro (the kokoro extra): local and free
vidgen render examples/mars-transfer [--variant short]
```

| scene | type | what it shows |
|---|---|---|
| `intro` | `title` | not pointing and firing: both planets move, the Sun's gravity bends every path |
| `straight` | `orbit` | the Earth's orbital speed (29.8 km/s, a live arrow); a rocket fired 3 km/s straight outwards keeps the Earth's sideways speed and goes round the Sun on an ellipse reaching 1.11 AU, far short of Mars |
| `hohmann` | `orbit` (transfer) | circular, coplanar orbits (stated on screen); the live phase angle shrinking to the window at 44.3°; Δv₁ 2.94 km/s on "burn", 259 days along half the transfer ellipse, Δv₂ 2.65 km/s on "second"; 5.59 km/s in all |
| `timing` | `calculation` | a = (r_E + r_M)/2 = 1.262 AU; T = π √(a³/GM☉) = 259 d; θ = π (1 − 2T/T_M) = 44.3° (Mars moves 136° during the flight) |
| `leaving` | `calculation` | from a 300 km orbit: v_circ 7.726, v_esc 10.93 km/s, the departure burn √(v∞² + v_esc²) − v_circ = 3.59 km/s with v∞ = Δv₁ from the `hohmann` scene (`from_scene`) — the Oberth effect |
| `sky` | `orbit` (date) | the Earth and Mars on 28 October 2026 from JPL's approximate elements: Mars 64° ahead, the next window around early December 2026, the opposition of 19 February 2027, windows every 780 days (about 26 months), the one after in early 2029 |
| `recap` | `bullets` | every path an orbit; Hohmann 2.94 + 2.65 km/s, 259 days; leave when Mars leads by 44°; a window every 780 days |

**Numbers.** All computed by vidgen (`vidgen.orbits`; DESIGN §98): the orbit radii are the
semi-major axes of JPL's Table 1 (Earth–Moon barycentre 1.00000261 AU, Mars 1.52371034 AU) taken as
circles, GM☉ the IAU 2015 nominal value. Hohmann: Δv₁ = 2.945 km/s, Δv₂ = 2.649 km/s (relative to
the Sun), 258.9 days, Mars 44.3° ahead at departure, synodic period 779.9 days (25.6 months). From
a circular orbit 300 km up, v∞ = Δv₁ needs √(v∞² + v_esc²) − v_circ = 3.59 km/s (escape speed
10.93 km/s, circular speed 7.73 km/s); escaping first and then adding Δv₁ would cost 6.14 km/s.

**The date.** On 2026-10-28 (the day the example was written) Mars leads the Earth by 64° in
heliocentric longitude (Table 1 positions); the lead falls to the Hohmann angle 44.3° around
2026-12-05 and again around 2029-01-07, so the narration says "around early December 2026" and
"early 2029": the real windows are wider and are found with the true elliptical, inclined orbits
(porkchop plots), so these dates are approximate. Mars's opposition, 2027-02-19 at 0.678 AU, is
`event: {kind: opposition, of: Mars}` (root finding on the longitudes; published oppositions come
out within hours). The launch window comes before the opposition because Mars must be ahead when
we leave.

**Approximations stated.** Two-body orbits, circular and coplanar for the transfer (a caption on
both orbit scenes), impulsive burns, and in the recap: real missions fly computed trajectories on
the true, tilted, elliptical orbits. The capture at Mars (a burn into orbit or aerobraking) and
gravity assists are left out.

**Choices.** `nu: 95` for Mars at the start of `hohmann` lets the viewer watch the phase angle
shrink to the window before the first burn (the clock runs so the burns fall on their words; the
burns' simulated times do not change). The low-orbit height (300 km) is a chosen, exact value;
the burn is worked out from `from_scene: hohmann.dv1` so the two scenes cannot disagree.
`results_in_table: false` keeps the departure table readable. Music: `discovery` at −9 dB, ducked
under the voice.

**Checks.** `vidgen validate`; `vidgen lint` with the Kokoro narration: 0 findings in 16:9 and in
9:16. The 16:9 video was rendered at 1280×720, 30 fps (a 47 s orbit scene at 1080p took longer
than the development machine's 10-minute limit per command): 223.3 s, video and audio the same
length, −16.0 LUFS integrated, true peak −1.9 dBTP, no silence over 1.5 s. No audio is committed.
