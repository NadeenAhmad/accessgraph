# D2: InterA11y's datasets, all cases as released

Scored with InterA11y's own `parse` on every case of the shared criteria; other systems are their saved predictions on the same cases. Flagged = a definite finding (uncertain counts as not flagged).

## expert: 129 in-scope cases (69 violations, 60 no violation)

Cross-check with our own count: 10 differ.

| System | Condition | Model | P | R | F1 | FP | missing/failed |
|---|---|---|---|---|---|---|---|
| accessgraph | r2-run-1 | luna | 0.889 | 0.232 | 0.368 | 2 | 84 |
| accessgraph | run-1 | luna | 1.000 | 0.072 | 0.135 | 0 | 83 |
| accessgraph | v10p-run-1 | luna | 0.917 | 0.319 | 0.473 | 2 | 82 |
| accessgraph | v11-run-1 | luna | 0.917 | 0.319 | 0.473 | 2 | 82 |
| accessgraph | v11-run-2 | luna | 0.875 | 0.304 | 0.452 | 3 | 82 |
| accessgraph | v11-run-3 | luna | 0.905 | 0.275 | 0.422 | 2 | 82 |
| accessgraph | v12-run-1 | luna | 0.880 | 0.319 | 0.468 | 3 | 1 |
| accessgraph | v12-run-2 | luna | 0.917 | 0.319 | 0.473 | 2 | 1 |
| accessgraph | v12-run-3 | luna | 0.913 | 0.304 | 0.457 | 2 | 1 |
| accessgraph | v13-run-1 | luna | 0.920 | 0.333 | 0.489 | 2 | 1 |
| accessgraph | v13-run-2 | luna | 0.920 | 0.333 | 0.489 | 2 | 1 |
| accessgraph | v13-run-3 | luna | 0.840 | 0.304 | 0.447 | 4 | 1 |
| accessgraph | v3-run-1 | luna | 0.947 | 0.261 | 0.409 | 1 | 82 |
| accessgraph | v3-run-2 | luna | 0.857 | 0.261 | 0.400 | 3 | 82 |
| accessgraph | v3-run-3 | luna | 0.818 | 0.261 | 0.396 | 4 | 82 |
| accessgraph | v9-run-1 | luna | 0.909 | 0.290 | 0.440 | 2 | 82 |
| accessguru | default | claude | 0.907 | 0.710 | 0.797 | 5 | 129 |
| accessguru | default | gemini | 0.917 | 0.638 | 0.752 | 4 | 129 |
| accessguru | default | glm | 0.895 | 0.739 | 0.810 | 6 | 129 |
| accessguru | default | luna | 0.939 | 0.667 | 0.780 | 3 | 129 |
| agentlab | general-tools | claude | 0.778 | 0.101 | 0.179 | 2 | 129 |
| agentlab | general-tools | gemini | 0.667 | 0.377 | 0.481 | 13 | 129 |
| agentlab | general-tools | glm | 0.632 | 0.174 | 0.273 | 7 | 129 |
| agentlab | general-tools | luna | 0.833 | 0.145 | 0.247 | 2 | 129 |
| alfa | default | none | 1.000 | 0.174 | 0.296 | 0 | 129 |
| aslint | default | none | 1.000 | 0.072 | 0.135 | 0 | 129 |
| axe | default | none | 0.976 | 0.580 | 0.727 | 1 | 129 |
| bagel | default | none | – | 0.000 | 0.000 | 0 | 129 |
| browser-use | general-tools | claude | 0.846 | 0.159 | 0.268 | 2 | 129 |
| browser-use | general-tools | gemini | 0.691 | 0.551 | 0.613 | 17 | 129 |
| browser-use | general-tools | glm | 0.803 | 0.826 | 0.814 | 14 | 129 |
| browser-use | general-tools | luna | 0.667 | 0.174 | 0.276 | 6 | 129 |
| ed11y | default | none | 0.929 | 0.188 | 0.313 | 1 | 129 |
| gena11y | default | claude | 0.800 | 0.348 | 0.485 | 6 | 129 |
| gena11y | default | gemini | 0.872 | 0.594 | 0.707 | 6 | 129 |
| gena11y | default | glm | 0.942 | 0.710 | 0.810 | 3 | 129 |
| gena11y | default | luna | 0.935 | 0.420 | 0.580 | 2 | 129 |
| htmlcs | default | none | 0.857 | 0.087 | 0.158 | 1 | 129 |
| ibm | default | none | 0.800 | 0.116 | 0.203 | 2 | 129 |
| intera11y | full | claude | 0.925 | 0.899 | 0.912 | 5 | 129 |
| intera11y | full | gemini | 0.913 | 0.913 | 0.913 | 6 | 129 |
| intera11y | full | glm | 0.955 | 0.913 | 0.933 | 3 | 129 |
| intera11y | full | luna | 0.926 | 0.913 | 0.920 | 5 | 129 |
| lynx | default | none | – | 0.000 | 0.000 | 0 | 129 |
| nuval | default | none | 1.000 | 0.101 | 0.184 | 0 | 129 |
| qualweb | default | none | 0.933 | 0.203 | 0.333 | 1 | 129 |
| rule-ensemble | default | none | 0.957 | 0.638 | 0.765 | 2 | 129 |
| testaro | default | none | 1.000 | 0.014 | 0.029 | 0 | 129 |

