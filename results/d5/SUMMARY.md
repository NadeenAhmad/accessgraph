# D5 summary (before expert labels)

10 apps; 933 states, 1885 transitions; 79,162 candidates; 600 judged (stratified sample); 300 exported for the experts.

| App | States (depth >= 1) | Transitions | Candidates | Judged | Violation verdicts |
|---|---|---|---|---|---|
| jira-clone-angular | 97 (46) | 123 | 2,010 | 14 | 4 |
| angular-realworld-example-app | 43 (42) | 456 | 1,288 | 12 | 2 |
| angular-challenges | 4 (3) | 6 | 28 | 0 | 0 |
| angular-ssr-course | 18 (17) | 32 | 272 | 3 | 0 |
| angular-course | 87 (78) | 336 | 2,011 | 21 | 6 |
| vuestic-admin | 150 (99) | 149 | 14,212 | 114 | 16 |
| flowbite-svelte-admin-dashboard | 150 (99) | 392 | 20,492 | 177 | 16 |
| react-admin-demo | 150 (99) | 149 | 20,360 | 139 | 4 |
| react-admin-simple | 84 (83) | 84 | 4,518 | 33 | 7 |
| react-admin-crm | 150 (99) | 158 | 13,971 | 87 | 8 |

Verdicts on the sample: {'no_violation': 514, 'violation': 63, 'uncertain': 23} (23 uncertain first verdicts resolved by follow-up).

| Direction | no_violation | uncertain | violation |
|---|---|---|---|
| backward | 135 | 3 | 26 |
| forward-button/widget | 8 | 0 | 2 |
| forward-link | 9 | 0 | 0 |
| state-local | 362 | 20 | 35 |

| Depth | no_violation | uncertain | violation |
|---|---|---|---|
| 0 | 206 | 10 | 19 |
| >=1 | 308 | 13 | 44 |

| Type | no_violation | uncertain | violation |
|---|---|---|---|
| aria-state-mismatch | 45 | 0 | 1 |
| autocomplete-purpose-mismatch | 2 | 1 | 3 |
| button-label-mismatch | 92 | 0 | 1 |
| error-message-mismatch | 13 | 2 | 2 |
| form-label-mismatch | 36 | 0 | 1 |
| heading-not-descriptive | 49 | 1 | 5 |
| image-alt-not-descriptive | 46 | 13 | 7 |
| landmark-purpose-mismatch | 49 | 2 | 4 |
| lang-mismatch | 19 | 0 | 1 |
| link-text-mismatch | 85 | 2 | 18 |
| page-title-not-descriptive | 6 | 1 | 16 |
| widget-label-purpose-mismatch | 72 | 1 | 4 |

Weighted estimates over all candidates (sampling weights):
- share of candidates judged a violation: 9.5%
- among AccessGraph's violation verdicts, share at depth >= 1: 75.5%
- among AccessGraph's violation verdicts, share whose evidence is a transition (backward or forward): 25.3%
