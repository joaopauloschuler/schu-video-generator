"""The distribution is ``schu-video-generator``; the command and the import package stay ``vidgen``."""

from __future__ import annotations

import re
from pathlib import Path

from vidgen import DIST_NAME, __version__

ROOT = Path(__file__).resolve().parents[1]


def test_distribution_name_version_and_commands() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")   # no tomllib on Python 3.10
    assert re.search(r'^name = "([^"]+)"$', pyproject, flags=re.M)[1] == DIST_NAME == "schu-video-generator"
    assert re.search(r'^version = "([^"]+)"$', pyproject, flags=re.M)[1] == __version__
    assert 'vidgen = "vidgen.cli:main"' in pyproject and 'vidgen-mcp = "vidgen.mcp_server:main"' in pyproject


def test_install_instructions_name_the_distribution() -> None:
    for doc in ("README.md", "AGENTS.md", "docs/CONFIG.md", "docs/EXTENDING.md"):
        text = (ROOT / doc).read_text(encoding="utf-8")
        assert "vidgen[" not in text and "pip install vidgen" not in text, doc
    for doc in ("README.md", "AGENTS.md"):
        text = (ROOT / doc).read_text(encoding="utf-8")
        assert "the command and the Python package are `vidgen`" in text, doc
