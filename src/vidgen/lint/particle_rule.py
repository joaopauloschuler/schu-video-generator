"""The particle-physics accuracy lint rules (Phase Y, Step 242, DESIGN §99.13): narration and
on-screen text against the particle model, the conservation checker, the vertex rules, the
detector signatures and what the particle scenes compute.

``particle_mass``, ``particle_charge``, ``particle_spin``, ``particle_lifetime`` (lifetimes,
half-lives and widths) against PDG 2024 (:mod:`vidgen.particle_physics.data`);
``branching_ratio`` against the tables (:mod:`vidgen.particle_physics.branching`);
``conservation_claim`` ("allowed", "forbidden by baryon number", "conserves charge") against
:func:`~vidgen.particle_physics.check`; ``feynman_boson`` (a boson coupling to what it does not,
flavour changed by something other than the W, a boson named as exchanged that the scene's
diagram does not have); ``kinematics_number`` (a ``kinematics`` scene's computed values — the
``from_scene`` names —, decay lengths βγcτ and dilated lives said with a momentum or γ,
thresholds of a written reaction); ``detector_signature``; ``significance_claim`` (the p-value
said as the chance the result is wrong; σ said for a ``mass_spectrum`` against its computed
significance); ``simulated_label`` (simulated data called real, a spectrum or event display
without "simulated" on screen); ``particle_units`` (info: masses written both as GeV and
GeV/c² in one video). The knowledge is in :mod:`vidgen.particle_physics.accuracy`; numbers
are read by the ``calc_*`` reader. ``particle_charge`` and ``particle_spin`` read every project,
the others projects with a particle-physics scene (a false positive elsewhere costs more than
the check gives). The runner adds :func:`particle_issues` to :attr:`SceneContext.science`.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from vidgen.lint.calc_rule import screen_texts
from vidgen.lint.rules import Issue, SceneContext, rule
from vidgen.lint.science_rule import ScienceIssue, _issues, _params
from vidgen.particle_physics import accuracy as pa
from vidgen.quantities import accuracy as qa

if TYPE_CHECKING:
    from vidgen.config import LintRules, SceneConfig
    from vidgen.project import Project

PARTICLE_RULES = pa.PARTICLE_RULES
#: Scene types of the particle-physics phase: a project with one is read by every rule.
PARTICLE_SCENES = frozenset({"standard_model", "feynman", "kinematics", "detector", "mass_spectrum", "decay_chain", "branching", "branching_pie"})
#: ``plot`` models that simulate particle data (labelled "simulated") or compute particle curves.
SIMULATED_MODELS = frozenset({"mass_spectrum", "decay_times"})
PARTICLE_MODELS = SIMULATED_MODELS | {"z_lineshape", "two_body_opening"}
_BOSON_KEYS = frozenset({"gamma", "g", "Z", "W+", "W-", "H"})
_cache: dict[int, tuple[Any, "_Project"]] = {}


@dataclass
class _Scene:
    """What one scene gives the rules: its processes ("this decay"), the diagram's bosons, a
    kinematics scene's values, a spectrum's significances, whether its data are simulated and
    what it shows on screen to say so."""

    processes: list[Any] = field(default_factory=list)
    bosons: list[str] = field(default_factory=list)
    values: dict[str, tuple[float, str]] = field(default_factory=dict)
    sigmas: list[tuple[str, float]] = field(default_factory=list)
    sigma_max: float | None = None
    simulated: bool = False
    labelled: bool = True


@dataclass
class _Project:
    particle: bool
    scenes: dict[str, _Scene]
    explicit_units: list[str]


def _plot_models(spec: SceneConfig) -> set[str]:
    models = spec.params.get("models") if spec.type == "plot" else None
    if not isinstance(models, dict):
        return set()
    return {str(m.get("function")) for m in models.values() if isinstance(m, dict) and m.get("kind") == "function"}


def _is_particle(spec: SceneConfig) -> bool:
    if spec.type in PARTICLE_SCENES:
        return True
    if spec.type == "plot":
        return bool(_plot_models(spec) & PARTICLE_MODELS)
    if spec.type == "calculation":
        symbols = spec.params.get("symbols") or spec.params.get("given") or []
        return any(isinstance(s, dict) and ({"mass", "lifetime", "width"} & set(s)) for s in (symbols if isinstance(symbols, list) else []))
    return False


def _scene_facts(spec: SceneConfig) -> _Scene:
    from vidgen.particle_physics import parse_process

    out = _Scene()
    if spec.type == "plot" and _plot_models(spec) & SIMULATED_MODELS:
        out.simulated = True
        words = " ".join(t for _, t in screen_texts(spec))
        series = spec.params.get("series") or []
        words += " " + " ".join(str(s.get("name", "")) for s in series if isinstance(s, dict))
        out.labelled = "simulat" in words.lower()
        return out
    if spec.type not in PARTICLE_SCENES:
        return out
    params = _params(spec)
    if params is None:
        return out
    if spec.type == "feynman":
        from vidgen.scenes.feynman import build_diagrams

        for d in build_diagrams(params):
            out.processes.append(d.process())
            out.bosons += [ln.particle.key for ln in d.lines if ln.particle.key in _BOSON_KEYS]
        out.processes = list({str(p): p for p in out.processes}.values())
    elif spec.type == "decay_chain":
        out.processes = [parse_process(str(d)) for d in params.decays]
    elif spec.type == "kinematics":
        from vidgen.scenes.kinematics import Kinematics

        out.values = Kinematics.calc_values(params)
        if params.decay:
            out.processes = [parse_process(params.decay)]
    elif spec.type == "mass_spectrum":
        out.simulated = True
        _spectrum_sigmas(params, out)
    elif spec.type == "detector":
        out.simulated = True
        out.labelled = "simulat" in str(params.label).lower()
    return out


def _spectrum_sigmas(params: Any, out: _Scene) -> None:
    """The significances a ``mass_spectrum`` computes: the expected (Asimov) one with all the
    events and its largest along the filling, and the likelihood-ratio fit's."""
    from vidgen.particle_physics import spectrum as sp
    from vidgen.scenes.mass_spectrum import significance

    s = sp.generate(params.spectrum_spec())
    curve = s.asimov_curve()
    if len(curve):
        out.sigmas.append(("expected, Asimov, all events", float(curve[-1])))
        out.sigma_max = float(max(curve))
    if params.fits:
        f = params.fits[0]
        try:
            z = significance(params.spectrum_spec(), float(params.series[0].bin_width), f.model, int(f.background or 0)).z
            out.sigmas.append(("likelihood-ratio fit", float(z)))
        except Exception:  # noqa: BLE001 - the scene reports a failing fit
            pass


