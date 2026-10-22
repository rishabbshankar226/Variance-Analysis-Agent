"""DeterministicChatClient: offline by default, honest about a failing backend, correct wire format."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

import pytest

from deterministic_conditioning.client_adapter import DeterministicChatClient

Urlopen = Callable[..., Any]


class FakeResponse(io.BytesIO):
    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def completion(text: object) -> FakeResponse:
    return FakeResponse(json.dumps({"choices": [{"message": {"content": text}}]}).encode())


def install(monkeypatch: pytest.MonkeyPatch, handler: Urlopen) -> list[urllib.request.Request]:
    seen: list[urllib.request.Request] = []

    def fake_urlopen(request: urllib.request.Request, timeout: float | None = None) -> Any:
        seen.append(request)
        return handler(request)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return seen


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_BASE", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)


def raises(error: BaseException) -> Urlopen:
    def handler(request: urllib.request.Request) -> Any:
        raise error
    return handler


def test_default_client_makes_no_network_call(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = install(monkeypatch, raises(AssertionError("the default client must stay offline")))
    result = DeterministicChatClient().step("hey what's good today")
    assert seen == []
    assert result.backend_used == "deterministic-simulator"
    assert result.routing_decision.rule_id == "R2"


def test_environment_variable_opts_in_to_a_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_BASE", "http://llm.test/v1/")
    seen = install(monkeypatch, lambda request: completion("  Kill the fork.  "))
    result = DeterministicChatClient().step("it is broken!")
    assert [request.full_url for request in seen] == ["http://llm.test/v1/chat/completions"]
    assert result.response_text == "Kill the fork."
    assert result.backend_used == "remote (http://llm.test/v1/)"


def test_request_body_puts_vendor_sampling_fields_at_the_top_level(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = install(monkeypatch, lambda request: completion("ok"))
    DeterministicChatClient(api_base="http://llm.test/v1").step("what is raft?")
    body = json.loads(seen[0].data)  # type: ignore[arg-type]
    # `extra_body` is an OpenAI-SDK keyword argument that the SDK merges into the JSON body; over
    # raw HTTP the server only understands the merged fields.
    assert "extra_body" not in body
    assert body["repetition_penalty"] == 1.10
    assert body["no_repeat_ngram_size"] == 4
    assert body["temperature"] == 0.0
    assert body["messages"][0]["role"] == "system" and body["messages"][-1]["content"] == "what is raft?"


def test_api_key_is_sent_only_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = install(monkeypatch, lambda request: completion("ok"))
    DeterministicChatClient(api_base="http://llm.test/v1").step("hello there")
    assert seen[0].get_header("Authorization") is None
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    DeterministicChatClient(api_base="http://llm.test/v1").step("hello there")
    assert seen[1].get_header("Authorization") == "Bearer test-key"


@pytest.mark.parametrize("error", [
    urllib.error.URLError("refused"),
    TimeoutError("slow"),
    ConnectionResetError("reset"),
    json.JSONDecodeError("bad", "", 0),
])
def test_an_unreachable_backend_falls_back_and_says_why(monkeypatch: pytest.MonkeyPatch, error: BaseException) -> None:
    install(monkeypatch, raises(error))
    result = DeterministicChatClient(api_base="http://llm.test/v1").step("it is broken!")
    assert result.backend_used.startswith("deterministic-simulator")
    assert type(error).__name__ in result.backend_used
    assert result.response_text


@pytest.mark.parametrize("payload", [
    b"{}",
    b'{"choices": []}',
    b'{"choices": [{"message": {}}]}',
    b'{"choices": [{"message": {"content": null}}]}',
    b'{"choices": [{"message": {"content": 7}}]}',
    b"[1]",
])
def test_a_malformed_reply_falls_back_and_says_why(monkeypatch: pytest.MonkeyPatch, payload: bytes) -> None:
    install(monkeypatch, lambda request: FakeResponse(payload))
    result = DeterministicChatClient(api_base="http://llm.test/v1").step("it is broken!")
    assert result.backend_used.startswith("deterministic-simulator (remote unavailable")


def test_a_programming_error_is_not_hidden_behind_canned_text(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, raises(AttributeError("bug in our own code")))
    with pytest.raises(AttributeError):
        DeterministicChatClient(api_base="http://llm.test/v1").step("it is broken!")


@pytest.mark.parametrize("base", ["file:///etc", "ftp://llm.test/v1", "llm.test/v1", "javascript:alert(1)"])
def test_only_http_backends_are_accepted(base: str) -> None:
    with pytest.raises(ValueError, match="http"):
        DeterministicChatClient(api_base=base)


def test_a_failed_turn_still_records_history(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, raises(urllib.error.URLError("down")))
    client = DeterministicChatClient(api_base="http://llm.test/v1")
    assert client.step("hey what's good today").history_turn_count == 1
    assert [turn["role"] for turn in client.history] == ["user", "assistant"]
