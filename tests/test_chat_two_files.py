"""X21: after one half of a pair, a whole file, the same half, or a broken file never trap the reader (fictional)."""

from __future__ import annotations

from pathlib import Path

from tests.chat_helpers import SAMPLE_CSV
from variance_agent.chat.handlers import handle_upload
from variance_agent.chat.session import Phase, Session

REALWORLD = Path(__file__).resolve().parent / "fixtures" / "realworld"
BUDGET = (REALWORLD / "fixture_f_budget_separate.csv").read_bytes()
ACTUALS = (REALWORLD / "fixture_f_actuals_separate.csv").read_bytes()


def _waiting() -> Session:
    session = Session()
    handle_upload(session, BUDGET, "bud.csv")
    assert session.pending_half is not None
    return session


def test_a_whole_file_is_read_on_its_own() -> None:
    session = _waiting()
    response = handle_upload(session, SAMPLE_CSV, "whole.csv")
    assert response.level != "error"
    assert "'whole.csv' has both Budget and Actual, so I read it on its own and set 'bud.csv' aside." in (
        response.text.replace("\\", ""))
    assert session.pending_half is None and session.source_name == "whole.csv"
    assert "--compare-file" not in response.text


def test_the_same_budget_again_is_named_as_such() -> None:
    session = _waiting()
    response = handle_upload(session, BUDGET, "bud.csv")
    assert response.text.replace("\\", "").startswith("That's 'bud.csv' again.")
    assert "Upload the file with the actuals" in response.text and response.ask_upload
    assert session.pending_half is not None


def test_another_budget_replaces_the_one_held() -> None:
    session = _waiting()
    response = handle_upload(session, BUDGET.replace(b"Fictional", b"Fictive", 1), "bud2.csv")
    assert response.text.replace("\\", "").startswith("'bud2.csv' replaces 'bud.csv':")
    assert session.pending_half is not None and session.pending_half[1] == "bud2.csv"


def test_the_missing_half_is_joined() -> None:
    session = _waiting()
    response = handle_upload(session, ACTUALS, "act.csv")
    assert response.level != "error" and session.pending_half is None
    assert session.phase is not Phase.AWAITING_FILE


def test_a_broken_file_keeps_the_half_waiting() -> None:
    session = _waiting()
    response = handle_upload(session, b"not a workbook", "broken.xlsx")
    assert response.level == "error"
    assert session.pending_half is not None and session.pending_half[1] == "bud.csv"
