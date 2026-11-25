# Evaluation protocol

How the paper's experiments are set up and how to run them. Every number in the paper can be rebuilt for free with
`python -m eval.reproduce` (see the README); this page is for re-running the experiments themselves.

## Configuration

- **AccessGraph** runs in the configuration frozen for the paper: `eval/FREEZE.json` lists every file that decides
  its output with its hash (freeze hash `1965a886…`), `eval/freeze_params.json` the parameters. Runs are refused if a
  frozen file changed (`python -m eval.freeze --verify`).
- **Model:** GPT-6 Luna (`openai/gpt-6-luna`) through OpenRouter for the judge and the explorer; no temperature is
  sent (the model does not accept it). Set `OPENROUTER_API_KEY`.
- **Judge:** one call per candidate on the recorded evidence; history-aware context for the seven transition-capable
  types; an uncertain verdict gets follow-up evidence (the link's destination, the element pressed on a fresh load of
  its page on an allowed host, or whether an image loaded) and is re-judged three times (majority).
- **Answers are cached** (`results/cache/`, in the data archive): re-running with unchanged prompts is free.
- **Budget guard:** `eval/cost.py` charges every paid call to `results/cost_ledger.json` and stops at the set limits.
- **External repositories** (not redistributed): `bash scripts/setup_external.sh` clones InterA11y and rampa-cli at
  the commits used; `--d5-apps` also clones the ten real SPAs. Locations: `eval/paths.py`.

## Datasets

| | Dataset | Cases | Used for |
|---|---|---|---|
| D1 | Our benchmark: seeded violations with matched negatives | to follow | RQ1, RQ3 |
| D2 | InterA11y's datasets, as released: every case of 1.1.1, 2.4.4, 3.3.1 | 129 expert-labelled (69 violations), 394 conformance (151) | RQ2 |
| D3 | W3C ACT test cases of 7 rules | 88 (30 failed, 33 passed, 25 inapplicable) | RQ2 |
| D5 | Ten open-source SPAs in four frameworks, run locally at pinned commits | 600 judged candidates; 163 expert items | RQ4 |
| D6 | Rampa's corrupted pairs (intact page and one injected fault) | 51 pairs | RQ2 |

## Running the experiments

| Step | Command | Time | Cost |
|---|---|---|---|
| D2: record the pages (optional, makes the runs fast) | `python -m eval.d2_prerecord --dataset expert` and `--dataset conformance` | 1–3 h | cents |
| D2: three runs | `python -m eval.d2 --run 1 --dataset all --full --tag mine` (then `--run 2`, `--run 3`) | 1–2 h | about $1 per run |
| D2: score with axe-core, statistics | `python -m eval.d2_combined --tag mine`; `python -m eval.d2_stats --tag mine --full --with-axe` | minutes | free |
| D3 and D6 | `python -m eval.d3d6 --tag mine`; `python -m eval.d3d6_stats --tag mine` | about 1 h | about $0.40 |
| D5: explore the ten apps | `python -m eval.d5 explore` (each app is started locally from `eval/d5_apps.yaml`) | several hours | about $1 |
| D5: candidates, sample, judge | `python -m eval.d5 build`, `sample`, `judge` | about 1 h | about $0.60 |
| D5: summary | `python -m eval.d5_summary` | minutes | free |
| All paper numbers | `python -m eval.paper_values --tag mine` | seconds | free |

Every run writes a row to `results/run_log.csv`. Single-page mode (D2, D3, D6): AccessGraph starts at the case's page
and explores at most 8 states (depth 2, 6 actions per state), the case's element first, then judges as usual. D2's
pages are saved copies; where a saved page's own scripts fail offline and erase its content, AccessGraph checks the
page as it was saved (without its scripts) and loads lazy images at once (`eval/adapters/ag_single.py`).

## Baselines

The baselines' results are the ones their authors released or stored, scored on the same cases:

- **D2:** InterA11y's released predictions (commit `8dcf06e`): InterA11y, López-Gil & Pereira (conformance set only),
  AccessGuru, GenA11y, browser-use 0.12.6 and AgentLab 0.4.2 (expert set only), and the rule checkers in InterA11y's
  setup (axe-core 4.12.1, Alfa 0.117.0, IBM Equal Access 4.0.26, QualWeb core 0.8.11, and others), with the same model
  wherever a baseline uses one. Scored with InterA11y's own scorer; flagged means a definite verdict.
- **D3, D6:** the stored results of Rampa's benchmark (rampa-cli `df32363`; results of 11–12 Oct 2026): Rampa with
  Gemma (`gemma4:12b` on Ollama 0.40.2), Rampa probes, and the rule checkers in Rampa's setup (axe-core 4.14.0, Alfa
  0.119.0, IBM Equal Access 4.0.34, Pa11y 10.0.0, QualWeb core 0.9.5), read with definite findings only and with
  "needs review" findings added.

## Statistics

95% confidence intervals of differences by cluster bootstrap (pages for D2, ACT rules for D3, pairs for D6; 10,000
replicates, seeded); paired permutation tests (10,000); exact McNemar for D6; p-values Holm-adjusted within each family
(D2: three comparisons; D3/D6: four). Pre-registered wording: "outperforms" only if the adjusted p < .05 and the CI
excludes 0, otherwise "comparable". Repeatability on D2: Fleiss' κ and flip rate over three runs. Code: `eval/stats.py`.

## D5: real SPAs and the expert review

- **Exploration:** each app once, with the paper configuration (at most 100 states, depth 5, 5 actions per state,
  plus outcome completion: 3 more controls per state, at most 150 actions and 50 extra states); forms and destructive
  actions only on the local app.
- **Sample:** all candidates are generated; a stratified random sample of 600 (type × depth 0 vs ≥ 1 × direction,
  seed 20261116) is judged; weights scale results to all 79,162 candidates.
- **Expert items:** 163, all 63 items AccessGraph judged violations plus 100 random others (`eval/d5_export165.py`),
  with sampling weights. One labeller labels all of them; three further labellers each label the same
  30 items (18 that AccessGraph judged violations, 12 others; a seeded subset, `eval/d5_shared30.py`). Agreement on
  the 30 by Fleiss' κ among the four and Cohen's κ between the main labeller and each of the others; disagreements
  are resolved by discussion. All labellers answer before AccessGraph's verdict is shown.
- **Review package per item** (`eval/d5_review.py`): the item's recorded path is replayed in the running app, with
  screenshots of every step, the screen before and after the action with the element outlined, and a short video of
  the action. Where the app cannot show the recorded content again (two apps generate random data on every start),
  the screen AccessGraph recorded is shown instead.
- **Two steps** (review site `eval/d5_site/`): the expert first answers without seeing AccessGraph's verdict; then the
  verdict and a one-sentence plain version of its reason (`eval/d5_explain.py`) are shown, and the expert says
  whether they agree. The first answer is locked once the verdict is shown, enforced by the server.
- **Metrics** from the first answers: precision among AccessGraph's findings (overall and by direction), negative
  predictive value, and the shares of confirmed violations at depth ≥ 1 and depending on a transition.
