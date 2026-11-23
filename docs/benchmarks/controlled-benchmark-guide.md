# Controlled Benchmark Guide

This guide describes how controlled benchmark cases are planned, implemented, validated, reviewed, and accepted in the standalone AccessGraph repository.

Design the semantic case first. Implement and validate it second. A tracker case can be marked `accepted` after researcher review; it counts toward the final dataset only after its batch is accepted in the manifest.

## Current Benchmark Status

The current development tracker contains 166 designs across Checkout and Booking Scheduler:

| Scope | Implemented | Planned | Blocked | Rejected | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Checkout | 108 | 2 | 3 | 2 | 115 |
| Booking Scheduler | 27 | 24 | 0 | 0 | 51 |
| **Current development corpus** | **135** | **26** | **3** | **2** | **166** |

The 31 non-implemented designs remain in the tracker for traceability. This is not the accepted dataset; `benchmarks/dataset-manifest.json` currently has no accepted batches.

Among the 135 implemented cases, difficulty labels are 28 easy and 107 hard, and evidence-state labels are 46 initial and 89 post-interaction. All 15 canonical taxonomy types have candidate-generation support and at least one implemented controlled benchmark case. This family-level representation is not exhaustive semantic accessibility coverage and does not establish precision on natural web applications.

Six implemented cases materially require graph context: `co-sem-027`, `co-sem-089`, `co-sem-102`, `co-sem-103`, `co-sem-104`, and `bs-sem-115`. Post-interaction describes how a state is acquired; graph-context dependence describes what evidence is required for reasoning. The two labels are not equivalent.

`co-sem-139` is a hard, initial-state `video-captions-inaccurate` case on Products and does not require graph context. Its seeded caption says the user moves to Cart after payment, while the authoritative narration says Review. The reference is a supervisor-provided exact narration transcript without timestamps. One controlled video-caption case provides family representation, not broad evidence about video accessibility performance. Confirm redistribution rights for the supervisor-provided MP4 before public publication.

`benchmarks/case-tracker.csv` is the authoritative source for current benchmark design and case status. Accepted dataset membership, when used, is represented separately by `benchmarks/dataset-manifest.json`.

The submitted thesis evaluation used a frozen 30-case benchmark: 10 Checkout, 11 Booking, and 9 Task Manager cases. The current development counts above should not be read as the submitted thesis dataset size. The Checkout expansion is refrozen at 108 implemented cases; Booking contains both implemented and planned post-thesis designs. Any further scope change requires an explicit research decision.

## Quick Workflow

```text
brainstorm case
  -> researcher approves
  -> add tracker row as planned
  -> implement
  -> capture and validate
  -> inspect technical result
  -> set tracker row to implemented
  -> researcher review
  -> accept / revise / reject
```

The researcher approves every dataset case. Tools may assist with repository inspection, implementation, registry entries, validation, and debugging, but they do not decide dataset membership.

## Plan A Case

Before implementation, answer:

- What violation type is this?
- What is the correct baseline?
- What exactly changes in the seeded version?
- Why is this case meaningfully different from existing cases?
- Which app naturally fits it?
- Which UI subject/state contains it?
- What interaction path reaches it?
- What `pattern` describes it?

Use only violation types currently in scope in `docs/taxonomy/current-semantic-taxonomy.md`.

Design cases as clear semantic contradictions with valid HTML/ARIA, observable supporting context, and one primary semantic issue. Avoid borderline cases unless the researcher explicitly chooses them.

Use the `pattern` field to avoid artificial dataset inflation. If two cases differ only in wording/content while the semantic mechanism, UI role, interaction/state, and mutation pattern are effectively the same, treat them as near-duplicates. The researcher makes the final diversity decision.

## Record The Planned Case

Use `benchmarks/case-tracker.csv`. A case enters the tracker only when the researcher says to implement it.

Tracker columns:

