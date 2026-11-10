"""Step 325: ``video_clip`` ``match_previous`` (``vidgen.clip_join``): the gain per colour channel
between the previous clip's last frame and this clip's first, its easing, the limits that skip
it, the frame treatment of ``ClipMobject``, what ``vidgen validate`` rejects, and the scene
fingerprint. No scene is rendered."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from conftest import minimal_config, write_clip
from test_builtin_scenes import cls_of
from vidgen.cli import check_project
from vidgen.clip_join import (
    APPLIED_RANGE,
    GAIN_RANGE,
    MAX_DIFFERENCE,
    ClipJoin,
    GainMatch,
    MatchPrevious,
    ShownClip,
    apply_gains,
    channel_gains,
    correction_left,
    measure_match,
    opening_treatment,
    picture_difference,
)
from vidgen.clips import ClipTiming, cover_crop
from vidgen.project import Project
from vidgen.render.fingerprint import scene_fingerprint
from vidgen.theme import Theme
from vidgen.videoplan import VideoPlan


def picture(scale: float = 1.0, tint: tuple[float, float, float] = (1.0, 1.0, 1.0)) -> np.ndarray:
    """A 16 x 16 RGBA picture (a ramp with a bright square), each channel times ``scale * tint``."""
    y, x = np.mgrid[0:16, 0:16]
    base = 60.0 + 4.0 * x + 3.0 * y
    base[4:8, 4:8] = 180.0
    rgb = np.stack([base * scale * t for t in tint], axis=-1)
    alpha = np.full((16, 16, 1), 255.0)
    return np.clip(np.rint(np.concatenate([rgb, alpha], axis=-1)), 0, 255).astype(np.uint8)


def test_channel_gains_restore_the_mean_colour() -> None:
    reference, darker = picture(), picture(0.92, (1.0, 0.98, 1.02))
    gains = channel_gains(reference, darker)
    assert gains == pytest.approx((1 / 0.92, 1 / (0.92 * 0.98), 1 / (0.92 * 1.02)), abs=0.01)
    corrected = apply_gains(darker, gains)
    assert corrected[..., :3].reshape(-1, 3).mean(axis=0) == pytest.approx(reference[..., :3].reshape(-1, 3).mean(axis=0), abs=0.5)
    assert (corrected[..., 3] == 255).all() and darker[0, 0, 0] != corrected[0, 0, 0]   # alpha kept, a new array
    assert channel_gains(reference, np.zeros_like(reference)) is None                    # too dark to measure


def test_apply_gains_cuts_off_at_white() -> None:
    frame = np.full((2, 2, 4), 250, dtype=np.uint8)
    assert apply_gains(frame, (1.1, 1.0, 0.5))[0, 0].tolist() == [255, 250, 125, 250]


def test_picture_difference() -> None:
    assert picture_difference(picture(), picture()) == 0.0
    assert picture_difference(np.zeros((4, 4, 3), np.uint8), np.full((4, 4, 3), 255, np.uint8)) == 1.0


@pytest.mark.parametrize(("played", "left"), [(-1.0, 1.0), (0.0, 1.0), (0.5, 0.5), (1.0, 0.0), (3.0, 0.0)])
def test_correction_left_eases_from_one_to_zero(played: float, left: float) -> None:
    assert correction_left(played, 1.0) == pytest.approx(left)
    assert correction_left(played * 2, 2.0) == pytest.approx(left)


def test_correction_left_never_rises() -> None:
    values = [correction_left(k / 24, 1.0) for k in range(30)]
    assert values == sorted(values, reverse=True) and values[1] > 0.99


def test_gain_match_eases_to_the_clips_own_pixels() -> None:
    match = GainMatch((1.08, 1.09, 1.07), seconds=1.0)
    assert match.state(0.0) == (1.08, 1.09, 1.07)
    assert match.state(0.5) == pytest.approx((1.04, 1.045, 1.035))
    assert match.state(1.0) is None and match.state(4.0) is None
    held = GainMatch((1.08, 1.09, 1.07), seconds=1.0, hold=True)
    assert held.state(0.0) == held.state(4.0) == (1.08, 1.09, 1.07)
    frame = picture()
    assert np.array_equal(match.apply(frame, (1.08, 1.09, 1.07)), apply_gains(frame, (1.08, 1.09, 1.07)))


def test_measure_match_matches_a_continuation() -> None:
    match, text = measure_match(picture(), picture(0.92), MatchPrevious(seconds=2.0, hold=True))
    assert match is not None and (match.seconds, match.hold) == (2.0, True)
    assert match.gains == pytest.approx((1 / 0.92,) * 3, abs=0.01) and "gains R 1.08" in text


def test_measure_match_skips_what_is_not_a_continuation() -> None:
    settings = MatchPrevious()
    match, text = measure_match(picture(), picture(0.7), settings)
    assert match is None and f"outside {GAIN_RANGE[0]}-{GAIN_RANGE[1]}" in text
    match, text = measure_match(picture(), picture()[::-1, ::-1], settings)   # same mean, another picture
    assert match is None and f"more than {MAX_DIFFERENCE}" in text
    match, text = measure_match(picture(), np.zeros_like(picture()), settings)
    assert match is None and "too dark" in text


def test_measure_match_follows_a_held_correction_within_the_applied_range() -> None:
    decoded, opening = picture(), picture(0.92)
    match, _ = measure_match(decoded, opening, MatchPrevious(), shown_reference=apply_gains(decoded, (1.1, 1.1, 1.1)))
    assert match is not None and match.gains == pytest.approx((1.1 / 0.92,) * 3, abs=0.02)
    match, text = measure_match(decoded, opening, MatchPrevious(), shown_reference=apply_gains(decoded, (1.6, 1.6, 1.6)))
    assert match is not None and max(match.gains) == APPLIED_RANGE[1] and "limited to" in text


def test_params_accept_true_or_settings() -> None:
    cls = cls_of("video_clip")
    base = {"path": "assets/clip.mp4", "region": "bleed", "fade": False}
    assert cls.validate_params(base, Theme()).match_previous is False
    assert cls.validate_params({**base, "match_previous": True}, Theme()).match_previous is True
    settings = cls.validate_params({**base, "match_previous": {"seconds": 0.5, "hold": True}}, Theme()).match_previous
    assert (settings.seconds, settings.hold) == (0.5, True)
    for bad in ({"seconds": 0}, {"secs": 1}, "yes"):
        with pytest.raises(ValidationError):
            cls.validate_params({**base, "match_previous": bad}, Theme())


# ----- projects (a test clip, nothing rendered) -----------------------------------------------------


@pytest.fixture(scope="module")
def clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 4 s, 5 fps clip whose frame n is a flat grey ``11.64 (n + 1)`` (frame 0: 12, frame 19: 233)."""
    return write_clip(tmp_path_factory.mktemp("clip") / "grey.mp4", audio=False)


