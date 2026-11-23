# D3 (W3C ACT, 7 rules) and D6 (Rampa's pairs, 9 corruptors)

88 ACT test cases; 51 pairs. Other tools: stored results of Rampa's harness (df32363, 2026-10-11). AccessGraph cost $0.0448.

| Tool | Reading | P | R (95% CI) | F1 | FP | inapplicable flagged | errors | pairs told apart |
|---|---|---|---|---|---|---|---|---|
| axe | definite | – | 0.00 (0.00–0.11) | – | 0 | 4/25 | 0 | 0/51 |
| axe | with review | – | 0.00 (0.00–0.11) | – | 0 | 4/25 | 0 | 0/51 |
| alfa | definite | – | 0.00 (0.00–0.11) | – | 0 | 4/25 | 0 | 0/51 |
| alfa | with review | – | 0.00 (0.00–0.11) | – | 0 | 4/25 | 0 | 0/51 |
| qualweb | definite | – | 0.00 (0.00–0.11) | – | 0 | 5/25 | 0 | 0/51 |
| qualweb | with review | 0.60 | 0.20 (0.10–0.37) | 0.30 | 4 | 7/25 | 0 | 3/51 |
| ibm | definite | – | 0.00 (0.00–0.11) | – | 0 | 5/25 | 0 | 0/51 |
| ibm | with review | – | 0.00 (0.00–0.11) | – | 0 | 6/25 | 0 | 0/51 |
| pa11y | definite | 0.00 | 0.00 (0.00–0.11) | 0.00 | 1 | 2/25 | 0 | 2/51 |
| pa11y | with review | 0.00 | 0.00 (0.00–0.11) | 0.00 | 1 | 4/25 | 0 | 2/51 |
| pa11y-axe | definite | – | 0.00 (0.00–0.11) | – | 0 | 4/25 | 0 | 0/51 |
| pa11y-axe | with review | – | 0.00 (0.00–0.11) | – | 0 | 4/25 | 0 | 0/51 |
| rampa | definite | – | 0.00 (0.00–0.11) | – | 0 | 4/25 | 0 | 0/51 |
| rampa | with review | – | 0.00 (0.00–0.11) | – | 0 | 4/25 | 0 | 1/51 |
| rampa | with low | – | 0.00 (0.00–0.11) | – | 0 | 4/25 | 0 | 1/51 |
| rampa-gemma | definite | 1.00 | 0.50 (0.33–0.67) | 0.67 | 0 | 4/25 | 0 | 36/51 |
| rampa-gemma | with review | 0.96 | 0.80 (0.63–0.90) | 0.87 | 1 | 4/25 | 0 | 49/51 |
| rampa-gemma | with low | 1.00 | 0.57 (0.39–0.73) | 0.72 | 0 | 4/25 | 0 | 36/51 |
| rampa-probes | definite | 1.00 | 0.33 (0.19–0.51) | 0.50 | 0 | 4/25 | 31 | 17/51 |
| rampa-probes | with review | 1.00 | 0.43 (0.27–0.61) | 0.60 | 0 | 4/25 | 31 | 27/51 |
| rampa-probes | with low | 1.00 | 0.33 (0.19–0.51) | 0.50 | 0 | 4/25 | 31 | 17/51 |
| accessgraph | definite | 0.97 | 0.97 (0.83–0.99) | 0.97 | 1 | 1/25 | 0 | 50/51 |
| accessgraph | with review | 0.97 | 0.97 (0.83–0.99) | 0.97 | 1 | 3/25 | 0 | 49/51 |
