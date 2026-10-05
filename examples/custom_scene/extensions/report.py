from vidgen.api import *


@hook("post_render")
def write_summary(ctx):
    """Write a small text summary next to the video."""
    out = ctx.data["output"]
    summary = out.with_suffix(".txt")
    scenes = ctx.data["timings"]["scenes"]
    lines = [f"{s['id']}: {s['duration']:.2f} s" for s in scenes]
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
