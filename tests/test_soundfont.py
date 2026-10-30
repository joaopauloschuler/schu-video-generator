"""The ``music`` extra (symusic) and the SoundFont: download checks, the cache, ``soundfont:``
overrides and ``vidgen soundfont`` (DESIGN.md §81). Nothing here downloads: fetches read
``file://`` URLs of small fake files."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import minimal_config

from vidgen import cli, soundfont, synth
from vidgen.config import VideoConfig
from vidgen.errors import VidgenError
from vidgen.project import PATH_KEYS, Project

ROOT = Path(__file__).resolve().parents[1]
#: A tiny stand-in for a SoundFont: a RIFF ``sfbk`` header and some bytes.
FAKE_SF2 = b"RIFF\x10\x00\x00\x00sfbk" + b"fake soundfont data"


@pytest.fixture(autouse=True)
def _offline_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A private cache folder, and a default URL that cannot reach the network."""
    cache = tmp_path / "cache"
    monkeypatch.setenv(soundfont.CACHE_ENV, str(cache))
    monkeypatch.setattr(soundfont, "URL", (tmp_path / "no-such-download.sf2").as_uri())
    monkeypatch.setattr(soundfont, "_checked", {})
    return cache


@pytest.fixture
def fake_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A local file the module takes for GeneralUser GS (its size and hash expected); its path."""
    source = tmp_path / "upstream" / soundfont.FILE_NAME
    source.parent.mkdir()
    source.write_bytes(FAKE_SF2)
    monkeypatch.setattr(soundfont, "SIZE_BYTES", len(FAKE_SF2))
    monkeypatch.setattr(soundfont, "SHA256", hashlib.sha256(FAKE_SF2).hexdigest())
    return source


# ----- the extra ----------------------------------------------------------------------------------


def test_missing_extra_names_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(synth, "symusic_version", lambda: None)
    with pytest.raises(VidgenError, match=r'pip install "schu-video-generator\[music\]"'):
        synth.require_symusic()
    assert synth.symusic_status() == f"not installed: {synth.INSTALL_COMMAND}"


def test_another_symusic_version_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(synth, "symusic_version", lambda: "0.6.0")
    with pytest.raises(VidgenError, match=r"needs symusic 0\.5\.9, and 0\.6\.0 is installed.*\[music\]"):
        synth.require_symusic()
    assert "0.6.0 installed, but schu-video-generator needs 0.5.9" in synth.symusic_status()


def test_the_extra_pins_symusic_and_no_soundfont_ships() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'music = ["symusic==0.5.9"]' in pyproject
    package_data = next(line for line in pyproject.splitlines() if line.startswith("vidgen = ["))
    assert "sf2" not in package_data and "sf3" not in package_data and "soundfont" not in package_data
    assert not [p for p in (ROOT / "src").rglob("*") if p.suffix.lower() in soundfont.SUFFIXES]


# ----- download and hash check --------------------------------------------------------------------


def test_cache_dir_follows_the_environment(_offline_cache: Path) -> None:
    assert soundfont.default_path() == _offline_cache / "soundfonts" / soundfont.FILE_NAME


def test_fetch_checks_and_moves_the_file_into_place(fake_default: Path, _offline_cache: Path) -> None:
    seen: list[int] = []
    path = soundfont.fetch(url=fake_default.as_uri(), progress=seen.append)
    assert path == soundfont.default_path() and path.read_bytes() == FAKE_SF2
    assert seen[-1] == len(FAKE_SF2)
    assert sorted(p.name for p in path.parent.iterdir()) == [soundfont.FILE_NAME]   # no .part left
    # present: no second download (the default URL would fail)
    assert soundfont.fetch() == path
    assert soundfont.resolve(None, ROOT, download=False) == path


def test_a_mismatched_download_is_not_kept(fake_default: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(soundfont, "SHA256", "0" * 64)
    with pytest.raises(VidgenError) as caught:
        soundfont.fetch(url=fake_default.as_uri())
    message = str(caught.value)
    assert "is not the expected GeneralUser GS 2.0.3" in message and "may have changed upstream" in message
    assert "soundfont: PATH" in message and hashlib.sha256(FAKE_SF2).hexdigest() in message
    folder = soundfont.default_path().parent
    assert not folder.exists() or not list(folder.iterdir())


def test_a_download_of_the_wrong_size_is_not_kept(fake_default: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(soundfont, "SIZE_BYTES", 10)   # the file is longer: the download stops early
    with pytest.raises(VidgenError, match="is not the expected"):
        soundfont.fetch(url=fake_default.as_uri())
    assert not soundfont.default_path().exists()


def test_offline_says_how_to_use_your_own_file() -> None:
    with pytest.raises(VidgenError) as caught:
        soundfont.fetch()
    message = str(caught.value)
    assert message.startswith("cannot download the GeneralUser GS 2.0.3 SoundFont (cannot reach")
    assert "`vidgen soundfont fetch`" in message and "`soundfont: PATH`" in message
    assert not soundfont.default_path().exists()


def test_a_changed_cached_file_is_never_used(fake_default: Path) -> None:
    path = soundfont.default_path()
    path.parent.mkdir(parents=True)
    path.write_bytes(FAKE_SF2[:-1] + b"X")   # same size, other bytes
    with pytest.raises(VidgenError, match=r"cached SoundFont .* is not the expected.*fetch --force"):
        soundfont.resolve(None, ROOT)
    assert soundfont.info(None, None).matches is False
    assert soundfont.fetch(force=True, url=fake_default.as_uri()).read_bytes() == FAKE_SF2


def test_resolve_without_download_says_what_to_run() -> None:
    with pytest.raises(VidgenError, match="not downloaded yet: run `vidgen soundfont fetch`"):
        soundfont.resolve(None, ROOT, download=False)


# ----- soundfont: PATH ----------------------------------------------------------------------------


def test_override_path_is_relative_to_the_project(tmp_path: Path) -> None:
    (tmp_path / "sounds").mkdir()
    (tmp_path / "sounds" / "Mine.SF3").write_bytes(FAKE_SF2)
    assert soundfont.resolve("sounds/Mine.SF3", tmp_path) == (tmp_path / "sounds" / "Mine.SF3").resolve()
    assert soundfont.soundfont_problems("sounds/Mine.SF3", tmp_path) == []
    assert not soundfont.default_path().exists()   # an override downloads nothing


def test_bad_override_paths(tmp_path: Path) -> None:
    (tmp_path / "notes.sf2").write_text("not a soundfont", encoding="utf-8")
    (tmp_path / "bank.wav").write_bytes(FAKE_SF2)
    assert soundfont.soundfont_problems("missing.sf2", tmp_path) == [
        ("soundfont", "'missing.sf2' does not exist (a SoundFont file: .sf2 or .sf3, relative to the project)")
    ]
    for name in ("notes.sf2", "bank.wav"):
        with pytest.raises(VidgenError, match=f"soundfont: '{name}' is not an SF2 / SF3 SoundFont file"):
            soundfont.resolve(name, tmp_path)


def test_config_key_validate_and_mcp_confinement(make_project: Callable[..., Path]) -> None:
    assert VideoConfig.model_validate(minimal_config(soundfont="bank.sf2")).soundfont == "bank.sf2"
    assert "soundfont" in PATH_KEYS
    root = make_project(minimal_config(soundfont="bank.sf2"))
    problems = cli.project_problems(Project.load(root))
    assert [(p.location, p.message) for p in problems if p.location == "soundfont"] == [
        ("soundfont", "'bank.sf2' does not exist (a SoundFont file: .sf2 or .sf3, relative to the project)")
    ]
    (root / "bank.sf2").write_bytes(FAKE_SF2)
    assert not [p for p in cli.project_problems(Project.load(root)) if p.location == "soundfont"]


# ----- vidgen soundfont ---------------------------------------------------------------------------


def test_cli_info_default_not_downloaded(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    assert cli.main(["soundfont", "info"]) == 0
    out = capsys.readouterr().out
    assert f"soundfont: {soundfont.default_path()} (GeneralUser GS 2.0.3, the default)" in out
    assert "not downloaded yet" in out and "licence: GeneralUser GS License v2.0" in out
    assert "suggested credit: Music rendered with the GeneralUser GS SoundFont" in out and "symusic: " in out


def test_cli_fetch_then_info(fake_default: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(soundfont, "URL", fake_default.as_uri())
    assert cli.main(["soundfont", "fetch"]) == 0
    assert f"saved: {soundfont.default_path()} (sha256 checked)" in capsys.readouterr().out
    assert cli.main(["soundfont", "fetch"]) == 0
    assert "already there:" in capsys.readouterr().out
    assert cli.main(["soundfont", "info"]) == 0
    out = capsys.readouterr().out
    assert f"size: {len(FAKE_SF2):,} bytes" in out and f"sha256: {soundfont.SHA256}" in out and "check: ok" in out


def test_cli_info_shows_the_projects_override(make_project: Callable[..., Path], capsys: pytest.CaptureFixture[str]) -> None:
    root = make_project(minimal_config(soundfont="bank.sf2"))
    (root / "bank.sf2").write_bytes(FAKE_SF2)
    assert cli.main(["soundfont", "info", str(root)]) == 0
    out = capsys.readouterr().out
    assert f"soundfont: {(root / 'bank.sf2').resolve()} (soundfont: in video.yaml)" in out
    assert "suggested credit" not in out and "check:" not in out


def test_cli_fetch_offline_is_an_error(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    assert cli.main(["soundfont", "fetch"]) == 1
    assert "error: cannot download the GeneralUser GS 2.0.3 SoundFont" in capsys.readouterr().err
