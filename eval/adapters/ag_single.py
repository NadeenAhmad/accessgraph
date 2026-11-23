"""AccessGraph's single-page mode (C4) as a checker inside external harnesses (D2 InterA11y, D3/D6 Rampa).

  python -m eval.adapters.ag_single REQUEST_JSON RESULT_JSON

Request: {"url", "out_dir" (one per page; shared by the cases on that page and by the runs), "stage",
"run_idx" (1..3), "case_id" (keeps the confirmations of cases on the same page apart), "types" (candidate types
to judge) or "intera11y_sc" (types from the frozen mapping's `external.intera11y`), "target_xpath" (optional:
judge only candidates on this element or inside it), "model" (optional)}.

The page is recorded once as a single state with the frozen recorder and candidate rules (`src.check_page`), and
the selected candidates are judged with the frozen AG-main judge (provider, model, v5 prompt) in isolated context,
as single-page mode does. Only the selection of candidates happens here; nothing that decides a verdict does.
Repeat runs (run_idx 2, 3) reuse the recording and re-ask the judge (the run index is part of the cache key), so
verdict stability can be measured. Every paid call goes through the cost ledger; answers are cached.

Result: {"state", "rows": [{"candidate_id", "type", "sc", "xpath", "outcome", "confidence", "reason"}],
"candidates", "judged", "cost_usd", "calls", "paid_calls", "seconds"}. "outcome" is the judge's decision
(violation / no_violation / uncertain / error).
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from eval.cost import BudgetedClient, CostLedger  # noqa: E402

RESULTS = ROOT / "results"
CACHE = RESULTS / "cache"
FREEZE_PARAMS = ROOT / "eval" / "freeze_params.json"
CALL_TIMEOUT_S = 60.0  # one model call, whole request (normal answers take ~4 s, the slowest observed 40 s)


def time_budget() -> float | None:
  """Seconds a harness allows per page (ACCESSGRAPH_TIME_BUDGET_S); None: no limit."""
  import os
  value = os.environ.get("ACCESSGRAPH_TIME_BUDGET_S", "").strip()
  return float(value) if value else None


class DeadlineClient:
  """Keeps the judging of one page inside the harness's time limit: each call gets at most the time left (a call
  and its one retry must fit), and once the time is used up, calls fail and the runner records `uncertain` for those
  candidates, so the page still reports everything decided by then instead of being cut off by the harness."""

  def __init__(self, inner: Any, deadline: float | None):
    self.inner, self.deadline = inner, deadline
    self.provider, self.model = inner.provider, inner.model

  def confirm(self, prompt):
    if self.deadline is not None:
      left = self.deadline - time.perf_counter()
      if left < 8:
        raise TimeoutError("the page's time budget is used up")
      provider_client = getattr(self.inner, "inner", None)
      if provider_client is not None and hasattr(provider_client, "timeout_seconds"):
        provider_client.timeout_seconds = min(CALL_TIMEOUT_S, (left - 4) / 2)
    return self.inner.confirm(prompt)


def _xkey(xpath: str | None) -> str | None:
  """Same normalisation as InterA11y's `within`: drop [1] steps and local-name() wrappers."""
  if not xpath:
    return None
  value = re.sub(r"\[1\](?=/|$|>>)", "", xpath.strip())
  return re.sub(r"\*\[local-name\(\)=['\"]([^'\"]+)['\"]\]", r"\1", value)


def within(path: str | None, target: str | None) -> bool:
  path, target = _xkey(path), _xkey(target)
  return bool(path and target and (path == target or path.startswith(target + "/") or path.startswith(target + ">>")))


def type_to_criteria() -> dict[str, list[str]]:
  import yaml
  mapping = yaml.safe_load((ROOT / "eval/mappings/taxonomy_sc_rules.yaml").read_text(encoding="utf-8"))
  return {t: list(v.get("success_criteria") or []) for t, v in mapping["types"].items()}


def main_config(model: str | None = None):
  """The frozen AG-main judge, in the isolated context single-page mode uses."""
  from src.analysis.confirmation.models import CONTEXT_MODE_ISOLATED, ConfirmationConfig
  from src.analysis.confirmation.providers.registry import resolve_confirmation_config
  frozen = json.loads(FREEZE_PARAMS.read_text(encoding="utf-8"))["ag_main"]
  return resolve_confirmation_config(ConfirmationConfig(
    provider=frozen["provider"], model=model or frozen["model"], prompt_version=frozen["prompt_version"],
    context_mode=CONTEXT_MODE_ISOLATED, effort=frozen["effort"]))


