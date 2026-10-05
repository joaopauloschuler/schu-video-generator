"""SRT generation from timings (no rendering)."""

from __future__ import annotations

from pathlib import Path

import pytest

from vidgen.subtitles import Cue, beat_cues, cues_from_timings, format_srt, format_time, split_text, write_srt


def test_format_time() -> None:
    assert format_time(0) == "00:00:00,000"
    assert format_time(3.0004) == "00:00:03,000"
    assert format_time(61.2346) == "00:01:01,235"
    assert format_time(3725.5) == "01:02:05,500"
    assert format_time(-0.001) == "00:00:00,000"


def test_split_text_short_and_long() -> None:
    assert split_text("  Hello   world. ") == ["Hello world."]
    long = " ".join(["word"] * 40)  # 199 chars
    parts = split_text(long)
    assert len(parts) == 3
    for part in parts:
        lines = part.split("\n")
        assert len(lines) <= 2 and all(len(line) <= 42 for line in lines)
    assert " ".join(p.replace("\n", " ") for p in parts) == long


def test_beat_cues_share_time_by_characters() -> None:
    text = "a" * 40 + " " + "b" * 40 + " " + "c" * 40  # 3 lines -> cues of 2 lines and 1 line
    cues = beat_cues(10.0, 13.0, text)
    assert [c.text for c in cues] == ["a" * 40 + "\n" + "b" * 40, "c" * 40]
    assert cues[0].start == 10.0 and cues[-1].end == pytest.approx(13.0)
    assert cues[0].end == cues[1].start
    # 81 vs 40 characters
    assert cues[0].end - cues[0].start == pytest.approx(3.0 * 81 / 121)


def test_cues_from_timings_and_srt_format(tmp_path: Path) -> None:
    timings = {
        "scenes": [
            {"id": "a", "start": 0.0, "beats": [{"id": "a_b1", "start": 0.0, "end": 1.25, "text": "Olá, João!"}]},
            {"id": "quiet", "start": 1.6, "beats": []},
            {"id": "b", "start": 2.6, "beats": [{"id": "b_b1", "start": 2.6, "end": 4.0, "text": "Second."}]},
        ]
    }
    cues = cues_from_timings(timings)
    assert cues == [Cue(0.0, 1.25, "Olá, João!"), Cue(2.6, 4.0, "Second.")]
    srt = tmp_path / "x.srt"
    write_srt(srt, timings)
    assert srt.read_text(encoding="utf-8") == (
        "1\n00:00:00,000 --> 00:00:01,250\nOlá, João!\n\n2\n00:00:02,600 --> 00:00:04,000\nSecond.\n"
    )
    assert format_srt([]) == ""
