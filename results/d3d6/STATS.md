# D3/D6 statistics: AccessGraph vs Rampa+Gemma

AccessGraph tag `v13` (definite verdicts). D3: difference in F1 with a cluster bootstrap CI (ACT rules, then cases; 10,000 replicates) and a paired permutation test; D6: pairs told apart, exact McNemar. Holm over the four comparisons on all cases.

| Set | Rampa+Gemma reading | n | AG | Rampa+Gemma | Difference (95% CI) | p | p (Holm) |
|---|---|---|---|---|---|---|---|
| D3 all | definite | 63 | F1 0.967 | F1 0.667 | +0.300 (+0.003 to +0.732) | 0.001 | 0.002 |
| D6 all | definite | 51 | 50 pairs | 36 pairs | +14 (only AG 15, only R+G 1) | 0.001 | 0.002 |
| D3 all | with review | 63 | F1 0.967 | F1 0.873 | +0.094 (-0.080 to +0.366) | 0.097 | 0.195 |
| D6 all | with review | 51 | 50 pairs | 49 pairs | +1 (only AG 2, only R+G 1) | 1.000 | 1.000 |
| D3 untouched | definite | 36 | F1 0.941 | F1 0.640 | +0.301 (-0.059 to +0.789) | 0.024 | – |
| D6 untouched | definite | 29 | 29 pairs | 20 pairs | +9 (only AG 9, only R+G 0) | 0.004 | – |
| D3 untouched | with review | 36 | F1 0.941 | F1 0.839 | +0.102 (-0.143 to +0.436) | 0.307 | – |
| D6 untouched | with review | 29 | 29 pairs | 28 pairs | +1 (only AG 1, only R+G 0) | 1.000 | – |
