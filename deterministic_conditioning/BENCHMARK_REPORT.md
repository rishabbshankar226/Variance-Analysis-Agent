# Benchmark Report: Deterministic Conditioning vs. Unconditioned Argmax

| Metric | Unconditioned Baseline (`temp=0.0`) | Conditioned Pipeline (`temp=0.0`) | Relative Delta |
|---|:---:|:---:|:---:|
| **Burstiness Score ($\sigma_{\text{lens}}$)** | 6.53 words | **10.05 words** | **+53.9%** |
| **Short Punchy Clauses (3–6w)** | 0.0% | **30.0%** | **+30.0 pts** |
| **Compound Observations (18–28w)**| 17.1% | **43.3%** | **+26.2 pts** |
| **Type-Token Ratio (TTR)** | 0.6441 | **0.7483** | **+16.2%** |
| **Distinct-2 Bigram Ratio** | 0.9618 | **0.9908** | **+3.0%** |
| **Greedy Attractors Detected** | 2 violations | **0 violations** | **-2** |
| **Total Evaluated Words** | 472 words | 437 words | -7.4% |

_This table scores the hand-written chosen/rejected pairs in the DPO dataset, not engine output._

## Engine output (`generate_verified_commentary` on 7 variance files)

| Metric | Engine output |
|---|:---:|
| **Commentaries with no contradicted claim** | **7/7** |
| **Burstiness Score** | 4.98 words |
| **Short Punchy Clauses (3–6w)** | 50.0% |
| **Compound Observations (18–28w)** | 0.0% |
| **Type-Token Ratio (TTR)** | 0.3447 |
| **Greedy Attractors Detected** | 0 violations |
| **Total Evaluated Words** | 235 words |