MAX_JUDGED_ELEMENT = 3   # candidates on the case's element in one state (e.g. a link and its image)
MAX_JUDGED_PAGE = 8      # page-level cases: candidates of the type in the start state and one action away


def judge_config(model: str | None = None):
  """The frozen AG-main judge with its own context policy (history-aware, escalation), as on whole apps."""
  from eval.dev_judge import _config
  frozen = json.loads(FREEZE_PARAMS.read_text(encoding="utf-8"))["ag_main"]
  return _config("AG-main", frozen["provider"], model or frozen["model"], frozen["effort"])


def _state_depths(run_dir: Path) -> dict[str, int]:
  try:
    nodes = json.loads((run_dir / "graph.json").read_text(encoding="utf-8")).get("nodes") or []
    return {n["state_id"]: int(n.get("depth") or 0) for n in nodes}
  except (OSError, ValueError, KeyError):
    return {}


def _root_state(run_dir: Path) -> str:
  try:
    return str(json.loads((run_dir / "graph.json").read_text(encoding="utf-8")).get("start_state") or "state_0000")
  except (OSError, ValueError):
    return "state_0000"


def intera11y_types(sc: str) -> list[str]:
  import yaml
  mapping = yaml.safe_load((ROOT / "eval/mappings/taxonomy_sc_rules.yaml").read_text(encoding="utf-8"))
  ctype = (mapping.get("external") or {}).get("intera11y", {}).get(sc)
  return [ctype] if ctype else []


# W4A phase 1: single-page mode explores from the page (AccessGraph's own method, started at the given page) with
# the frozen LLM explorer, small bounds, the case's element first (focus), forms allowed on local hosts and saved
# local files only; then candidates are judged with history (AG-main) instead of on the bare page.
SINGLE_PAGE_EXPLORE = {"max_states": 8, "max_depth": 2, "max_actions_per_state": 6}
SINGLE_PAGE_ALLOW_HOSTS = ("127.0.0.1", "localhost", "file:")


async def _explore_page(url: str, run_dir: Path, focus: list[str], stage: str) -> None:
  from src.crawler.crawl.crawl_config import CrawlConfig
  from src.crawler.crawl.entrypoint import run_crawl
  from src.crawler.crawl.priority.llm_policy import LLMPolicyConfig, _build_client
  from src.crawler.platform.browser import BrowserController
  from eval.dev_explore import BudgetedJsonClient
  frozen = json.loads(FREEZE_PARAMS.read_text(encoding="utf-8"))["explorer"]
  llm_cfg = LLMPolicyConfig(provider=frozen["llm_provider"], model=frozen["llm_model"])
  cfg = CrawlConfig(**SINGLE_PAGE_EXPLORE, traversal_strategy="bfs", scope_policy="same_origin", action_policy="llm",
                    llm_policy=llm_cfg, submission_allow_hosts=SINGLE_PAGE_ALLOW_HOSTS, network_guard=True,
                    enable_tile_screenshots=False, focus_xpaths=tuple(focus))
  client = BudgetedJsonClient(_build_client(llm_cfg), CostLedger(RESULTS / "cost_ledger.json"),
                              "single-page-explore", stage=stage)
  browser = BrowserController(headless=True)
  await browser.start()
  try:
    if url.startswith("file:"):
      url = await _check_snapshot_as_saved(browser, url, run_dir)
    await browser.goto(url)
    if url.startswith("file:"):
      await _show_saved_images(browser.page)
    await _scroll_through(browser.page)
    graph = await run_crawl(browser.page, url, run_dir, cfg, llm_client=client)
    graph.save_json(run_dir / "graph.json")
    if hasattr(graph, "save_transitions_json"):
      graph.save_transitions_json(run_dir / "transitions.json")
    else:
      (run_dir / "transitions.json").write_text("[]", encoding="utf-8")
  finally:
    await browser.stop()


_PAGE_SIZE_JS = "() => ({n: document.getElementsByTagName('*').length, text: document.body ? document.body.innerText.length : 0})"
_SAVED_IMAGES_JS = """() => {
  // a saved page shows all its saved images: lazy images load now (not only when scrolled into view), and a
  // <picture> source that points online (it cannot load offline) gives way to the <img>'s saved copy
  for (const img of document.querySelectorAll('img[loading="lazy"]')) img.loading = 'eager';
  for (const img of document.querySelectorAll('picture > img[src]')) {
    const src = img.getAttribute('src') || '';
    if (!src || /^(https?:|data:)/i.test(src)) continue;
    for (const s of Array.from(img.parentElement.querySelectorAll(':scope > source')))
      if (/^https?:/i.test((s.getAttribute('srcset') || '').trim())) s.remove();
  }
}"""
_SCRIPT_TAG = re.compile(rb"<script\b[^>]*>.*?</script\s*>", re.S | re.I)
_HEAD_TAG = re.compile(rb"<head\b[^>]*>", re.I)