def take(scene_id: str, **params: Any) -> dict[str, Any]:
    return {"id": scene_id, "type": "video_clip", "duration": 4, "params": {"path": "assets/clip.mp4", "region": "bleed", "fade": False, **params}}


def load(make_project, clip: Path, scenes: list[dict[str, Any]]) -> Project:
    root = make_project(minimal_config(scenes=scenes))
    (root / "assets").mkdir(exist_ok=True)
    (root / "assets" / "clip.mp4").write_bytes(clip.read_bytes())
    return Project.load(root)


def test_validate_rejects_a_match_that_cannot_apply(make_project, clip: Path) -> None:
    project = load(make_project, clip, [
        take("first", match_previous=True),
        {"id": "card", "type": "title", "duration": 2, "params": {"title": "T"}},
        take("after_card", match_previous=True),
        take("fades", fade=True, match_previous=True),
        take("region", region="body"),
        take("after_region", match_previous=True),
        {**take("crossfaded", match_previous=True), "transition": "crossfade"},
    ])
    problems = check_project(project)
    assert any("scenes[0].params.match_previous: the first scene has no scene before it" in p for p in problems)
    assert any("scenes[2].params.match_previous: the scene before ('card') is a title, not a video_clip" in p for p in problems)
    assert any("scenes[3].params.match_previous: scene 'fades' needs fade: false and region: bleed" in p for p in problems)
    assert any("scenes[5].params.match_previous: scene 'region' needs fade: false and region: bleed" in p for p in problems)
    assert any("scenes[6].params.match_previous: needs a cut" in p for p in problems)


