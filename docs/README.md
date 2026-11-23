# AccessGraph Documentation

Start with these guides:

- [Evaluation protocol](evaluation.md) - datasets, configuration, commands and costs of the paper's experiments.
- [Data](data.md) - the data archive, and what is not included and where its owners publish it.
- [Benchmark (D1)](benchmark.md) - the controlled benchmark.

1. [Setup and local workflow](getting-started.md) - fresh-clone installation, local crawl, candidates, fake judgment, reports, and troubleshooting.
2. [Project context](architecture/accessgraph-project-context.md) - research objective and stage boundaries.
3. [Full crawl flow](architecture/full-crawl-flow.md) - acquisition behavior and saved artifacts.
4. [Implementing a benchmark case](benchmarks/implementing-benchmark-cases.md) - subjects, effects, seeds, profiles, registry evidence, acquisition, recovery, and tests.
5. [Controlled benchmark guide](benchmarks/controlled-benchmark-guide.md) - planning, validation, review, and acceptance lifecycle.

## Reference

- [Application configuration](architecture/app-config.md)
- [Run metadata](architecture/run-metadata.md)
- [Current semantic taxonomy](taxonomy/current-semantic-taxonomy.md)
- [Semantic candidate builder](candidates/semantic-candidate-builder.md)
- [Model judgment reference](confirmation/confirmation-reference.md)
- [Developer report reference](reporting/developer-report-reference.md)
- [Checkout benchmark SPA](../benchmarks/local-spas/checkout-flow/README.md)
- [Booking Scheduler SPA](../benchmarks/local-spas/booking-scheduler/README.md)

The current development tracker is separate from the submitted thesis's frozen 30-case evaluation and from accepted dataset membership in `benchmarks/dataset-manifest.json`.
