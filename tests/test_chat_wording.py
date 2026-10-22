"""The chat bot's explanations must say what the engine does (WS2 P1, language accuracy)."""

from __future__ import annotations

import inspect

import pytest

from tests.chat_helpers import analysed, ask
from variance_agent.chat import knowledge
from variance_agent.chat.handlers import handle_message
from variance_agent.chat.session import Session

# Claims the engine does not back, and the engine's real behaviour spelled the old way.
UNSUPPORTED = (
    "SOX",
    "SEC/",
    "audit-certified",
    "never leaves",
    "Strict Conjunction",
    "AND/OR",
    "positive decimal number",
)


def _knowledge_texts() -> dict[str, str]:
    return {
        name: function()
        for name, function in inspect.getmembers(knowledge, inspect.isfunction)
        if name.startswith("explain_")
    }


@pytest.mark.parametrize("name", sorted(_knowledge_texts()))
def test_knowledge_makes_no_unsupported_claims(name: str) -> None:
    text = _knowledge_texts()[name]
    for phrase in UNSUPPORTED:
        assert phrase not in text, f"{name}: {phrase}"


def test_materiality_is_amount_or_percent_with_a_strict_comparison() -> None:
    text = knowledge.explain_materiality()
    assert "either" in text.lower()
    assert "strict" in text.lower()
    assert "`>`" in text
    assert "absolute" in text.lower()


def test_formats_describe_the_positive_cost_convention() -> None:
    text = knowledge.explain_supported_formats()
    assert "positive" in text.lower() and "cost" in text.lower()


def test_ebitda_is_only_mentioned_to_say_it_is_not_what_the_tool_computes() -> None:
    for name, text in _knowledge_texts().items():
        if name == "explain_ebitda_margin":
            continue
        assert "EBITDA" not in text, name
    concept = knowledge.explain_ebitda_margin()
    assert "operating profit" in concept.lower()
    assert "not EBITDA" in concept


ANSWER_PROMPTS = [
    "what if revenue drops 5%", "sensitivity", "run rate", "memo", "tldr", "profitability",
    "compare revenue vs expenses", "compare actual vs budget", "waterfall", "summary",
    "are we in the black?", "what is net impact?", "operating leverage",
    "what are financial kpis?", "action playbook", "audit trail", "who are you",
]


@pytest.mark.parametrize("prompt", ANSWER_PROMPTS)
def test_answers_do_not_call_operating_profit_ebitda(prompt: str) -> None:
    response = ask(analysed(), prompt)
    shown = response.text + " ".join(
        " ".join([*row.keys(), *row.values()]) for row in (response.table or [])
    )
    for phrase in ("EBITDA", *UNSUPPORTED):
        assert phrase not in shown, f"{prompt}: {phrase}"


def test_ebitda_input_is_still_understood() -> None:
    assert "Profitability Standing" in ask(analysed(), "how is ebitda looking").text


def test_the_identity_answer_does_not_promise_data_stays_put() -> None:
    session = Session(path_exports_enabled=False)
    text = handle_message(session, "who are you").text
    assert "never leaves" not in text
    assert "hosted" in text.lower()
    local = handle_message(Session(path_exports_enabled=True), "who are you").text
    assert "never leaves" not in local


def test_audit_text_claims_reproducibility_not_regulatory_compliance() -> None:
    text = knowledge.explain_audit_trail()
    assert "SHA-256" in text
    assert "not a certification" in text



def test_every_knowledge_intent_has_an_answer_and_none_is_orphaned() -> None:
    from variance_agent.chat.handlers import _KNOWLEDGE_TEXTS
    from variance_agent.chat.intent import KNOWLEDGE_INTENTS

    assert set(_KNOWLEDGE_TEXTS) == set(KNOWLEDGE_INTENTS)
