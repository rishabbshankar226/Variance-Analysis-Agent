"""Deterministic inference client adapter.

Wraps model invocations with dynamic prompt routing, state inversion tracking,
and deterministic logit modifiers (temperature=0.0).

The client is offline by default and answers from a rule-adhering simulator. It only
contacts an OpenAI-compatible server (vLLM, TGI, ...) when one is configured explicitly,
through ``api_base`` or the ``LLM_API_BASE`` environment variable; ``LLM_API_KEY`` supplies
a bearer token when that server wants one.
"""

from __future__ import annotations

import http.client
import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass

from deterministic_conditioning.config import DeterministicDecodingConfig
from deterministic_conditioning.router import DynamicPromptRouter, RoutingDecision


@dataclass(frozen=True)
class GenerationResult:
    """Output from the deterministic inference client."""

    response_text: str
    routing_decision: RoutingDecision
    history_turn_count: int
    backend_used: str


class DeterministicChatClient:
    """Manages multi-turn conversation with dynamic conditioning and deterministic decoding."""

    def __init__(
        self,
        config: DeterministicDecodingConfig | None = None,
        router: DynamicPromptRouter | None = None,
        api_base: str | None = None,
        model_name: str = "meta-llama/Meta-Llama-3-8B-Instruct",
    ) -> None:
        self.config = config or DeterministicDecodingConfig()
        self.router = router or DynamicPromptRouter()
        base = api_base or os.getenv("LLM_API_BASE") or None
        if base is not None:
            parts = urllib.parse.urlsplit(base)
            if parts.scheme not in {"http", "https"} or not parts.netloc:
                raise ValueError(f"api_base must be an http or https URL, got {base!r}")
        self.api_base: str | None = base
        self.model_name = model_name
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.history: list[dict[str, str]] = []

    def reset_history(self) -> None:
        """Clear conversation context."""
        self.history.clear()

    def step(self, user_prompt: str) -> GenerationResult:
        """Process a user turn: evaluate signals, compile dynamic prompt, and invoke backend."""
        # 1. Deterministically route and evaluate state inversion
        decision = self.router.route(user_prompt, self.history)

        # 2. Build full message payload
        messages = [
            {"role": "system", "content": decision.compiled_system_instruction},
            *self.history,
            {"role": "user", "content": user_prompt},
        ]

        # 3. Attempt invocation via local/remote HTTP server, falling back to simulated output
        response_text, backend = self._dispatch_completion(messages, decision)

        # 4. Update multi-turn state
        self.history.append({"role": "user", "content": user_prompt})
        self.history.append({"role": "assistant", "content": response_text})

        return GenerationResult(
            response_text=response_text,
            routing_decision=decision,
            history_turn_count=len(self.history) // 2,
            backend_used=backend,
        )

    def _dispatch_completion(
        self, messages: list[dict[str, str]], decision: RoutingDecision
    ) -> tuple[str, str]:
        """Dispatch generation request to the configured endpoint, or to the offline simulator."""
        if self.api_base is None:
            return self._generate_adherent_mock(decision), "deterministic-simulator"

        endpoint = f"{self.api_base.rstrip('/')}/chat/completions"
        payload: dict[str, object] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.config.temperature,
            "frequency_penalty": self.config.frequency_penalty,
            "presence_penalty": self.config.presence_penalty,
            # vLLM and TGI read these sampling fields from the top level of the JSON body. The OpenAI
            # SDK's ``extra_body`` argument merges into that body; a nested "extra_body" key would be
            # ignored by the server.
            "repetition_penalty": self.config.repetition_penalty,
            "no_repeat_ngram_size": self.config.no_repeat_ngram_size,
        }

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                text = self._completion_text(json.loads(resp.read().decode("utf-8")))
            return text, f"remote ({self.api_base})"
        except (OSError, http.client.HTTPException, ValueError) as error:
            # Unreachable server (URLError, timeouts and resets are OSError), truncated reply, or a body
            # that is not the expected JSON. Anything else is a bug and must surface.
            mock_text = self._generate_adherent_mock(decision)
            return mock_text, f"deterministic-simulator (remote unavailable: {type(error).__name__})"

    @staticmethod
    def _completion_text(data: object) -> str:
        """The first choice's message text, or ValueError when the reply is not a chat completion."""
        choices = data.get("choices") if isinstance(data, dict) else None
        first = choices[0] if isinstance(choices, list) and choices else None
        message = first.get("message") if isinstance(first, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise ValueError("The backend reply has no completion text")
        return content.strip()

    def _generate_adherent_mock(self, decision: RoutingDecision) -> str:
        """Generate a rule-adhering synthetic response matching exact POS & burstiness contracts."""
        if decision.rule_id == "R1":
            return (
                "Check your termination grace periods first. Rolling deploys love spawning fresh "
                "application containers before old processes release their open sockets, instantly "
                "choking Postgres against its `max_connections` ceiling. Brutal time sink. Give your "
                "orchestrator thirty seconds to drain active database clients, and flip PgBouncer into "
                "transaction pooling so orphaned idle deployment handles stop killing your rollout."
            )
        elif decision.rule_id == "R2":
            return (
                "Quiet morning so far. Depends entirely on what we're building today—we could untangle "
                "that stubborn pipeline bug, refactor messy database queries, or just map out new systems. "
                "What's at the top of your stack?"
            )
        elif decision.rule_id == "R3":
            # Check if previous turn ended with '?'
            must_terminate_period = any(
                "Must terminate with a declarative period" in c
                for c in decision.inversion_constraints
            )
            closing = (
                "Straightforward architecture."
                if must_terminate_period
                else "Are your client and API hosted under the same root domain?"
            )
            return (
                "Skip the manual headers entirely. Set `credentials: 'include'` on your fetch calls, "
                "and the browser quietly attaches the cookie to every outbound request on your domain "
                "without JavaScript ever touching it. Your backend API just pulls the token off incoming "
                f"`Cookie` headers as normal. {closing}"
            )
        elif decision.rule_id == "R4":
            return (
                "While asynchronous gossip yields massive write throughput under high concurrency, "
                "it demands distributed conflict resolution schemas that add immense operational overhead down the road. "
                "Total pain point. If your workload requires linearizable reads, stick with synchronous Raft consensus; "
                "otherwise, partition your cluster geographically to insulate network partitions."
            )
        else:
            return (
                "Trading CSRF for trivial XSS isn't a win. While localStorage indeed ignores automatic "
                "cookie payloads—dodging forged requests cleanly—it leaves your raw credentials sitting naked "
                "in JavaScript reach. Keys gone in seconds. One unvetted third-party npm package or malicious injected "
                "script reads your token store immediately, exfiltrating authentication state without touching network proxies. "
                "Store tokens in secure `HttpOnly`, `SameSite=Strict` cookies instead."
            )
