# Evaluation harness

Code for the paper's experiments. AccessGraph itself lives in `../src/` and never imports this folder
(`eval/tests/test_harness.py` checks that the tool contains no benchmark ids, app names or registry fields). The
protocol, commands and costs are in [../docs/evaluation.md](../docs/evaluation.md).

```bash
python -m eval.reproduce     # rebuild and check every paper number (free)
python -m pytest eval/tests  # harness tests
```

| File | Purpose |
| --- | --- |
| `reproduce.py` | Rebuilds every paper number from the saved results and compares them with `results/PAPER_NUMBERS.md` |
| `paths.py` | Where the external repositories are (InterA11y, rampa-cli, the D5 apps); environment overrides |
| `freeze.py`, `FREEZE.json`, `freeze_params.json` | The frozen configuration: file hashes and parameters; runs are refused if a frozen file changed |
| `adapters/ag_single.py` | AccessGraph's single-page mode inside the external harnesses (D2, D3, D6) |
| `d2.py`, `d2_prerecord.py`, `d2_filter.py`, `d2_combined.py`, `d2_stats.py` | D2: runs inside InterA11y's harness, pre-recording, semantic scope, scoring with axe-core, statistics |
| `d3d6.py`, `d3d6_stats.py` | D3 and D6 with Rampa's benchmark, statistics |
| `d5.py`, `d5_apps.yaml`, `d5_summary.py` | D5: start the apps, explore, candidates, sample, judge, export, summary |
| `d5_export165.py`, `d5_review*.py`, `d5_explain.py`, `d5_site.py`, `d5_site_check.py`, `d5_site/` | D5 expert review: item selection, replay capture with screenshots and videos, plain explanations, the review website and its checks |
| `paper_values.py` | All numbers reported in the paper, from the saved results |
| `stats.py` | Wilson CI, cluster bootstrap, paired permutation, exact McNemar, Holm, Cohen's and Fleiss' κ, flip rate (seeded) |
| `cost.py`, `prices_*.yaml` | Spend ledger and budget guard for paid model calls |
| `runlog.py` | Run log (`results/run_log.csv`) and exclusions |
| `predictions.py`, `matching.py`, `scoring.py` | Case-level predictions, matching of findings to cases, metrics |
| `dev_*.py`, `ext_eval.py`, `intera11y_dev.py` | Benchmark (D1) acquisition, linking and judging |
| `mappings/` | Violation type to WCAG success criteria; mappings to the external datasets' rules |
| `patches/` | The small local patches applied to InterA11y and rampa-cli (model parameters; documented in each file) |
