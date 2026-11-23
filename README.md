# AccessGraph

AccessGraph detects **semantic Web accessibility violations across the states and transitions of single-page
applications (SPAs)**: page titles, headings, landmark names and labels that no longer describe what is on screen,
and buttons, links and widgets whose names promise something other than what they do. An LLM-guided explorer works
through the application within fixed bounds and records every state and transition. A judge then decides each
candidate violation from this record, using the transition as evidence where needed, so every verdict is
reproducible and traceable to the screens an auditor needs to inspect.

This repository accompanies the paper *Broken Promises: Detecting Semantic Accessibility Violations Across the
States and Transitions of Single-Page Applications* (W4A 2027). It contains the tool, the evaluation code, all
results and logs, and the instructions to reproduce every number in the paper.

## Quick start (free, about 10 minutes)

Requirements: Python 3.10–3.12, Node.js ≥ 20.19, Git. macOS and Linux shown; Windows commands are in
[docs/getting-started.md](docs/getting-started.md).

```bash
git clone https://github.com/NadeenAhmad/accessgraph.git && cd accessgraph
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt -r eval/requirements.txt   # or, for the paper's exact versions: -r requirements-lock.txt
python -m playwright install chromium

# start the demo shop (a local SPA) in a second terminal
npm ci --prefix benchmarks/local-spas/checkout-flow
npm run dev --prefix benchmarks/local-spas/checkout-flow -- --host 127.0.0.1 --port 4173

# explore it, propose candidates, judge them with a placeholder judge, write a report (no API key, no cost)
python scripts/run_accessgraph.py --url http://127.0.0.1:4173/ --out runs/demo --fake
```

The report is in `runs/demo/reports/`. The individual stages (`crawl`, `candidates`, `judge`, `report`,
`check-page`) are also available through `python accessgraph.py --help`; see [docs/getting-started.md](docs/getting-started.md).

## Run AccessGraph on your own app

```bash
export OPENROUTER_API_KEY=...        # judge and explorer: openai/gpt-6-luna via OpenRouter
python scripts/run_accessgraph.py --url http://127.0.0.1:5173/ --out runs/my-app
```

This uses exactly the configuration of the paper (`eval/freeze_params.json`): breadth-first exploration with an LLM
action policy (at most 100 states, depth 5, 5 actions per state, plus a pass that tries the remaining controls'
outcomes), and the judge with history-aware context; uncertain verdicts get follow-up evidence and are re-judged
three times. A typical app costs well under $1. **Run it on a local copy of your app:** forms are filled and
destructive actions (delete, remove, buy) are tried only on the hosts in `--allow-hosts` (default `127.0.0.1` and
`localhost`), and every write to another host is blocked. `--limit N` judges only the first N candidates.

## Reproduce the paper

Every number in the paper can be rebuilt from this repository, for free, in a few minutes:

```bash
bash scripts/setup_external.sh     # clones InterA11y (8dcf06e) and rampa-cli (df32363): labels and baseline results
python -m eval.reproduce           # rescoring + statistics; compares all 58 numbers with results/PAPER_NUMBERS.md
```

Re-running the experiments themselves needs an OpenRouter key, the apps, and time; the commands are in
[docs/evaluation.md](docs/evaluation.md), with the cost of each step. Model answers are cached, so a repeated run
with unchanged prompts costs nothing.

## Results at a glance

| Dataset | AccessGraph | Strongest baseline (same model) | Result |
|---|---|---|---|
| InterA11y's conformance set, 394 cases (with axe-core) | F1 0.910 | InterA11y 0.826, López-Gil & Pereira 0.829 | outperforms both (adjusted p ≤ .001) |
| InterA11y's expert-labelled pages, 129 cases (with axe-core) | F1 0.907 | InterA11y 0.920 | comparable (adjusted p = .61) |
| W3C ACT test cases, 7 rules | F1 0.97 | Rampa + Gemma 0.67 | outperforms (adjusted p = .002) |
| Rampa's corrupted pairs, 51 | 50 told apart | Rampa + Gemma 36 | outperforms (adjusted p = .002) |
| 10 real open-source SPAs | 933 states, 79,162 candidates; 600 judged | | expert labels pending (see below) |

Full tables, confidence intervals and per-run results: [results/README.md](results/README.md).

## Data

Recordings that are too large for Git are in the data archive (Zenodo, DOI to follow, and the same files as
[GitHub release assets](https://github.com/NadeenAhmad/accessgraph/releases)): the explorations of the ten real SPAs,
the recordings of the W3C ACT and Rampa pages, and the expert review material. What each file holds, and what is not
included and where its owners publish it (InterA11y's datasets, the W3C ACT test cases, Rampa's pairs): [docs/data.md](docs/data.md).

## Expert review of the real SPAs

The ten real SPAs have no ground truth, so accessibility experts label a stratified sample of AccessGraph's findings
(163 items) on a review website: https://a11y-review-4u8202.netlify.app (answering needs a personal link). Each item
shows the screens before and after the user's action, replayed in the running app, with a short video. The expert
first answers without seeing AccessGraph's verdict; then the verdict is shown and they say whether they agree.
Protocol: [docs/evaluation.md](docs/evaluation.md#d5-real-spas-and-the-expert-review). AccessGraph's per-item
verdicts on these items are published after the review ends, so that reviewers cannot look them up.

## Repository layout

| Path | Contents |
|---|---|
| `src/` | AccessGraph: exploration and recording (`crawler/`), candidates, judge and reports (`analysis/`) |
| `scripts/` | `run_accessgraph.py` (paper configuration on any app), `setup_external.sh`, benchmark tools |
| `eval/` | Evaluation code for every dataset, statistics, the frozen configuration (`FREEZE.json`, `freeze_params.json`), the review site (`d5_site/`) |
| `results/` | Final results, tables and statistics per dataset; `PAPER_NUMBERS.md` lists every number in the paper |
| `logs/` | Run log and cost ledger of all model calls |
| `benchmarks/` | The benchmark SPAs and cases (D1) |
| `docs/` | Setup, architecture, taxonomy, benchmark, evaluation protocol and data description |
| `tests/`, `eval/tests/` | Tests of the tool and of the evaluation harness |

## Status

Still to come: the benchmark (D1) and its results, the expert labels for the real SPAs, and the archive DOI. See
[TODO.md](TODO.md); contributors adding the benchmark follow its instructions.



## License

Code: [MIT](LICENSE). Data in the archive: CC BY 4.0 (the recorded applications keep their own licences; see
[docs/data.md](docs/data.md)).
