# Benchmark Report: Deterministic Conditioning vs. Unconditioned Argmax

| Metric | Unconditioned Baseline (`temp=0.0`) | Conditioned Pipeline (`temp=0.0`) | Relative Delta |
|---|:---:|:---:|:---:|
| **Burstiness Score ($\sigma_{\text{lens}}$)** | 6.53 words | **10.05 words** | **+53.9%** |
| **Short Punchy Clauses (3–6w)** | 5.7% | **40.0%** | **+34.3%** |
| **Compound Observations (18–28w)**| 22.9% | **43.3%** | **+20.4%** |
| **Type-Token Ratio (TTR)** | 0.6441 | **0.7483** | **+16.2%** |
| **Distinct-2 Bigram Ratio** | 0.9618 | **0.9908** | **+3.0%** |
| **Greedy Attractors Detected** | 2 violations | **0 violations** | **-100% (Clean)** |
| **Total Evaluated Words** | 472 words | 437 words | Within ±15% symmetry |
