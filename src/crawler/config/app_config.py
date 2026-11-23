from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..crawl.crawl_config import CrawlConfig

DEFAULT_URL = "https://example.com"
DEFAULT_RUNS_DIR = "runs"
DEFAULT_TRAVERSAL_STRATEGY = "bfs"
DEFAULT_SCOPE_POLICY = "same_origin"

ALLOWED_TRAVERSAL_STRATEGIES = {"dfs", "bfs"}
ALLOWED_SCOPE_POLICIES = {"any", "same_origin", "same_host", "same_domain"}
PREFERRED_ACTION_CANDIDATE_PRIORITY_KEY = "prioritize_action_candidates"
LEGACY_ACTION_CANDIDATE_PRIORITY_KEY = "prioritize_candidates"


@dataclass
class AppConfig:
  url: str = DEFAULT_URL
  headless: bool = True
  runs_dir: str = DEFAULT_RUNS_DIR
  enable_run_timing: bool = True
  crawl: CrawlConfig = field(default_factory=CrawlConfig)


def _load_json(path: Path) -> dict[str, Any]:
  raw = json.loads(path.read_text(encoding="utf-8"))
  if not isinstance(raw, dict):
    raise ValueError(f"Config root must be an object: {path}")
  return raw


def _read_bool(
  raw: dict[str, Any],
  *,
  key: str,
  default: bool,
  error_key: str | None = None,
) -> bool:
  value = raw.get(key, default)
  if not isinstance(value, bool):
    display_key = error_key or key
    raise ValueError(f"`{display_key}` must be a boolean")
  return value


def _read_string(
  raw: dict[str, Any],
  *,
  key: str,
  default: str,
  error_key: str | None = None,
) -> str:
  value = raw.get(key, default)
  if not isinstance(value, str):
    display_key = error_key or key
    raise ValueError(f"`{display_key}` must be a string")
  return value


def _read_non_negative_int(
  raw: dict[str, Any],
  *,
  key: str,
  default: int,
  error_key: str | None = None,
) -> int:
  value = raw.get(key, default)
  if isinstance(value, bool) or not isinstance(value, int):
    display_key = error_key or key
    raise ValueError(f"`{display_key}` must be a non-negative integer")
  if value < 0:
    display_key = error_key or key
    raise ValueError(f"`{display_key}` must be a non-negative integer")
  return value


def _read_strategy(raw: dict[str, Any]) -> str:
  traversal_strategy = _read_string(
    raw,
    key="traversal_strategy",
    default=DEFAULT_TRAVERSAL_STRATEGY,
    error_key="crawl.traversal_strategy",
  ).strip().lower()
  if traversal_strategy not in ALLOWED_TRAVERSAL_STRATEGIES:
    raise ValueError("`crawl.traversal_strategy` must be either 'dfs' or 'bfs'")
  return traversal_strategy


def _read_scope_policy(raw: dict[str, Any]) -> str:
  scope_policy = _read_string(
    raw,
    key="scope_policy",
    default=DEFAULT_SCOPE_POLICY,
    error_key="crawl.scope_policy",
  ).strip().lower()
  if scope_policy not in ALLOWED_SCOPE_POLICIES:
    raise ValueError("`crawl.scope_policy` must be one of: 'any', 'same_origin', 'same_host', 'same_domain'")
  return scope_policy


def _read_prioritize_action_candidates(raw: dict[str, Any]) -> bool:
  if PREFERRED_ACTION_CANDIDATE_PRIORITY_KEY in raw:
    return _read_bool(
      raw,
      key=PREFERRED_ACTION_CANDIDATE_PRIORITY_KEY,
      default=False,
      error_key=f"crawl.{PREFERRED_ACTION_CANDIDATE_PRIORITY_KEY}",
    )

  # Legacy config key; prefer crawl.prioritize_action_candidates in new configs.
  return _read_bool(
    raw,
    key=LEGACY_ACTION_CANDIDATE_PRIORITY_KEY,
    default=False,
    error_key=f"crawl.{LEGACY_ACTION_CANDIDATE_PRIORITY_KEY}",
  )


