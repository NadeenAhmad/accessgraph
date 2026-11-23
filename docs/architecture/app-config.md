# Crawler Configuration Reference

This document describes the JSON configuration accepted by the crawl stage: field names, defaults, validation rules, and loader behavior.

## Quick Start

The normal crawl command is:

```powershell
python accessgraph.py crawl --config path\to\my-config.json
```

If `--config` is omitted, the CLI loads `crawler_config.json` from the current working directory. `accessgraph.py crawl` delegates to `main.py`, which contains the lower-level crawl implementation.

## Configuration Shape

The configuration root must be a JSON object. The `crawl` object is optional; when it is omitted or set to `null`, all crawl defaults apply.

```json
{
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
}
```

## Top-Level Fields

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `url` | string | `"https://example.com"` | Start URL opened by the browser before traversal begins. |
| `headless` | boolean | `true` | Whether Chromium runs without a visible window. |
| `runs_dir` | string | `"runs"` | Parent directory for timestamped run directories. Relative paths are resolved from the process working directory. |
| `enable_run_timing` | boolean | `true` | Whether to write `run_timing.json`. |
| `crawl` | object or `null` | `{}` | Crawl-stage settings. |

`crawler_config.json` in the repository is an example configuration and may override some loader defaults, such as `url` and `crawl.enable_tile_screenshots`.

## Crawl Fields

| Field | Type | Default | Allowed values | Meaning |
| --- | --- | --- | --- | --- |
| `crawl.max_states` | non-negative integer | `100` | - | Maximum number of UI states saved in one crawl. The initial state counts toward this limit. |
| `crawl.max_depth` | non-negative integer | `5` | - | Maximum transition depth expanded from the initial state. |
| `crawl.max_actions_per_state` | non-negative integer | `5` | - | Maximum number of browser actions attempted while expanding one UI state. |
| `crawl.back_timeout_ms` | non-negative integer | `10000` | - | Timeout used by restore and back-navigation logic. |
| `crawl.traversal_strategy` | string | `"bfs"` | `"bfs"`, `"dfs"` | Traversal order. BFS explores states level by level; DFS explores a child state immediately. |
| `crawl.scope_policy` | string | `"same_origin"` | `"any"`, `"same_origin"`, `"same_host"`, `"same_domain"` | URL scope policy for crawl actions and state restoration. |
| `crawl.prioritize_action_candidates` | boolean | `false` | - | Enables priority scoring for crawler action candidates before selection. |
| `crawl.enable_tile_screenshots` | boolean | `true` | - | Writes up to six viewport tile screenshots in addition to the main screenshot. |
| `crawl.wait_timeout_ms` | non-negative integer | `2000` | - | Post-action wait timeout for DOM mutation or timeout-based settling. |

## URL Scope Policies

Scope is evaluated from the configured start URL.

| Policy | Implementation behavior |
| --- | --- |
| `any` | Allows every target URL. |
| `same_origin` | Allows targets with the same scheme, normalized host, and port as the start URL. Default ports are normalized to `80` for HTTP and `443` for HTTPS. Relative or hostless targets are allowed. |
| `same_host` | Allows targets with the same normalized host as the start URL, regardless of scheme or port. Relative or hostless targets are allowed. |
| `same_domain` | Removes a leading `www.` from the start host and allows that base host plus its subdomains. Relative or hostless targets are allowed. |

Out-of-scope link targets can be skipped before execution when the target is known. If an action navigates out of scope after execution, the crawler records the skip and restores the previous state when possible.

## Action Candidate Prioritization

`prioritize_action_candidates` controls how the crawler orders possible browser interactions during crawling. "Action candidate" here means a possible browser interaction, such as a link, button, select, or native radio action. It is unrelated to semantic candidates generated during offline analysis.

When this setting is `false`, action candidates are considered in discovery order up to `max_actions_per_state`. When it is `true`, the crawler scans a wider action-candidate window, scores actions by route and control heuristics, records priority diagnostics, and selects the highest-priority unattempted action. It does not change action discovery, action execution, state identity, URL scope rules, or the later semantic candidate builder.

The legacy key `crawl.prioritize_candidates` is still accepted. If both keys are present, `crawl.prioritize_action_candidates` takes precedence.

## Defaults

Loader defaults come from `src/crawler/config/app_config.py` and `src/crawler/crawl/crawl_config.py`.

| Area | Defaults |
| --- | --- |
| Top level | `url = "https://example.com"`, `headless = true`, `runs_dir = "runs"`, `enable_run_timing = true` |
| Crawl | `max_states = 100`, `max_depth = 5`, `max_actions_per_state = 5`, `back_timeout_ms = 10000`, `traversal_strategy = "bfs"`, `scope_policy = "same_origin"`, `prioritize_action_candidates = false`, `enable_tile_screenshots = true`, `wait_timeout_ms = 2000` |

## Validation and Loader Behavior

The loader validates only the fields it reads:

- the root value must be a JSON object;
- top-level `url` and `runs_dir` must be strings;
- top-level `headless` and `enable_run_timing` must be booleans;
- `crawl` must be an object or `null`;
- crawl numeric fields must be non-negative integers; booleans are rejected for numeric fields;
- `crawl.traversal_strategy` and `crawl.scope_policy` must be strings and are stripped, lowercased, and checked against their allowed values;
- `crawl.prioritize_action_candidates`, the legacy `crawl.prioritize_candidates`, and `crawl.enable_tile_screenshots` must be booleans.

Unknown top-level and crawl fields are ignored. Invalid known values raise `ValueError`. Missing files and invalid JSON fail before a run directory is created.

A crawl run creates `runs/<run_id>/`, where `<run_id>` is a timestamp such as `20260423_102530`. The effective crawl settings are written to `runs/<run_id>/crawl_config.json`. `run_metadata.json` stores the config path as passed to the loader, its resolved path, and a file hash when the config file exists.

## Examples

Minimal configuration:

```json
{
  "url": "https://example.com"
}
```

Typical bounded crawl configuration:

```json
{
  "url": "https://reactrouter.com/",
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
    "enable_tile_screenshots": false,
    "wait_timeout_ms": 2000
  }
}
```

## Related Documentation and Source Files

- [Default Crawl Flow](full-crawl-flow.md)
- [Run Metadata Reference](run-metadata.md)
- `crawler_config.json`
- `accessgraph.py`
- `main.py`
- `src/crawler/config/app_config.py`
- `src/crawler/crawl/crawl_config.py`
- `src/crawler/crawl/navigation/scope.py`
- `src/crawler/crawl/actions/selection.py`
- `src/crawler/crawl/priority/`