| Column | Use |
| --- | --- |
| `case_id` | Case/seed ID, such as `co-sem-###`. |
| `violation_type` | One of the current in-scope semantic candidate types. |
| `app` | Natural application home for the case. |
| `short_description` | One short sentence describing the scenario. |
| `pattern` | Reusable pattern label for duplicate review. |
| `tier` | `easy` or `hard` semantic difficulty for review and later slicing. |
| `baseline` | Correct behavior with no seed active. |
| `mutation` | Intended seeded semantic fault. |
| `why_unambiguous` | Short reason the seeded contradiction has clear ground truth, not a borderline interpretation. |
| `interaction_path` | User actions or state needed to observe the case, such as `Products page (initial state)`. |
| `evidence_state` | `initial` if the violating evidence is present without interaction, or `post_interaction` if user action is needed to expose it. |
| `batch_id` | Primary acquisition batch/profile, when known. |
| `status` | `planned`, `implemented`, `accepted`, `rejected`, or `blocked`. |
| `notes` | Short blocker or review notes only. |

`evidence_state` describes where the violating state is exposed; it does not by itself mean graph context is required for judgment.

Status flow is `planned -> implemented -> accepted`; side states are `blocked` and `rejected`. `planned` means the design exists but implementation or technical validation is incomplete. `implemented` means the executable case exists, the intended state/evidence/candidate have been technically validated, and deterministic recovery passes. `accepted` means researcher review has approved the case for inclusion through the dataset process. Candidate recovery is part of technical validation before `implemented`, not a separate tracker status.

`case-tracker.csv` is the repository planning and progress record. It may be imported into a shared spreadsheet for supervisor review; spreadsheet filters and comments are a collaboration view, while implementation ground truth stays in the registry and accepted dataset membership stays in the manifest.

Assign a case/seed ID when the tracker row first enters `planned`. Once allocated, do not renumber it. Gaps are acceptable.

- Checkout: `co-sem-###`
- Booking: `bs-sem-###`
- Task Manager: `tm-sem-###`

Existing Checkout developer-fixture IDs remain reserved and are not reused; real dataset case allocation begins at `co-sem-006`. Human-facing dataset ordinals may differ from the stable repository ID.

Tracker = planning, progress, diversity, and weekly memory. Registry = implemented evaluation ground truth. Manifest = accepted batch membership.

## Implement The Case

For the full implementation, evidence, recovery, and review procedure, use [Implementing Benchmark Cases](implementing-benchmark-cases.md).

For an existing UI surface:

1. identify or add the benchmark subject;
2. add the seed ID;
3. implement the explicit effect/mutation;
4. add profile membership;
5. add the registry expectation;
6. update the runner only if a real new state must be captured.

Common paths:

| Area | Path |
| --- | --- |
| Checkout subjects | `benchmarks/local-spas/checkout-flow/src/benchmark/subjects.js` |
| Checkout seeds | `benchmarks/local-spas/checkout-flow/src/benchmark/seeds.js` |
| Checkout profiles | `benchmarks/local-spas/checkout-flow/src/benchmark/profiles.js` |
| Checkout effects | `benchmarks/local-spas/checkout-flow/src/benchmark/effects/` |
| Checkout components | `benchmarks/local-spas/checkout-flow/src/components/` |
| Booking subjects | `benchmarks/local-spas/booking-scheduler/src/benchmark/subjects.js` |
| Booking seeds/profiles/effects | `benchmarks/local-spas/booking-scheduler/src/benchmark/` |
| Booking components | `benchmarks/local-spas/booking-scheduler/src/components/` |
| Registry families | `benchmarks/registry/families/<violation-type>.json` |
| Registry manifest | `benchmarks/registry/benchmark-case-registry.json` |
| Checkout runner | `scripts/benchmarks/checkout/runner.py` |

Reuse existing subjects and test IDs when they fit the case. Do not use seed IDs, profile IDs, violation names, or ground-truth labels as DOM/test identifiers. No seed/profile metadata should leak into captured DOM or evidence.

When a meaningful case needs a new surface, add normal application functionality first, make sure it is semantically correct with no seed active, then add subject identity, seed effects, focused state capture, and validation. The feature should make sense even if no benchmark seed existed. Do not add arbitrary UI solely so an AccessGraph candidate heuristic can trigger.

For simple mutations, the baseline component owns the correct semantics and a page/component-scoped effect resolver supplies the explicit seeded override. For stateful or interaction-dependent cases, keep normal workflow/state in the component or `App.jsx`; benchmark code should introduce only the semantic fault. Use explicit seed branches, not a generic mutation DSL.

## Capture The Required State

Every accepted dataset case needs a deterministic focused acquisition path to the state containing the seeded behavior.