def facts(project: Project) -> _Project:
    """Whether the project is about particles, each particle scene's facts and the masses its
    screens write in eV/c² (computed once per project)."""
    key = id(project)
    if key in _cache and _cache[key][0] is project:
        return _cache[key][1]
    import vidgen.scenes  # noqa: F401 - the scene types read their params (registered once)

    specs = list(project.config.scenes)
    particle = any(_is_particle(s) for s in specs)
    scenes: dict[str, _Scene] = {}
    explicit: list[str] = []
    if particle:
        for spec in specs:
            try:
                scenes[spec.id] = _scene_facts(spec)
            except Exception:  # noqa: BLE001 - validation reports a scene that cannot be resolved
                scenes[spec.id] = _Scene()
            for _, text in screen_texts(spec):
                for sentence in pa.sentences(text):
                    explicit += pa.unit_styles(sentence)[1]
    found = _Project(particle, scenes, explicit)
    _cache.clear()
    _cache[key] = (project, found)
    return found


def _texts(spec: SceneConfig) -> list[tuple[str | None, str, str | None]]:
    """``(beat, text, where)``: the narration, then the screen texts."""
    first = spec.beats[0].id if spec.beats else None
    out: list[tuple[str | None, str, str | None]] = [(beat.id, str(beat.text), None) for beat in spec.beats]
    out += [(first, text, where) for where, text in screen_texts(spec)]
    for key in ("label",):
        value = spec.params.get(key)
        if spec.type in ("detector", "mass_spectrum") and isinstance(value, str) and value:
            out.append((first, value, key))
    return out