async def _check_snapshot_as_saved(browser, url: str, run_dir: Path) -> str:
  """W4A round 5: a saved page (a file) is checked as it was saved. Offline, a snapshot's own scripts sometimes fail
  and erase the saved content (a blank or emptied page seconds after loading). The page is measured once without
  scripts and once with them after 6 s; when the scripted page keeps less than half of the saved elements or text,
  AccessGraph records a copy of the saved file without its <script> elements (written next to the recording, with a
  <base> pointing at the original so its saved resources and links resolve as before). Returns the URL to record:
  the original for every other page."""
  from src.crawler.platform.browser import DEFAULT_VIEWPORT, IGNORE_HTTPS_ERRORS
  from urllib.request import url2pathname
  from urllib.parse import urlparse
  saved = live = None
  off = await browser.browser.new_context(viewport=DEFAULT_VIEWPORT, ignore_https_errors=IGNORE_HTTPS_ERRORS,
                                          java_script_enabled=False)
  try:
    page = await off.new_page()
    await page.goto(url, wait_until="load", timeout=45_000)
    saved = await page.evaluate(_PAGE_SIZE_JS)
    await browser.page.goto(url, wait_until="load", timeout=45_000)
    await browser.page.wait_for_timeout(6_000)
    live = await browser.page.evaluate(_PAGE_SIZE_JS)
  except Exception:  # a page that cannot be measured is recorded as before
    pass
  finally:
    await off.close()
  erased = bool(saved and live and (live["n"] < 0.5 * saved["n"] or live["text"] < 0.5 * saved["text"]))
  (run_dir / "snapshot.json").write_text(json.dumps({"saved": saved, "with_scripts_after_6s": live,
                                                     "scripts_removed": erased}) + "\n", encoding="utf-8")
  if not erased:
    return url
  raw = Path(url2pathname(urlparse(url).path)).read_bytes()
  stripped = _SCRIPT_TAG.sub(b"", raw)
  if not re.search(rb"<base\b", stripped, re.I):
    base = b'<base href="' + url.replace('"', "%22").encode() + b'">'
    head = _HEAD_TAG.search(stripped)
    stripped = (stripped[:head.end()] + base + stripped[head.end():]) if head else base + stripped
  copy = run_dir / "saved-without-scripts.html"
  copy.write_bytes(stripped)
  return copy.resolve().as_uri()


def _recorded_url(url: str, run_dir: Path) -> str:
  """The URL the page was recorded from: the copy without scripts when _check_snapshot_as_saved made one."""
  copy = run_dir / "saved-without-scripts.html"
  return copy.resolve().as_uri() if copy.exists() else url


async def _show_saved_images(page) -> None:
  """W4A round 5: a saved page shows all its saved images (see _SAVED_IMAGES_JS), after loading and on every later
  load of the page."""
  try:
    await page.evaluate(_SAVED_IMAGES_JS)
    await page.context.add_init_script(f"document.addEventListener('DOMContentLoaded', {_SAVED_IMAGES_JS});")
    await page.wait_for_load_state("load", timeout=10_000)
    await page.wait_for_timeout(1_000)
  except Exception:
    pass


async def _scroll_through(page) -> None:
  """W4A round 4: scroll the page once from top to bottom (and back) before recording, as a reader would, so content
  that loads only when scrolled into view (lazy images, carousels) is in the recorded page. Read-only."""
  try:
    await page.evaluate("""async () => {
      const step = Math.max(400, Math.floor(window.innerHeight * 0.8));
      const end = Math.min(document.documentElement.scrollHeight, 40000);
      for (let y = 0; y < end; y += step) { window.scrollTo(0, y); await new Promise((r) => setTimeout(r, 60)); }
      window.scrollTo(0, 0);
    }""")
    await page.wait_for_timeout(500)
  except Exception:  # a page that blocks scripting or navigates away keeps its loaded state
    pass


def explore_mode() -> bool:
  import os
  return os.environ.get("ACCESSGRAPH_SINGLE_PAGE_MODE", "explore") == "explore"


_CODE_HASH: str | None = None


def code_hash() -> str:
  """Hash of every file that decides AccessGraph's output (eval.freeze.FREEZE_PATTERNS), computed now."""
  global _CODE_HASH
  if _CODE_HASH is None:
    from eval.freeze import FREEZE_PATTERNS, expand, file_sha256, freeze_hash
    _CODE_HASH = freeze_hash({rel: file_sha256(ROOT / rel) for rel in expand(FREEZE_PATTERNS, ROOT)}, {})
  return _CODE_HASH