```text
Cart -> Address -> submit invalid form -> validation state
```

Use the runner to perform real application actions needed to reproduce that state. Do not make it search for a known violation, expected evidence, or expected candidate.

| ID | Meaning |
| --- | --- |
| `state_0003` | Stored artifact ID generated for one run. |
| `CO-S006` | Stable Checkout benchmark state ID. |

Autonomous crawler reachability is evaluated separately. The crawler does not need to discover every dataset case for that case to be accepted. Later evaluation should distinguish state not reached, candidate not generated, and candidate generated but not judged as the intended violation.

## Validate A Batch

From the repository root:

```powershell
python scripts\benchmarks\checkout\validate_batch.py --profile <profile>
```

For implemented Checkout dataset cases, the profile convention is:

```text
co-sem-NNN -> checkout-co-sem-NNN
```

For example, tracker case `co-sem-052` runs as profile `checkout-co-sem-052`:

```powershell
python scripts\benchmarks\checkout\validate_batch.py --profile checkout-co-sem-052
```

This is the preferred single-case reviewer entry point. It runs static safeguards, builds and launches the Checkout SPA through focused acquisition, generates semantic candidates, runs deterministic seeded recovery, and prints the generated run directory. It does not require a separately running SPA process, does not call an LLM, and does not approve dataset membership. Use `--skip-build` only when the current Checkout `dist/` build already exists and you intentionally want to reuse it.

## Explore Cases Visually

Start the local AccessGraph Benchmark SPA Explorer from the repository root:

```powershell
python scripts\benchmarks\serve_benchmark_explorer.py
```

The Benchmark SPA Explorer opens a local catalogue of all 166 tracked designs and supports search and filters. It can launch all 135 implemented cases in a separate headed browser: 108 Checkout variants and 27 Booking Scheduler variants. Booking cases are prepared at their registry-declared route through the reusable workflow runner, including Services, Schedule, Details, Review, Confirmation, and Help. Planned, blocked, and rejected designs are non-launchable. Two executable historical pilot configurations, `co-sem-001` and `co-sem-002`, remain intentionally outside the tracker catalogue.

Select a case and choose **Open Variant**. The case detail shows the manual interaction path; some post-interaction faults still require that visible action after the route is prepared. Choose **Stop** to close the active browser and SPA process. Opening another case first stops the current session so its profile and process cannot leak into the replacement. Press Ctrl+C in the terminal running the Explorer server to stop the Explorer itself.

The Benchmark SPA Explorer is for manual review only. It does not capture states, generate candidates, run seeded recovery, call an LLM, edit tracker rows, or approve dataset membership. Use Checkout `validate_batch.py` for Checkout deterministic validation; Booking cases are exercised by the Booking runner and focused integration tests.

## Inspect A Case Interactively

For implemented Checkout cases, open a headed browser with the selected variant active:

```powershell
python scripts\benchmarks\inspect_case.py co-sem-052
```

The CLI reads tracker metadata, resolves the executable registry profile, builds and starts the Checkout preview, injects the profile before the SPA loads, and prints the case summary and interaction path. Follow the printed interaction path manually for `post_interaction` cases. Press Ctrl+C in the terminal to close the browser and stop the preview server.

This is for manual review only. It does not capture states, generate candidates, run seeded recovery, call an LLM, or approve dataset membership. Use `validate_batch.py` for deterministic technical validation.

