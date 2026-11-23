"""Rampa (pinned df32363) on recorded states, judgment only (regime R2; EVALUATION_SPEC Section 5, Baselines).

  python -m eval.adapters.rampa_state --cases bs-sem-114,co-sem-052 [--model openai/gpt-6-luna] [--stage dev]

Each case's state is served statically (eval/adapters/recorded.py) and checked once with `rampa check` as a user
runs it: the main model through OpenRouter (`--model openrouter:<model>`), JSON report, its own judgment cache in
results/cache/rampa (re-runs are free), no probes. Rampa sends no temperature on OpenRouter, so it runs unpatched.

Its cost is charged to the cost ledger from the token counts in its report and the dated price table. Readings,
both from the same run (spec): `default` = findings at or above Rampa's threshold (what fails `rampa check`);
`review` = also findings below the threshold and items sent to review; `judged` = only `default` findings whose
source is the model's judgment. Results: results/<dataset>/rampa/<model>/<case>.json.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from eval.adapters.recorded import XPATH_JS, finding_matches, items, serve_state  # noqa: E402
from eval.cost import CostLedger  # noqa: E402
from eval.intera11y_dev import _env  # noqa: E402

from eval.paths import RAMPA  # noqa: E402
CLI = RAMPA / "dist" / "cli.mjs"
CACHE = ROOT / "results" / "cache" / "rampa"
PRICES = ROOT / "eval" / "prices_2026-11-16.yaml"
EST_STATE_USD = 0.004


def browser_path() -> str:
  base = Path.home() / "Library" / "Caches" / "ms-playwright"
  found = sorted(base.glob("chromium-*/chrome-mac*/*.app/Contents/MacOS/*"))
  if not found:
    raise FileNotFoundError("no Playwright Chromium found; run `playwright install chromium`")
  return str(found[-1])


def price(model: str) -> tuple[float, float]:
  table = yaml.safe_load(PRICES.read_text(encoding="utf-8"))["models"][model]
  return float(table["input"]), float(table["output"])


def rampa_env() -> dict:
  env = {k: v for k, v in _env().items() if not k.startswith("RAMPA_")}
  env.update({"RAMPA_BROWSER_PATH": browser_path(), "RAMPA_LOCALE": "en", "NO_COLOR": "1"})
  return env


def run_rampa(url: str, out_file: Path, model: str) -> dict:
  env = rampa_env()
  work = out_file.parent / "work"
  work.mkdir(parents=True, exist_ok=True)  # cwd: no rampa.config or .env applies
  args = ["node", str(CLI), "check", url, "--model", f"openrouter:{model}", "--format", "json", "-o", str(out_file),
          "--fail-on", "none", "--cache-dir", str(CACHE)]
  done = subprocess.run(args, cwd=work, env=env, capture_output=True, text=True, timeout=900)
  if not out_file.exists():
    raise RuntimeError(f"rampa exit {done.returncode}: {done.stderr[-600:]}")
  return json.loads(out_file.read_text(encoding="utf-8"))


async def _xpaths_for(url: str, refs: list[str]) -> dict[str, str | None]:
  from playwright.async_api import async_playwright
  out: dict[str, str | None] = {}
  async with async_playwright() as p:
    browser = await p.chromium.launch()
    page = await browser.new_page()
    await page.goto(url, wait_until="load")
    for ref in refs:
      try:
        handle = await page.query_selector(ref)
        out[ref] = await handle.evaluate(XPATH_JS) if handle else None
      except Exception:  # refs into shadow roots or frames are not plain selectors
        out[ref] = None
    await browser.close()
  return out


def findings(report: dict, url: str) -> list[dict]:
  rows = []
  for level, key in (("default", "findings"), ("low", "belowThreshold"), ("review", "needsReview")):
    for f in report.get(key) or []:
      rows.append({"level": level, "criterion": f.get("criterion"), "source": f.get("source"),
                   "ref": f.get("ref") or f.get("target"), "subject": f.get("subject"),
                   "message": (f.get("message") or "")[:300], "ruleId": f.get("ruleId"),
                   "confidence": f.get("confidence")})
  refs = sorted({r["ref"] for r in rows if r["ref"]})
  if "w4aXpaths" in report:  # live handover: resolved on the replayed page itself
    xpaths = report["w4aXpaths"]
  else:
    xpaths = asyncio.run(_xpaths_for(url, refs)) if refs else {}
  for r in rows:
    r["xpath"] = xpaths.get(r["ref"]) if r["ref"] else None
  return rows


def predictions(item: dict, rows: list[dict]) -> dict[str, str]:
  def hit(levels, judged_only=False):
    return any(r["level"] in levels and finding_matches(item, r["criterion"], r["xpath"])
               and (not judged_only or r["source"] == "judgment") for r in rows)
  yes = lambda flag: "violation" if flag else "no_violation"  # noqa: E731
  return {"default": yes(hit({"default"})), "review": yes(hit({"default", "low", "review"})),
          "judged": yes(hit({"default"}, judged_only=True))}


def run_case(item: dict, model: str, stage: str, ledger: CostLedger, out_dir: Path) -> dict:
  out = out_dir / f"{item['case_id']}.json"
  if out.exists():
    return json.loads(out.read_text(encoding="utf-8"))
  if not item["state_id"]:
    result = {"case_id": item["case_id"], "state": "no_state", "predictions": {}, "cost_usd": 0.0}
  else:
    ledger.check(stage, EST_STATE_USD)
    started = time.perf_counter()
    report, handover = None, item["handover"]
    report_file = out_dir / "reports" / f"{item['case_id']}.json"
    live = item.get("live")  # {"base_url", "init_script"}: the app runs locally; the state is replayed in it
    if live:
      from eval.adapters.live_state import rampa_check_live
      outcome = rampa_check_live(ROOT / item["run_dir"], item["state_id"], report_file, model, rampa_env(),
                                 base_url=live.get("base_url"), init_script=live.get("init_script"), cache_dir=CACHE)
      if outcome.get("handover") == "live":
        report, handover, url = json.loads(report_file.read_text(encoding="utf-8")), "live", outcome.get("url") or ""
        rows = findings(report, url)
      else:  # spec step 3: the static handover, logged
        handover = "static-fallback"
        print(f"{item['case_id']}: live handover failed ({str(outcome.get('error'))[:160]}); static fallback",
              flush=True)
    if report is None:
      server, url = serve_state(item)
      try:
        report = run_rampa(url, report_file, model)
        rows = findings(report, url)
      finally:
        server.shutdown()
    usage = report.get("usage") or {}
    p_in, p_out = price(model)
    # Rampa adds the tokens of cached answers to its totals too: the case's cost is all of them (what a fresh run
    # pays), the ledger is charged only the share of calls that went to the model now.
    cost = (usage.get("inputTokens", 0) * p_in + usage.get("outputTokens", 0) * p_out) / 1e6
    calls, cached = usage.get("calls", 0), usage.get("cachedCalls", 0)
    charged = cost * calls / (calls + cached) if calls + cached else 0.0
    if charged:
      ledger.charge(stage, charged, run_id=f"rampa-{model}", note=f"rampa {item['case_id']}")
    result = {"case_id": item["case_id"], "candidate_type": item["candidate_type"], "state": "complete",
              "handover": handover, "url": url, "predictions": predictions(item, rows), "findings": rows,
              "usage": usage, "cost_usd": round(cost, 6), "charged_usd": round(charged, 6), "seconds": round(time.perf_counter() - started, 1),
              "errors": report.get("errors") or []}
  out.parent.mkdir(parents=True, exist_ok=True)
  out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
  return result


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument("--cases", default="")
  parser.add_argument("--model", default="openai/gpt-6-luna")
  parser.add_argument("--stage", default="dev")
  parser.add_argument("--dataset", default="dev")
  args = parser.parse_args(argv)
  wanted = set(filter(None, args.cases.split(",")))
  selected = [i for i in items() if not wanted or i["case_id"] in wanted]
  from eval.external_check import verify
  verify()  # the clones must carry exactly the frozen patches
  ledger = CostLedger(ROOT / "results" / "cost_ledger.json")
  out_dir = ROOT / "results" / args.dataset / "rampa" / args.model.replace("/", "-")
  for item in selected:
    result = run_case(item, args.model, args.stage, ledger, out_dir)
    print(item["case_id"], result.get("state"), result.get("predictions"), f"${result.get('cost_usd', 0):.4f}",
          flush=True)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
