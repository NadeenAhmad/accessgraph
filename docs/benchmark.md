# Benchmark (D1)

Our benchmark pairs each seeded semantic violation with matched negatives that measure false alarms: the unmodified
application, a version with correctly updated metadata or a correctly behaving control, and decoys whose metadata
rightly stays the same. It is used for RQ1 (transition-dependent violations against single-state methods) and RQ3
(LLM-guided against breadth-first exploration).

**Status: the cases are being added** (see `../TODO.md`). Numbers to fill in when they are: applications [K],
cases [N] (seeded and matched negatives), transition-dependent cases, and the label agreement.

How a case is built and validated: [implementing benchmark cases](benchmarks/implementing-benchmark-cases.md) and the
[controlled benchmark guide](benchmarks/controlled-benchmark-guide.md). The apps live in `benchmarks/local-spas/`, the
expected evidence per case in `benchmarks/registry/`; `python scripts/benchmarks/serve_benchmark_explorer.py` opens
any implemented case in the browser.
