# D2 statistics (H3)

AccessGraph = mean F1 over the `final` runs; baselines with the same model (GPT-6 Luna). Difference = AccessGraph - baseline; 95% CI from a cluster bootstrap (pages, then cases), 10,000 replicates; p from a paired permutation test (10,000); Holm-adjusted over the comparisons on all cases.

| Set | Cases | Baseline | AG F1 | Baseline F1 | Difference (95% CI) | p | p (Holm) |
|---|---|---|---|---|---|---|---|
| expert all | 129 | InterA11y | 0.907 | 0.920 | -0.012 (-0.073 to +0.041) | 0.610 | 0.610 |
| conformance all | 394 | InterA11y | 0.910 | 0.826 | +0.085 (+0.040 to +0.133) | 0.001 | 0.001 |
| conformance all | 394 | Lopez-Pereira | 0.910 | 0.829 | +0.082 (+0.039 to +0.128) | 0.000 | 0.001 |

## Cost and time per case

AccessGraph: billed cost (OpenRouter, incl. its prompt-cache discount) of runs whose calls were all paid; time = wall time per case in single-page mode (recording + judging). InterA11y: its recorded tokens at the list price; time = its recorded total seconds.

| Set | System | Cases | USD per case | Mean s per case | Median s per case |
|---|---|---|---|---|---|
| expert | InterA11y (full) | 129 | 0.0030 | 35.0 | 24.2 |
