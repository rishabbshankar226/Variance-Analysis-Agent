"""Interactive CLI for testing deterministic conditioning in real-time.

Allows developers to enter arbitrary prompts, inspect signal routing,
observe last-turn state inversion, and verify deterministic responses.
"""

from __future__ import annotations

import argparse
import sys

from deterministic_conditioning.client_adapter import DeterministicChatClient


def print_banner() -> None:
    print("\n" + "=" * 68)
    print("      DETERMINISTIC CONVERSATIONAL AI: LIVE TERMINAL INTERACTION     ")
    print("=" * 68)
    print("• Target Model : Llama-3-8B-Instruct (temperature=0.0 / Greedy Argmax)")
    print("• Routing      : Dynamic Token-0 POS + State Inversion Enabled")
    print("• Commands     : /reset (clear history), /rules (view matrix), /exit")
    print("=" * 68 + "\n")


def print_rules_matrix() -> None:
    print("\n--- DETERMINISTIC INPUT-TO-SYNTAX ROUTER MATRIX ---")
    print("  R1: Frustration / Friction Marker -> Imperative / Active Verb")
    print("  R2: Terse / Casual Opener (<10w)  -> Fragment / Adverbial Pivot")
    print("  R3: Direct Interrogative (<15w, ?) -> Concrete Noun / Direct Action")
    print("  R4: Analytical Query (>30w, tech) -> Subordinate Conjunction")
    print("  R5: Fallback / Statement          -> Gerund / Prepositional Framing")
    print("---------------------------------------------------\n")


def run_interactive_session() -> None:
    client = DeterministicChatClient()
    print_banner()

    while True:
        try:
            user_input = input("\nYou > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            sys.exit(0)

        if not user_input:
            continue

        if user_input.lower() in {"/exit", "exit", "quit"}:
            print("Session closed.")
            sys.exit(0)

        if user_input.lower() == "/reset":
            client.reset_history()
            print("[History cleared. Reset to Turn 1.]")
            continue

        if user_input.lower() == "/rules":
            print_rules_matrix()
            continue

        # Process turn
        result = client.step(user_input)
        d = result.routing_decision

        print(f"\n[ROUTER ACTIVE | Turn {result.history_turn_count}]")
        print(f"  • Triggered Rule   : {d.rule_id} ({d.rule_name})")
        print(f"  • Mandatory POS    : {d.required_first_token_pos}")
        print(f"  • Allowed Starters : {', '.join(d.pos_examples[:4])}")

        if d.inversion_constraints:
            print("  • History Inversions Applied:")
            for inv in d.inversion_constraints:
                print(f"      - {inv}")
        else:
            print("  • History Inversions : None (Turn 1)")

        print(f"\nAssistant ({result.backend_used}) >")
        print(result.response_text)


def run_automated_demo() -> None:
    """Run an automated multi-turn conversation showing signal extraction and state inversion."""
    print_banner()
    client = DeterministicChatClient()

    turns = [
        "hey, what's good today",
        "Can you explain Raft consensus without all the academic math jargon?",
        "Wait, our Postgres cluster died again right now, this is ridiculous!",
        "Okay, but how do we handle auth headers if the client can't read the cookie directly?",
    ]

    for idx, prompt in enumerate(turns, 1):
        print(f"\n[DEMO TURN {idx}] User > {prompt}")
        result = client.step(prompt)
        d = result.routing_decision
        print(f"  -> Rule Triggered: {d.rule_id} ({d.rule_name})")
        print(f"  -> First-Token POS: {d.required_first_token_pos}")
        if d.inversion_constraints:
            print("  -> Inversions Applied:")
            for inv in d.inversion_constraints:
                print(f"       * {inv}")
        print(f"Assistant > {result.response_text}\n" + "-" * 68)


def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministic LLM Conversational CLI.")
    parser.add_argument("--demo", action="store_true", help="Run automated multi-turn demo.")
    args = parser.parse_args()

    if args.demo:
        run_automated_demo()
    else:
        run_interactive_session()


if __name__ == "__main__":
    main()