## conformance: 394 in-scope cases (151 violations, 243 no violation)

Cross-check with our own count: 10 differ.

| System | Condition | Model | P | R | F1 | FP | missing/failed |
|---|---|---|---|---|---|---|---|
| accessgraph | r2-run-1 | luna | 0.854 | 0.232 | 0.365 | 6 | 260 |
| accessgraph | run-1 | luna | 0.756 | 0.225 | 0.347 | 11 | 125 |
| accessgraph | v10p-run-1 | luna | 0.891 | 0.272 | 0.416 | 5 | 260 |
| accessgraph | v11-run-1 | luna | 0.838 | 0.550 | 0.664 | 16 | 125 |
| accessgraph | v11-run-2 | luna | 0.814 | 0.550 | 0.656 | 19 | 125 |
| accessgraph | v11-run-3 | luna | 0.838 | 0.550 | 0.664 | 16 | 125 |
| accessgraph | v12-run-1 | luna | 0.851 | 0.682 | 0.757 | 18 | 0 |
| accessgraph | v12-run-2 | luna | 0.833 | 0.695 | 0.758 | 21 | 0 |
| accessgraph | v12-run-3 | luna | 0.848 | 0.702 | 0.768 | 19 | 0 |
| accessgraph | v13-run-1 | luna | 0.891 | 0.755 | 0.817 | 14 | 0 |
| accessgraph | v13-run-2 | luna | 0.896 | 0.742 | 0.812 | 13 | 0 |
| accessgraph | v13-run-3 | luna | 0.895 | 0.735 | 0.807 | 13 | 0 |
| accessgraph | v3-run-1 | luna | 0.847 | 0.477 | 0.610 | 13 | 125 |
| accessgraph | v3-run-2 | luna | 0.877 | 0.470 | 0.612 | 10 | 125 |
| accessgraph | v3-run-3 | luna | 0.899 | 0.470 | 0.617 | 8 | 125 |
| accessgraph | v9-run-1 | luna | 0.897 | 0.464 | 0.611 | 8 | 125 |
| accessguru | default | claude | 0.459 | 0.709 | 0.557 | 126 | 0 |
| accessguru | default | gemini | 0.725 | 0.629 | 0.674 | 36 | 394 |
| accessguru | default | glm | 0.520 | 0.689 | 0.593 | 96 | 394 |
| accessguru | default | luna | 0.688 | 0.656 | 0.671 | 45 | 394 |
| alfa | default | none | 0.967 | 0.192 | 0.320 | 1 | 394 |
| aslint | default | none | 0.429 | 0.099 | 0.161 | 20 | 0 |
| axe | default | none | 1.000 | 0.192 | 0.322 | 0 | 394 |
| bagel | default | none | – | 0.000 | 0.000 | 0 | 394 |
| ed11y | default | none | 0.682 | 0.099 | 0.173 | 7 | 0 |
| gena11y | default | claude | 0.542 | 0.556 | 0.549 | 71 | 0 |
| gena11y | default | gemini | 0.659 | 0.589 | 0.622 | 46 | 394 |
| gena11y | default | glm | 0.576 | 0.503 | 0.537 | 56 | 394 |
| gena11y | default | luna | 0.566 | 0.570 | 0.568 | 66 | 394 |
| htmlcs | default | none | 0.423 | 0.073 | 0.124 | 15 | 394 |
| ibm | default | none | 0.824 | 0.185 | 0.303 | 6 | 394 |
| lopez-pereira | default | claude | 0.767 | 0.762 | 0.764 | 35 | 0 |
| lopez-pereira | default | gemini | 0.861 | 0.861 | 0.861 | 21 | 0 |
| lopez-pereira | default | glm | 0.744 | 0.596 | 0.662 | 31 | 0 |
| lopez-pereira | default | luna | 0.824 | 0.834 | 0.829 | 27 | 0 |
| lynx | default | none | – | 0.000 | 0.000 | 0 | 394 |
| nuval | default | none | 0.333 | 0.020 | 0.037 | 6 | 0 |
| qualweb | default | none | 0.800 | 0.212 | 0.335 | 8 | 394 |
| rule-ensemble | default | none | 0.622 | 0.404 | 0.490 | 37 | 394 |
| testaro | default | none | 0.441 | 0.172 | 0.248 | 33 | 0 |

