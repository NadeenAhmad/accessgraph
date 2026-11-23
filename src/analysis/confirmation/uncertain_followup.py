"""Follow-up for uncertain verdicts (W4A phase 2): gather the evidence a tool-using reviewer would fetch, then
re-judge three times and take the majority.

After the judge (with its history escalation) still answers `uncertain` for a candidate, this step:

1. gathers evidence for the candidate's type, live where a live page is available and safe:
   - links: the destination, loaded read-only (`peeked_destination_v1`);
   - buttons, widgets, ARIA states: the element pressed on a fresh load of the state's page, and what changed
     (URL, title, dialogs, headings, states, new or short-lived text) (`pressed_outcome_v1`); only on hosts the
     auditor allows (local apps, saved local files) and only for a state reachable by loading its URL;
   - images: whether the image loaded, and its intrinsic size (`image_render_v1`);
2. re-judges the candidate three times with the added evidence (independent answers; the run index is part of the
   cache key) and takes the majority of violation / no violation; with no majority the verdict stays uncertain.

The follow-up result is written as a separate confirmation run; `final_decisions()` merges it over the first run.
"""
from __future__ import annotations

import asyncio
import json
from collections import Counter
from pathlib import Path
from typing import Any, Callable

PRESS_TYPES = {"button-label-mismatch", "widget-label-purpose-mismatch", "aria-state-mismatch"}
FOLLOWUP_SAMPLES = 3

_RESOLVE_JS = """(path) => {
  let ctx = document, el = null;
  const parts = String(path).split('>>');
  for (let i = 0; i < parts.length; i++) {
    let cur = ctx;
    for (const step of parts[i].split('/').filter(Boolean)) {
      const m = step.match(/^([^\\[]+)(?:\\[(\\d+)\\])?$/);
      if (!m) return null;
      let count = 0, found = null;
      for (const child of Array.from(cur.children || [])) {
        if (child.localName === m[1].toLowerCase() && ++count === Number(m[2] || 1)) { found = child; break; }
      }
      if (!found) return null;
      cur = found;
    }
    el = cur;
    if (i < parts.length - 1) {
      let inner = el.shadowRoot;
      if (!inner && el.tagName === 'IFRAME') { try { inner = el.contentDocument; } catch (e) { inner = null; } }
      if (!inner) return null;
      ctx = inner;
    }
  }
  return el;
}"""

_SNAPSHOT_JS = """() => ({
  url: location.href, title: document.title,
  headings: Array.from(document.querySelectorAll('h1, h2, h3')).filter((h) => h.offsetParent !== null)
    .slice(0, 8).map((h) => h.innerText.trim().slice(0, 100)),
  dialogs: Array.from(document.querySelectorAll('dialog[open], [role="dialog"], [role="alertdialog"]'))
    .filter((d) => d.offsetParent !== null || d.open).map((d) => (d.getAttribute('aria-label') || d.innerText || '').trim().slice(0, 120)),
  states: Array.from(document.querySelectorAll('[aria-expanded], [aria-pressed], [aria-selected], [aria-checked]'))
    .slice(0, 40).map((e) => [e.getAttribute('aria-expanded'), e.getAttribute('aria-pressed'), e.getAttribute('aria-selected'), e.getAttribute('aria-checked')].join('|')),
  text: (document.body ? document.body.innerText : '').replace(/\\s+/g, ' ').trim()
})"""


def _element(run_dir: Path, candidate: dict[str, Any]) -> dict[str, Any]:
  refs = candidate.get("element_refs") or []
  if not refs or not isinstance(refs[0], dict):
    return {}
  context_path = run_dir / "states" / str(candidate.get("state_id")) / "accessibility_context.json"
  try:
    context = json.loads(context_path.read_text(encoding="utf-8"))
  except (OSError, ValueError):
    return {}
  for item in context.get(str(refs[0].get("bucket"))) or []:
    if isinstance(item, dict) and item.get("element_id") == refs[0].get("element_id"):
      return item
  return {}


async def _press(url: str, xpath: str, allow_hosts: tuple[str, ...]) -> dict[str, Any]:
  from playwright.async_api import async_playwright
  from src.crawler.crawl.actions.forms import host_allowed
  if not host_allowed(url, allow_hosts):
    return {"skipped": "not an allowed host: pressing is only done on local apps and saved local files"}
  async with async_playwright() as playwright:
    browser = await playwright.chromium.launch(headless=True)
    try:
      page = await browser.new_page()
      await page.goto(url, wait_until="load", timeout=30_000)
      await page.wait_for_timeout(800)
      before = await page.evaluate(_SNAPSHOT_JS)
      handle = await page.evaluate_handle(f"({_RESOLVE_JS})({json.dumps(xpath)})")
      element = handle.as_element()
      if element is None:
        return {"skipped": "element not found on a fresh load of the page"}
      await element.click(timeout=5_000)
      await page.wait_for_timeout(1_200)
      after = await page.evaluate(_SNAPSHOT_JS)
      added = [w for w in after["text"].split(". ") if w and w not in before["text"]][:6]
      return {
        "url_changed": before["url"] != after["url"], "url_after": after["url"],
        "title_before": before["title"], "title_after": after["title"],
        "dialogs_after": after["dialogs"], "headings_after": after["headings"],
        "states_changed": before["states"] != after["states"],
        "new_text": " ".join(added)[:400],
      }
    except Exception as error:
      return {"skipped": f"could not press: {type(error).__name__}"}
    finally:
      await browser.close()