def _set_aside_if_stale(run_dir: Path) -> None:
  """A recording is reused only by the code that made it (the runs of one version); one made by other code is moved
  to <pages>-stale/<its code hash>/ and the page is recorded again."""
  import shutil
  if not (run_dir / "graph.json").exists():
    return
  try:
    previous = str(json.loads((run_dir / "recorded_with.json").read_text(encoding="utf-8"))["code_hash"])
  except (OSError, ValueError, KeyError):
    previous = "unmarked"
  if previous == code_hash():
    return
  stale = run_dir.parent.parent / f"{run_dir.parent.name}-stale" / previous[:12] / run_dir.name
  stale.parent.mkdir(parents=True, exist_ok=True)
  if stale.exists():
    shutil.rmtree(stale)
  shutil.move(str(run_dir), str(stale))


def record(url: str, run_dir: Path, types: list[str] | None, *, focus: list[str] | None = None,
           stage: str = "external") -> list[dict]:
  """Record (or explore from) the page once, reused by later runs of the same code; return its candidates."""
  import fcntl
  from src.analysis.candidates.builder import build_semantic_candidates
  from src.check_page import CheckPageOptions, _record_single_state
  path = run_dir / "candidates" / "candidates.jsonl"
  run_dir.parent.mkdir(parents=True, exist_ok=True)
  with open(run_dir.parent / f".{run_dir.name}.lock", "w") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)  # parallel workers on the same page record it once
    _set_aside_if_stale(run_dir)
    if not (run_dir / "graph.json").exists():
      run_dir.mkdir(parents=True, exist_ok=True)
      if explore_mode():
        asyncio.run(_explore_page(url, run_dir, focus or [], stage))
      else:
        asyncio.run(_record_single_state(url, run_dir, CheckPageOptions(target=url, out_dir=run_dir)))
    if not path.exists():
      build_semantic_candidates(run_dir, candidate_types=None)
      (run_dir / "recorded_with.json").write_text(json.dumps({"code_hash": code_hash()}) + "\n", encoding="utf-8")
  candidates = [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]
  return [c for c in candidates if not types or c.get("candidate_type") in types]


