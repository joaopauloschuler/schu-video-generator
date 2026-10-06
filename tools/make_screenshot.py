"""Draw the fake app screenshot used by ``examples/gallery`` (``assets/app.png``) with Pillow.

Not shipped with vidgen; a maintainer tool. The picture is a generic task-planner dashboard
(no real product or brand) in flat colours, so the PNG stays small. Run from the repository
root::

    python tools/make_screenshot.py [--out examples/gallery/assets/app.png]

Regions the example's callouts point at (fractions of 1280 x 800, ``[x, y, w, h]`` from the
top left): search field ``[0.216, 0.038, 0.269, 0.055]``, "New task" button
``[0.8, 0.038, 0.114, 0.055]`` (its centre ``[0.857, 0.065]``), overdue card
``[0.736, 0.15, 0.25, 0.17]``, chart ``[0.205, 0.37, 0.428, 0.58]`` (Thursday's bar near
``[0.425, 0.55]``), "Review pull request" row ``[0.675, 0.545, 0.28, 0.085]``, task list
``[0.656, 0.37, 0.313, 0.58]``, sidebar ``[0, 0, 0.16, 1]``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "src" / "vidgen" / "data" / "fonts" / "Inter"
W, H = 1280, 800

BG, CARD, LINE = "#F3F4F7", "#FFFFFF", "#E2E5EB"
INK, MUTED = "#1D2433", "#6B7385"
SIDEBAR, SIDE_INK, SIDE_ACTIVE = "#1E2533", "#AEB6C6", "#2F3A4F"
BLUE, GREEN, RED, AMBER = "#3D6FE0", "#2E9E6A", "#D9483B", "#E0A23D"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / ("Inter-Bold.ttf" if bold else "Inter-Regular.ttf")), size)


def card(d: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    d.rounded_rectangle(box, radius=12, fill=CARD, outline=LINE, width=2)


def draw() -> Image.Image:
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)

    # sidebar: app name and navigation
    d.rectangle((0, 0, 204, H), fill=SIDEBAR)
    d.rounded_rectangle((24, 26, 52, 54), radius=7, fill=BLUE)
    d.text((64, 26), "Planner", font=font(22, True), fill="#FFFFFF")
    nav = ["Overview", "Tasks", "Calendar", "Reports", "Team", "Settings"]
    for k, name in enumerate(nav):
        y = 104 + k * 52
        if k == 0:
            d.rounded_rectangle((14, y - 10, 190, y + 32), radius=8, fill=SIDE_ACTIVE)
        d.rounded_rectangle((30, y + 3, 46, y + 19), radius=4, outline=SIDE_INK if k else "#FFFFFF", width=2)
        d.text((60, y), name, font=font(18, k == 0), fill="#FFFFFF" if k == 0 else SIDE_INK)

    # top bar: search, new task, avatar
    d.rounded_rectangle((276, 30, 620, 74), radius=10, fill=CARD, outline=LINE, width=2)
    d.ellipse((292, 43, 308, 59), outline=MUTED, width=2)
    d.line((306, 57, 313, 64), fill=MUTED, width=2)
    d.text((324, 41), "Search tasks…", font=font(17), fill=MUTED)
    d.rounded_rectangle((1024, 30, 1170, 74), radius=10, fill=BLUE)
    d.text((1044, 40), "+  New task", font=font(18, True), fill="#FFFFFF")
    d.ellipse((1196, 30, 1240, 74), fill="#C9D4EA")
    d.text((1206, 40), "AK", font=font(17, True), fill=INK)

    # stat cards
    stats = [("Open tasks", "24", INK), ("Done this week", "18", GREEN), ("Overdue", "3", RED)]
    for k, (label, value, color) in enumerate(stats):
        x0 = 262 + k * 340
        card(d, (x0, 120, x0 + 320, 256))
        d.text((x0 + 24, 140), label, font=font(17), fill=MUTED)
        d.text((x0 + 24, 172), value, font=font(48, True), fill=color)
        if k == 2:
            d.rounded_rectangle((x0 + 196, 190, x0 + 296, 222), radius=16, fill="#FBE3E0")
            d.text((x0 + 212, 195), "Review", font=font(16, True), fill=RED)

    # chart card: tasks completed per day
    card(d, (262, 296, 810, 760))
    d.text((286, 316), "Tasks completed", font=font(20, True), fill=INK)
    d.text((286, 346), "Last 7 days", font=font(15), fill=MUTED)
    values = [5, 8, 6, 11, 9, 4, 7]
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    base, top = 712, 400
    for g in range(4):
        y = base - g * (base - top) // 3
        d.line((300, y, 790, y), fill=LINE, width=1)
    for k, (v, day) in enumerate(zip(values, days)):
        x = 320 + k * 68
        h = int(v / 12 * (base - top))
        d.rounded_rectangle((x, base - h, x + 38, base), radius=6, fill=BLUE if k != 3 else AMBER)
        d.text((x + 2, base + 10), day, font=font(14), fill=MUTED)
        d.text((x + 12 - (6 if v > 9 else 0), base - h - 22), str(v), font=font(14, True), fill=INK)

    # task list card
    card(d, (840, 296, 1240, 760))
    d.text((864, 316), "Today", font=font(20, True), fill=INK)
    tasks = [("Draft release notes", "10:00", BLUE, False), ("Review pull request", "11:30", AMBER, True),
             ("Update the roadmap", "14:00", GREEN, False), ("Team sync", "16:00", BLUE, False),
             ("Plan next sprint", "17:30", RED, False)]
    for k, (name, time, color, done) in enumerate(tasks):
        y = 364 + k * 76
        d.line((864, y + 60, 1216, y + 60), fill=LINE, width=1)
        d.rounded_rectangle((864, y + 12, 886, y + 34), radius=5, outline=MUTED if not done else GREEN, width=2, fill=GREEN if done else None)
        if done:
            d.line((869, y + 23, 874, y + 29, 882, y + 17), fill="#FFFFFF", width=3)
        d.text((900, y + 10), name, font=font(17, False), fill=MUTED if done else INK)
        d.ellipse((900, y + 40, 908, y + 48), fill=color)
        d.text((916, y + 35), time, font=font(13), fill=MUTED)
    return im


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "examples" / "gallery" / "assets" / "app.png")
    args = parser.parse_args()
    image = draw().quantize(colors=64, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    image.save(args.out, optimize=True)
    print(f"wrote {args.out} ({args.out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
