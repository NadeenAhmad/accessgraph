# Implementing Benchmark Cases

This guide is the operational handoff for adding one controlled AccessGraph benchmark case. The tracker records the approved design; the SPA catalogues create the controlled mutation; the registry defines expected evidence; focused acquisition captures the state; deterministic scoring verifies that the seeded case can be recovered.

Implementation does not decide whether a case belongs in the research dataset. Researcher review and the accepted-dataset manifest remain separate.

## Core Concepts

| Concept | Responsibility |
| --- | --- |
| Subject | Stable, case-neutral identity for a real UI element or page. |
| Effect | One explicit semantic override consumed by generic SPA wiring. |
| Seed | Names one controlled mutation and its target/effect value. |
| Profile | Activates an independent set of seeds for acquisition. |
| Registry variant | Declares the expected route/state and matcher-evaluated neutral evidence. |
| Focused acquisition | Replays the shortest deterministic workflow to the relevant state. |
| Seeded recovery | Offline proof that the expected registry variant matches the seeded candidate and not the clean candidate. |

These boundaries matter. A seed ID must not appear in production component branches. A candidate is a hypothesis. A deterministic registry match is not an LLM judgment.

## Tracker Contract

`benchmarks/case-tracker.csv` is authoritative for planned designs and statuses. It has 14 columns:

`case_id`, `violation_type`, `app`, `short_description`, `pattern`, `tier`, `baseline`, `mutation`, `why_unambiguous`, `interaction_path`, `evidence_state`, `batch_id`, `status`, and `notes`.

Do not renumber IDs, rewrite approved design fields during implementation, or mark a case implemented before its mutation and deterministic recovery are verified. Preserve CSV column count, unique IDs and patterns, CRLF, and UTF-8 without a BOM.

## The 13-Step Workflow

### 1. Verify the approved design

Read the row from the committed tracker version. Confirm it is `planned`, semantically defensible, and clear about the clean baseline, seeded mutation, route, interaction path, evidence timing, and graph dependence. Stop rather than silently redesigning an ambiguous case.

### 2. Locate the real UI surface

Inspect the component, normal state, submitted values, and user-visible context. The clean application must make sense without any benchmark configuration. Prefer an existing stable element over adding a benchmark-only surface.

### 3. Choose or add a stable subject

Subjects belong in the SPA benchmark catalogue, for example:

- Checkout: `benchmarks/local-spas/checkout-flow/src/benchmark/subjects.js`
- Booking: `benchmarks/local-spas/booking-scheduler/src/benchmark/subjects.js`

Use domain identity such as `checkout.navigation.routes` or `booking.details.fullName`. Do not use a case ID, violation name, or expected judgment as a DOM identifier.

### 4. Reuse a generic effect

Use the existing effect vocabulary when it expresses the mutation: text, accessible name, ARIA state, autocomplete, language, activation destination, association, and similar properties. Add reusable component wiring only when the component does not yet consume that generic effect.

The component should resolve the effect for its subject and fall back to its ordinary clean value. Never add `if (caseId === ...)` rendering logic.

### 5. Add exactly one seed

Define one seed with the approved ID, subject, effect kind, and value. Keep the mutation single-fault: unrelated text, navigation, validation, DOM structure, names, and states stay unchanged.

### 6. Add an independent profile

Create one profile such as `checkout-co-sem-052` or `booking-bs-sem-154`. Unless the approved design deliberately requires coupled mutations, the profile contains only the new seed. Verify that no other profile activates it.

### 7. Add one registry variant

Registry family variants live under:

`benchmarks/registry/families/<violation-type>.json`

Use the existing family schema. Constrain the application, route, canonical state when one exists, target identity, and decisive semantic evidence. Conditions in descriptive metadata do not affect matching; every decisive condition must be inside matcher-evaluated fields such as `candidate_evidence`.

Do not persist a run-specific candidate ID. The root registry manifest assembles family files and normally synthesizes single-case configurations; explicit root configurations are reserved for intentional pilots, groups, or acquisition exceptions.

### 8. Define focused acquisition

Reuse the SPA runner and focused-state helpers. Capture the shortest normal workflow that reaches the state, including required form values and interactions. Use the real route and canonical state ID; Help and Confirmation focused runs may use only a run-local state when no `BS-S...` identifier exists.

Post-interaction acquisition does not automatically make a case graph-dependent. Graph dependence means the semantic judgment requires transition or cross-state evidence.

