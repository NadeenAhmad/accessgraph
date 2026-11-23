"""Phase 3 dev judging: judge the case-linked candidates of the dev captures and score them.

  python -m eval.dev_judge --system AG-main --model anthropic/claude-haiku-5.5 --dry-run
  python -m eval.dev_judge --system AG-main --model anthropic/claude-haiku-5.5
  python -m eval.dev_judge --system AG-main --model openai/gpt-6-luna --score-only

Every paid answer goes through the response cache (results/cache) and then the budget guard (eval/cost.py), so an
interrupted run repeats no paid call: re-run the same command. Prompts and raw responses are saved in each run
directory under confirmations/<confirmation_run_id>/. On HTTP 402 / insufficient credits the step stops at once
and is logged as stopped_out_of_credits.

Prediction per gold row = strongest verdict over its linked candidates (violation > uncertain > no_violation);
no linked candidate = not_applicable (never judged; counts as negative in the strict view).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from eval.cost import BudgetedClient, CostLedger, Estimate, TopUpNeeded, preflight  # noqa: E402
from eval.matching import STRENGTH  # noqa: E402
from eval.predictions import PredictionRow, read_gold, write_rows  # noqa: E402
from eval.runlog import RunLog, new_run_id  # noqa: E402
from eval.scoring import breakdown, join, score_cases  # noqa: E402

RESULTS = ROOT / "results"
DEV = RESULTS / "dev"
CACHE = RESULTS / "cache"
CHARS_PER_TOKEN = 3.6
IMAGE_TOKENS = 1_600
OUTPUT_TOKENS = 300
ESCALATION_MARGIN = 1.25
FOLLOW_UP = True  # W4A phase 2

SYSTEMS = {
  # name: (prompt family, context mode)
  "AG-main": ("v5", "adaptive_v2"),
  "AG-thesis": ("v4_1", "graph_context"),   # the student's configuration before C1-C4 (reference only)
  "AG-isolated": ("v5", "isolated_state"),
  "AG-graph": ("v5", "graph_context"),
}


def _config(system: str, provider: str, model: str, effort: str | None):
  from src.analysis.confirmation.models import ConfirmationConfig
  from src.analysis.confirmation.providers.registry import get_confirmation_provider_spec, resolve_confirmation_config
  family, mode = SYSTEMS[system]
  vision = get_confirmation_provider_spec(provider).screenshot_required
  prompt = f"confirm_{family}_{'vision' if vision else 'text'}"
  return resolve_confirmation_config(ConfirmationConfig(provider=provider, model=model, prompt_version=prompt,
                                                        context_mode=mode, effort=effort))


def _slug(text: str) -> str:
  return "".join(ch if ch.isalnum() else "-" for ch in text).strip("-").lower()


def _links() -> dict[str, list[dict]]:
  by_run: dict[str, list[dict]] = defaultdict(list)
  for line in (DEV / "links.jsonl").read_text(encoding="utf-8").splitlines():
    if line.strip():
      link = json.loads(line)
      by_run[link["run_dir"]].append(link)
  return by_run


class _Counting:
  """Free stand-in used for the estimate: records prompt sizes, answers no_violation."""
  provider, model = "fake", "estimate"

  def __init__(self):
    self.chars, self.images, self.calls = 0, 0, 0

  def confirm(self, prompt):
    from src.analysis.confirmation.models import ConfirmationProviderResponse
    self.calls += 1
    self.chars += len(prompt.system_prompt or "") + len(prompt.user_prompt or "")
    self.images += 1 if "vision" in prompt.prompt_version else 0
    content = json.dumps({"candidate_id": prompt.bundle.candidate_id, "candidate_type": prompt.bundle.candidate_type,
                          "state_id": prompt.bundle.state_id, "decision": "no_violation", "confidence": 0.5,
                          "reason": "estimate", "supporting_evidence": []})
    return ConfirmationProviderResponse(provider="fake", model="estimate", raw_content=content)


def estimate(config, price_in: float, price_out: float) -> Estimate:
  from dataclasses import replace
  from src.analysis.confirmation.runner import ConfirmationRunOptions, run_confirmation
  counter = _Counting()
  fake = config  # the counting client answers; nothing is sent
  for run_dir, links in _links().items():
    ids = tuple(sorted({cid for link in links for cid in link["candidate_ids"]}))
    if ids:
      run_confirmation(config=fake, client=counter, options=ConfirmationRunOptions(
        run_dir=ROOT / run_dir, confirmation_run_id="w4a-estimate", candidate_ids=ids, overwrite=True,
        save_prompts=False, save_raw_responses=False))
  calls = max(counter.calls, 1)
  per_call_in = (counter.chars / CHARS_PER_TOKEN + counter.images * IMAGE_TOKENS) / calls
  print(f"[estimate] {counter.calls} first-pass calls, ~{per_call_in:.0f} input tokens per call "
        f"({counter.images} with a screenshot); +{ESCALATION_MARGIN - 1:.0%} for history re-judging")
  return Estimate(calls=int(counter.calls * ESCALATION_MARGIN + 0.5), input_tokens_per_call=int(per_call_in),
                  output_tokens_per_call=OUTPUT_TOKENS, input_usd_per_million=price_in,
                  output_usd_per_million=price_out)


def judge(config, system: str, stage: str, run_id: str) -> tuple[float, int]:
  from src.analysis.confirmation.providers.base import ProviderOutOfCredits
  from src.analysis.confirmation.providers.caching import CachingConfirmationClient
  from src.analysis.confirmation.providers.registry import build_confirmation_client
  from src.analysis.confirmation.runner import ConfirmationRunOptions, run_confirmation

  ledger = CostLedger(RESULTS / "cost_ledger.json")
  budgeted = BudgetedClient(build_confirmation_client(config), ledger, stage, run_id=run_id)
  client = CachingConfirmationClient(budgeted, CACHE, parameters={"effort": config.effort})
  confirmation_run_id = _confirmation_run_id(config, system)
  try:
    for run_dir, links in sorted(_links().items()):
      ids = tuple(sorted({cid for link in links for cid in link["candidate_ids"]}))
      if not ids:
        continue
      run_confirmation(config=config, client=client, options=ConfirmationRunOptions(
        run_dir=ROOT / run_dir, confirmation_run_id=confirmation_run_id, candidate_ids=ids, overwrite=True,
        save_prompts=True, save_raw_responses=True, fail_fast=False))
      if FOLLOW_UP:  # W4A phase 2: the same uncertain follow-up as the other modes (no live page in dev captures)
        from src.analysis.confirmation.uncertain_followup import follow_up

        def rejudge(run_id, sample_ids, sample, _dir=ROOT / run_dir):
          sample_client = CachingConfirmationClient(budgeted, CACHE, parameters={"effort": config.effort,
                                                                                 "followup_sample": sample})
          run_confirmation(config=config, client=sample_client, options=ConfirmationRunOptions(
            run_dir=_dir, confirmation_run_id=run_id, candidate_ids=sample_ids, overwrite=True,
            save_prompts=True, save_raw_responses=True, fail_fast=False))

        follow_up(ROOT / run_dir, first_run_id=confirmation_run_id, judge=rejudge, state_url=lambda _sid: None,
                  allow_hosts=())
      print(f"  {run_dir}: {len(ids)} candidates (cache hits {client.hits}, paid {client.misses}, "
            f"${budgeted.spent:.4f})", flush=True)
  except ProviderOutOfCredits:
    raise
  return budgeted.spent, client.misses


TAG = ""  # set by --tag: a fix round gets its own confirmation run id, so earlier rounds stay on disk


def _confirmation_run_id(config, system: str) -> str:
  effort = f"-{config.effort}" if config.effort else ""
  return f"w4a-dev-{_slug(system)}-{_slug(config.model)}{effort}{'-' + TAG if TAG else ''}"


def predictions(config, system: str, run_id: str) -> tuple[list[PredictionRow], dict]:
  confirmation_run_id = _confirmation_run_id(config, system)
  rows, cost_by_case, details = [], {}, {}
  for run_dir, links in _links().items():
    path = ROOT / run_dir / "confirmations" / confirmation_run_id / "confirmations.jsonl"
    records = {}
    if path.exists():
      for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
          record = json.loads(line)
          records[record["candidate_id"]] = record
    if FOLLOW_UP:  # uncertain verdicts replaced by the follow-up majority where one exists
      from src.analysis.confirmation.uncertain_followup import final_decisions
      for cid, decision in final_decisions(ROOT / run_dir, confirmation_run_id).items():
        if cid in records and records[cid].get("decision") != decision:
          records[cid] = {**records[cid], "decision": decision}
    scopes = {}
    cand_path = ROOT / run_dir / "candidates" / "candidates.jsonl"
    if cand_path.exists():
      for line in cand_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
          cand = json.loads(line)
          scopes[cand["candidate_id"]] = cand.get("evidence_scope") or ""
    for link in links:
      best, cost, scope = "not_applicable", 0.0, ""
      for cid in link["candidate_ids"]:
        record = records.get(cid)
        decision = (record or {}).get("decision") or "error"
        cost += float((record or {}).get("estimated_cost_usd") or 0.0)
        if decision not in STRENGTH:
          decision = "error"
        if best == "not_applicable" or STRENGTH[decision] > STRENGTH.get(best, 0):
          best, scope = decision, scopes.get(cid, "")
      details[link["case_id"]] = {"prediction": best, "candidates": len(link["candidate_ids"]),
                                  "status": link.get("status")}
      rows.append(PredictionRow(run_id=run_id, system=system, config=confirmation_run_id, model=config.model,
                                run_idx=0, regime="R2", dataset="dev", case_id=link["case_id"],
                                prediction=best, evidence_scope=scope, cost_usd=round(cost, 6)))
  return rows, details


def error_buckets(gold, details) -> dict:
  buckets = Counter()
  for case in gold:
    d = details.get(case.case_id, {})
    p = d.get("prediction", "error")
    if case.expected == "violation":
      if not d.get("candidates"):
        buckets["positive: no candidate"] += 1
      elif p in ("uncertain", "not_applicable", "error"):
        buckets[f"positive: missing evidence ({p})"] += 1
      elif p == "no_violation":
        buckets["positive: wrong verdict"] += 1
    elif p == "violation":
      buckets["clean twin: wrong verdict (false positive)"] += 1
    elif p == "uncertain":
      buckets["clean twin: uncertain"] += 1
  return dict(buckets)


def report(system: str, config, rows: list[PredictionRow], details: dict, out: Path) -> dict:
  gold = read_gold(DEV / "gold.csv")
  joined = join(gold, {r.case_id: r.prediction for r in rows})
  views = {view: score_cases(joined, view).as_dict() for view in ("strict", "selective", "triage")}
  by_type = {k: m.as_dict() for k, m in breakdown(joined, "type").items()}
  by_app = {k: m.as_dict() for k, m in breakdown(joined, "app").items()}
  cost = sum(r.cost_usd for r in rows)
  summary = {"system": system, "model": config.model, "prompt_version": config.prompt_version,
             "context_mode": config.context_mode, "effort": config.effort, "cases": len(gold),
             "views": views, "by_type": by_type, "by_app": by_app, "errors": error_buckets(gold, details),
             "judge_cost_usd": round(cost, 4),
             "f1_per_dollar": round(views["strict"]["f1"] / cost, 1) if cost else None}
  out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
  return summary


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument("--system", choices=sorted(SYSTEMS), default="AG-main")
  parser.add_argument("--provider", default="openrouter-vision")
  parser.add_argument("--model", required=True)
  parser.add_argument("--effort", default=None)
  parser.add_argument("--stage", default="dev")
  parser.add_argument("--price-in", type=float, default=0.10)
  parser.add_argument("--price-out", type=float, default=0.50)
  parser.add_argument("--dry-run", action="store_true")
  parser.add_argument("--score-only", action="store_true")
  parser.add_argument("--tag", default="", help="name of a fix round, e.g. fix1")
  args = parser.parse_args(argv)
  global TAG
  TAG = args.tag

  config = _config(args.system, args.provider, args.model, args.effort)
  name = f"{_slug(args.system)}__{_slug(args.model)}{'-' + args.effort if args.effort else ''}{'__' + TAG if TAG else ''}"
  ledger = CostLedger(RESULTS / "cost_ledger.json")
  if not args.score_only:
    est = estimate(config, args.price_in, args.price_out)
    print(ledger.dry_run(args.stage, est))
    if args.dry_run:
      return 0
    try:
      print(preflight(ledger, args.stage, est.usd))
    except TopUpNeeded as exc:
      print(f"STOP: {exc}")
      return 3
    log = RunLog(RESULTS)
    run_id = new_run_id(_slug(args.system), "dev")
    row = log.start(run_id=run_id, stage=args.stage, system=args.system, dataset="dev", split="dev",
                    command=" ".join(["python -m eval.dev_judge", *(argv or sys.argv[1:])]))
    started = time.perf_counter()
    try:
      spent, paid = judge(config, args.system, args.stage, run_id)
    except Exception as exc:
      from src.analysis.confirmation.providers.base import ProviderOutOfCredits
      status = "stopped_out_of_credits" if isinstance(exc, ProviderOutOfCredits) else "failed"
      log.finish(row, status=status, notes=f"{type(exc).__name__}: {str(exc)[:200]}")
      print(f"STOP ({status}): {exc}")
      if status == "stopped_out_of_credits":
        print("OpenRouter is out of credits: top up, then re-run the same command (finished calls are cached).")
      return 2
    log.finish(row, status="done", cost_usd=spent, notes=f"paid calls {paid}, {time.perf_counter() - started:.0f}s")
  else:
    run_id = "score-only"
  rows, details = predictions(config, args.system, run_id)
  write_rows(DEV / "predictions" / f"{name}.csv", rows)
  (DEV / "scores").mkdir(parents=True, exist_ok=True)
  summary = report(args.system, config, rows, details, DEV / "scores" / f"{name}.json")
  s = summary["views"]["strict"]
  print(f"{args.system} {args.model}: P={s['precision']:.3f} R={s['recall']:.3f} F1={s['f1']:.3f} "
        f"cost=${summary['judge_cost_usd']:.4f} errors={summary['errors']}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
