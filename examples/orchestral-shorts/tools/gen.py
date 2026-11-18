"""Write a film's video.yaml from its shot list, cut on the score's bar lines.

Usage: python tools/gen.py FILM_DIR  (reads FILM_DIR/shots.yaml, writes FILM_DIR/video.yaml)

Bar timing, colours and reactions come from `vidgen music plan --json` (the section a shot starts
in) unless a shot sets them. Every film draws with ../shared/orch.js and cuts with the `web_cut`
scene type of ../shared/web_cut.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

FPS = 30
GRADE = {"intro": {"temperature": -0.15, "saturation": 0.95}, "verse": {"temperature": -0.05, "saturation": 1.0},
         "build": {"temperature": 0.0, "saturation": 1.05}, "drop": {"temperature": 0.08, "saturation": 1.12},
         "climax": {"temperature": 0.15, "saturation": 1.15}, "breakdown": {"temperature": -0.1, "saturation": 0.95},
         "outro": {"temperature": -0.05, "saturation": 0.95}}
SCRIPT = "../shared/orch.js"


def music_plan(score: Path) -> dict:
    """`vidgen music plan SCORE --json`."""
    run = subprocess.run([sys.executable, "-m", "vidgen", "music", "plan", str(score), "--json"],
                         capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(run.stdout)


def video_text(spec: dict, plan: dict) -> str:
    """The film's video.yaml from its shot list ``spec`` and the score's ``plan``."""
    score = spec["score"]
    bar = plan["bar_seconds"]

    def plan_scene(b: int) -> dict:
        for s in plan["scenes"]:
            if s["first_bar"] <= b < s["first_bar"] + s["bars"]:
                return s
        return plan["scenes"][-1]

    scenes, b, tracks = [], 1, set()
    for i, sh in enumerate(spec["shots"]):
        n = sh.pop("bars")
        ps = plan_scene(b)
        f0, f1 = round((b - 1) * bar * FPS), round((b - 1 + n) * bar * FPS)
        last = i == len(spec["shots"]) - 1
        frames = f1 - f0 + (round(spec.get("tail", 3.0) * FPS) if last else 0)
        react = sh.pop("react", None) or ps["react"]
        for v in react.values():
            tracks.update(v)
        if sh.get("melody"):
            tracks.add(sh["melody"])
        data = {"mode": sh.pop("mode"), "seed": sh.pop("seed", 100 + 17 * i), "colours": sh.pop("colours", ps["colours"]),
                "react": react, "grade": sh.pop("grade", GRADE.get(ps["role"], {})), **sh}
        if last:
            data.setdefault("fadeOut", spec.get("fade_out", 1.8))
        data["note"] = f"bars {b}-{b + n - 1} ({ps['section']}, {ps['role']})"
        scenes.append({"id": f"{i + 1:02d}_{data['mode']}", "type": "web_cut", "duration": round(frames / FPS, 7),
                       "params": {"script": SCRIPT, "data": data}})
        b += n
    if b - 1 > plan["bars"]:
        raise SystemExit(f"shots cover {b - 1} bars, the score has {plan['bars']}")
    music_data = {"tracks": sorted(tracks)}
    for s in scenes:
        s["params"]["music_data"] = music_data
    header = [f"# {spec['title']}: a portrait orchestral music video.",
              f"# Music: assets/music/{score}.yaml, an original score for vidgen's own orchestra ({plan['tempo']} BPM, {plan['key']}; one bar = {bar:.4f} s).",
              f"# Pictures: {SCRIPT} (vidgen/three-kit, music-time, three-finish, title-cards), one web_cut shot per 1-2 bars.",
              "# Written by ../tools/gen.py from shots.yaml.", ""]
    config = {"title": spec["title"], "output": spec["output"],
              "format": {"width": spec.get("width", 1080), "height": spec.get("height", 1920), "fps": FPS},
              "preview": {"width": 360, "height": 640, "fps": FPS},
              "theme": {"preset": spec.get("theme", "dark_tech")}, "transition": "cut",
              "render": {"intermediate": "compact", "keep_intermediates": False},
              "music": {"source": score, "volume": 0, "start": 0, "loop": False, "fade_in": 0, "fade_out": spec.get("music_fade", 1.5), "duck": False},
              "audio": {"normalize": True, "target_lufs": -14, "true_peak": -1.5, "bitrate": "256k"},
              "extensions": ["../shared"], "web_root": "..", "scenes": scenes}
    return "\n".join(header) + yaml.safe_dump(config, sort_keys=False, width=220, default_flow_style=None)


def main() -> None:
    film = Path(sys.argv[1])
    spec = yaml.safe_load((film / "shots.yaml").read_text(encoding="utf-8"))
    plan = music_plan(film / "assets" / "music" / f"{spec['score']}.yaml")
    text = video_text(spec, plan)
    (film / "video.yaml").write_text(text, encoding="utf-8", newline="\n")
    config = yaml.safe_load(text)
    print(f"{len(config['scenes'])} shots, {sum(s['duration'] for s in config['scenes']):.2f} s")


if __name__ == "__main__":
    main()
