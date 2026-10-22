"""Conversational Benchmark Evaluator.

Compares quantitative linguistic metrics across generation regimes:
1. Unconditioned Argmax Baseline (temperature=0.0, standard generic prompt)
2. Deterministic Conditioned Pipeline (temperature=0.0, router + state inversion)

The first table scores the hand-written chosen/rejected pairs in the DPO dataset.
The "Engine output" section scores what the engine actually produces:
``generate_verified_commentary`` over real variance files, plus a fact check of
every claim against the analysis result.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from variance_agent.models import AnalysisResult

_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENGINE_FIXTURES = (
    _ROOT / "examples" / "sample_variance.csv",
    *(_ROOT / "tests" / "fixtures" / "chrome_qa" / f"{name}.csv"
      for name in ("fav_net", "unfav_net", "mixed_sign", "edge_values", "names", "structure")),
)


@dataclass(frozen=True)
class LinguisticMetrics:
    burstiness_score: float  # std_dev of sentence lengths
    avg_sentence_len: float
    short_sentence_pct: float  # % sentences with 3-6 words
    long_sentence_pct: float  # % sentences with 18-28 words
    type_token_ratio: float  # unique words / total words
    distinct_2_ratio: float  # distinct bigrams / total bigrams
    attractor_count: int  # count of greedy stock affirmations/closers
    word_count: int


class BenchmarkEvaluator:
    """Evaluates lexical diversity, burstiness, and attractor density across corpora."""

    ATTRACTOR_PATTERN = re.compile(
        r"\b(certainly|great question|i'd be happy to|sure thing|of course|in summary|overall|hope this helps|furthermore|moreover)\b",
        re.IGNORECASE,
    )
    SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
    # Inclusive word-count ranges; the report rows and README label them "3–6w" and "18–28w".
    SHORT_WORDS = (3, 6)
    LONG_WORDS = (18, 28)

    @classmethod
    def evaluate(cls, corpus: list[str]) -> LinguisticMetrics:
        all_words: list[str] = []
        sentence_lens: list[int] = []
        short_count = 0
        long_count = 0
        attractor_count = 0

        for text in corpus:
            attractor_count += len(cls.ATTRACTOR_PATTERN.findall(text))
            sentences = [s.strip() for s in cls.SENTENCE_SPLIT.split(text.strip()) if s.strip()]

            for s in sentences:
                cleaned = (re.sub(r"[^\w]", "", w).lower() for w in s.split())
                words = [w for w in cleaned if w]  # a spaced dash or bare symbol is not a word
                if not words:
                    continue
                w_len = len(words)
                sentence_lens.append(w_len)
                all_words.extend(words)

                if cls.SHORT_WORDS[0] <= w_len <= cls.SHORT_WORDS[1]:
                    short_count += 1
                elif cls.LONG_WORDS[0] <= w_len <= cls.LONG_WORDS[1]:
                    long_count += 1

        total_words = len(all_words)
        total_sentences = len(sentence_lens)

        if total_sentences < 2 or total_words == 0:
            return LinguisticMetrics(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0)

        mean_len = total_words / total_sentences
        variance = sum((slen - mean_len) ** 2 for slen in sentence_lens) / (total_sentences - 1)
        burstiness = math.sqrt(variance)

        # Type-token ratio
        unique_words = len(set(all_words))
        ttr = unique_words / total_words

        # Distinct-2 ratio
        bigrams = [(all_words[i], all_words[i + 1]) for i in range(len(all_words) - 1)]
        distinct_2 = len(set(bigrams)) / len(bigrams) if bigrams else 0.0

        return LinguisticMetrics(
            burstiness_score=round(burstiness, 2),
            avg_sentence_len=round(mean_len, 2),
            short_sentence_pct=round((short_count / total_sentences) * 100, 1),
            long_sentence_pct=round((long_count / total_sentences) * 100, 1),
            type_token_ratio=round(ttr, 4),
            distinct_2_ratio=round(distinct_2, 4),
            attractor_count=attractor_count,
            word_count=total_words,
        )


def commentary_contradictions(text: str, result: AnalysisResult) -> list[str]:
    """Claims in ``text`` that the analysis result does not support (empty when truthful)."""
    from variance_agent.models import Status

    lower = text.lower()
    net = result.revenue.variance_dollars - result.expenses.variance_dollars
    actual_profit = result.revenue.actual - result.expenses.actual
    status = {row.line_item: row.status for row in result.rows}
    problems: list[str] = []
    if net < 0:
        problems += [f"claims {word!r} on a net-unfavourable period"
                     for word in ("outpaced", "beat", "surplus", "widening", "improving") if word in lower]
    if net > 0 and "shortfall" in lower:
        problems.append("claims a shortfall on a net-favourable period")
    if actual_profit >= Decimal(0) and ("negative territory" in lower or "turned negative" in lower):
        problems.append("claims negative operating profit")
    if result.material_rows and "no unresolved variances" in lower:
        problems.append("claims no unresolved variances while material items exist")
    if "cash" in lower:
        problems.append("mentions cash, which is not an input field")
    review = re.match(r"Review (.+?) immediately", text)
    if review and status.get(review.group(1)) != Status.UNFAVORABLE:
        problems.append(f"asks to review {review.group(1)!r}, which is not unfavourable")
    for name, row_status in status.items():
        if re.search(rf"Favorable (?:variance|expansion) across {re.escape(name)}\b", text) \
                and row_status != Status.FAVORABLE:
            problems.append(f"calls {name!r} favourable")
    return problems


@dataclass(frozen=True)
class EngineBenchmark:
    metrics: LinguisticMetrics
    truthful: int
    total: int
    failures: tuple[str, ...]


def run_engine_benchmark(fixtures: list[Path] | None = None) -> EngineBenchmark:
    """Score real engine commentary over variance files ($10k or 5%, USD, Q3 2026)."""
    from deterministic_conditioning.variance_bridge import generate_verified_commentary
    from variance_agent.analysis import analyze_rows
    from variance_agent.models import AnalysisConfig
    from variance_agent.numeric import financial_context
    from variance_agent.parsing import load_input

    paths = list(fixtures) if fixtures is not None else [p for p in DEFAULT_ENGINE_FIXTURES if p.exists()]
    corpus: list[str] = []
    failures: list[str] = []
    for path in paths:
        parsed = load_input(path.read_bytes(), path.suffix.lower(), source_name=path.name)
        config = AnalysisConfig(period="Q3 2026", dollar_threshold=Decimal("10000"),
                                percent_threshold=Decimal("0.05"))
        with financial_context():
            result = analyze_rows(parsed.rows, config)
        text = generate_verified_commentary(result)[0]
        corpus.append(text)
        failures += [f"{path.name}: {problem}" for problem in commentary_contradictions(text, result)]
    failed_files = {failure.split(":", 1)[0] for failure in failures}
    return EngineBenchmark(
        metrics=BenchmarkEvaluator.evaluate(corpus),
        truthful=len(paths) - len(failed_files),
        total=len(paths),
        failures=tuple(failures),
    )


def _relative(new: float, old: float) -> str:
    return f"{(new - old) / old:+.1%}" if old else "n/a"


def run_benchmark_comparison(engine_fixtures: list[Path] | None = None) -> str:
    """Run comparative benchmark and return Markdown report."""
    from deterministic_conditioning.dataset_generator import EXPANDED_DATASET_SPECS

    unconditioned_corpus = [s.rejected for s in EXPANDED_DATASET_SPECS]
    conditioned_corpus = [s.chosen for s in EXPANDED_DATASET_SPECS]

    m_uncond = BenchmarkEvaluator.evaluate(unconditioned_corpus)
    m_cond = BenchmarkEvaluator.evaluate(conditioned_corpus)

    report = rf"""# Benchmark Report: Deterministic Conditioning vs. Unconditioned Argmax

