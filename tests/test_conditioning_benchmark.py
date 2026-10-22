"""BenchmarkEvaluator buckets must match the ranges its report labels and README promise."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from deterministic_conditioning.benchmark import BenchmarkEvaluator

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "deterministic_conditioning"


def sentence(words: int) -> str:
    return " ".join(["word"] * words) + "."


def corpus_of(*lengths: int) -> list[str]:
    return [" ".join(sentence(n) for n in lengths)]


@pytest.mark.parametrize(("length", "short"), [(1, 0), (2, 0), (3, 1), (6, 1), (7, 0), (12, 0)])
def test_short_bucket_is_three_to_six_words(length: int, short: int) -> None:
    metrics = BenchmarkEvaluator.evaluate(corpus_of(length, 12))
    assert metrics.short_sentence_pct == short * 50.0, length


@pytest.mark.parametrize(("length", "long"), [(12, 0), (17, 0), (18, 1), (28, 1), (29, 0), (30, 0)])
def test_long_bucket_is_eighteen_to_twenty_eight_words(length: int, long: int) -> None:
    metrics = BenchmarkEvaluator.evaluate(corpus_of(length, 12))
    assert metrics.long_sentence_pct == long * 50.0, length


def test_a_lone_dash_is_not_a_word() -> None:
    metrics = BenchmarkEvaluator.evaluate(["Quiet morning — then silence. Another sentence follows here."])
    assert metrics.word_count == 8


def test_labels_in_the_report_and_dataclass_match_the_buckets() -> None:
    source = (PACKAGE / "benchmark.py").read_text(encoding="utf-8")
    assert "3-6 words" in source and "18-28 words" in source
    assert re.search(r"Short Punchy Clauses \(3–6w\)", source)
    assert re.search(r"Compound Observations \(18–28w\)", source)
