# Checkout Benchmark SPA

Checkout is a clean React SPA for the standalone controlled benchmark foundation. It is semantically correct by default and can run with opt-in developer pilot seed profiles.

For case planning, clean SPA extension, and focused acquisition rules, see the [Controlled Benchmark Guide](../../../docs/benchmarks/controlled-benchmark-guide.md).

## Workflow

Products -> Cart -> Address -> Payment -> Review.

## Current Developer Fixtures

These profiles are developer smoke-test fixtures, not accepted production dataset batches.

| Profile | Seeds |
| --- | --- |
| `checkout-pilot-001` | `co-sem-001`, `co-sem-002` |

No profile, an unknown profile, and `checkout-clean-v1` activate no seeds. The dataset manifest has no accepted final batches.

`co-sem-003` is intentionally absent because the old landmark-structural pilot was excluded during standalone migration.

## Structure

| Area | Path |
| --- | --- |
| Subjects | `src/benchmark/subjects.js` |
| Seeds | `src/benchmark/seeds.js` |
| Profiles | `src/benchmark/profiles.js` |
| Effects | `src/benchmark/effects/` |
| Components | `src/components/` |
| Registry | `benchmarks/registry/benchmark-case-registry.json` |
| Runner | `scripts/benchmarks/checkout/runner.py` |
| Validator | `scripts/benchmarks/checkout/validate_batch.py` |

## Commands

From `benchmarks/local-spas/checkout-flow/`:

```powershell
npm.cmd ci
npm.cmd run build
```

From the repository root, run scaffolding tests:

```powershell
python -m pytest tests/test_checkout_benchmark_scaffolding.py -q
```

Validate seeded developer fixture batches from the repository root:

```powershell
python scripts\benchmarks\checkout\validate_batch.py --profile checkout-pilot-001
```

The validator runs static safeguards, focused acquisition, candidate generation, and seeded scoring. It does not run LLM judgment or approve dataset membership.
