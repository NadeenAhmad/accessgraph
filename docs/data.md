# AccessGraph: data for the paper

Recordings and review material behind the paper "Broken Promises: Detecting Semantic Accessibility Violations
Across the States and Transitions of Single-Page Applications". The code, the results tables and the logs are in
the repository https://github.com/NadeenAhmad/accessgraph; `python -m eval.reproduce` there rebuilds every number
of the paper from the repository alone. These files are needed only to inspect the recordings or to re-judge them.

## Files

| File | Size | Contents |
|---|---|---|
| `accessgraph-d5-explorations.tar.gz` | 426 MB | Real SPAs (D5): for each of the ten apps, the state graph (`graph.json`), the explorer's log with its decisions (`exploration_log.jsonl`), every recorded state (`states/<id>/`: rendered DOM, screenshot, ARIA snapshot, accessibility context, metadata) and all candidates (`candidates/candidates.jsonl`, 79,162 in total). |
| `accessgraph-d3d6-recordings.tar.gz` | 43 MB | W3C ACT test cases (D3) and Rampa's corrupted pairs (D6): AccessGraph's single-page recording, candidates and verdicts for each page. |
| `accessgraph-d5-review.tar.gz` | 68 MB | Expert review material for the 163 D5 items: per item the replayed screens (`s1.jpg`, `s2.jpg`), a short video of the action (`clip.mp4`, 98 items), the path screenshots (`step-<k>.jpg`) and `meta.json`; the item list shown to the experts (`items.json`) and the labelling sheet. |
| `SHA256SUMS` | | Checksums: `shasum -a 256 -c SHA256SUMS`. |

## Using the files

From the repository root:

```bash
mkdir -p runs/w4a-d5 runs/w4a-d3d6
tar -xzf accessgraph-d5-explorations.tar.gz
for app in d5-explorations/*; do mkdir -p runs/w4a-d5/$(basename $app) && mv $app runs/w4a-d5/$(basename $app)/explore; done
tar -xzf accessgraph-d3d6-recordings.tar.gz && mv d3d6-recordings runs/w4a-d3d6/pages
tar -xzf accessgraph-d5-review.tar.gz          # results/d5/review material, browsable as is
```

Re-judging the D5 sample with another model then needs no new exploration: `python -m eval.d5 judge` (an OpenRouter
key; see the repository's README). Paths in the files are written as `<repo>/...` and `<external>/...` (the folder of
the external repositories, see `eval/paths.py`).

## Not included, and why

- **InterA11y's datasets (D2).** The pages belong to InterA11y's authors and may not be redistributed; neither are
  AccessGraph's recordings of them. They are published by InterA11y's authors in their repository:
  [jszh/InterA11y, `datasets/` at commit 8dcf06e](https://github.com/jszh/InterA11y/tree/8dcf06e258df88a8f39a3e37ebfce060c45a1cdd/datasets)
  (expert-labelled and conformance sets, with their released baseline results in
  [`results/`](https://github.com/jszh/InterA11y/tree/8dcf06e258df88a8f39a3e37ebfce060c45a1cdd/results); paper:
  [arXiv:2610.39488](https://arxiv.org/abs/2610.39488)). `bash scripts/setup_external.sh` clones that commit, and
  `python -m eval.d2_prerecord` and `python -m eval.d2` record and judge the pages again.
- **The W3C ACT test cases and Rampa's pairs (D3, D6)** are published by the
  [W3C (ACT test cases)](https://www.w3.org/WAI/standards-guidelines/act/report/testcases) and by Rampa's author, with
  the baselines' stored results, in
  [guilhermebsantiago/rampa-cli, `bench/` at commit df32363](https://github.com/guilhermebsantiago/rampa-cli/tree/df3236322c5f3d8404172b0f65ca697c859c3e3d/bench).
  The archive holds only AccessGraph's own recordings of these pages.
- **AccessGraph's per-item D5 verdicts, the saved model answers and the expert labels.** They are added after the
  expert study ends, so that labellers cannot look up the tool's answers while labelling.
- **The benchmark (D1).** It is part of the repository.

## Licence

Our recordings, candidates and review material: CC BY 4.0. The screens show open-source applications, each under
its own licence (pinned commits in `eval/d5_apps.yaml` of the repository); W3C ACT test cases: W3C Software and
Document License; Rampa's corrupted pairs are derived from them with rampa-cli (commit `df32363`).
