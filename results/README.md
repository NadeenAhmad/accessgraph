# Results

Final results of the paper's experiments. `python -m eval.reproduce` rebuilds the tables and statistics from these
files and checks every number against `PAPER_NUMBERS.md`.

| File | Contents |
|---|---|
| `PAPER_NUMBERS.md` | Every number reported in the paper, with its key |
| `d2/COMBINED.md` | D2 (InterA11y's datasets, all cases as released): AccessGraph alone, axe-core alone, and AccessGraph + axe-core per run, with InterA11y for comparison (P, R, F1, TP, FP, FN) |
| `d2/SCORES-full.md` | All systems on D2, scored with InterA11y's own scorer |
| `d2/STATS-full-axe.md`, `stats-full-axe.json` | D2 differences of AccessGraph + axe-core vs InterA11y and López-Gil & Pereira: bootstrap CIs, permutation tests, Holm-adjusted p |
| `d2/STATS-full.md`, `d2/STATS.md` | The same for AccessGraph alone, on all cases and on the semantic cases only (further analysis) |
| `d2/predictions/` | AccessGraph's prediction for every D2 case, three runs per set |
| `d2/scope.csv` | Which D2 cases are semantic (name present, decided from the accessibility tree without labels) |
| `d2/parse-*-full/` | InterA11y's scorer output for all systems |
| `d2/logs/` | Logs of the three runs per set |
| `d3d6/SCORES.md`, `scores.json` | D3 (W3C ACT) and D6 (Rampa's pairs): every tool, both readings |
| `d3d6/STATS.md`, `stats.json` | AccessGraph vs Rampa + Gemma: bootstrap CIs, permutation test, McNemar, Holm |
| `d3d6/raw/` | AccessGraph's verdicts per page; `pairs.json`, `pages.json` list the pairs and pages |
| `d5/SUMMARY.md`, `summary.json` | Real SPAs: states, transitions, candidates, judged sample, verdict shares (weighted) |
| `d5/sample.csv`, `population.json` | The stratified sample of 600 candidates and the strata sizes |

AccessGraph's per-item verdicts on the D5 sample, the expert labels and the cached model answers are added after
the expert review (see `../TODO.md`). Run and cost logs: `../logs/`.
