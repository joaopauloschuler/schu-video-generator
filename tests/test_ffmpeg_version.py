"""ffmpeg version detection and the "too old" hint on ffmpeg errors (Step 64)."""

from __future__ import annotations

from pathlib import Path

import pytest

from vidgen.errors import VidgenError
from vidgen.render import ffmpeg as ff


@pytest.mark.parametrize(
    ("line", "version"),
    [
        ("ffmpeg version 7.1.5 Copyright (c) 2000-2026 the FFmpeg developers", (7, 1)),
        ("ffmpeg version n7.1.5 Copyright (c) 2000-2026", (7, 1)),
        ("ffmpeg version 6.1.1-3ubuntu5 Copyright (c) 2000-2023", (6, 1)),
        ("ffmpeg version 4.4.2-0ubuntu0.22.04.1 Copyright", (4, 4)),
        ("ffmpeg version 8.1-full_build-www.gyan.dev Copyright", (8, 1)),
        ("ffmpeg version 2025-01-02-git-0a1b2c3d-full_build-www.gyan.dev", None),
        ("ffmpeg version N-117000-g1234abcd Copyright", None),
        ("", None),
    ],
)
def test_parse_version(line: str, version: tuple[int, int] | None) -> None:
    assert ff.parse_version(line + "\nbuilt with gcc 13\n") == version


def test_version_of_the_ffmpeg_on_path() -> None:
    version = ff.ffmpeg_version(ff.find_ffmpeg())
    assert version is None or version >= ff.MIN_VERSION  # what the test machine runs is supported
    assert ff.ffmpeg_version("/no/such/ffmpeg") is None


def test_hint_only_for_an_old_ffmpeg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ff, "ffmpeg_version", lambda exe: (4, 2))
    assert "ffmpeg 4.2 is too old: vidgen needs ffmpeg 4.4 or newer" in ff.version_hint("ffmpeg")
    with pytest.raises(VidgenError, match=r"(?s)failed while testing.*4\.2 is too old"):
        ff.run_ffmpeg(ff.find_ffmpeg(), ["-i", str(tmp_path / "missing.mp4"), str(tmp_path / "out.mp4")], "testing")
    for version in [(4, 4), (7, 1), None]:
        monkeypatch.setattr(ff, "ffmpeg_version", lambda exe, v=version: v)
        assert ff.version_hint("ffmpeg") == ""
