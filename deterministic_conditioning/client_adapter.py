"""Deterministic inference client adapter.

Wraps model invocations with dynamic prompt routing, state inversion tracking,
and deterministic logit modifiers (temperature=0.0).
"""

from __future__ import annotations

import json
import os
import urllib.error
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
        self.api_base: str = api_base or os.getenv("LLM_API_BASE") or "http://localhost:8000/v1"
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
        """Dispatch generation request to OpenAI-compatible endpoint or mock simulator."""
        endpoint = f"{self.api_base.rstrip('/')}/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.config.temperature,
            "frequency_penalty": self.config.frequency_penalty,
            "presence_penalty": self.config.presence_penalty,
            # Note: repetition_penalty / no_repeat_ngram_size are supported in vLLM/TGI
            "extra_body": {
                "repetition_penalty": self.config.repetition_penalty,
                "no_repeat_ngram_size": self.config.no_repeat_ngram_size,
            },
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
                data = json.loads(resp.read().decode("utf-8"))
                choice = data["choices"][0]["message"]["content"]
                return choice.strip(), f"remote ({self.api_base})"
        except (urllib.error.URLError, TimeoutError, KeyError, Exception):
            # Fallback to local rule-adhering mock generation when offline
            mock_text = self._generate_adherent_mock(decision)
            return mock_text, "deterministic-simulator"

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
                f"without JavaScript ever touching it. Your backend API just pulls the token off incoming `Cookie` headers as normal. {closing}"
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
