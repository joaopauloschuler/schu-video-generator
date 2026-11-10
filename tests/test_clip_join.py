"""Step 325: ``video_clip`` ``match_previous`` (``vidgen.clip_join``): the gain per colour channel
between the previous clip's last frame and this clip's first, its easing, the limits that skip
it, the frame treatment of ``ClipMobject``, what ``vidgen validate`` rejects, and the scene
fingerprint. Step 326: the dissolve at the cut (``match_previous: {dissolve: N}``): its weights,
its combination with the gain, its settings. No scene is rendered."""

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
    JoinTreatment,
    MatchPrevious,
    ShownClip,
    apply_gains,
    blend,
    channel_gains,
    correction_left,
    dissolve_weight,
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


# ----- the dissolve (Step 326) ----------------------------------------------------------------------


def test_dissolve_weights_fall_in_equal_steps_to_zero() -> None:
    assert [dissolve_weight(k, 3) for k in range(-1, 5)] == [0.75, 0.75, 0.5, 0.25, 0.0, 0.0]
    assert dissolve_weight(0, 1) == 0.5 and dissolve_weight(0, 0) == 0.0
    weights = [1.0] + [dissolve_weight(k, 12) for k in range(13)]   # 1.0: the frame before the cut
    assert [round(a - b, 6) for a, b in zip(weights, weights[1:])] == [round(1 / 13, 6)] * 13


def test_blend_mixes_colour_and_keeps_alpha() -> None:
    frame = np.full((2, 2, 4), (100, 50, 0, 200), dtype=np.uint8)
    reference = np.full((2, 2, 4), (200, 50, 101, 255), dtype=np.uint8)
    assert blend(frame, reference, 0.75)[0, 0].tolist() == [175, 50, 76, 200]
    assert np.array_equal(blend(frame, reference, 0.0), frame) and frame[0, 0, 0] == 100   # a new array


def test_join_treatment_blends_after_the_gain() -> None:
    asked: list[tuple[int, int]] = []

    def reference(size: tuple[int, int]) -> np.ndarray:
        asked.append(size)
        return np.full((size[1], size[0], 4), 200, dtype=np.uint8)

    treatment = JoinTreatment(GainMatch((1.1, 1.1, 1.1), seconds=1.0), dissolve=3, fps=24.0, reference=reference)
    states = [treatment.state(k / 24) for k in range(4)]
    assert [s[1] for s in states] == [0.75, 0.5, 0.25, 0.0] and states[0][0] == (1.1, 1.1, 1.1)
    assert all(hash(s) is not None for s in states) and states[3][0] is not None   # the gain is still easing
    assert treatment.state(1.0) is None and treatment.state(5.0) is None
    frame = np.full((3, 5, 4), 100, dtype=np.uint8)
    shown = treatment.apply(frame, ((1.1, 1.1, 1.1), 0.75))
    assert shown[0, 0].tolist() == [178, 178, 178, 100]          # 0.75 x 200 + 0.25 x (100 x 1.1)
    assert treatment.apply(frame, ((1.1, 1.1, 1.1), 0.0))[0, 0, 0] == 110
    treatment.apply(frame, (None, 0.5))
    assert asked == [(5, 3)]                                      # (width, height), fetched once


def test_join_treatment_without_the_gain_ends_with_the_dissolve() -> None:
    treatment = JoinTreatment(None, dissolve=2, fps=30.0, reference=lambda size: np.zeros((size[1], size[0], 4), np.uint8))
    assert [treatment.state(k / 30) for k in range(4)] == [(None, 0.6667), (None, 0.3333), None, None]
    frame = np.full((2, 2, 4), 90, dtype=np.uint8)
    assert treatment.apply(frame, (None, 0.3333))[0, 0].tolist() == [60, 60, 60, 90]