| Metric | Unconditioned Baseline (`temp=0.0`) | Conditioned Pipeline (`temp=0.0`) | Relative Delta |
|---|:---:|:---:|:---:|
| **Burstiness Score ($\sigma_{{\text{{lens}}}}$)** | {m_uncond.burstiness_score} words | **{m_cond.burstiness_score} words** | **{_relative(m_cond.burstiness_score, m_uncond.burstiness_score)}** |
| **Short Punchy Clauses (3–6w)** | {m_uncond.short_sentence_pct}% | **{m_cond.short_sentence_pct}%** | **{m_cond.short_sentence_pct - m_uncond.short_sentence_pct:+.1f} pts** |
| **Compound Observations (18–28w)**| {m_uncond.long_sentence_pct}% | **{m_cond.long_sentence_pct}%** | **{m_cond.long_sentence_pct - m_uncond.long_sentence_pct:+.1f} pts** |
| **Type-Token Ratio (TTR)** | {m_uncond.type_token_ratio} | **{m_cond.type_token_ratio}** | **{_relative(m_cond.type_token_ratio, m_uncond.type_token_ratio)}** |
| **Distinct-2 Bigram Ratio** | {m_uncond.distinct_2_ratio} | **{m_cond.distinct_2_ratio}** | **{_relative(m_cond.distinct_2_ratio, m_uncond.distinct_2_ratio)}** |
| **Greedy Attractors Detected** | {m_uncond.attractor_count} violations | **{m_cond.attractor_count} violations** | **{m_cond.attractor_count - m_uncond.attractor_count:+d}** |
| **Total Evaluated Words** | {m_uncond.word_count} words | {m_cond.word_count} words | {_relative(m_cond.word_count, m_uncond.word_count)} |

_This table scores the hand-written chosen/rejected pairs in the DPO dataset, not engine output._
"""
    engine = run_engine_benchmark(engine_fixtures)
    m = engine.metrics
    report += f"""
## Engine output (`generate_verified_commentary` on {engine.total} variance files)

| Metric | Engine output |
|---|:---:|
| **Commentaries with no contradicted claim** | **{engine.truthful}/{engine.total}** |
| **Burstiness Score** | {m.burstiness_score} words |
| **Short Punchy Clauses (3–6w)** | {m.short_sentence_pct}% |
| **Compound Observations (18–28w)** | {m.long_sentence_pct}% |
| **Type-Token Ratio (TTR)** | {m.type_token_ratio} |
| **Greedy Attractors Detected** | {m.attractor_count} violations |
| **Total Evaluated Words** | {m.word_count} words |
"""
    if engine.failures:
        report += "\nContradicted claims:\n" + "\n".join(f"- {failure}" for failure in engine.failures) + "\n"
    return report


def main() -> None:
    report = run_benchmark_comparison()
    print(report)

    output_path = Path(__file__).parent / "BENCHMARK_REPORT.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Report written to: {output_path}")


if __name__ == "__main__":
    main()
