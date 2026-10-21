"""Deterministic LLM Conditioning and Fine-Tuning Package."""

from deterministic_conditioning.client_adapter import DeterministicChatClient, GenerationResult
from deterministic_conditioning.config import DeterministicDecodingConfig
from deterministic_conditioning.curation_gates import CurationGates, GateResult, PairValidationReport
from deterministic_conditioning.dataset_generator import EXPANDED_DATASET_SPECS, generate_and_filter_dataset
from deterministic_conditioning.financial_commentary import FinancialAuditSummary, FinancialCommentaryConditioner
from deterministic_conditioning.logits_processor import DeterministicLogitsProcessor, LogitStepTrace
from deterministic_conditioning.router import DynamicPromptRouter, ObservableSignals, RoutingDecision
from deterministic_conditioning.simulate_generation import DeterministicTextGenerator, SimulationOutcome, ToyLanguageModel
from deterministic_conditioning.train_dpo_hf import format_llama3_chat, run_training_pipeline

__all__ = [
    "DeterministicDecodingConfig",
    "DeterministicLogitsProcessor",
    "LogitStepTrace",
    "DeterministicTextGenerator",
    "ToyLanguageModel",
    "SimulationOutcome",
    "FinancialAuditSummary",
    "FinancialCommentaryConditioner",
    "CurationGates",
    "GateResult",
    "PairValidationReport",
    "DynamicPromptRouter",
    "ObservableSignals",
    "RoutingDecision",
    "DeterministicChatClient",
    "GenerationResult",
    "generate_and_filter_dataset",
    "EXPANDED_DATASET_SPECS",
    "format_llama3_chat",
    "run_training_pipeline",
]
