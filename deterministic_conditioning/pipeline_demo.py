"""Interactive demo demonstrating dynamic prompt routing and history inversion."""

from __future__ import annotations

from deterministic_conditioning.config import DeterministicDecodingConfig
from deterministic_conditioning.router import DynamicPromptRouter


def run_conversation_simulation() -> None:
    router = DynamicPromptRouter()
    config = DeterministicDecodingConfig()

    print("=================================================================")
    print("      END-TO-END DETERMINISTIC CONDITIONING PIPELINE DEMO       ")
    print("=================================================================")
    print(f"Sampling Setup : temperature={config.temperature} (Greedy Argmax)")
    print(f"Logit Modifiers: repetition_penalty={config.repetition_penalty}, "
          f"freq_penalty={config.frequency_penalty}, pres_penalty={config.presence_penalty}, "
          f"no_repeat_ngram={config.no_repeat_ngram_size}\n")

    history: list[dict[str, str]] = []

    # Turn 1: Casual Opener
    turn_1_user = "hey, what's good today"
    decision_1 = router.route(turn_1_user, history)
    print("-----------------------------------------------------------------")
    print(f"[TURN 1] User: \"{turn_1_user}\"")
    print(f"Triggered Rule: {decision_1.rule_id} ({decision_1.rule_name})")
    print(f"Required POS  : {decision_1.required_first_token_pos}")
    print("Compiled System Instruction Preview:")
    for line in decision_1.compiled_system_instruction.strip().split("\n")[:6]:
        print(f"  | {line}")

    # Simulated deterministic assistant response matching R2
    assistant_1 = (
        "Quiet morning so far. Depends entirely on what we're building today—we could untangle "
        "that stubborn pipeline bug, refactor messy database queries, or just map out new systems. "
        "What's at the top of your stack?"
    )
    print(f"\nAssistant Turn 1: \"{assistant_1}\"")
    history.append({"role": "user", "content": turn_1_user})
    history.append({"role": "assistant", "content": assistant_1})

    # Turn 2: Follow-up with technical question
    turn_2_user = "Can you explain Raft consensus without all the academic math jargon?"
    decision_2 = router.route(turn_2_user, history)
    print("\n-----------------------------------------------------------------")
    print(f"[TURN 2] User: \"{turn_2_user}\"")
    print(f"Triggered Rule: {decision_2.rule_id} ({decision_2.rule_name})")
    print(f"Required POS  : {decision_2.required_first_token_pos}")
    print("Active Inversion Directives:")
    for inv in decision_2.inversion_constraints:
        print(f"  * {inv}")

    # Simulated assistant response matching R3 + Turn 1 inversion (Turn 1 ended with '?'; Turn 2 must end with '.')
    assistant_2 = (
        "Picture a shared project notebook. One person gets elected team leader, writes down every "
        "decision, and hands exact carbon copies to everyone else at the table. Simple setup. "
        "If that leader abruptly stops answering, the team checks their timers, calls a snap vote, "
        "and picks whichever peer holds the freshest copy of the notebook so nobody loses track of the truth."
    )
    print(f"\nAssistant Turn 2: \"{assistant_2}\"")
    history.append({"role": "user", "content": turn_2_user})
    history.append({"role": "assistant", "content": assistant_2})

    # Turn 3: Follow-up under frustration
    turn_3_user = "Wait, our Postgres cluster died again right now, this is ridiculous!"
    decision_3 = router.route(turn_3_user, history)
    print("\n-----------------------------------------------------------------")
    print(f"[TURN 3] User: \"{turn_3_user}\"")
    print(f"Triggered Rule: {decision_3.rule_id} ({decision_3.rule_name})")
    print(f"Required POS  : {decision_3.required_first_token_pos}")
    print("Active Inversion Directives:")
    for inv in decision_3.inversion_constraints:
        print(f"  * {inv}")

    print("\n=================================================================")
    print("Pipeline simulation complete.")
    print("=================================================================")


if __name__ == "__main__":
    run_conversation_simulation()