Fresh local setup needs the Python dependencies, the Checkout SPA dependencies, and a Playwright Chromium browser:

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
cd benchmarks\local-spas\checkout-flow
npm.cmd ci
cd ..\..\..
```

The validator writes runs under:

```text
runs/benchmark/checkout_flow/<profile-slug>/run_<timestamp>/
```

For `checkout-co-sem-052`, the profile slug is `checkout_co_sem_052`. Use the `Run:` line printed by the validator, or the newest `run_*` folder under that profile slug, instead of hardcoding a timestamp.

Useful artifacts in a generated run include:

| Artifact | Use |
| --- | --- |
| `run_metadata.json` | Stable benchmark state IDs, routes, focused state names, and state count. |
| `graph.json`, `transitions.json` | Captured focused state graph and transitions. |
| `states/<state>/metadata.json` | Route, title, benchmark state ID, screenshot metadata, and capture notes for one saved state. |
| `states/<state>/screenshot.png` | Visual UI context for the saved state. |
| `states/<state>/dom.html` | Rendered DOM snapshot. |
| `states/<state>/accessibility_context.json` | Neutral extracted evidence such as landmarks, links, buttons, headings, language samples, and relationships. |
| `candidates/manifest.json` and `candidates/by_type/<type>.jsonl` | Candidate-generation counts and type-specific candidate records. |
| `evaluation/seeded_recovery/<score_run_id>/seeded_recovery_summary.json` | Deterministic registry-to-candidate recovery result. |

Recovery `1/1` means the registry expectation for the one seed in the profile recovered the intended generated candidate. It is not an LLM judgment and does not mean the case is accepted into the dataset.

The `co-sem-139` video-caption case illustrates the distinction between candidate generation and violation recovery. The clean Brightlane video still produces a neutral video-caption candidate, but clean recovery against the seeded expectation is `0/1`; the seeded run recovers `1/1`. Candidate existence does not establish a violation.

A practical review loop is:

1. Open `benchmarks/case-tracker.csv` and inspect the case row.
2. Convert the case ID to its Checkout profile, for example `co-sem-052 -> checkout-co-sem-052`.
3. Run the validator command above.
4. Open the printed run directory.
5. Use `run_metadata.json` to find the relevant benchmark state and route.
6. Inspect that state's `screenshot.png`, `dom.html`, and `accessibility_context.json`.
7. Inspect the relevant `candidates/by_type/<type>.jsonl` candidate.
8. Confirm `seeded_recovery_summary.json` reports recovery for the case.

For `co-sem-052`, expect an initial Products-state acquisition where the native Checkout route-navigation landmark is named `Order totals`, the Products and Cart links remain intact, and a `landmark-purpose-mismatch` candidate is recovered. Interaction-required cases use the same command; for example, `checkout-co-sem-047` captures Products -> Cart before recovering the stale Cart-heading candidate.

If validation fails, diagnose in order:

1. Did the mutation actually render?
2. Was the intended state captured?
3. Is neutral evidence present?
4. Was the expected candidate type produced?
5. Is registry/scorer matching correct?
6. Is the case unsupported by the current pipeline?

Do not weaken expectations or change crawler/candidate logic simply to make one case pass unless a general bug has been identified.

## Batches And Acceptance

Profiles group compatible seeds for acquisition. One seed should have one primary acquisition batch. Temporary development profiles are fine.

Before grouping cases, check obvious `subject + mutation_property` conflicts:

```json
{"subject": "checkout.address.street", "mutation_property": "autocomplete"}
```

Then manually consider shared DOM, workflow dependencies, state interactions, focus changes, and hidden or removed subjects.

The dataset consists of accepted batches listed in `benchmarks/dataset-manifest.json`. Pilot profiles stay excluded unless the researcher later reviews and promotes individual cases through the dataset process. No fixed final total, such as 20 cases per type or 340 cases overall, is encoded in the repository.

A case may be marked `accepted` after all of the following are true:

- [ ] Researcher approved the design.
- [ ] Tracker row exists.
- [ ] Clean baseline is correct.
- [ ] Seeded version introduces the intended fault.
- [ ] Case is meaningfully distinct.
- [ ] Subject/state are identified.
- [ ] Deterministic focused path works.
- [ ] Intended state is captured.
- [ ] Relevant evidence/candidate exists.
- [ ] Scorer matches the intended case.
- [ ] Researcher inspects the final result.
- [ ] Detector-aware adjustment, if any, remains independently defensible.

Candidate recovery is technical validation, not scientific or dataset acceptance. An implemented case counts toward the final dataset only when researcher review accepts it and its batch is listed in the manifest.

## Current Developer Fixtures

Current pilot profiles are not dataset batches:

- `checkout-pilot-001`

They are developer fixtures for validation and regression checks until researcher review promotes accepted batches through the dataset process.

## Boundaries

- SPA runtime applies seed effects; it does not contain evaluation expectations.
- Runner reproduces application states; it does not search for violations.
- Registry stores evaluation ground truth; it does not control runtime.
- Validator checks technical readiness; it does not approve semantic quality.
- Do not expose seed/profile metadata in captured artifacts.
- Do not treat autonomous crawler reachability as an acceptance requirement.