async def _image(url: str, xpath: str) -> dict[str, Any]:
  from playwright.async_api import async_playwright
  async with async_playwright() as playwright:
    browser = await playwright.chromium.launch(headless=True)
    try:
      page = await browser.new_page()
      await page.goto(url, wait_until="load", timeout=30_000)
      return await page.evaluate(f"""(path) => {{
        const el = ({_RESOLVE_JS})(path);
        if (!el) return {{ found: false }};
        const img = el.tagName === 'IMG' ? el : el.querySelector && el.querySelector('img');
        return {{ found: true, loaded: img ? (img.complete && img.naturalWidth > 0) : null,
                  natural_size: img ? [img.naturalWidth, img.naturalHeight] : null,
                  css_background: getComputedStyle(el).backgroundImage }};
      }}""", xpath)
    except Exception as error:
      return {"skipped": f"could not load: {type(error).__name__}"}
    finally:
      await browser.close()


def gather_evidence(run_dir: Path, candidate_ids: list[str], *, state_url: Callable[[str], str | None],
                    allow_hosts: tuple[str, ...]) -> int:
  """Add follow-up evidence to the given candidates in candidates.jsonl; return how many got any."""
  from src.analysis.candidates.destination_peek import peek_destinations
  run_dir = Path(run_dir)
  peek_destinations(run_dir, candidate_ids)
  path = run_dir / "candidates" / "candidates.jsonl"
  candidates = [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]
  wanted, added = set(candidate_ids), 0
  for candidate in candidates:
    if candidate["candidate_id"] not in wanted:
      continue
    supporting = candidate.setdefault("evidence", {}).setdefault("supporting", {})
    xpath = str(_element(run_dir, candidate).get("xpath") or "")
    url = state_url(str(candidate.get("state_id")))
    if not xpath or not url:
      continue
    if candidate["candidate_type"] in PRESS_TYPES and "pressed_outcome_v1" not in supporting:
      supporting["pressed_outcome_v1"] = asyncio.run(_press(url, xpath, allow_hosts))
      added += 1
    elif candidate["candidate_type"] == "image-alt-not-descriptive" and "image_render_v1" not in supporting:
      supporting["image_render_v1"] = asyncio.run(_image(url, xpath))
      added += 1
    elif "peeked_destination_v1" in supporting:
      added += 1
  # ASCII-escaped, so text from a page (e.g. U+2028) can never split a JSON line
  path.write_text("".join(json.dumps(c) + "\n" for c in candidates), encoding="utf-8")
  return added


def read_decisions(run_dir: Path, confirmation_run_id: str) -> dict[str, dict[str, Any]]:
  path = Path(run_dir) / "confirmations" / confirmation_run_id / "confirmations.jsonl"
  if not path.exists():
    return {}
  return {r["candidate_id"]: r for r in (json.loads(l) for l in path.read_text(encoding="utf-8").split("\n") if l.strip())}


def majority(decisions: list[str]) -> str:
  """The more frequent of violation / no violation among the samples; uncertain when neither occurs or they tie."""
  votes = Counter(d for d in decisions if d in ("violation", "no_violation"))
  if votes["violation"] == votes["no_violation"]:
    return "uncertain"
  return "violation" if votes["violation"] > votes["no_violation"] else "no_violation"


def follow_up(run_dir: Path, *, first_run_id: str, judge: Callable[[str, tuple[str, ...], int], None],
              state_url: Callable[[str], str | None], allow_hosts: tuple[str, ...]) -> dict[str, str]:
  """For candidates answered `uncertain` in `first_run_id`: gather evidence, re-judge FOLLOWUP_SAMPLES times via
  `judge(run_id, candidate_ids, sample_index)`, and return {candidate_id: majority decision}. The samples are
  written as runs `<first_run_id>-followup-s<k>`."""
  first = read_decisions(run_dir, first_run_id)
  uncertain = sorted(cid for cid, r in first.items() if r.get("decision") == "uncertain")
  if not uncertain:
    return {}
  gather_evidence(run_dir, uncertain, state_url=state_url, allow_hosts=allow_hosts)
  samples: dict[str, list[str]] = {cid: [] for cid in uncertain}
  for k in range(1, FOLLOWUP_SAMPLES + 1):
    run_id = f"{first_run_id}-followup-s{k}"
    judge(run_id, tuple(uncertain), k)
    for cid, record in read_decisions(run_dir, run_id).items():
      if cid in samples:
        samples[cid].append(str(record.get("decision") or "uncertain"))
  result = {cid: majority(votes) for cid, votes in samples.items()}
  (Path(run_dir) / "confirmations" / f"{first_run_id}-followup.json").write_text(
    json.dumps({"samples": samples, "majority": result}, indent=2) + "\n", encoding="utf-8")
  return result


def final_decisions(run_dir: Path, first_run_id: str) -> dict[str, str]:
  """The first run's decisions with uncertain ones replaced by the follow-up majority, where a follow-up exists."""
  decisions = {cid: str(r.get("decision")) for cid, r in read_decisions(run_dir, first_run_id).items()}
  path = Path(run_dir) / "confirmations" / f"{first_run_id}-followup.json"
  if path.exists():
    decisions.update(json.loads(path.read_text(encoding="utf-8")).get("majority") or {})
  return decisions
