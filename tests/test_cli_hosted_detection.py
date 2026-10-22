"""--chat binds all interfaces only when hosting is asked for (flag) or announced (RENDER)."""

from __future__ import annotations

import pytest

from variance_agent import cli
from variance_agent.chat import server


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    recorded: list[dict[str, object]] = []

    def fake_run_chat_server(**kwargs: object) -> int:
        recorded.append(kwargs)
        return 0

    monkeypatch.setattr(server, "run_chat_server", fake_run_chat_server)
    for name in ("PORT", "RENDER"):
        monkeypatch.delenv(name, raising=False)
    return recorded


def test_a_stray_port_variable_does_not_expose_the_local_chat(
    monkeypatch: pytest.MonkeyPatch, calls: list[dict[str, object]],
) -> None:
    monkeypatch.setenv("PORT", "3000")
    assert cli.main(["--chat", "--no-browser"]) == 0
    assert calls == [{"initial_input": None, "initial_sheet": None, "open_browser": False}]


def test_hosted_flag_binds_all_interfaces_on_port(
    monkeypatch: pytest.MonkeyPatch, calls: list[dict[str, object]],
) -> None:
    monkeypatch.setenv("PORT", "3000")
    assert cli.main(["--chat", "--hosted"]) == 0
    assert calls[0]["host"] == "0.0.0.0" and calls[0]["port"] == 3000 and calls[0]["hosted"] is True


def test_hosted_flag_defaults_to_port_10000(calls: list[dict[str, object]]) -> None:
    assert cli.main(["--chat", "--hosted"]) == 0
    assert calls[0]["port"] == 10000


def test_render_environment_implies_hosted(
    monkeypatch: pytest.MonkeyPatch, calls: list[dict[str, object]],
) -> None:
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("PORT", "10000")
    assert cli.main(["--chat"]) == 0
    assert calls[0]["host"] == "0.0.0.0" and calls[0]["hosted"] is True


def test_invalid_port_is_a_clear_error(
    monkeypatch: pytest.MonkeyPatch, calls: list[dict[str, object]], capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("PORT", "not-a-number")
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--chat", "--hosted"])
    assert exit_info.value.code == 2
    assert "PORT" in capsys.readouterr().err
