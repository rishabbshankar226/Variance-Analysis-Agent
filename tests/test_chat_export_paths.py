"""X25: '~' in a local export path is the home folder, never a folder named '~' (fictional data)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.chat_helpers import analysed, ask


@pytest.fixture
def places(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    home, work = tmp_path / "home", tmp_path / "work"
    home.mkdir()
    work.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(work)
    return home, work


def _session():  # type: ignore[no-untyped-def]
    session = analysed()
    session.path_exports_enabled = True
    return session


def test_a_tilde_path_lands_in_the_home_folder(places: tuple[Path, Path]) -> None:
    home, work = places
    response = ask(_session(), "export report ~/r.md")
    assert (home / "r.md").is_file()
    assert not (work / "~").exists()
    assert f"Report written to `{home / 'r.md'}`." in response.text.replace("\\", "")


def test_a_relative_path_lands_where_it_did(places: tuple[Path, Path]) -> None:
    _, work = places
    ask(_session(), "export report out/r.md")
    assert (work / "out" / "r.md").is_file()
