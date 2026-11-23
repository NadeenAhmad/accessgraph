# Default Crawl Flow

The crawl stage opens a configured start URL, explores UI states within configured bounds, captures state artifacts, records transitions, and writes crawl metadata. Semantic candidate generation, LLM judgment, and report generation run later from the saved run directory.

## Command

```powershell
python accessgraph.py crawl --config crawler_config.json
```

`accessgraph.py crawl` delegates to `main.py`, which contains the lower-level crawl implementation.

## Crawl Responsibilities

The crawl stage:

- loads the crawler configuration;
- launches Chromium through Playwright;
- opens the configured start URL and captures the initial state;
- discovers and executes action candidates within configured limits;
- saves UI-state artifacts;
- records graph nodes and transitions;
- exports graph artifacts;
- writes run metadata, optional timing data, and crawl metrics.

The crawl stage does not generate semantic candidates, decide whether a violation exists, call an LLM provider, or create developer reports.

## Action Discovery and Selection

Crawler action candidates are possible browser interactions, not semantic accessibility candidates. The default discovery strategies cover visible links, native buttons, role buttons, summaries, tabs, disclosure controls, selects, native unselected radios, and button-like inputs. Text inputs, textareas, date/time controls, and checkbox toggles are not selected by the default action loop.

Native `input[type="radio"]` support is limited to enabled, unselected native radios. The crawler can activate a visible radio directly, or a hidden radio through a visible associated label (`for=...` or wrapping label). Already-selected radios, disabled radios, hidden radios without a visible label, and custom ARIA `role="radio"` controls are skipped.

Submit controls are attempted only when the surrounding form passes the crawler's submission filters. The crawler does not generate meaningful text-field values, intentionally trigger invalid form submissions, or complete arbitrary multi-step forms. Select controls can be changed, but selects inside forms excluded by those filters are skipped. Opening a dialog can create a distinct state when the rendered UI changes, and visible actions inside that dialog can be discovered later; forms inside dialogs follow the same form limits.

Action selection has four parts:

1. discovery finds controls from the configured strategies;
2. filtering removes unsafe, disabled, invisible, out-of-scope, or unsupported candidates;
3. optional prioritization scores remaining candidates using element type, route/navigation hints, text categories, state history, and diversity heuristics;
4. budgeting limits how many actions are attempted per state.

When `crawl.prioritize_action_candidates` is `false`, the crawler uses discovery order up to `crawl.max_actions_per_state`. When it is `true`, it scans a wider candidate window and chooses the highest-scored unattempted action. Prioritization is a navigation heuristic; it does not use semantic accessibility reasoning or choose actions because they are likely to expose violations.

## State Identity and Restoration

State identity is based on canonical URL plus normalized rendered DOM identity. URL canonicalization normalizes routine URL differences such as default ports and tracking parameters. The rendered-DOM identity focuses on meaningful visible UI structure and interactive state, so two UI states can have the same route or URL but remain distinct when the rendered interface differs.

Before trying another action from an already discovered state, the crawler restores that state. Restoration can use the current page when it already matches, direct URL or route navigation when appropriate, browser-back fallback, or replay of the saved action path from the start state. Replay matches actions by stable trigger identity where available, then by bounded action metadata such as strategy, href, text, and input type.

## Graph Artifacts

Graph nodes are saved UI states. Each node stores state identity, URL, route, title, parent-state metadata for first discovery, and the incoming action when available. Graph edges are observed transitions between states and include action metadata. If a later action returns to an existing UI state, the existing node is reused and another edge records the transition.

`graph.json` is the serialized state graph with nodes, edges, metrics, and start-state metadata. `transitions.json` is an edge-oriented export of the same observed transitions; it is not a separate graph model.

## Output Shape

A completed crawl run writes a timestamped run directory:

```text
runs/<run_id>/
  crawl_config.json
  run_metadata.json
  run_timing.json              # optional, controlled by enable_run_timing
  crawl_metrics.json           # written when crawl metrics exist
  graph.json
  transitions.json
  graph.dot
  graph.png                    # optional, only when Graphviz dot renders it
  states/
    state_0000/
      dom.html
      screenshot.png
      metadata.json
      aria_snapshot.json        # optional; omitted if ARIA snapshot capture fails
      accessibility_context.json
      state_0000.tile_00.png    # optional tile screenshot when enabled
```

`accessibility_context.json` is the saved state-level accessibility context. It records observations such as page context, visible text, roles, accessible names, labels, form controls, headings, landmarks, focusable elements, relationships, bounding boxes, language evidence, and extraction metadata. It does not contain violation labels, semantic candidate judgments, LLM judgments, seed expectations, external review labels, or report findings.

## Main Source Areas

| Path | Role |
| --- | --- |
| `accessgraph.py` | Staged CLI for crawl, semantic candidate generation, LLM judgment, and report generation. |
| `main.py` | Lower-level crawl-stage entry point. |
| `src/crawler/config/` | Configuration loading and validation. |
| `src/crawler/platform/browser.py` | Browser startup and page loading. |
| `src/crawler/crawl/entrypoint.py` | Crawl orchestration facade. |
| `src/crawler/crawl/crawl_session.py` | Bounded exploration, action execution, transition recording, and metrics. |
| `src/crawler/crawl/actions/` | Action candidate discovery, filtering, and execution. |
| `src/crawler/crawl/navigation/` | URL scope handling and state restoration during traversal. |
| `src/crawler/crawl/state_tracking/` | Saved-state registry, deduplication, parent links, and transitions. |
| `src/crawler/state/` | UI-state artifact capture. |
| `src/crawler/evidence/` | State-level accessibility context extraction. |
| `src/crawler/graph/` | State graph representation and export. |

## Later Stages

After a crawl finishes, run later stages explicitly:

```powershell
python accessgraph.py candidates --run runs\<run_id>
python accessgraph.py judge --run runs\<run_id> --provider fake --limit 5
python accessgraph.py report --run runs\<run_id> --judgment-run-id <judgment_run_id>
```

Semantic candidate generation reads the saved graph and state-level accessibility context, then writes semantic candidates for later analysis under `candidates/`. LLM judgment reads those semantic candidates and writes structured LLM judgments under `confirmations/`; `confirmations/` is the current implementation path for this stage. Reporting reads one completed LLM-judgment run and packages its evidence for developer review.

## Focused Benchmark Runs

The controlled local benchmark can write normalized run directories through app-specific deterministic acquisition scripts. These deterministic scripts produce the same run and per-state artifact structure consumed by the later analysis stages. They are evaluation fixtures, not evidence that the ordinary crawler independently discovers every possible benchmark state.

## Scope and Limitations

State acquisition is bounded by configuration. A completed crawl documents the UI states, transitions, artifacts, accessibility context, metadata, and metrics it captured; it does not prove that all possible SPA states or accessibility-relevant workflows were reached.
