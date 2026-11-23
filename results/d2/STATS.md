# D2 statistics (H3)

AccessGraph = mean F1 over the `final` runs; baselines with the same model (GPT-6 Luna). Difference = AccessGraph - baseline; 95% CI from a cluster bootstrap (pages, then cases), 10,000 replicates; p from a paired permutation test (10,000); Holm-adjusted over the comparisons on all cases.

| Set | Cases | Baseline | AG F1 | Baseline F1 | Difference (95% CI) | p | p (Holm) |
|---|---|---|---|---|---|---|---|
| expert all | 47 | InterA11y | 0.931 | 0.920 | +0.011 (-0.122 to +0.147) | 0.816 | 0.816 |
| conformance all | 269 | InterA11y | 0.883 | 0.829 | +0.054 (-0.007 to +0.117) | 0.089 | 0.267 |
| conformance all | 269 | Lopez-Pereira | 0.883 | 0.849 | +0.034 (-0.021 to +0.091) | 0.240 | 0.480 |

## Cost and time per case

AccessGraph: billed cost (OpenRouter, incl. its prompt-cache discount) of runs whose calls were all paid; time = wall time per case in single-page mode (recording + judging). InterA11y: its recorded tokens at the list price; time = its recorded total seconds.

| Set | System | Cases | USD per case | Mean s per case | Median s per case |
|---|---|---|---|---|---|
| expert | InterA11y (full) | 47 | 0.0035 | 43.7 | 32.5 |