### 9. Compare clean and seeded artifacts

Acquire equivalent clean and seeded runs. Verify the intended DOM or behavior difference directly. Normalize only that difference and compare the remaining DOM, accessibility snapshots, and relevant behavior. Any second semantic change is a defect, even if recovery succeeds.

### 10. Inspect neutral evidence and candidates

Run the production candidate builder and inspect `candidates.jsonl`. Confirm that evidence contains enough context for the semantic contradiction without seed, profile, expected-label, or benchmark-ground-truth leakage.

Candidate generation may identify multiple nearby elements. Registry matching must distinguish the intended target using stable, neutral evidence rather than a candidate ID.

### 11. Prove deterministic recovery

Run the production seeded scorer against clean and seeded artifacts. The usual requirement is:

| Condition | Expected |
| --- | ---: |
| Clean expected seed recovery | `0/1` |
| Seeded expected seed recovery | `1/1` |
| Extra unique matches | `0` |

Expected-seed count, recovered-seed count, and matched-entry count are separate. One seed can intentionally match more than one structured evidence entry. Add negative counterfactuals for the clean value, wrong target, wrong route/state, missing decisive evidence, and legitimate content that resembles the mutation.

### 12. Add focused tests

Cover:

- seed, profile, subject, and effect registration;
- clean baseline preservation;
- exact seeded mutation and profile isolation;
- route/state and registry specificity;
- negative counterfactuals;
- deterministic clean `0/1` and seeded `1/1` recovery;
- graph transition evidence when the design genuinely requires it.

Keep browser workflows explicit. Reuse local candidate and scoring helpers, but do not hide semantic assertions inside a broad data-driven framework.

### 13. Update status only after validation

Change only the approved row from `planned` to `implemented`, then recompute totals and validate formatting. Review the full diff, run `git diff --check`, and request an independent read-only review before committing.

## Worked Example: co-sem-052

`co-sem-052` is a Checkout `landmark-purpose-mismatch` case on the Products page.

### Approved design

- Target subject: `checkout.navigation.routes`
- Route/state: Products, canonical `CO-S001`
- Clean landmark name: `Checkout routes`
- Seeded landmark name: `Order totals`
- Evidence: initial, state-local

### Implementation chain

1. `benchmarks/local-spas/checkout-flow/src/benchmark/subjects.js` defines the stable routes-navigation subject.
2. `seeds.js` defines `co-sem-052` and the `navigationRoutesAccessibleNameOrderTotals` seed.
3. `profiles.js` exposes the independent `checkout-co-sem-052` profile.
4. `effects/landmarkEffects.js` resolves the accessible-name override.
5. `components/AppNav.jsx` consumes that generic effect and otherwise renders the clean name.
6. `benchmarks/registry/families/landmark-purpose-mismatch.json` constrains Products/`CO-S001`, the routes navigation identity, and the incorrect `Order totals` purpose evidence.
7. Checkout focused acquisition captures the initial Products state.
8. Tests in `tests/test_checkout_landmark_purpose.py`, registry-loader tests, and Checkout scaffolding tests verify the baseline, mutation, registry, and recovery.

The component contains no `co-sem-052` branch. The case is represented by configuration and a generic effect boundary.

Run its focused validator with:

```powershell
python scripts/benchmarks/checkout/validate_batch.py --profile checkout-co-sem-052
```

## Recovery Is Not LLM Detection

Deterministic seeded recovery answers: "Did the candidate evidence and registry locate the controlled mutation?" It does not answer: "Did a model independently judge this as a violation?"

LLM confirmation is an optional later stage over saved candidates. It must preserve context-mode isolation, record provider/model configuration, and save complete judgment artifacts. A benchmark may be correctly implemented even when a model returns a false negative; conversely, a registry match does not establish model performance or natural-web precision.

## Review Checklist

- The tracker row was approved and remains semantically intact.
- Exactly one controlled fault exists.
- Clean behavior is unchanged.
- Subjects and component wiring are generic and case-neutral.
- One seed and one independent profile were added.
- Registry conditions are matcher-evaluated and use neutral evidence.
- Route and canonical state are correct.
- Clean recovery is `0/1`; seeded recovery is `1/1`; extras are zero.
- Relevant counterfactuals and neighboring regressions pass.
- No LLM call was required for implementation validation.
- Only the intended tracker status changed.
- `git diff --check` passes and no generated artifacts are included.
