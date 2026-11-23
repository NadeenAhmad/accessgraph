# Booking Scheduler Local SPA

Booking Scheduler is a deterministic React SPA used for AccessGraph browser acquisition and controlled semantic benchmark cases. With no benchmark profile active, it is the clean application baseline. Profiles opt into one seed, and generic runtime consumers apply that seed's effects without case-ID branches in components.

## Workflow And Routes

The normal booking workflow is:

```text
/services -> /schedule -> /details -> /review -> /confirmation
```

`/help` is a separate directly reachable information page. Route guards and in-memory state preserve the selected service, appointment, and customer details through the workflow. Deterministic fixtures use June 16 and June 18, 2026 with fixed available and unavailable times.

## Benchmark Architecture

| Concept | Path | Responsibility |
| --- | --- | --- |
| Subjects | `src/benchmark/subjects.js` | Stable semantic target IDs and test IDs. |
| Seeds | `src/benchmark/seeds.js` | Stable `bs-sem-*` seed IDs. |
| Profiles | `src/benchmark/profiles.js` | Clean and independent single-seed `booking-bs-sem-*` profiles. |
| Effects | `src/benchmark/effects.js` | Generic effect resolution by subject and property. |
| Consumers | `src/App.jsx`, `src/components/` | Apply resolved effects while retaining clean fallback behavior. |
| Focused runner | `scripts/benchmarks/booking/runner.py` | Reaches Services, Schedule, Details, Review, Confirmation, or Help through valid interactions. |
| Registry | `benchmarks/registry/families/*.json` | Offline expected evidence and recovery matching. |

The focused runner activates a profile before the SPA loads by setting `window.__ACCESSGRAPH_BOOKING_PROFILE__`. `booking-clean` activates no seeds. Implemented case profiles contain exactly one seed. This profile global is test/runner configuration and is not written into captured semantic evidence.

Booking differs from Checkout in two practical ways:

- Booking deep states depend on workflow state and are reached by the reusable Booking runner rather than treated as autonomous crawl roots.
- All 27 implemented Booking cases can be launched from the Benchmark Explorer. The launcher injects the selected profile into an isolated browser context and uses the reusable runner to prepare the registry-declared route.

## Run Locally

From this directory:

```powershell
npm.cmd ci
npm.cmd run dev
```

Build the standalone SPA with:

```powershell
npm.cmd run build
```

Installed dependencies and build output are ignored by Git.

## Tests

From the repository root:

```powershell
python -m pytest -q tests\test_booking_scheduler_baseline.py
python -m pytest -q tests\test_booking_effect_consumption.py
python -m pytest -q tests\test_booking_benchmark_scaffolding.py
python -m pytest -q tests\test_booking_accessgraph_integration.py
```

The integration suite compares clean and seeded browser artifacts, checks profile isolation and case-specific semantics, generates candidates, and verifies deterministic recovery. It does not call an LLM.

See [Implementing a benchmark case](../../../docs/benchmarks/implementing-benchmark-cases.md) before extending the catalogue.