def test_params_accept_a_dissolve() -> None:
    cls = cls_of("video_clip")
    base = {"path": "assets/clip.mp4", "region": "bleed", "fade": False}

    def settings(value: Any) -> Any:
        return cls.validate_params({**base, "match_previous": value}, Theme()).match_previous

    assert MatchPrevious().dissolve == 0 and MatchPrevious().level is True       # true stays the gain alone
    both = settings({"dissolve": 3, "seconds": 0.5})
    assert (both.dissolve, both.seconds, both.level) == (3, 0.5, True)
    assert settings({"dissolve": 12, "level": False}).level is False
    for bad in ({"dissolve": 13}, {"dissolve": -1}, {"dissolve": 1.5}, {"dissolve": True}, {"level": False},
                {"dissolve": 3, "level": False, "hold": True}, {"dissolve": 3, "level": False, "seconds": 2}):
        with pytest.raises(ValidationError):
            settings(bad)


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


def dissolved(make_project, clip: Path, setting: dict[str, Any], **params: Any) -> tuple[Any, str]:
    """The treatment of scene ``b`` (opens on frame 14, grey 175) after ``a`` (ends on 15, 186)."""
    project = load(make_project, clip, [
        {**take("a", trim=[2.4, 3.2], **params), "duration": 0.8},
        {**take("b", trim=[2.8, 4.0], match_previous=setting), "duration": 1.2},
    ])
    cls_of("video_clip")
    return opening_treatment(project, VideoPlan(project, 5), 1, 16 / 9)


def test_opening_treatment_with_a_dissolve(make_project, clip: Path) -> None:
    treatment, text = dissolved(make_project, clip, {"dissolve": 2})
    assert isinstance(treatment, JoinTreatment) and treatment.fps == 5 and "dissolve over 2 frames" in text
    assert treatment.gain is not None and treatment.gain.gains == pytest.approx((186 / 175,) * 3, abs=0.02)
    assert [treatment.state(k / 5)[1] for k in range(3)] == [0.6667, 0.3333, 0.0]
    frame = np.full((8, 8, 4), 175, dtype=np.uint8)
    shown = treatment.apply(frame, treatment.state(0.0))
    assert shown.shape == frame.shape and int(shown[0, 0, 0]) == pytest.approx(186, abs=2)   # same level both sides


def test_a_dissolve_alone_leaves_the_level(make_project, clip: Path) -> None:
    treatment, text = dissolved(make_project, clip, {"dissolve": 2, "level": False})
    assert isinstance(treatment, JoinTreatment) and treatment.gain is None and "left as they are" in text
    assert treatment.state(0.0) == (None, 0.6667) and treatment.state(0.4) is None
    frame = np.full((8, 8, 4), 175, dtype=np.uint8)
    assert int(treatment.apply(frame, (None, 0.6667))[0, 0, 0]) == pytest.approx(182, abs=2)   # 2/3 of 186, 1/3 of 175


def test_a_dissolve_is_skipped_with_the_match(make_project, clip: Path) -> None:
    project = load(make_project, clip, [
        {**take("a", trim=[0.0, 0.8]), "duration": 0.8},                          # ends on frame 3 (grey 47)
        {**take("b", trim=[2.8, 4.0], match_previous={"dissolve": 2, "level": False}), "duration": 1.2},
    ])
    cls_of("video_clip")
    treatment, text = opening_treatment(project, VideoPlan(project, 5), 1, 16 / 9)
    assert treatment is None and "does not continue the one before" in text


def test_a_dissolve_needs_the_same_part_of_the_frame(make_project, clip: Path) -> None:
    treatment, _ = dissolved(make_project, clip, {"dissolve": 2}, fit="contain")
    assert treatment is not None                         # a 16:9 clip whole in a 16:9 frame: the same part as b
    project = load(make_project, clip, [
        {**take("a", trim=[2.4, 3.2], fit="contain"), "duration": 0.8},
        {**take("b", trim=[2.8, 4.0], fit="cover", match_previous={"dissolve": 2}), "duration": 1.2},
    ])
    treatment, text = opening_treatment(project, VideoPlan(project, 5), 1, 1.0)
    assert treatment is None and "dissolve cannot lay one on the other" in text


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
    dissolving = prints([take("a"), take("b", match_previous={"dissolve": 3}), take("c")])
    longer = prints([take("a"), take("b", match_previous={"dissolve": 4}), take("c")])
    assert len({matched[1], dissolving[1], longer[1]}) == 3 and dissolving[0] == matched[0]
