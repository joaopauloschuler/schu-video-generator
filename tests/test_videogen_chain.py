"""The frame arithmetic of chained parts: no rendering, nothing sent."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from vidgen.generated_layer import _Take
from vidgen.videogen.chain import CHAIN_DROP_FRAMES, frame_index, guide_span, lead_frames, picture_at
from vidgen.videogen.compose import Placement

FPS = 24
#: The footage-test beat: 5.29 s in two parts of 63.5 frames.
PART = 63.5 / FPS


def test_the_frame_index_ignores_rounding_noise() -> None:
    assert frame_index(PART, FPS) == frame_index(5.291666666666667 - PART, FPS) == round(63.5)
    assert frame_index(0.1 + 0.2, 10) == 3


def test_only_later_parts_with_a_picture_lead() -> None:
    assert CHAIN_DROP_FRAMES == 1
    assert (lead_frames(1, "render"), lead_frames(2, "render"), lead_frames(3, "restyled"), lead_frames(2, "none")) == (0, 1, 1, 0)


def test_a_part_without_lead_is_cut_as_planned() -> None:
    assert guide_span(1.5, 2.0, 0, FPS) == (1.5, 2.0)


def test_the_guide_starts_on_the_pictures_film_frame_and_ends_with_the_part() -> None:
    begin, length = guide_span(PART, PART, 1, FPS)
    first = frame_index(PART, FPS)   # 64: the part's first film frame
    assert begin * FPS == pytest.approx(first - 1.25)   # a cut keeping frames from begin keeps frame 63
    assert int(np.ceil(begin * FPS)) == first - 1
    assert begin + length == pytest.approx(2 * PART)


def test_the_picture_is_the_last_frame_the_film_shows_of_the_part_before() -> None:
    assert picture_at(PART, PART, 1, 0, FPS) * FPS == pytest.approx(63)   # part 1's take frame 63, film frame 63


@pytest.mark.parametrize("start, length, lead", [(PART, PART, 1), (2 * PART, PART, 1), (3.1, 2.9, 1), (3.1, 2.9, 2), (4.0, 2.0, 1)])
def test_the_take_frames_line_up_with_the_film_frames(start: float, length: float, lead: int) -> None:
    """Laid in as GeneratedLayer does (film frame ``J`` shows take frame ``J - first + lead``), the
    picture is the previous take's frame shown at film frame ``first - lead``, and guide frame 0 is
    that film frame: this take's frame ``i`` lines up with film frame ``first - lead + i``."""
    previous_lead = lead if start - length > 1e-9 else 0
    first, before = frame_index(start, FPS), frame_index(start - length, FPS)
    picture = first - lead   # the film frame the picture shows
    assert picture_at(start, length, lead, previous_lead, FPS) * FPS == pytest.approx(picture - before + previous_lead)
    begin, _ = guide_span(start, length, lead, FPS)
    assert int(np.ceil(begin * FPS)) == picture   # guide frame 0 is that film frame


class _Reader:
    def __init__(self) -> None:
        self.asked: list[float] = []

    def frame(self, t: float) -> np.ndarray:
        self.asked.append(t)
        return np.zeros((18, 32, 4), dtype=np.uint8)


def test_the_layer_skips_the_lead_frames(tmp_path: Path) -> None:
    placement = Placement("s", "w_p2", tmp_path / "t.mp4", 1, "m", 2.0, 2.0, "cover", 0.0, 0.0, 0.0, True, lead=1)
    take = _Take(placement, 5)
    reader = _Reader()
    take.reader, take.box = reader, (0, 0, 32, 18)   # type: ignore[assignment]
    base = np.zeros((18, 32, 4), dtype=np.uint8)
    take.picture(base, take.first, 5)
    take.picture(base, take.first + 3, 5)
    assert (take.first, reader.asked) == (10, pytest.approx([0.2, 0.8]))


def test_the_lead_is_in_the_fingerprint(tmp_path: Path) -> None:
    take = tmp_path / "t.mp4"
    take.write_bytes(b"x")
    plain = Placement("s", "w_p2", take, 1, "m", 2.0, 2.0, "cover", 0.0, 0.0, 0.0, True)
    led = Placement("s", "w_p2", take, 1, "m", 2.0, 2.0, "cover", 0.0, 0.0, 0.0, True, lead=1)
    assert led.fingerprint(tmp_path)[-3:] == ["lead", 1, "match_join"] and "lead" not in plain.fingerprint(tmp_path)
