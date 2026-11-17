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


def space_plan_yaml(plan: MusicPlan, source: str, seed: int = 1) -> str:
    """The draft's ``video.yaml``: the score as ``music:`` and a ``space`` scene per cut of the plan."""
    lines = [
        f"# {plan.title}: a space film drafted by `vidgen music plan --style space` (seed {seed}) from {Path(source).name}.",
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
    warp_ready = True
    for k in range(len(plan.scenes)):
        shot = space_shot(plan, k, seed, warp_ready)
        if plan.scenes[k].role in LOUD:
            warp_ready = not shot["warp"]
        lines += space_scene_lines(plan, k, shot, seed)
    return "\n".join(lines) + "\n"


def space_plan_text(plan: MusicPlan, seed: int = 1) -> str:
    """One line per scene: what its space scene shows."""
    out, warp_ready = [f"space scenes (seed {seed}):"], True
    width = max(len(c.id) for c in plan.scenes)
    for k, c in enumerate(plan.scenes):
        shot = space_shot(plan, k, seed, warp_ready)
        if c.role in LOUD:
            warp_ready = not shot["warp"]
        out.append(f"  {c.id:<{width}}  {c.role:<9} {_say(shot, _name(shot['world']))}")
    return "\n".join(out)


def write_space_video(plan: MusicPlan, output: Path, *, force: bool = False, seed: int = 1) -> DraftResult:
    """Write ``plan`` as a draft space film in the folder ``output`` (as :func:`write_music_video`, with
    ``space`` scenes and no pages: the scenes need no code)."""
    from vidgen.fileio import write_text_atomic

    source, files, created = place_score(plan, output, force=force)
    config = output / "video.yaml"
    write_text_atomic(config, space_plan_yaml(plan, source, seed))
    gitignore = output / ".gitignore"
    if not gitignore.exists():
        write_text_atomic(gitignore, "build/\nexports/\n*.mp4\n")
    return DraftResult(output, config, tuple(files), created)


__all__ = ["WORLD_COLOURS", "colour_family", "move_spec", "space_plan_text", "space_plan_yaml", "space_shot", "write_space_video"]