def judge_page(url: str, out_dir: Path, *, stage: str, run_idx: int = 1, types: list[str] | None = None,
               target_xpath: str | None = None, model: str | None = None, case_id: str = "page") -> dict:
  from src.analysis.confirmation.providers.caching import CachingConfirmationClient
  from src.analysis.confirmation.providers.registry import build_confirmation_client
  from src.analysis.confirmation.runner import ConfirmationRunOptions, run_confirmation
  from src.check_page import PAGE_LEVEL_XPATHS, _element_for

  started = time.perf_counter()
  run_dir = Path(out_dir).resolve()
  if explore_mode() and target_xpath:  # the exploration is directed at the case's element: one per case
    run_dir = run_dir.parent / f"{run_dir.name}--{re.sub(r'[^A-Za-z0-9]+', '-', case_id).strip('-')[:60]}"
  candidates = record(url, run_dir, types, focus=[target_xpath] if target_xpath else [], stage=stage)
  xpaths = {c["candidate_id"]: str(_element_for(run_dir, c).get("xpath") or "")
            or PAGE_LEVEL_XPATHS.get(c["candidate_type"], "") for c in candidates}
  root = _root_state(run_dir)
  depth = _state_depths(run_dir)
  ordered = sorted(candidates, key=lambda c: (depth.get(c.get("state_id"), 99), c.get("state_id") or ""))
  if target_xpath:
    # the case's element is judged once, in the first state where it appears (normally the start page); what its
    # own actions led to is part of that judgment as outgoing evidence
    matching = [c for c in ordered if within(xpaths[c["candidate_id"]], target_xpath)]
    first_state = matching[0].get("state_id") if matching else None
    selected = [c for c in matching if c.get("state_id") == first_state][:MAX_JUDGED_ELEMENT]
  else:
    # page-level cases: the start page and the states one action away (e.g. after a form submission)
    selected = [c for c in ordered if depth.get(c.get("state_id"), 99) <= 1][:MAX_JUDGED_PAGE]
  result = {"state": "complete", "rows": [], "candidates": len(candidates), "judged": len(selected),
            "cost_usd": 0.0, "calls": 0, "paid_calls": 0, "run_idx": run_idx}
  if selected and explore_mode():  # follow link targets one step, read-only, where no outcome was recorded
    from src.analysis.candidates.destination_peek import peek_destinations
    peek_destinations(run_dir, [c["candidate_id"] for c in selected])
  if selected:
    config = judge_config(model) if explore_mode() else main_config(model)
    case = re.sub(r"[^A-Za-z0-9]+", "-", case_id).strip("-")[:80] or "page"
    confirmation_run_id = f"ag-single-{config.model.replace('/', '-')}-r{run_idx}-{case}"
    ledger = CostLedger(RESULTS / "cost_ledger.json")
    import dataclasses
    budget = time_budget()
    deadline = started + budget if budget else None
    budgeted = BudgetedClient(build_confirmation_client(dataclasses.replace(config, timeout_seconds=CALL_TIMEOUT_S)),
                              ledger, stage, run_id=confirmation_run_id)
    guarded = DeadlineClient(budgeted, deadline)
    # ACCESSGRAPH_CACHE_ROUND: a name for a set of final runs; answers stored under another name are not reused, so
    # every model answer of those runs is fresh (round 3: the PI asked for runs that reuse no earlier answer)
    import os
    cache_round = os.environ.get("ACCESSGRAPH_CACHE_ROUND", "")
    parameters = {"effort": config.effort, "run_idx": run_idx, **({"round": cache_round} if cache_round else {})}
    client = CachingConfirmationClient(guarded, CACHE, parameters=parameters)
    run_confirmation(config=config, client=client, options=ConfirmationRunOptions(
      run_dir=run_dir, confirmation_run_id=confirmation_run_id,
      candidate_ids=tuple(sorted(c["candidate_id"] for c in selected)), overwrite=True,
      save_prompts=True, save_raw_responses=True, fail_fast=False))
    final: dict[str, str] = {}
    # W4A phase 2: uncertain verdicts get follow-up evidence and a majority of three re-judgements (skipped when a
    # harness time limit leaves too little time for it; the first verdicts then stand)
    if explore_mode() and (deadline is None or deadline - time.perf_counter() > 30):
      from src.analysis.confirmation.uncertain_followup import follow_up

      def rejudge(run_id: str, ids: tuple[str, ...], sample: int) -> None:
        sample_client = CachingConfirmationClient(guarded, CACHE, parameters={**parameters, "followup_sample": sample})
        run_confirmation(config=config, client=sample_client, options=ConfirmationRunOptions(
          run_dir=run_dir, confirmation_run_id=run_id, candidate_ids=ids, overwrite=True,
          save_prompts=True, save_raw_responses=True, fail_fast=False))

      root_state = _root_state(run_dir)
      final = follow_up(run_dir, first_run_id=confirmation_run_id, judge=rejudge,
                        state_url=lambda sid: _recorded_url(url, run_dir) if sid == root_state else None,
                        allow_hosts=SINGLE_PAGE_ALLOW_HOSTS)
    criteria = type_to_criteria()
    path = run_dir / "confirmations" / confirmation_run_id / "confirmations.jsonl"
    for line in path.read_text(encoding="utf-8").split("\n"):
      if not line.strip():
        continue
      record_ = json.loads(line)
      ctype = record_["candidate_type"]
      result["rows"].append({
        "candidate_id": record_["candidate_id"], "type": ctype, "sc": criteria.get(ctype, []),
        "xpath": xpaths.get(record_["candidate_id"], ""),
        "outcome": final.get(record_["candidate_id"]) or record_.get("decision") or "error",
        "followed_up": record_["candidate_id"] in final,
        "confidence": record_.get("confidence"), "reason": record_.get("reason") or ""})
      result["calls"] += 1
    result["cost_usd"] = round(budgeted.spent, 6)
    result["paid_calls"] = client.misses
  result["seconds"] = round(time.perf_counter() - started, 1)
  result["time_budget_s"] = time_budget()
  return result


def main(argv: list[str] | None = None) -> int:
  argv = sys.argv[1:] if argv is None else argv
  request = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
  try:
    types = request.get("types") or (intera11y_types(request["intera11y_sc"]) if request.get("intera11y_sc") else None)
    if request.get("intera11y_sc") and not types:
      raise ValueError(f"no AccessGraph type for criterion {request['intera11y_sc']}")
    result = judge_page(request["url"], Path(request["out_dir"]), stage=request["stage"],
                        run_idx=int(request.get("run_idx") or 1), types=types,
                        target_xpath=request.get("target_xpath") or None, model=request.get("model") or None,
                        case_id=str(request.get("case_id") or "page"))
  except Exception as error:  # reported to the harness as an error row, never as "not flagged"
    import traceback
    traceback.print_exc()
    result = {"state": "error", "rows": [], "error": f"{type(error).__name__}: {error}"}
  Path(argv[1]).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
