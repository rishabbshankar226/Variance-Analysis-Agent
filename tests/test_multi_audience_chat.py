"""Fictional HALV.FAKE: confirm rate interpretation and ask operational questions."""
from variance_agent.chat.handlers import handle_upload, handle_message
from variance_agent.chat.session import Session, Phase


def test_rate_missing_direction_asks_higher_or_lower_before_analysis():
    session = Session()
    reply = handle_upload(session, b"Line Item,Measure,Budget,Actual\nGross Margin,Percent,41.2%,40.6%\n", "fictional.csv")
    assert "Percent" in reply.text
    for text in ("Looks right", "3Q26", "$10 or 2%", "USD"):
        reply = handle_message(session, text)
    assert "Gross Margin" in reply.text and "Higher" in reply.text and "Lower" in reply.text
    assert session.result is None
    reply = handle_message(session, "Higher")
    assert "basis points" in reply.text.lower() and "threshold" in reply.text.lower()
    reply = handle_message(session, "25")
    assert session.phase is Phase.EXPLORING
    assert "-60 bps" in reply.text
    assert session.result.rows[0].status == "U"


def test_fraction_scale_is_proposed_and_confirmed_before_analysis():
    session = Session()
    handle_upload(session, b"Line Item,Measure,Better,Budget,Actual\nGross Margin,Percent,Higher,0.412,0.406\n", "fictional.csv")
    for text in ("Looks right", "3Q26", "$10 or 2%", "USD"):
        reply = handle_message(session, text)
    assert "41.2%" in reply.text and session.result is None
    reply = handle_message(session, "Read bare rates as fractions")
    assert "threshold" in reply.text.lower()
    reply = handle_message(session, "25")
    assert "-60 bps" in reply.text


def test_followup_material_table_retains_rate_units():
    session = Session()
    handle_upload(session, b"Line Item,Measure,Better,Budget,Actual\nGross Margin,Percent,Higher,41.2%,40.6%\n", "fictional.csv")
    for text in ("Looks right", "3Q26", "$10 or 2%", "USD", "25"):
        handle_message(session, text)
    reply = handle_message(session, "material")
    assert reply.table is not None
    assert "-60 bps" in list(reply.table[0].values())
