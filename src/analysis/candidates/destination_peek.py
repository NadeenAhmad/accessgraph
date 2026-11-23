"""Destination peek (W4A phase 1): follow a link one step to see where it leads.

When a link candidate has no recorded outcome (its target lies outside the explored scope, e.g. another site),
the link's URL is loaded once, read-only (GET; the network guard blocks every other request method), and the
destination's title, main headings and first text are added to the candidate as `peeked_destination_v1`. Nothing
is clicked, filled or submitted there. Used by single-page mode; the judge reads it like other destination evidence.

Saved local pages (file:// HTML documents) are peeked like web pages. For links with the same name
(`links_with_the_same_name`), each other link's destination is peeked too and added to its entry as
`peeked_destination`, so the judge can compare where the links lead (ACT rule fd3a94).
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

PEEK_TIMEOUT_MS = 10_000
MAX_PEEKS = 12
MAX_SAME_NAME_PEEKS = 12  # destinations of other links with the same name, over all candidates of one call
SAME_NAME_PER_LINK = 3
LOCAL_PAGE_SUFFIXES = (".html", ".htm", ".xhtml")

_SUMMARY_JS = """() => ({
  title: document.title || '',
  headings: Array.from(document.querySelectorAll('h1, h2')).filter((h) => h.getClientRects().length > 0)
    .slice(0, 5).map((h) => (h.innerText || '').trim().slice(0, 120)),
  text: (document.body ? document.body.innerText : '').replace(/\\s+/g, ' ').trim().slice(0, 300),
  main_text: ((document.querySelector('main, [role="main"]') || {}).innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 300),
  lang: document.documentElement.lang || ''
})"""


def _needs_peek(candidate: dict[str, Any]) -> str | None:
  if candidate.get("candidate_type") != "link-text-mismatch":
    return None
  supporting = (candidate.get("evidence") or {}).get("supporting") or {}
  if supporting.get("destination_state_context_v1") or supporting.get("same_page_target_v1") \
     or supporting.get("peeked_destination_v1"):
    return None
  destination = supporting.get("link_destination_context_v1") or {}
  url = str(destination.get("resolved_url") or "")
  return url if _peekable(url) else None


def _peekable(url: str) -> bool:
  """Web pages, and saved local pages (file:// HTML documents); no other schemes or local files."""
  parts = urlsplit(url)
  if parts.scheme in ("http", "https"):
    return True
  return parts.scheme == "file" and parts.path.lower().endswith(LOCAL_PAGE_SUFFIXES)


def _page_url(run_dir: Path, candidate: dict[str, Any]) -> str:
  try:
    metadata = json.loads((run_dir / "states" / str(candidate.get("state_id")) / "metadata.json").read_text("utf-8"))
  except (OSError, ValueError):
    return ""
  return str(metadata.get("url") or "")


def _same_name_targets(run_dir: Path, candidate: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
  """(entry, url) for other links with the same name whose destination has not been peeked yet."""
  if candidate.get("candidate_type") != "link-text-mismatch":
    return []
  entries = ((candidate.get("evidence") or {}).get("supporting") or {}).get("links_with_the_same_name") or []
  base = _page_url(run_dir, candidate)
  out = []
  for entry in entries[:SAME_NAME_PER_LINK]:
    href = str(entry.get("href") or "") if isinstance(entry, dict) else ""
    if not href or "peeked_destination" in entry:
      continue
    url = urljoin(base, href) if base else href
    if _peekable(url):
      out.append((entry, url))
  return out


async def _peek(urls: list[str]) -> dict[str, dict[str, Any]]:
  from playwright.async_api import async_playwright
  out: dict[str, dict[str, Any]] = {}
  async with async_playwright() as playwright:
    browser = await playwright.chromium.launch(headless=True)
    try:
      context = await browser.new_context()

      async def read_only(route):
        if route.request.method in ("GET", "HEAD", "OPTIONS"):
          await route.continue_()
        else:
          await route.abort()

      await context.route("**/*", read_only)
      for url in urls:
        page = await context.new_page()
        try:
          response = await page.goto(url, wait_until="domcontentloaded", timeout=PEEK_TIMEOUT_MS)
          await page.wait_for_timeout(800)
          summary = await page.evaluate(_SUMMARY_JS)
          out[url] = {"requested_url": url, "final_url": page.url, "status": response.status if response else None,
                      **summary}
        except Exception as error:  # unreachable or too slow: recorded as such, never guessed
          out[url] = {"requested_url": url, "error": f"{type(error).__name__}"}
        finally:
          await page.close()
    finally:
      await browser.close()
  return out


def peek_destinations(run_dir: Path, candidate_ids: list[str]) -> int:
  """Add `peeked_destination_v1` to the given link candidates in candidates.jsonl; return how many were peeked."""
  run_dir = Path(run_dir)
  path = run_dir / "candidates" / "candidates.jsonl"
  candidates = [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]
  wanted = set(candidate_ids)
  urls = []
  for candidate in candidates:
    if candidate["candidate_id"] in wanted:
      url = _needs_peek(candidate)
      if url and url not in urls:
        urls.append(url)
  urls = urls[:MAX_PEEKS]
  same_name_urls: list[str] = []
  for candidate in candidates:
    if candidate["candidate_id"] in wanted:
      for _, url in _same_name_targets(run_dir, candidate):
        if url not in urls and url not in same_name_urls and len(same_name_urls) < MAX_SAME_NAME_PEEKS:
          same_name_urls.append(url)
  if not urls and not same_name_urls:
    return 0
  results = asyncio.run(_peek(urls + same_name_urls))
  peeked = 0
  for candidate in candidates:
    if candidate["candidate_id"] not in wanted:
      continue
    url = _needs_peek(candidate)
    if url and url in results:
      candidate["evidence"]["supporting"]["peeked_destination_v1"] = results[url]
      peeked += 1
    for entry, other in _same_name_targets(run_dir, candidate):
      if other in results:
        entry["peeked_destination"] = {k: v for k, v in results[other].items() if k != "lang"}
  # ASCII-escaped, so text from a page (e.g. U+2028) can never split a JSON line
  path.write_text("".join(json.dumps(c) + "\n" for c in candidates), encoding="utf-8")
  return peeked
