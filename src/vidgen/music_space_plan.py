"""A draft space film from a score (DESIGN.md §122.12): ``vidgen music plan SCORE --style space``.

The music video plan (:mod:`vidgen.music_video_plan`: sections, roles, cuts on bar lines, a colour
per scene, the tracks each scene follows) is kept as it is; each of its scenes becomes a ``space``
scene instead of a ``web_cut`` scene with a starter page. The choices are rules, deterministic from
the score and ``--seed`` (the same score and seed, the same draft):

- **the move from the scene's role**: quiet (intro, breakdown, outro) a slow arc round a world toward
  its crescent, or in the first quiet scene a sunrise over the world's limb whose first light lands on
  a bar line where a section starts (else on the scene's last phrase line); build: an arrival at a
  world; verse: a chase view of a craft passing the world; drop and climax: a fly-by of the world, a
  craft passing the camera, or a jump to warp (the seed picks; a warp at most every other loud scene);
- **colour**: the scene's base colour (from the plan's colour script) picks the world, a ready-made one
  whose own colours are near that hue (gold, red, violet, blue, green or pale), the seed choosing among
  them; the sky is one sky (the seed) for the whole film, its look by energy (sparse when quiet, rich
  with nebulae at the peak); the grade is the plan's per role;
- **music**: the scene's pulse tracks pulse the sun's glare (or a warp's intensity), its glow and glint
  tracks drive a craft's throttle and lights; the camera never follows the beat;
- every scene starts and ends on a bar line with no fade (``fade: false``); the moves run over the
  scene's bars (``over: ['bar 9', 'bar 13']``), so they stay on the music however the film is cut;
  the first scene has an opening title, the last an end card (vidgen/title-cards).

It is a starting point: look at each scene (``vidgen still``), then change worlds, moves and timing.

``--style space-air`` (Step 392, DESIGN.md §123.14) makes the same plan into scenes in the air and beside
giant ships, by role and from the same score and seed: quiet, a skim over the sea at sunset; build, a
descent from orbit to the sea; verse, a plane chased over the alpine range (its afterburner on the glow
track); drop and climax, a pass along a dressed giant hull or a craft into its bay, by turns (the hull's
windows on the glow track). ``--style space`` is unchanged.
"""

from __future__ import annotations

import colorsys
import re
from pathlib import Path
from typing import Any

from vidgen.music_video_plan import ROLE_GRADES, DraftResult, MusicPlan, SceneCut, _bars_text, _flow, _seed, _yaml, place_score

#: Ready-made worlds by the colour they show (hue ranges in degrees, or "pale" for low saturation).
WORLD_COLOURS: dict[str, tuple[str, ...]] = {
    "gold": ("saturn", "jupiter", "ochre", "venus"), "red": ("mars", "ember", "io"), "violet": ("tempest",),
    "blue": ("neptune", "azure", "earth"), "green": ("verdant", "uranus"), "pale": ("moon", "europa", "boreas", "callisto"),
}
QUIET = ("intro", "breakdown", "outro")
LOUD = ("drop", "climax")
LOOK_BY_ROLE = {"intro": "sparse", "outro": "sparse", "breakdown": "natural", "verse": "natural", "build": "natural", "drop": "rich", "climax": "rich"}


