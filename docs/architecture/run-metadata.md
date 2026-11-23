# Run Metadata Reference

## Overview

`runs/<run_id>/run_metadata.json` is the top-level summary record for one crawl run. It stores run identity, the loaded configuration, runtime environment, browser details, source-control metadata when available, final status, error or warning details, and graph and crawl-metric summaries when the crawl reaches those stages.

## Lifecycle

`main.py` creates a timestamp run ID such as `20260423_102530`, creates `runs/<run_id>/`, writes the effective `crawl_config.json`, and builds the initial metadata payload with `status = "running"`. After Chromium starts, `attach_browser_metadata(...)` may add the browser version and user agent. When crawling finishes or fails inside the crawl flow, `main.py` records the primary crawl result. Browser-stop cleanup then runs, and cleanup errors may add warnings. The final `run_metadata.json` write happens at the end of that flow.

Failures that happen before the run directory and metadata payload are created, such as a missing or invalid config file, do not produce `runs/<run_id>/run_metadata.json`.

## Field Reference

| Field | Type | When present | Meaning |
| --- | --- | --- | --- |
| `run_id` | string | initial payload | Timestamp-based run identifier and run-directory name. |
| `status` | string | initial payload, updated before final write | Final top-level status after cleanup handling. Starts as `running`. |
| `primary_status` | string | after crawl result is known | Main crawl result before cleanup warnings are applied. |
| `started_at_utc` | string | initial payload | UTC ISO-8601 timestamp for metadata creation. |
| `ended_at_utc` | string | final write | UTC ISO-8601 timestamp for metadata finalization. |
| `run_dir` | string | initial payload | Run directory path used by the crawl. |
| `config_file` | object | initial payload | Path, resolved path, existence flag, and file hash/size when the config file exists. |
| `config_snapshot` | object | initial payload | Loaded `AppConfig` values after parsing and defaults. |
| `runtime` | object | initial payload | Python version, implementation, executable, platform, machine, and processor. |
| `tooling` | object | initial payload | Playwright package version when available and whether Graphviz `dot` is available. |
| `source_control` | object | initial payload | Git availability, commit, branch, and dirty flag when Git metadata can be read. |
| `browser` | object | initial payload, updated after browser start | Browser engine, headless flag, HTTPS-error behavior, and optional browser version/user agent. |
| `graph` | object | successful crawl | Node and edge counts. |
| `crawl_metrics` | object | when metrics exist | Crawl metrics copied from `crawl_metrics.json` for summary access. |
| `warnings` | array | when cleanup or non-primary errors occur | Warning records with phase, error type, and message. |
| `cleanup` | object | when cleanup errors occur | Cleanup phase status and error details. |
| `error` | object | failed crawl or navigation timeout | Primary error type and message. |

### `config_file`

`config_file.path` stores the path passed to the loader. `config_file.resolved_path` stores the resolved filesystem path. If the file exists, `sha256` and `size_bytes` are added.

### `config_snapshot`

`config_snapshot` is a dataclass-to-dict snapshot of the loaded config. It usually contains `url`, `headless`, `runs_dir`, `enable_run_timing`, and the nested crawl settings after defaults and validation.

### `browser`

The initial browser object includes:

```json
{
  "engine": "chromium",
  "headless": true,
  "ignore_https_errors": true
}
```

After browser startup, `version` and `user_agent` may be added if Playwright exposes them successfully.

## Status and Error Handling

Current status values are:

| Value | Meaning |
| --- | --- |
| `running` | Initial value before the crawl result is known. |
| `success` | The crawl completed and cleanup did not add warnings. |
| `success_with_warnings` | The crawl completed, but cleanup recorded a warning such as browser-stop failure. |
| `navigation_timeout` | Initial navigation raised `NavigationTimeout`. |
| `error` | Another exception occurred during the crawl flow. |

`primary_status` records the main crawl result. `status` records the final top-level result after cleanup handling. For example, if the crawl succeeds but browser shutdown raises an error, `primary_status` remains `success`, `status` becomes `success_with_warnings`, and warning details are written under `warnings` and `cleanup.browser_stop`.

A browser-stop cleanup warning after a successful crawl does not invalidate the saved graph, state artifacts, accessibility context, or crawl metrics. It means the primary crawl work completed and cleanup ended with warnings.

Example cleanup warning:

```json
{
  "primary_status": "success",
  "status": "success_with_warnings",
  "warnings": [
    {
      "phase": "browser_stop",
      "type": "RuntimeError",
      "message": "..."
    }
  ],
  "cleanup": {
    "browser_stop": {
      "status": "error",
      "error": {
        "type": "RuntimeError",
        "message": "..."
      }
    }
  }
}
```

## Example

A successful run usually contains sections like:

```json
{
  "run_id": "20260423_102530",
  "status": "success",
  "primary_status": "success",
  "started_at_utc": "2026-04-23T10:25:30.000000Z",
  "ended_at_utc": "2026-04-23T10:26:01.000000Z",
  "run_dir": "runs/20260423_102530",
  "config_file": {
    "path": "crawler_config.json",
    "resolved_path": "C:/path/to/accessgraph/crawler_config.json",
    "exists": true,
    "sha256": "...",
    "size_bytes": 321
  },
  "config_snapshot": {
    "url": "https://example.com",
    "headless": true,
    "runs_dir": "runs",
    "enable_run_timing": true,
    "crawl": {
      "max_states": 100,
      "max_depth": 5,
      "max_actions_per_state": 5,
      "back_timeout_ms": 10000,
      "traversal_strategy": "bfs",
      "scope_policy": "same_origin",
      "prioritize_action_candidates": false,
      "enable_tile_screenshots": true,
      "wait_timeout_ms": 2000
    }
  },
  "browser": {
    "engine": "chromium",
    "headless": true,
    "ignore_https_errors": true,
    "version": "...",
    "user_agent": "..."
  },
  "graph": {
    "nodes": 3,
    "edges": 2
  }
}
```

## Related Artifacts

| Artifact | Role |
| --- | --- |
| `runs/<run_id>/run_metadata.json` | Run identity, environment, configuration, status, warnings, errors, and summary fields. |
| `runs/<run_id>/run_timing.json` | Duration and phase timing information when `enable_run_timing` is enabled. |
| `runs/<run_id>/crawl_metrics.json` | Crawl measurements, action counts, coverage counters, and stop information. |
| `runs/<run_id>/graph.json` | State graph nodes and transitions. |
| `runs/<run_id>/transitions.json` | Transition edge list. |
| `runs/<run_id>/states/<state_id>/` | Per-state DOM, screenshot, metadata, optional ARIA snapshot, optional tile screenshots, and `accessibility_context.json`. |

Optional fields may be absent. For example, `browser.version` may be missing if browser metadata could not be read, Git details may be reduced to `available: false` outside a Git work tree, `crawl_metrics` appears only when metrics are written, and `warnings` or `cleanup` appear only when warning conditions occur.

## Related Source Files

- `main.py`
- `src/crawler/platform/run_metadata.py`
- `src/crawler/platform/browser.py`
- `src/crawler/crawl/metrics/`
- [Default Crawl Flow](full-crawl-flow.md)
- [Crawler Configuration Reference](app-config.md)
