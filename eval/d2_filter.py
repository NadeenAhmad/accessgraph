"""D2 semantic scope filter (evaluation protocol: docs/evaluation.md). Deterministic, no model calls.

  python -m eval.d2_filter [--dataset expert|conformance|all] [--cases C032,C133]

Reads only `case_id, sc, page, scope, xpath` of InterA11y's `elements.csv` (never the labels), loads each page as
InterA11y's harness does (file URL, Chromium), and decides with Chromium's computed accessibility tree:

- 1.1.1 (image alt) and 2.4.4 (link text), element rows: keep when the target exists and is exposed with a
  non-empty accessible name. Missing names are syntactic and left to rule checkers.
- 1.1.1 and 2.4.4, page rows (conformance fixtures, no XPath): keep when the page exposes at least one image
  (image roles, image buttons and image-map areas; resp. links) and every exposed one has a non-empty name. Elements hidden from assistive technologies, or marked
  decorative (alt="", role none/presentation), are not exposed and do not count.
- 3.3.1 (error message): keep when an error message is present: an exposed alert with text, a field marked
  invalid that has a description or an error-message reference, or a visible element whose id or class names an
  error and that has text. Element rows also need the target to exist.

Output: results/d2/scope.csv (one row per case: keep, reason, evidence) and the out-of-scope cases in
results/exclusions.csv (reported as "out of scope", never as misses).
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from eval.runlog import RunLog  # noqa: E402

from eval.paths import INTERA11Y  # noqa: E402
OUT = ROOT / "results" / "d2" / "scope.csv"
CRITERIA = ("1.1.1", "2.4.4", "3.3.1")
FIELDS = ("case_id", "dataset", "sc", "scope", "page", "keep", "reason", "evidence")
IMAGE_ROLES = {"image", "img", "graphics-document", "graphics-symbol"}
LINK_ROLES = {"link"}
ERROR_WORD = re.compile(r"(^|[-_\s])(error|errors|invalid|err)([-_\s]|$)", re.IGNORECASE)

ERROR_JS = """(re) => {
  const rx = new RegExp(re, 'i');
  const visible = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const out = [];
  for (const e of document.querySelectorAll('[id], [class]')) {
    const tag = (e.id || '') + ' ' + (typeof e.className === 'string' ? e.className : '');
    if (!rx.test(tag)) continue;
    const text = (e.innerText || '').trim();
    if (text && text.length <= 300 && visible(e)) out.push(text.slice(0, 80));
    if (out.length >= 3) break;
  }
  return out;
}"""


def rows(dataset: str, wanted: set[str] | None) -> list[dict]:
  path = INTERA11Y / "datasets" / dataset / "elements.csv"
  keep = ("case_id", "sc", "page", "scope", "xpath")  # labels are never read
  with path.open(encoding="utf-8") as stream:
    out = [{k: r[k] for k in keep} | {"dataset": dataset} for r in csv.DictReader(stream)]
  return [r for r in out if r["sc"] in CRITERIA and (not wanted or r["case_id"] in wanted)]


def ns_safe(xpath: str) -> str:
  """'/html[1]/body[1]/svg[1]' -> steps by local-name(), so SVG and MathML elements in HTML pages match too."""
  steps = []
  for step in [s for s in xpath.split("/") if s]:
    m = re.match(r"^([A-Za-z][\w.-]*)(\[\d+\])?$", step)
    steps.append(f"*[local-name()='{m.group(1).lower()}']{m.group(2) or ''}" if m else step)
  return "/" + "/".join(steps)


def _value(node: dict, key: str) -> str:
  return str(((node.get(key) or {}).get("value")) or "").strip()


def _props(node: dict) -> dict:
  return {p["name"]: (p.get("value") or {}).get("value") for p in node.get("properties") or []}


async def _ax_tree(page) -> list[dict]:
  cdp = await page.context.new_cdp_session(page)
  await cdp.send("Accessibility.enable")
  tree = await cdp.send("Accessibility.getFullAXTree")
  return tree.get("nodes", []), cdp


async def _target_node(page, cdp, xpath: str, nodes: list[dict]) -> tuple[bool, dict | None]:
  xpath = ns_safe(xpath)
  handle = await page.evaluate_handle(
    "(x) => document.evaluate(x, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue", xpath)
  element = handle.as_element()
  if element is None:
    return False, None
  remote = await cdp.send("Runtime.evaluate", {
    "expression": f"document.evaluate({json.dumps(xpath)}, document, null, 9, null).singleNodeValue"})
  object_id = (remote.get("result") or {}).get("objectId")
  described = await cdp.send("DOM.describeNode", {"objectId": object_id})
  backend = described["node"]["backendNodeId"]
  node = next((n for n in nodes if n.get("backendDOMNodeId") == backend), None)
  return True, node


def _exposed(node: dict) -> bool:
  return not node.get("ignored") and _value(node, "role") not in ("none", "presentation", "generic", "")


async def _error_present(page, nodes: list[dict]) -> tuple[bool, str]:
  for n in nodes:
    if n.get("ignored"):
      continue
    role, name = _value(n, "role"), _value(n, "name")
    if role == "alert" and name:
      return True, f"alert: {name[:80]}"
    props = _props(n)
    if props.get("invalid") not in (None, "false", False) and (_value(n, "description") or props.get("errormessage")):
      return True, f"invalid field with description: {_value(n, 'description')[:80]}"
  texts = await page.evaluate(ERROR_JS, ERROR_WORD.pattern)
  if texts:
    return True, f"error element: {texts[0]}"
  return False, "no error message on the page"


async def decide(page, row: dict) -> tuple[bool, str, str]:
  nodes, cdp = await _ax_tree(page)
  await cdp.send("DOM.enable")
  sc, element_row = row["sc"], row["scope"] == "element" and bool(row["xpath"])
  if sc == "3.3.1":
    if element_row:
      found, _ = await _target_node(page, cdp, row["xpath"], nodes)
      if not found:
        return False, "target not in the DOM as loaded", ""
    present, evidence = await _error_present(page, nodes)
    return present, ("error message present" if present else "no error message"), evidence
  roles = IMAGE_ROLES if sc == "1.1.1" else LINK_ROLES
  if element_row:
    found, node = await _target_node(page, cdp, row["xpath"], nodes)
    if not found:
      return False, "target not in the DOM as loaded", ""
    if node is None or node.get("ignored"):
      return False, "target hidden from assistive technologies", ""
    name = _value(node, "name")
    if not name:
      return False, "target has no accessible name (syntactic)", _value(node, "role")
    return True, "target has a non-empty accessible name", f"{_value(node, 'role')}: {name[:80]}"
  extra: set[int] = set()
  if sc == "1.1.1":  # image buttons and image-map areas carry a text alternative too (their role is not image)
    root = (await cdp.send("DOM.getDocument", {"depth": 0}))["root"]["nodeId"]
    found = await cdp.send("DOM.querySelectorAll", {"nodeId": root, "selector": "input[type=image i], area[href]"})
    for node_id in found.get("nodeIds", []):
      extra.add((await cdp.send("DOM.describeNode", {"nodeId": node_id}))["node"]["backendNodeId"])
  exposed = [n for n in nodes if _exposed(n) and (_value(n, "role") in roles or n.get("backendDOMNodeId") in extra)]
  if not exposed:
    return False, "no exposed element of this type on the page", ""
  unnamed = [n for n in exposed if not _value(n, "name")]
  if unnamed:
    return False, f"{len(unnamed)} of {len(exposed)} exposed elements have no accessible name (syntactic)", ""
  return True, f"all {len(exposed)} exposed elements have a non-empty accessible name", _value(exposed[0], "name")[:80]


async def run(cases: list[dict], done: set[str]) -> None:
  from playwright.async_api import async_playwright
  OUT.parent.mkdir(parents=True, exist_ok=True)
  new_file = not OUT.exists()
  log = RunLog(ROOT / "results")
  with OUT.open("a", newline="", encoding="utf-8") as stream:
    writer = csv.DictWriter(stream, fieldnames=FIELDS)
    if new_file:
      writer.writeheader()
    async with async_playwright() as p:
      browser = await p.chromium.launch()
      for i, row in enumerate(cases):
        key = f"{row['dataset']}:{row['case_id']}"
        if key in done:
          continue
        page = await browser.new_page(viewport={"width": 1280, "height": 1024})
        try:
          # saved pages can reference remote resources that never finish loading: wait for the DOM, then 2 s
          await page.goto((INTERA11Y / row["page"]).resolve().as_uri(), wait_until="domcontentloaded", timeout=60_000)
          await page.wait_for_timeout(2000)
          keep, reason, evidence = await decide(page, row)
        except Exception as error:  # a page that cannot be loaded is out of scope for every system
          keep, reason, evidence = False, f"page could not be checked: {type(error).__name__}", str(error)[:120]
        finally:
          await page.close()
        writer.writerow({"case_id": row["case_id"], "dataset": row["dataset"], "sc": row["sc"],
                         "scope": row["scope"], "page": row["page"], "keep": int(keep), "reason": reason,
                         "evidence": evidence})
        stream.flush()
        if not keep:
          log.exclude(f"D2-{row['dataset']}", row["case_id"], f"out of scope: {reason}", rule="eval/d2_filter.py")
        if i % 25 == 0:
          print(f"{i + 1}/{len(cases)}", flush=True)
      await browser.close()


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument("--dataset", choices=("expert", "conformance", "all"), default="all")
  parser.add_argument("--cases", default="")
  args = parser.parse_args(argv)
  wanted = set(filter(None, args.cases.split(","))) or None
  datasets = ("expert", "conformance") if args.dataset == "all" else (args.dataset,)
  cases = [r for d in datasets for r in rows(d, wanted)]
  done = set()
  if OUT.exists():
    with OUT.open(encoding="utf-8") as stream:
      done = {f"{r['dataset']}:{r['case_id']}" for r in csv.DictReader(stream)}
  asyncio.run(run(cases, done))
  with OUT.open(encoding="utf-8") as stream:
    scope = list(csv.DictReader(stream))
  summary: dict[str, dict[str, int]] = {}
  for r in scope:
    s = summary.setdefault(f"{r['dataset']} {r['sc']}", {"cases": 0, "kept": 0})
    s["cases"] += 1
    s["kept"] += int(r["keep"])
  print(json.dumps(summary, indent=2))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
