# Remaining before the final release

## For Andre: add the benchmark (D1)

- [ ] Put the benchmark apps and cases under `benchmarks/` exactly as in the original repository (`benchmarks/local-spas/`, `benchmarks/registry/`, `benchmarks/dataset-manifest.json`), including the extension apps (course portal, finance portal) and their 121 cases from the `dataset-extension` branch.
- [ ] Run the checks before pushing: `python -m pytest tests` and `ACCESSGRAPH_EXTENSION_TESTS=1 python -m pytest extension/tests`.
- [ ] Push to `main` of https://github.com/NadeenAhmad/accessgraph with your own name, in one or a few commits, and describe what was added in the commit message.
- [ ] Update the benchmark numbers in `README.md` (number of apps and cases) and in `docs/benchmark.md`.
- [ ] Do not change `src/`, `eval/` or `results/`: the D1 evaluation run comes after your push.

## After the expert study (D5)

The tool's per-item D5 verdicts and the saved model answers stay **out of the public repository until the experts have finished**; otherwise a labeller could look them up. They go into the data archive afterwards:

- [ ] Download the expert labels from the review site's store, compute expert agreement (Cohen's κ) and the RQ4 numbers (precision among AccessGraph's findings by direction, NPV, shares at depth ≥ 1 and depending on a transition).
- [ ] Publish the D5 verdicts (`results/d5/verdicts.csv`), the expert labels, and the answer cache in the data archive.
- [ ] Take the review site down.

## Release

- [ ] D1 evaluation run and its results (RQ1, RQ3).
- [ ] Data archive on Zenodo (DOI) and the same files as GitHub release assets (each at most 2 GB).
- [ ] Add the DOI and the paper's citation to `README.md` and `CITATION.cff`; tag the release.
