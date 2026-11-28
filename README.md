# AccessGraph

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10–3.12](https://img.shields.io/badge/Python-3.10%E2%80%933.12-blue.svg)](requirements-lock.txt)
[![Release](https://img.shields.io/github/v/release/NadeenAhmad/accessgraph?include_prereleases&label=Release)](https://github.com/NadeenAhmad/accessgraph/releases)
[![WCAG 2.2](https://img.shields.io/badge/WCAG-2.2-purple.svg)](https://www.w3.org/TR/WCAG22/)
[![Data DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24484345.svg)](https://doi.org/10.5281/zenodo.24484345)

AccessGraph detects **semantic Web accessibility violations across the states and transitions of single-page
applications (SPAs)**: page titles, headings, landmark names and labels that no longer describe what is on screen,
and buttons, links and widgets whose names promise something other than what they do. An LLM-guided explorer works
through the application within fixed bounds and records every state and transition. A judge then decides each
candidate violation from this record, using the transition as evidence where needed, so every verdict is
reproducible and traceable to the screens an auditor needs to inspect.

This repository accompanies the paper *Broken Promises: Detecting Semantic Accessibility Violations Across the
States and Transitions of Single-Page Applications*. It contains the tool, the evaluation code, all results and logs,
and the instructions to reproduce every number in the paper.

![Two violations in an online shop that only a transition reveals. Judged one screen at a time, every screen looks fine. Across transitions, AccessGraph finds an outdated dialog heading (the user pressed Remove next to Drift Parka, but the screen reader announces Remove Storm Shell) and a misleading skip link (Skip to main content loads the home page).](docs/figures/accessgraph-example.png)

<details>
<summary>Full description of the figure</summary>

The figure has three parts: a row of four screenshots, two recorded transitions below them, and two explanation
boxes at the bottom.

**Screenshots.** The four screenshots show an online shop in four states, labeled A, B, C and D from left to right.
Under each screenshot, a box lists what a screen reader announces in that state.

- *State A* has the tab title "Your bag – Shop" and the address shop.example/bag. Below the heading "Your bag" are
  two jackets: Storm Shell at €89 and Drift Parka at €129, each with a "Remove" button, followed by a total of €218
  with a "Checkout" button. The "Remove" button next to Drift Parka is outlined, marking the action the user takes.
  The screen reader announces "Remove Drift Parka, button".
- *State B* is the same bag, shaded, with a dialog. Its visible heading reads "Remove this item?", followed by the
  buttons "Cancel" and "Remove". The heading is marked 1: the screen reader announces "Remove Storm Shell from your
  bag?" while the screen shows "Remove this item?".
- *State C* is the product page of Storm Shell (tab title "Storm Shell – Shop", address shop.example/p/storm-shell).
  A focused link, "Skip to main content", is marked 2; the screen reader announces "Skip to main content, link".
- *State D* has the tab title "Home – Shop" and the address shop.example/#main. It shows the shop's home page with a
  "New season" banner and tiles for jackets, boots and bags.

**Transitions.** An arrow from state A to state B is labeled "press Remove next to Drift Parka" and carries the badge
"1 Outdated heading". An arrow from state C to state D is labeled "press Skip to main content" and carries the badge
"2 Misleading link".

**Explanation boxes.** "One screen at a time": judged alone, every screen looks fine; in B, the dialog names Storm
Shell, which is in the bag, and in C, the skip link points to #main, which exists; verdict: no violation, both
problems are missed. "Across transitions (AccessGraph)": 1, from A to B, the user pressed "Remove" next to Drift
Parka, but the dialog asks about Storm Shell, because its hidden heading was written for the first item in the bag
and never updated; 2, from C to D, "Skip to main content" loaded the shop's home page instead of moving to the
product, and the keyboard user loses their place.
</details>

## How it works

![The AccessGraph pipeline in five stages. Exploration against the live application: 1 Explore (LLM policy within fixed bounds) and 2 Record (states and change records). Judgment on the recorded evidence: 3 Propose candidates, 4 Judge (one LLM call per candidate), 5 Report.](docs/figures/accessgraph-pipeline.png)

<details>
<summary>Full description of the figure</summary>

Five numbered stages from left to right, applied to the shop example above. A strip labeled "Live application (the
SPA under test)" runs along the bottom.

- **Exploration.** *1 Explore* (LLM): a breadth-first frontier with fixed bounds; an LLM policy picks the actions to
  try, for example "Remove", and fills forms with valid and invalid values; a second pass records what untried
  controls do. *2 Record*: states A, B, C, D with change records (Δ) on the transitions A→B and C→D; the change record
  of A→B ("evidence only") shows the trigger, the button "Remove Drift Parka", and the new heading "Remove Storm Shell
  from your bag?"; per state, the DOM, a screenshot and the accessibility context are saved.
- **Judgment on the recorded evidence.** *3 Propose*: rules turn the record into candidates for the judge, for
  example the dialog heading in B with the action that opened it, and the link "Skip to main content" in C with its
  outcome C→D. *4 Judge* (LLM): one call per candidate; the dialog heading with state B alone is "no violation", with
  B and the change record "violation"; an uncertain verdict is re-judged with history, then with look-ups and three
  votes. *5 Report*: the outdated dialog heading in B, linked to the transition A→B, both screenshots and the DOM;
  re-judging with another model needs no new exploration.

A solid arrow labeled "states observed after each action" leads from the live application to Explore; a dashed arrow
labeled "read-only look-ups, uncertain verdicts only" leads to Judge. No other stage touches the live application.
</details>

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

Recordings that are too large for Git are in the data archive on Zenodo, [doi:10.5281/zenodo.24484345](https://doi.org/10.5281/zenodo.24484345) (always the
latest version; the version used for the paper is [doi:10.5281/zenodo.24484346](https://doi.org/10.5281/zenodo.24484346)), and the same files are
[GitHub release assets](https://github.com/NadeenAhmad/accessgraph/releases): the explorations of the ten real SPAs,
the recordings of the W3C ACT and Rampa pages, and the expert review material. What each file holds, and what is not
included and where its owners publish it (InterA11y's datasets, the W3C ACT test cases, Rampa's pairs): [docs/data.md](docs/data.md).

## Expert review of the real SPAs

The ten real SPAs have no ground truth, so labellers with a background in Web accessibility research label a
stratified sample of AccessGraph's findings (161 items) on a review website: https://a11y-review-4u8202.netlify.app
(answering needs a personal link). One labeller labels all items and three others label the same 29, for agreement.
Each item shows the screens before and after the user's action, replayed in the running app, with a short video.
The labeller first answers without seeing AccessGraph's verdict; then the verdict is shown and they say whether they
agree. Protocol: [docs/evaluation.md](docs/evaluation.md#d5-real-spas-and-the-expert-review). AccessGraph's per-item
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

## Development history

AccessGraph was first developed in [andrekn-do/accessgraph-semantic-a11y](https://github.com/andrekn-do/accessgraph-semantic-a11y),
which holds the full development history, including the earlier thesis version of the tool and of the benchmark.
This repository is the cleaned release for the paper: the final version of the tool, its evaluation, results and
logs.

## Status

Still to come: the benchmark (D1) and its results, and the expert labels for the real SPAs. See
[TODO.md](TODO.md); contributors adding the benchmark follow its instructions.

## License

Code: [MIT](LICENSE). Data in the archive: CC BY 4.0 (the recorded applications keep their own licences; see
[docs/data.md](docs/data.md)).
