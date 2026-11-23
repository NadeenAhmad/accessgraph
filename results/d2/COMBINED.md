# D2, all cases of the shared criteria: AccessGraph integrated with axe-core

AccessGraph judges the semantic (in-scope) cases; axe-core's saved results cover all cases. AccessGraph runs: tag `final`.

## expert: 129 cases (69 violations)

| System | P | R | F1 | TP | FP | FN |
|---|---|---|---|---|---|---|
| InterA11y (full, GPT-6 Luna) | 0.926 | 0.913 | 0.920 | 63 | 5 | 6 |
| axe-core | 0.976 | 0.580 | 0.727 | 40 | 1 | 29 |
| AccessGraph alone (expert-final-run-1) | 0.920 | 0.333 | 0.489 | 23 | 2 | 46 |
| AccessGraph + axe-core (expert-final-run-1) | 0.953 | 0.884 | 0.917 | 61 | 3 | 8 |
| AccessGraph alone (expert-final-run-2) | 0.920 | 0.333 | 0.489 | 23 | 2 | 46 |
| AccessGraph + axe-core (expert-final-run-2) | 0.953 | 0.884 | 0.917 | 61 | 3 | 8 |
| AccessGraph alone (expert-final-run-3) | 0.840 | 0.304 | 0.447 | 21 | 4 | 48 |
| AccessGraph + axe-core (expert-final-run-3) | 0.922 | 0.855 | 0.887 | 59 | 5 | 10 |

## conformance: 394 cases (151 violations)

| System | P | R | F1 | TP | FP | FN |
|---|---|---|---|---|---|---|
| InterA11y (full, GPT-6 Luna) | 0.837 | 0.815 | 0.826 | 123 | 24 | 28 |
| axe-core | 1.000 | 0.192 | 0.322 | 29 | 0 | 122 |
| AccessGraph alone (conformance-final-run-1) | 0.891 | 0.755 | 0.817 | 114 | 14 | 37 |
| AccessGraph + axe-core (conformance-final-run-1) | 0.908 | 0.921 | 0.914 | 139 | 14 | 12 |
| AccessGraph alone (conformance-final-run-2) | 0.896 | 0.742 | 0.812 | 112 | 13 | 39 |
| AccessGraph + axe-core (conformance-final-run-2) | 0.913 | 0.907 | 0.910 | 137 | 13 | 14 |
| AccessGraph alone (conformance-final-run-3) | 0.895 | 0.735 | 0.807 | 111 | 13 | 40 |
| AccessGraph + axe-core (conformance-final-run-3) | 0.913 | 0.901 | 0.907 | 136 | 13 | 15 |

