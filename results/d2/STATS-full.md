# D2 statistics (H3)

AccessGraph = mean F1 over the `final` runs; baselines with the same model (GPT-6 Luna). Difference = AccessGraph - baseline; 95% CI from a cluster bootstrap (pages, then cases), 10,000 replicates; p from a paired permutation test (10,000); Holm-adjusted over the comparisons on all cases.

| Set | Cases | Baseline | AG F1 | Baseline F1 | Difference (95% CI) | p | p (Holm) |
|---|---|---|---|---|---|---|---|
| expert all | 129 | InterA11y | 0.475 | 0.920 | -0.445 (-0.769 to -0.163) | 0.000 | 0.000 |
| conformance all | 394 | InterA11y | 0.812 | 0.826 | -0.013 (-0.076 to +0.049) | 0.669 | 1.000 |
| conformance all | 394 | Lopez-Pereira | 0.812 | 0.829 | -0.017 (-0.078 to +0.042) | 0.581 | 1.000 |

## Cost and time per case

AccessGraph: billed cost (OpenRouter, incl. its prompt-cache discount) of runs whose calls were all paid; time = wall time per case in single-page mode (recording + judging). InterA11y: its recorded tokens at the list price; time = its recorded total seconds.

| Set | System | Cases | USD per case | Mean s per case | Median s per case |
|---|---|---|---|---|---|
| expert | InterA11y (full) | 129 | 0.0030 | 35.0 | 24.2 |
