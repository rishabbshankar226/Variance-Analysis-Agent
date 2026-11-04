"""M1: a filing without statement tables names the document to upload next (fictional filings)."""

from __future__ import annotations

import re

import pytest

from tests.fixtures.ixbrl.build_ixbrl import all_statements_filing
from variance_agent.ixbrl import IxbrlError, read_statements


def _without_statements(extra: bytes = b"") -> bytes:
    data = re.sub(rb"(?i)statements? of (operations|income|cash flows|comprehensive income)|balance sheets?",
                  b"Supplementary Note", all_statements_filing())
    return data.replace(b"</body>", extra + b"</body>")


def _refusal(data: bytes) -> str:
    with pytest.raises(IxbrlError) as refused:
        read_statements(data, "f.htm")
    return str(refused.value)


def test_a_linked_exhibit_13_is_named() -> None:
    message = _refusal(_without_statements(b'<p>See <a href="fake-20261231ex13.htm">Exhibit 13</a>.</p>'))
    assert message == ("The financial statements aren't in 'f.htm' itself: it points to Exhibit 13 "
                       "('fake-20261231ex13.htm'), the annual report that holds them. Upload that document from the "
                       "same EDGAR filing, or the statements as Excel or CSV.")


def test_a_mention_of_exhibit_13_is_named_without_a_file() -> None:
    message = _refusal(_without_statements(b"<p>Incorporated by reference to Exhibit 13 to this report.</p>"))
    assert message.startswith("The financial statements aren't in 'f.htm' itself: it points to Exhibit 13, the annual "
                              "report that holds them.")


def test_no_pointer_gives_the_generic_next_step() -> None:
    message = _refusal(_without_statements())
    assert message.startswith("I could not find the financial statements in 'f.htm'")
    assert message.endswith("If the filing puts them in another document (often Exhibit 13, the annual report), upload "
                            "that document from the same EDGAR filing; otherwise upload the statements as Excel or CSV.")


def test_a_link_with_path_characters_is_not_quoted() -> None:
    message = _refusal(_without_statements(b'<p><a href="../../evil/ex13.htm?x=<script>">Exhibit 13</a></p>'))
    assert "evil" not in message and "<script>" not in message