def colour_family(hex_colour: str) -> str:
    """The family of WORLD_COLOURS a ``#rrggbb`` colour belongs to."""
    r, g, b = (int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
    h, light, s = colorsys.rgb_to_hls(r, g, b)
    hue = h * 360
    if s < 0.25:
        return "pale"
    if hue < 15 or hue >= 330:
        return "red"
    if hue < 70:
        return "gold"
    if hue < 170:
        return "green"
    if hue < 255:
        return "blue"
    return "violet"


def _pick(options: tuple[str, ...], key: int) -> str:
    return options[key % len(options)]


def space_shot(plan: MusicPlan, k: int, seed: int, warp_allowed: bool) -> dict[str, Any]:
    """What the space scene ``k`` of ``plan`` shows: ``{world, move, craft, warp, look, first_light}``."""
    cut = plan.scenes[k]
    key = _seed(f"{cut.id}:{seed}")
    world = _pick(WORLD_COLOURS[colour_family(cut.colours["base"])], key)
    look = LOOK_BY_ROLE[cut.role]
    first_quiet = cut.role in QUIET and not any(c.role in QUIET for c in plan.scenes[:k])
    if cut.role in QUIET:
        move = "reveal" if first_quiet and cut.bars >= 4 else "arc"
    elif cut.role == "build":
        move = "arrive"
    elif cut.role == "verse":
        move = "follow"
    else:
        move = _pick(("fly-by", "pass", "warp") if warp_allowed else ("fly-by", "pass"), key // 7)
    light_bar = None
    if move == "reveal":
        starts = [s.first_bar for s in plan.sections if cut.first_bar < s.first_bar < cut.first_bar + cut.bars]
        light_bar = (starts[0] if starts else cut.first_bar + cut.bars - 4 if cut.bars >= 8 else cut.first_bar + cut.bars // 2) + 1
    return {"world": world, "move": move, "craft": move in ("follow", "pass"), "warp": move == "warp", "look": look, "first_light": light_bar,
            "craft_kind": _pick(("ship", "tug", "probe", "station"), key // 13), "craft_seed": key % 50 + 1}


def _name(world: str) -> str:
    return world.capitalize()


def space_scene_lines(plan: MusicPlan, k: int, shot: dict[str, Any], seed: int) -> list[str]:
    """The YAML lines of space scene ``k`` (indented for ``scenes:``)."""
    c: SceneCut = plan.scenes[k]
    world = _name(shot["world"])
    over = [f"bar {c.first_bar + 1}", f"bar {c.first_bar + c.bars + 1}"]
    grade = dict(zip(("temperature", "saturation"), ROLE_GRADES[c.role]))
    music = f"{{tracks: {_flow(c.tracks)}}}" if c.tracks else "true"
    lines = [
        f"  # {_bars_text(c.first_bar, c.bars)} ({c.start:.2f} s): {c.section}, {c.role}: {_say(shot, world)}",
        f"  - id: {c.id}",
        "    type: space",
        f"    duration: {round(c.frames / plan.fps, 7)}",
        "    params:",
        "      fade: false",
        f"      music_data: {music}",
        f"      sky: {{seed: {seed}, look: {shot['look']}" + (", nebulae: 3" if shot["look"] == "rich" else "") + "}",
        "      sun: {direction: [1, -0.35, 0.22]}",
    ]
    if not shot["warp"]:
        lines.append(f"      bodies: [{{name: {world}, world: {shot['world']}}}]")
    if shot["craft"]:
        lines.append(f"      craft: [{{name: Ship, kind: {shot['craft_kind']}, seed: {shot['craft_seed']}, at: {_flow(world_offset(shot['world']))}, velocity: [0, 1500, 0]}}]")
    if shot["warp"]:
        lines.append(f"      phenomena: [{{kind: warp, over: {_flow(over)}}}]")
    lines.append(f"      camera: {_flow(move_spec(shot, world, over))}")
    react = []
    for track in c.react.get("pulse", ())[:1]:
        react.append({"track": track, "pulse": "warp" if shot["warp"] else "Sun", "amount": 0.35})
    if shot["craft"]:
        for track in c.react.get("glow", ())[:1]:
            react.append({"track": track, "glow": "Ship"})
        for track in c.react.get("glint", ())[:1]:
            react.append({"track": track, "glint": "Ship"})
    if react:
        lines.append(f"      music: {_flow(react)}")
    lines.append(f"      finish: {{grade: {_flow(grade)}}}")
    if k == 0:
        lines.append(f"      title: {{title: {_yaml(plan.title)}, start: 1}}")
    if k == len(plan.scenes) - 1:
        lines.append(f"      end_card: {{title: {_yaml(plan.title)}}}")
    return lines


def world_offset(world: str) -> list[str]:
    """Where a craft passes a world (the world at the middle): a little above its day side."""
    return [f"{_radius_km(world) * 1.3:.0f} km", "0 km", f"{_radius_km(world) * 0.12:.0f} km"]


def _radius_km(world: str) -> float:
    from vidgen.scenes.space_params import DEFAULT_RADIUS, real_radius
    return (real_radius(world) or DEFAULT_RADIUS) / 1000


def move_spec(shot: dict[str, Any], world: str, over: list[str]) -> dict[str, Any]:
    """The camera move of a shot (one move over the scene's bars)."""
    move = shot["move"]
    if move == "reveal":
        return {"move": "reveal", "behind": world, "at": f"bar {shot['first_light']}", "over": over, "rate": 0.4, "lens": "wide-normal"}
    if move == "arc":
        return {"move": "arc", "subject": world, "over": over, "phase": ["three-quarter", "crescent"], "distance": {"radii": 5}, "lens": "wide-normal"}
    if move == "arrive":
        return {"move": "arrive", "subject": world, "over": over, "lens": "wide"}
    if move == "follow":
        return {"move": "follow", "subject": "Ship", "over": over, "view": "chase", "push": 0.85, "around": world}
    if move == "pass":
        return {"move": "pass", "subject": "Ship", "over": over, "around": world}
    if move == "fly-by":
        return {"move": "fly-by", "subject": world, "over": over, "closest": {"radii": 2.4}, "side": "left"}
    return {"move": "look", "from": [0, 0, 0], "to": ["1000 km", 0, 0], "over": over}


def _say(shot: dict[str, Any], world: str) -> str:
    move = shot["move"]
    words = {"reveal": f"first light over {world}'s limb at bar {shot['first_light']}", "arc": f"a slow arc round {world} to its crescent",
             "arrive": f"arriving at {world}", "follow": f"a chase view of a {shot['craft_kind']} passing {world}",
             "pass": f"a {shot['craft_kind']} passing the camera over {world}", "fly-by": f"a fly-by of {world}", "warp": "a jump to warp"}
    return words[move]


#: The templates of ``--style space-air`` by role (DESIGN.md §123.14).
AIR_BY_ROLE = {"intro": "skim", "outro": "skim", "breakdown": "skim", "build": "descent", "verse": "chase", "drop": "ship", "climax": "ship"}
#: Hull families a pass shows (the seed picks); a craft into a bay is always the carrier's (hangar slots along a side).
PASS_HULLS = ("carrier", "ark", "spine", "cluster", "lance")
AIR_WORDS = {"skim": "a skim over the sea at sunset", "descent": "a descent from orbit to the sea", "chase": "a {plane} chased over the alpine range",
             "pass": "a pass along a {hull}", "bay": "a craft into a carrier's bay"}


def air_shot(plan: MusicPlan, k: int, seed: int, bay_next: bool) -> dict[str, Any]:
    """What scene ``k`` of ``plan`` shows with ``--style space-air``: {template, plane, hull, seed}."""
    cut = plan.scenes[k]
    key = _seed(f"{cut.id}:{seed}:air")
    template = AIR_BY_ROLE[cut.role]
    if template == "ship":
        template = "bay" if bay_next else "pass"
    return {"template": template, "plane": _pick(("glider", "skiff", "needle", "scout"), key // 3), "hull": _pick(PASS_HULLS, key // 11),
            "seed": key % 40 + 1}


def _air_say(shot: dict[str, Any]) -> str:
    return AIR_WORDS[shot["template"]].format(plane=shot["plane"], hull=shot["hull"])


def air_scene_lines(plan: MusicPlan, k: int, shot: dict[str, Any], seed: int) -> list[str]:
    """The YAML lines of scene ``k`` with ``--style space-air`` (indented for ``scenes:``)."""
    c: SceneCut = plan.scenes[k]
    over = [f"bar {c.first_bar + 1}", f"bar {c.first_bar + c.bars + 1}"]
    seconds = c.frames / plan.fps
    grade = dict(zip(("temperature", "saturation"), ROLE_GRADES[c.role]))
    music = f"{{tracks: {_flow(c.tracks)}}}" if c.tracks else "true"
    glow = list(c.react.get("glow", ()))[:1]
    t = shot["template"]
    lines = [f"  # {_bars_text(c.first_bar, c.bars)} ({c.start:.2f} s): {c.section}, {c.role}: {_air_say(shot)}",
             f"  - id: {c.id}", "    type: space", f"    duration: {round(c.frames / plan.fps, 7)}", "    params:", "      fade: false",
             f"      music_data: {music}", f"      sky: {{seed: {seed}, look: {LOOK_BY_ROLE[c.role]}}}"]
    if t == "skim":
        lines += ["      world: {sea: {state: breeze, seed: " + str(shot["seed"]) + "}, sun: [4, 284]}",
                  f"      camera: {_flow({'move': 'skim', 'over': over, 'heading': 284, 'speed': 90, 'clearance': 14, 'turn': 10, 'lens': 'wide'})}"]
    elif t == "descent":
        top = "400 km" if seconds >= 10 else "40 km"
        lines += ["      world: {planet: earth, at: [8, -150], sun: [38, 250], sea: {state: breeze, seed: 3}, clouds: {sky: fair, seed: " + str(shot["seed"]) + "}}",
                  f"      camera: {_flow({'move': 'descend', 'over': over, 'from': top, 'to': 300, 'heading': 300, 'turn': 30, 'speed': 90, 'lens': ['normal', 'wide']})}"]
    elif t == "chase":
        legs = [{"follow": {"clearance": 300}, "for": float(round(seconds + 2))}]
        flight = {"name": "Plane", "start": {"x": -6000, "z": 2000, "above_ground": 600, "heading": 70, "speed": 140}, "legs": legs}
        lines += ["      world: {land: alpine, clouds: fair, sun: [24, 250]}", f"      flights: [{_flow(flight)}]",
                  f"      craft: [{{name: Plane, plane: {shot['plane']}, seed: {shot['seed']}, fly: Plane, effects: {{contrails: {{always: true}}, exhaust: true}}}}]",
                  f"      camera: {_flow({'move': 'chase', 'flight': 'Plane', 'over': over, 'lens': 'wide-normal'})}"]
        if glow:
            lines.append(f"      music: {_flow([{'track': glow[0], 'glow': 'Plane', 'as': 'boost'}])}")
    else:
        hull = "carrier" if t == "bay" else shot["hull"]
        ref = ", scale_ref: {kind: ship, at: hangar-1, into: {hangar: hangar-1, over: " + _flow(over) + "}}" if t == "bay" else ""
        lines += ["      orbits: {central: earth, speedup: 1, bodies: [{name: Ship, altitude: 900 km}]}", "      bodies: [{name: Earth}]",
                  f"      craft: [{{name: Ship, hull: {hull}, seed: {shot['seed']}, dress: {{plumes: bank}}{ref}}}]"]
        move = ({"move": "into-bay", "ship": "Ship", "hangar": "hangar-1", "over": over} if t == "bay" else
                {"move": "hull-pass", "ship": "Ship", "over": over, "side": "port", "standoff": 60, "from": 0.2, "speed": 40})
        lines.append(f"      camera: {_flow(move)}")
        if glow:
            lines.append(f"      music: {_flow([{'track': glow[0], 'glow': 'Ship', 'as': 'lights'}])}")
        lines.append(f"      finish: {{grade: {_flow(grade)}}}")
    if k == 0:
        lines.append(f"      title: {{title: {_yaml(plan.title)}, start: 1}}")
    if k == len(plan.scenes) - 1:
        lines.append(f"      end_card: {{title: {_yaml(plan.title)}}}")
    return lines


def _air_shots(plan: MusicPlan, seed: int) -> list[dict[str, Any]]:
    out, bay = [], False
    for k in range(len(plan.scenes)):
        shot = air_shot(plan, k, seed, bay)
        if shot["template"] in ("pass", "bay"):
            bay = shot["template"] == "pass"
        out.append(shot)
    return out


def space_plan_yaml(plan: MusicPlan, source: str, seed: int = 1, style: str = "space") -> str:
    """The draft's ``video.yaml``: the score as ``music:`` and a ``space`` scene per cut of the plan (``style``:
    ``space``, Phase AN's orbital scenes; ``space-air``, scenes in the air and beside giant ships)."""
    lines = [
        f"# {plan.title}: a space film drafted by `vidgen music plan --style {style}` (seed {seed}) from {Path(source).name}.",
        f"# Music: {plan.key}, {plan.tempo:g} BPM, {plan.time[0]}/{plan.time[1]}; one bar = {plan.bar_seconds:.4f} s. Form: "
        + " | ".join(f"{s.name} {s.bars}" for s in plan.sections) + f" = {plan.bars} bars.",
        "# Every scene is a space scene (no code): a world chosen by the scene's colour, a camera move by its role, its bars as",
        "# the move's time. Change anything; look before rendering: vidgen still . --scene " + plan.scenes[0].id + " --at 2 --size 640x360",
        "# Render: vidgen render . --draft   (then --preview, then the final render). Code: vidgen space-page . --scene ID",
        f"title: {_yaml(plan.title)}",
        f"output: {re.sub(r'[^a-z0-9_]+', '_', plan.title.lower()).strip('_') or 'space_film'}",
        f"format: {{width: 1280, height: 720, fps: {plan.fps}}}",
        f"preview: {{width: 640, height: 360, fps: {plan.fps}}}",
        "transition: cut",
        f"music: {{source: {_yaml(source)}, volume: 0, start: 0, loop: false, fade_in: 0, fade_out: 1.5, duck: false}}",
        "audio: {normalize: true, target_lufs: -14, true_peak: -1.5}",
        "scenes:",
    ]
    if style == "space-air":
        lines[2] = "# Every scene is a space scene (no code): in the air (a skim, a descent, a chase) or beside a giant ship, by its role; its bars as"
        for k, shot in enumerate(_air_shots(plan, seed)):
            lines += air_scene_lines(plan, k, shot, seed)
        return "\n".join(lines) + "\n"
    warp_ready = True
    for k in range(len(plan.scenes)):
        shot = space_shot(plan, k, seed, warp_ready)
        if plan.scenes[k].role in LOUD:
            warp_ready = not shot["warp"]
        lines += space_scene_lines(plan, k, shot, seed)
    return "\n".join(lines) + "\n"


def space_plan_text(plan: MusicPlan, seed: int = 1, style: str = "space") -> str:
    """One line per scene: what its space scene shows."""
    width = max(len(c.id) for c in plan.scenes)
    if style == "space-air":
        out = [f"space scenes in the air and beside giant ships (seed {seed}):"]
        for c, shot in zip(plan.scenes, _air_shots(plan, seed)):
            out.append(f"  {c.id:<{width}}  {c.role:<9} {_air_say(shot)}")
        return "\n".join(out)
    out, warp_ready = [f"space scenes (seed {seed}):"], True
    for k, c in enumerate(plan.scenes):
        shot = space_shot(plan, k, seed, warp_ready)
        if c.role in LOUD:
            warp_ready = not shot["warp"]
        out.append(f"  {c.id:<{width}}  {c.role:<9} {_say(shot, _name(shot['world']))}")
    return "\n".join(out)


def write_space_video(plan: MusicPlan, output: Path, *, force: bool = False, seed: int = 1, style: str = "space") -> DraftResult:
    """Write ``plan`` as a draft space film in the folder ``output`` (as :func:`write_music_video`, with
    ``space`` scenes and no pages: the scenes need no code)."""
    from vidgen.fileio import write_text_atomic

    source, files, created = place_score(plan, output, force=force)
    config = output / "video.yaml"
    write_text_atomic(config, space_plan_yaml(plan, source, seed, style))
    gitignore = output / ".gitignore"
    if not gitignore.exists():
        write_text_atomic(gitignore, "build/\nexports/\n*.mp4\n")
    return DraftResult(output, config, tuple(files), created)


__all__ = ["AIR_BY_ROLE", "PASS_HULLS", "WORLD_COLOURS", "air_scene_lines", "air_shot", "colour_family", "move_spec", "space_plan_text", "space_plan_yaml",
           "space_shot", "write_space_video"]