def _read_action_policy(crawl_raw: dict[str, Any]) -> str | None:
  value = crawl_raw.get("action_policy")
  if value is None:
    return None
  if value not in ("discovery", "heuristic", "llm"):
    raise ValueError("`crawl.action_policy` must be one of: discovery, heuristic, llm")
  return value


def _read_llm_policy(crawl_raw: dict[str, Any]):
  raw = crawl_raw.get("llm_policy")
  if raw is None:
    return None
  if not isinstance(raw, dict):
    raise ValueError("`crawl.llm_policy` must be an object")
  from ..crawl.priority.llm_policy import LLMPolicyConfig

  timeout = raw.get("timeout_s", 60)
  if not isinstance(timeout, (int, float)) or timeout <= 0:
    raise ValueError("`crawl.llm_policy.timeout_s` must be a positive number")
  return LLMPolicyConfig(
    provider=str(raw.get("provider", "fake")),
    model=str(raw.get("model", "")),
    temperature=float(raw.get("temperature", 0.0)),
    timeout_s=float(timeout),
    effort=raw.get("effort"),
    use_screenshot=bool(raw.get("use_screenshot", True)),
  )


def _read_allow_hosts(crawl_raw: dict[str, Any]) -> tuple[str, ...]:
  submission = crawl_raw.get("submission") or {}
  if not isinstance(submission, dict):
    raise ValueError("`crawl.submission` must be an object")
  hosts = submission.get("allow_hosts", [])
  if not isinstance(hosts, list) or not all(isinstance(h, str) and h.strip() for h in hosts):
    raise ValueError("`crawl.submission.allow_hosts` must be a list of host names")
  return tuple(h.strip().lower() for h in hosts)


def _parse_crawl_cfg(raw: dict[str, Any]) -> CrawlConfig:
  crawl_raw = raw.get("crawl", {})
  if crawl_raw is None:
    crawl_raw = {}
  if not isinstance(crawl_raw, dict):
    raise ValueError("`crawl` must be an object in config")

  return CrawlConfig(
    max_states=_read_non_negative_int(
      crawl_raw,
      key="max_states",
      default=100,
      error_key="crawl.max_states",
    ),
    max_depth=_read_non_negative_int(
      crawl_raw,
      key="max_depth",
      default=5,
      error_key="crawl.max_depth",
    ),
    max_actions_per_state=_read_non_negative_int(
      crawl_raw,
      key="max_actions_per_state",
      default=5,
      error_key="crawl.max_actions_per_state",
    ),
    back_timeout_ms=_read_non_negative_int(
      crawl_raw,
      key="back_timeout_ms",
      default=10_000,
      error_key="crawl.back_timeout_ms",
    ),
    traversal_strategy=_read_strategy(crawl_raw),
    scope_policy=_read_scope_policy(crawl_raw),
    prioritize_action_candidates=_read_prioritize_action_candidates(crawl_raw),
    enable_tile_screenshots=_read_bool(
      crawl_raw,
      key="enable_tile_screenshots",
      default=True,
      error_key="crawl.enable_tile_screenshots",
    ),
    wait_timeout_ms=_read_non_negative_int(
      crawl_raw,
      key="wait_timeout_ms",
      default=2_000,
      error_key="crawl.wait_timeout_ms",
    ),
    action_policy=_read_action_policy(crawl_raw),
    llm_policy=_read_llm_policy(crawl_raw),
    submission_allow_hosts=_read_allow_hosts(crawl_raw),
    network_guard=_read_bool(crawl_raw, key="network_guard", default=True, error_key="crawl.network_guard"),
  )


def load_app_config(path: Path) -> AppConfig:
  raw = _load_json(path)
  return AppConfig(
    url=_read_string(raw, key="url", default=DEFAULT_URL),
    headless=_read_bool(raw, key="headless", default=True),
    runs_dir=_read_string(raw, key="runs_dir", default=DEFAULT_RUNS_DIR),
    enable_run_timing=_read_bool(raw, key="enable_run_timing", default=True),
    crawl=_parse_crawl_cfg(raw),
  )
