"""Single-state VLM baselines on recorded states (regime R2; EVALUATION_SPEC Section 5, Baselines).

  python -m eval.adapters.vlm_baselines --mode batch|criterion --cases bs-sem-114,co-sem-058 [--stage dev]

Both see what a single-state checker sees: the state's recorded screenshot and its HTML (scripts, styles and SVG
drawing data removed), with the main model through OpenRouter, no history and no other state.

- batch: one call per state, asking for violations of the success criteria AccessGraph's types map to.
- criterion: one call per state and criterion, only for the criteria that have a case in that state.

The model names each violating element with a CSS selector; selectors are resolved in the served state (scripts
disabled, at its own route) to an XPath, and a finding counts for a case when it names one of the case's criteria
on the case's element (or anywhere, for page-level types). Answers are cached (results/cache/vlm) and charged to
the cost ledger. Results: results/<dataset>/vlm_<mode>/<model>/<case>.json and states/<key>.json.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from eval.adapters.ag_single import main_config  # noqa: E402
from eval.adapters.recorded import XPATH_JS, finding_matches, items, serve_state  # noqa: E402
from eval.cost import BudgetExceeded, CostLedger  # noqa: E402

CACHE = ROOT / "results" / "cache" / "vlm"
MAX_HTML_CHARS = 60_000
MAX_CALL_USD = 0.02

# WCAG 2.2 success criteria of AccessGraph's types (frozen mapping), with their normative text, shortened.
CRITERIA = {
  "1.1.1": "Non-text Content: all non-text content presented to the user has a text alternative that serves the equivalent purpose.",
  "1.2.2": "Captions (Prerecorded): captions are provided for all prerecorded audio content in synchronized media.",
  "1.3.1": "Info and Relationships: information, structure and relationships conveyed through presentation can be programmatically determined or are available in text.",
  "1.3.5": "Identify Input Purpose: the purpose of each input field collecting information about the user can be programmatically determined (autocomplete) when it serves a listed input purpose.",
  "1.3.6": "Identify Purpose: the purpose of user interface components, icons and regions can be programmatically determined.",
  "2.4.2": "Page Titled: web pages have titles that describe topic or purpose.",
  "2.4.4": "Link Purpose (In Context): the purpose of each link can be determined from the link text alone or from the link text together with its programmatically determined link context.",
  "2.4.6": "Headings and Labels: headings and labels describe topic or purpose.",
  "3.1.1": "Language of Page: the default human language of each web page can be programmatically determined.",
  "3.1.2": "Language of Parts: the human language of each passage or phrase in the content can be programmatically determined.",
  "3.3.1": "Error Identification: if an input error is automatically detected, the item that is in error is identified and the error is described to the user in text.",
  "4.1.2": "Name, Role, Value: for all user interface components, the name and role can be programmatically determined; states, properties and values can be programmatically determined and set; and changes are notified to user agents.",
}

SYSTEM = ("You are a web accessibility auditor. You check one state of a web page, given as a screenshot and its "
          "HTML, against WCAG 2.2 success criteria. Report only violations that this page state shows. For each "
          "violation give the success criterion number, a CSS selector that matches exactly the violating element in "
          "the given HTML (for a page-level problem such as the page title or the page language, use \"html\"), the "
          "element's text, and a one-sentence reason. Return an empty list when you find no violation.")

SCHEMA = {
  "type": "object", "additionalProperties": False, "required": ["violations"],
  "properties": {"violations": {"type": "array", "items": {
    "type": "object", "additionalProperties": False, "required": ["criterion", "selector", "element_text", "reason"],
    "properties": {"criterion": {"type": "string"}, "selector": {"type": "string"},
                   "element_text": {"type": "string"}, "reason": {"type": "string"}}}}},
}


def clean_html(dom: str) -> str:
  dom = re.sub(r"<!--.*?-->", "", dom, flags=re.DOTALL)
  dom = re.sub(r"<(script|style|noscript)\b[^>]*>.*?</\1>", "", dom, flags=re.DOTALL | re.IGNORECASE)
  dom = re.sub(r"(<svg\b[^>]*>).*?</svg>", r"\1</svg>", dom, flags=re.DOTALL | re.IGNORECASE)
  dom = re.sub(r"\s+", " ", dom)
  return dom[:MAX_HTML_CHARS]


def user_prompt(criteria: list[str], html: str) -> str:
  listed = "\n".join(f"- {sc} {CRITERIA[sc]}" for sc in criteria)
  return f"Success criteria to check:\n{listed}\n\nHTML of the page state:\n{html}"


class CachedVLM:
  def __init__(self, model: str, ledger: CostLedger, stage: str):
    from src.analysis.confirmation.providers.registry import build_confirmation_client
    self.config = main_config(model)
    self.client = build_confirmation_client(self.config)
    self.ledger, self.stage = ledger, stage
    self.spent = 0.0

  def ask(self, user: str, image_url: str) -> tuple[dict, float]:
    key = hashlib.sha256(json.dumps([self.config.model, SYSTEM, user, SCHEMA,
                                     hashlib.sha256(image_url.encode()).hexdigest()]).encode()).hexdigest()
    path = CACHE / key[:2] / f"{key}.json"
    if path.exists():
      saved = json.loads(path.read_text(encoding="utf-8"))
      return json.loads(saved["raw_content"]), saved["cost_usd"]
    self.ledger.check(self.stage, planned_usd=MAX_CALL_USD)
    response = self.client.complete_json(system=SYSTEM, user=user, schema=SCHEMA, schema_name="w4a_vlm_audit",
                                         image_data_urls=[image_url])
    cost = response.estimated_cost_usd
    if cost is None:
      raise BudgetExceeded(f"{self.config.model} returned no cost")
    self.ledger.charge(self.stage, cost, run_id=f"vlm-{self.config.model}", note="vlm baseline")
    self.spent += cost
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"model": self.config.model, "raw_content": response.raw_content, "cost_usd": cost}),
                    encoding="utf-8")
    return json.loads(response.raw_content), cost


async def _resolve(url: str, selectors: list[str]) -> dict[str, str | None]:
  from playwright.async_api import async_playwright
  out: dict[str, str | None] = {}
  async with async_playwright() as p:
    browser = await p.chromium.launch()
    page = await browser.new_page()
    await page.goto(url, wait_until="load")
    for selector in selectors:
      try:
        handles = await page.query_selector_all(selector)
        out[selector] = await handles[0].evaluate(XPATH_JS) if len(handles) == 1 else None
      except Exception:  # an invalid selector resolves to nothing
        out[selector] = None
    await browser.close()
  return out


def judge_state(item: dict, criteria_sets: list[list[str]], vlm: CachedVLM, out: Path) -> dict:
  if out.exists():
    return json.loads(out.read_text(encoding="utf-8"))
  state_dir = ROOT / item["run_dir"] / "states" / item["state_id"]
  html = clean_html((state_dir / "dom.html").read_text(encoding="utf-8"))
  image = "data:image/png;base64," + base64.b64encode((state_dir / "screenshot.png").read_bytes()).decode()
  findings, cost, calls = [], 0.0, 0
  for criteria in criteria_sets:
    answer, c = vlm.ask(user_prompt(criteria, html), image)
    cost, calls = cost + c, calls + 1
    findings += [{**v, "asked": criteria} for v in answer.get("violations") or []]
  server, url = serve_state(item)
  try:
    resolved = asyncio.run(_resolve(url, sorted({f["selector"] for f in findings if f["selector"]})))
  finally:
    server.shutdown()
  for f in findings:
    f["xpath"] = "/html[1]" if f["selector"].strip().lower() == "html" else resolved.get(f["selector"])
  result = {"state_key": item["state_key"], "calls": calls, "cost_usd": cost, "findings": findings,
            "unresolved_selectors": sum(1 for f in findings if not f["xpath"]), "html_chars": len(html)}
  out.parent.mkdir(parents=True, exist_ok=True)
  out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
  return result


def decide(item: dict, state: dict) -> str:
  hit = any(finding_matches(item, str(f["criterion"]).strip(), f["xpath"]) for f in state["findings"])
  return "violation" if hit else "no_violation"


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument("--mode", choices=("batch", "criterion"), required=True)
  parser.add_argument("--cases", default="")
  parser.add_argument("--model", default="openai/gpt-6-luna")
  parser.add_argument("--stage", default="dev")
  parser.add_argument("--dataset", default="dev")
  args = parser.parse_args(argv)
  wanted = set(filter(None, args.cases.split(",")))
  ledger = CostLedger(ROOT / "results" / "cost_ledger.json")
  vlm = CachedVLM(args.model, ledger, args.stage)
  out_dir = ROOT / "results" / args.dataset / f"vlm_{args.mode}" / args.model.replace("/", "-")
  by_state = defaultdict(list)
  for item in items():
    if item["state_id"] and (not wanted or item["case_id"] in wanted):
      item["state_key"] = hashlib.sha1(f"{item['run_dir']}|{item['state_id']}".encode()).hexdigest()[:12]
      by_state[item["state_key"]].append(item)
  for key, group in by_state.items():
    if args.mode == "batch":
      sets = [sorted(CRITERIA)]
    else:
      sets = [[sc] for sc in sorted({sc for i in group for sc in i["criteria"] if sc in CRITERIA})]
    state = judge_state(group[0], sets, vlm, out_dir / "states" / f"{key}.json")
    for item in group:
      result = {"case_id": item["case_id"], "candidate_type": item["candidate_type"], "state_key": key,
                "handover": item["handover"], "prediction": decide(item, state),
                "cost_usd": state["cost_usd"] / len(group)}
      (out_dir / f"{item['case_id']}.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
      print(item["case_id"], result["prediction"], f"state ${state['cost_usd']:.4f} calls {state['calls']}",
            f"unresolved {state['unresolved_selectors']}/{len(state['findings'])}", flush=True)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
