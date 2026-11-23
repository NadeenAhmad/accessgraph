"""Single-page mode (C4): judge one page state without exploring.

  python accessgraph.py check-page https://example.com/ --provider openrouter --model anthropic/claude-haiku-5.5
  python accessgraph.py check-page ./saved/page.html --out runs/check-page-1 --json findings.json

The page is loaded once and recorded as a single state (no actions are performed, and the network guard
blocks writes), candidates are built from that state, and every candidate is judged in isolated context with
the same judge and prompts as the full pipeline. Findings carry a CSS selector and an XPath for the element.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FINDING_DECISIONS = ("violation", "uncertain")
PAGE_LEVEL_XPATHS = {"lang-mismatch": "/html[1]", "page-title-not-descriptive": "/html[1]/head[1]/title[1]"}


@dataclass(frozen=True)
class CheckPageOptions:
  target: str
  out_dir: Path
  provider: str = "fake"
  model: str = ""
  prompt_version: str | None = None
  candidate_types: tuple[str, ...] = ()
  effort: str | None = None
  timeout_seconds: float = 120.0
  response_cache: Path | None = None
  headless: bool = True
  wait_timeout_ms: int = 2_000


def target_url(target: str) -> str:
  if re.match(r"^[a-z][a-z0-9+.-]*://", target, re.IGNORECASE):
    return target
  path = Path(target).expanduser().resolve()
  if not path.exists():
    raise FileNotFoundError(f"check-page target not found: {target}")
  return path.as_uri()


def xpath_to_css(xpath: str) -> str:
  """'/html[1]/body[1]/div[2]/a[1]' -> 'html > body > div:nth-of-type(2) > a:nth-of-type(1)'.

  XPath positions count same-tag siblings, exactly like :nth-of-type, so the selector picks the same element.
  """
  parts = []
  for step in [s for s in xpath.split("/") if s]:
    match = re.match(r"^([a-zA-Z][\w-]*)(?:\[(\d+)\])?$", step)
    if not match:
      return ""
    tag, index = match.group(1).lower(), match.group(2)
    parts.append(tag if tag in ("html", "body", "head") or index is None else f"{tag}:nth-of-type({index})")
  return " > ".join(parts)


async def _record_single_state(url: str, run_dir: Path, options: CheckPageOptions) -> None:
  from src.crawler.crawl.crawl_config import CrawlConfig
  from src.crawler.crawl.entrypoint import run_crawl
  from src.crawler.platform.browser import BrowserController

  cfg = CrawlConfig(max_states=1, max_depth=0, max_actions_per_state=0, enable_tile_screenshots=False,
                    wait_timeout_ms=options.wait_timeout_ms, network_guard=True)
  browser = BrowserController(headless=options.headless)
  await browser.start()
  try:
    await browser.goto(url)
    graph = await run_crawl(browser.page, url, run_dir, cfg)
    graph.save_json(run_dir / "graph.json")
    if hasattr(graph, "save_transitions_json"):
      graph.save_transitions_json(run_dir / "transitions.json")
    else:
      (run_dir / "transitions.json").write_text("[]", encoding="utf-8")
  finally:
    await browser.stop()


def _element_for(run_dir: Path, candidate: dict[str, Any]) -> dict[str, Any]:
  refs = candidate.get("element_refs") or []
  if not refs or not isinstance(refs[0], dict):
    return {}
  bucket, element_id = refs[0].get("bucket"), refs[0].get("element_id")
  context_path = run_dir / "states" / str(candidate.get("state_id")) / "accessibility_context.json"
  try:
    context = json.loads(context_path.read_text(encoding="utf-8"))
  except (OSError, ValueError):
    return {}
  for element in context.get(str(bucket)) or []:
    if isinstance(element, dict) and element.get("element_id") == element_id:
      return element
  return {}


def check_page(options: CheckPageOptions) -> dict[str, Any]:
  from src.analysis.candidates.builder import build_semantic_candidates
  from src.analysis.confirmation.models import ConfirmationConfig, CONTEXT_MODE_ISOLATED
  from src.analysis.confirmation.providers.caching import CachingConfirmationClient
  from src.analysis.confirmation.providers.registry import (
    build_confirmation_client, get_confirmation_provider_spec, resolve_confirmation_config)
  from src.analysis.confirmation.runner import ConfirmationRunOptions, run_confirmation

  url = target_url(options.target)
  run_dir = options.out_dir.resolve()
  run_dir.mkdir(parents=True, exist_ok=True)
  asyncio.run(_record_single_state(url, run_dir, options))
  summary = build_semantic_candidates(run_dir, candidate_types=list(options.candidate_types) or None)
  candidates = [json.loads(line) for line in (summary.output_dir / "candidates.jsonl").read_text().splitlines() if line]

  spec = get_confirmation_provider_spec(options.provider)
  v5 = "confirm_v5_vision" if spec.screenshot_required else "confirm_v5_text"
  prompt_version = options.prompt_version or (v5 if v5 in spec.compatible_prompt_versions else spec.default_prompt_version)
  config = resolve_confirmation_config(ConfirmationConfig(
    provider=options.provider, model=options.model or "fake-confirmation-model", prompt_version=prompt_version,
    context_mode=CONTEXT_MODE_ISOLATED, timeout_seconds=options.timeout_seconds, effort=options.effort))
  client = None
  if options.response_cache is not None:
    client = CachingConfirmationClient(build_confirmation_client(config), options.response_cache,
                                       parameters={"effort": options.effort, "timeout_seconds": options.timeout_seconds})
  run_id = "check-page-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
  findings: list[dict[str, Any]] = []
  cost = 0.0
  if candidates:
    run_options = ConfirmationRunOptions(run_dir=run_dir, confirmation_run_id=run_id,
                                         candidate_ids=tuple(c["candidate_id"] for c in candidates))
    extra = {"client": client} if client is not None else {}
    run_confirmation(config=config, options=run_options, **extra)
    by_id = {c["candidate_id"]: c for c in candidates}
    for line in (run_dir / "confirmations" / run_id / "confirmations.jsonl").read_text().splitlines():
      record = json.loads(line)
      cost += float(record.get("estimated_cost_usd") or 0.0)
      if record.get("decision") not in FINDING_DECISIONS:
        continue
      candidate = by_id.get(record["candidate_id"], {})
      element = _element_for(run_dir, candidate)
      xpath = str(element.get("xpath") or "") or PAGE_LEVEL_XPATHS.get(record["candidate_type"], "")
      findings.append({
        "candidate_id": record["candidate_id"], "candidate_type": record["candidate_type"],
        "decision": record["decision"], "confidence": record.get("confidence"), "reason": record.get("reason"),
        "css_selector": xpath_to_css(xpath) if xpath else "", "xpath": xpath,
        "accessible_name": element.get("accessible_name") or element.get("text") or "",
      })
  report = {"schema_version": "check_page_v1", "target": options.target, "url": url, "run_dir": str(run_dir),
            "provider": options.provider, "model": config.model, "prompt_version": prompt_version,
            "context_mode": CONTEXT_MODE_ISOLATED, "confirmation_run_id": run_id if candidates else None,
            "candidates": len(candidates), "findings": findings, "estimated_cost_usd": round(cost, 6)}
  (run_dir / "check_page_findings.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                                                     encoding="utf-8")
  return report