def particle_issues(project: Project, scene_id: str, rules: LintRules) -> list[ScienceIssue]:
    """Every particle-physics finding of scene ``scene_id`` (rules turned off are skipped)."""
    spec = project.scene(scene_id)
    on = {name for name in PARTICLE_RULES if getattr(rules, name).severity != "off"}
    if not on:
        return []
    known = facts(project)
    if not known.particle:
        on &= set(pa.EVERYWHERE)
        if not on:
            return []
    scene = known.scenes.get(scene_id, _Scene())
    out: list[ScienceIssue] = []
    seen: set[tuple[str, str | None, str]] = set()
    first = spec.beats[0].id if spec.beats else None

    def add(found: pa.Said, beat: str | None, where: str | None) -> None:
        if found.rule not in on:
            return
        said = f"{where} '{qa.quote(found.quote)}'" if where else f'"{qa.quote(found.quote)}"'
        message = f"{said}: {found.message}"
        if (found.rule, beat, message) not in seen:
            seen.add((found.rule, beat, message))
            out.append(ScienceIssue(found.rule, beat, message, found.severity))

    t_mass = rules.particle_mass.tolerance
    t_life = rules.particle_lifetime.tolerance
    t_br = rules.branching_ratio.tolerance
    t_kin = rules.kinematics_number.tolerance
    t_sig = rules.significance_claim.sigmas
    for beat, text, where in _texts(spec):
        for sentence in pa.sentences(text):
            for found in pa.conservation_claims(sentence, scene.processes):
                add(found, beat, where)
        for sentence in pa.plain_sentences(text):
            claims = pa.charge_claims(sentence) + pa.spin_claims(sentence)
            if known.particle:
                claims += pa.mass_claims(sentence, t_mass) + pa.lifetime_claims(sentence, t_life) + pa.branching_claims(sentence, t_br)
                claims += pa.boson_claims(sentence, scene.bosons if spec.type == "feynman" else None)
                claims += pa.signature_claims(sentence) + pa.p_meaning_claims(sentence)
                claims += pa.flight_claims(sentence, max(t_kin, 0.1)) + pa.threshold_claims(sentence, t_kin)
                if scene.values:
                    claims += pa.kinematics_claims(sentence, scene.values, t_kin)
                if scene.sigmas:
                    claims += pa.sigma_claims(sentence, scene.sigmas, t_sig, scene.sigma_max)
                if scene.simulated and where is None:
                    claims += pa.real_data_claims(sentence)
                if where is not None and known.explicit_units:
                    natural = pa.unit_styles(sentence)[0]
                    if natural:
                        claims.append(pa.Said("particle_units", sentence, f"{', '.join(natural)}: this video also writes masses in GeV/c² "
                                                                          f"({', '.join(dict.fromkeys(known.explicit_units))}); write them one way "
                                                                          f"(natural units, c = 1: GeV; or GeV/c² throughout)"))
            for found in claims:
                add(found, beat, where)
    if "simulated_label" in on and scene.simulated and not scene.labelled:
        what = "event display" if spec.type == "detector" else "plot of simulated data"
        fix = "keep \"simulated event\" in label" if spec.type == "detector" else "say \"simulated\" in a series name, the title or the caption"
        out.append(ScienceIssue("simulated_label", first, f"the {what} does not say on screen that its data are simulated: {fix}"))
    return out


# ----- the rules -----------------------------------------------------------------------------------------


@rule("particle_mass", scope="scene")
def particle_mass(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """A particle's mass said or shown differently from PDG 2024 ("the W weighs 91 GeV")."""
    yield from _issues(ctx, "particle_mass")


@rule("particle_charge", scope="scene", default="error")
def particle_charge(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """A particle's electric charge said wrong ("the down quark has charge +2/3")."""
    yield from _issues(ctx, "particle_charge")


@rule("particle_spin", scope="scene", default="error")
def particle_spin(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """A particle's spin said wrong ("the photon has spin 1/2", "the Higgs boson is a fermion")."""
    yield from _issues(ctx, "particle_spin")


@rule("particle_lifetime", scope="scene")
def particle_lifetime(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """A mean life, half-life or width said differently from PDG 2024 ("the muon lives 2.2 ms")."""
    yield from _issues(ctx, "particle_lifetime")


@rule("branching_ratio", scope="scene")
def branching_ratio(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """A branching ratio said wrong ("most Higgs bosons decay to two photons", "70 % of W decays give leptons")."""
    yield from _issues(ctx, "branching_ratio")


@rule("conservation_claim", scope="scene")
def conservation_claim(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """A reaction or decay called allowed (or forbidden, or conserving / violating a law) against the conservation checker."""
    yield from _issues(ctx, "conservation_claim")


@rule("feynman_boson", scope="scene")
def feynman_boson(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """The wrong boson for an interaction: a coupling the Standard Model does not have, flavour changed without a W, a boson the diagram does not show."""
    yield from _issues(ctx, "feynman_boson")


@rule("kinematics_number", scope="scene")
def kinematics_number(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """An invariant mass, momentum, energy, decay length, dilated life or threshold said differently from what is computed."""
    yield from _issues(ctx, "kinematics_number")


@rule("detector_signature", scope="scene")
def detector_signature(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """A detector signature said wrong ("photons leave tracks", "muons stop in the ECAL", "neutrinos are seen in the calorimeter")."""
    yield from _issues(ctx, "detector_signature")


@rule("significance_claim", scope="scene")
def significance_claim(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """A p-value said as the chance the result is wrong, or a σ said that the spectrum does not reach."""
    yield from _issues(ctx, "significance_claim")


@rule("simulated_label", scope="scene")
def simulated_label(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """Simulated data called real, or a spectrum or event display that does not say on screen it is simulated."""
    yield from _issues(ctx, "simulated_label")


@rule("particle_units", scope="scene", default="info")
def particle_units(ctx: SceneContext, settings: Any) -> Iterator[Issue]:
    """Masses written both in GeV (natural units) and GeV/c² on screen in one video."""
    yield from _issues(ctx, "particle_units")