def test_validate_accepts_a_chain_of_takes(make_project, clip: Path) -> None:
    project = load(make_project, clip, [take("a"), take("b", match_previous=True), take("c", match_previous={"hold": True})])
    assert check_project(project) == []


def test_cover_crop() -> None:
    assert cover_crop(16 / 9, 16 / 9) == pytest.approx((0.0, 0.0, 1.0, 1.0))
    assert cover_crop(16 / 9, 1.0) == pytest.approx((0.21875, 0.0, 0.5625, 1.0))
    assert cover_crop(1.0, 16 / 9) == pytest.approx((0.0, 0.21875, 1.0, 0.5625))


def test_clip_join_reads_the_frames_at_the_cut(clip: Path) -> None:
    whole = ClipTiming(0.0, 4.0)
    full = (0.0, 0.0, 1.0, 1.0)
    # the previous clip ends on frame 16 (grey 198), this one opens on frame 14 (grey 175)
    join = ClipJoin(ShownClip(clip, whole, full, last_played=3.2), ShownClip(clip, ClipTiming(2.8, 4.0), full, last_played=1.0))
    assert int(join.reference((8, 8))[0, 0, 0]) == pytest.approx(198, abs=2)
    assert int(join.opening((8, 8))[0, 0, 0]) == pytest.approx(175, abs=2)
    match, _ = join.gain_match(MatchPrevious())
    assert match is not None and match.gains == pytest.approx((198 / 175,) * 3, abs=0.02)
    held = ClipJoin(join.previous, join.current, GainMatch((1.1, 1.1, 1.1), hold=True))
    assert int(held.reference((8, 8))[0, 0, 0]) == pytest.approx(218, abs=2)
    assert int(held.reference((8, 8), treated=False)[0, 0, 0]) == pytest.approx(198, abs=2)


def test_opening_treatment_of_a_scene(make_project, clip: Path) -> None:
    """Scene ``a`` shows frames 12-15 and ends on 15 (grey 186); ``b`` opens on frame 14 (175)."""
    project = load(make_project, clip, [
        {**take("a", trim=[2.4, 3.2]), "duration": 0.8},
        {**take("b", trim=[2.8, 4.0], match_previous={"seconds": 0.5}), "duration": 1.2},
        take("c"),
    ])
    cls_of("video_clip")   # loads the built-in scene types the join looks its params up in
    plan = VideoPlan(project, 5)
    match, text = opening_treatment(project, plan, 1, 16 / 9)
    assert isinstance(match, GainMatch) and match.seconds == 0.5 and not match.hold
    assert match.gains == pytest.approx((186 / 175,) * 3, abs=0.02) and "gains R" in text
    assert opening_treatment(project, plan, 2, 16 / 9)[0] is None   # match_previous is off on c


def test_fingerprint_follows_the_scene_before(make_project, clip: Path) -> None:
    root = load(make_project, clip, [take("a")]).root

    def prints(scenes: list[dict[str, Any]]) -> list[str]:
        make_project(minimal_config(scenes=scenes))   # the config again; the clip file stays as it is
        project = Project.load(root)
        return [scene_fingerprint(project, s["id"]) for s in scenes]

    plain = prints([take("a"), take("b"), take("c")])
    matched = prints([take("a"), take("b", match_previous=True), take("c")])
    assert [x == y for x, y in zip(plain, matched)] == [True, False, True]       # only the scene with the param
    trimmed = prints([take("a", trim=[0, 2]), take("b", match_previous=True), take("c")])
    assert [x == y for x, y in zip(matched, trimmed)] == [False, False, True]    # the scene before changed: b follows
    unmatched = prints([take("a", trim=[0, 2]), take("b"), take("c")])
    assert unmatched[1] == plain[1]                                             # without the param b does not follow
