"""X27: the chat never shows 'Unclassified'; it says 'not yet labeled revenue or expense' (fictional data)."""

from __future__ import annotations

from tests.chat_helpers import analysed, ask

MYSTERY = b"""Line Item,Budget,Actual
Fictional Product Sales,100000,120000
Fictional Rent,50000,55000
Fictional Mystery Line,10000,30000
"""


def _shown(response) -> str:  # type: ignore[no-untyped-def]
    cells = " ".join(str(v) for row in response.table or [] for v in row.values())
    return f"{response.text} {cells} {' '.join(response.chips or [])}"


def test_the_skip_path_never_shows_unclassified() -> None:
    session = analysed(MYSTERY, "mystery.csv", unclassified="Skip all")
    for prompt in ("show material variances", "warnings", "summary", "why fictional mystery line"):
        shown = _shown(ask(session, prompt))
        assert "Unclassified" not in shown, (prompt, shown[:300])
    assert "not yet labeled revenue or expense" in ask(session, "warnings").text


def test_the_not_yet_labeled_chip_lists_the_same_rows_as_the_word() -> None:
    session = analysed(MYSTERY, "mystery.csv", unclassified="Skip all")
    by_chip, by_word = ask(session, "Not yet labeled"), ask(session, "unclassified")
    assert by_chip.table == by_word.table
    assert [row["Line Item"] for row in by_chip.table or []] == ["Fictional Mystery Line"]
    assert "Not yet labeled" in by_chip.text
