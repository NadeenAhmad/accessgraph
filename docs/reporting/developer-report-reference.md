# Developer Report Reference

The developer report is a separate stage after LLM judgment. It
turns one existing implementation confirmation run into a static HTML report, a
Markdown developer summary, and a structured JSON representation for later
inspection or tooling.

This document uses `confirmation` when referring to concrete implementation
artifacts such as `confirmations/`, `confirmations.jsonl`, and
`confirmation_run_id`. In developer-facing prose, these are LLM-judgment artifacts.

Reporting presents completed LLM-judgment records. It does not crawl, extract
evidence, build candidates, call an LLM provider, rerun LLM judgment, create
external labels, embed screenshot bytes, or generate
fixes.

The records stored in implementation confirmation artifacts remain LLM judgments rather than ground truth.
Controlled benchmark expectations are separate evaluation inputs and are not created or applied by this reporting stage.

## Input

The report requires an existing confirmation run containing:

```text
runs/<run_id>/confirmations/<confirmation_run_id>/
  manifest.json
  confirmations.jsonl
```

`confirmations.jsonl` is the canonical record input. The report does not read
candidate outputs as an alternative to confirmation records and does not use
`by_type/*.jsonl`.

The reader verifies that the confirmation directory, manifest, and JSONL file
exist and are parseable. It does not independently validate a lifecycle
completion marker, so callers should provide a completed confirmation run.

By default, the report tries to load compact source-candidate excerpts through
`source_candidate_ref` and checks whether paths in `artifact_refs` exist. Missing
source candidates or artifacts produce warnings, not run failures.

## Output

Reports are written separately from confirmation outputs:

```text
runs/<run_id>/reports/<report_run_id>/
  manifest.json
  report.html
  report.md
  report.json
```

`report.html` is a static local inspection view. `report.md` remains the
Markdown summary. `report.json` includes all confirmation records, including
`no_violation`, so other tooling can consume the report without scraping a
presentation format.

The HTML and Markdown reports use the same no-violation detail behavior:
`no_violation` records are summarized by default and included in detail only
when `--include-no-violation` is used.

## Markdown Behavior

The Markdown report groups LLM-judged findings by SPA state/page first, then
by display category:

1. likely violations;
2. non-parsed records and client/parser/id/schema errors;
3. uncertain records;
4. no-violation records only when `--include-no-violation` is used.

No confidence thresholds are applied. Confidence remains model-reported or
heuristic, not calibrated probability.

Each finding uses an AccessGraph-native developer evidence block:

- candidate type;
- decision, confidence, and parse status;
- reason and supporting evidence from confirmation output;
- compact source-candidate excerpt when available;
- truncated affected HTML snippet when present in saved candidate evidence;
- state/page and artifact references;
- source candidate reference;
- warnings.

Artifact references are rendered as links to saved run artifacts when possible.
For example, a screenshot may be linked through its saved path, but the image
bytes are not copied or embedded in the report output.

The report does not invent fix suggestions or remediation advice. Labels such
as "Likely Violations" are report display categories derived from confirmation
records; they do not convert model output into verified ground truth.

## JSON Behavior

`report.json` includes:

- `schema_version`;
- `report_run_id`;
- `generated_at`;
- source run and confirmation paths;
- provider, model, prompt version, prompt/config hashes, and confidence
  semantics;
- summary counts by decision, parse status, candidate type, and state;
- `states[]`;
- complete `findings[]`, including additive context-mode metadata when present
  in the source LLM-judgment records;
- `warnings[]`.

Full source candidates are not duplicated in `report.json`; the raw candidate
and confirmation artifacts remain canonical.

The report manifest records:

- schema and generator versions;
- report, source run, and confirmation run identifiers;
- input and output paths;
- report options;
- summary counts and a report hash;
- invocation and runtime provenance.

The old `main.py --report-run` flag is legacy-disabled. It fails with a pointer
to `python accessgraph.py report --run <run_id> --judgment-run-id <id>` instead
of invoking the old crawler-era report path.

## CLI

```powershell
python accessgraph.py report `
  --run runs/<run_id> `
  --judgment-run-id <judgment_run_id>
```

Useful options:

- `--report-run-id <id>`;
- `--output-dir <path>`;
- `--include-no-violation`;
- `--overwrite`;
- `--no-load-source-candidates`;
- `--no-verify-artifacts`.

## Relationship To Evaluation

The developer report supports inspection of one LLM-judgment run. Cross-run model or context comparison is a separate evaluation operation. Controlled benchmark expectations are also separate scoring inputs.

## Developer-Facing Style

The report presents useful developer-facing fields such as violation type, decision, confidence, affected HTML, source state, artifact references, and evidence. These fields are presentation summaries over AccessGraph state graph artifacts, semantic candidate records, and LLM judgments; they are not verified ground truth.
