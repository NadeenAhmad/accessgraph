"""Plain one-sentence versions of AccessGraph's explanations for the D5 review's reveal step (PI 2026-11-23: "too
much text ... explain in a simple way, not childish"). Paid, cached, stage `d5_review` (a few cents).

  python -m eval.d5_explain

For every one of the 165 items: AccessGraph's final verdict (with the follow-up majority) and its reason, rewritten
by the same model into one sentence that keeps the verdict and the main reason and adds nothing. The PI approved the
style on D5-187. Output (private, never in the public site): results/d5/export165/explanations.json.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "results" / "d5" / "export165"
SYSTEM = (
  "You rewrite an accessibility checker's explanation for accessibility experts. Write ONE plain, professional "
  "sentence of at most 30 words that keeps the checker's conclusion and its main reason. Use everyday words: no field "
  "or attribute names, no code, and none of these words: evidence, programmatic, saved, recorded, state, candidate, "
  "payload, href, DOM. Name the element by its visible text in quotes when the explanation gives it. Do not add any "
  "fact that the explanation does not contain, and do not soften or strengthen the conclusion. Call the checker "
  "'the tool'; never write 'I' or 'the checker'. Do not start with 'There is no violation' or 'No violation' (the "
  "verdict is shown separately); state the reason directly. If the tool could not decide, say what it could not "
  "tell.\n\nExample. Explanation: The link is named “Terms and conditions,” "
  "but its href is “#” and the saved destination evidence resolves it to the dashboard, whose title and headings "
  "describe dashboard content rather than terms and conditions. Its programmatic list-item context contains only the "
  "link text and does not clarify a different destination.\nSentence: The link says “Terms and conditions”, but "
  "it leads to the Dashboard page, which shows no terms and conditions.")
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["sentence"],
          "properties": {"sentence": {"type": "string"}}}
VERDICT = {"violation": "violation", "no_violation": "no violation", "uncertain": "could not decide"}


def _followup_reason(app: str, candidate_id: str, decision: str) -> str:
  from eval.d5 import CONFIRMATION_RUN_ID, RUNS
  for k in (1, 2, 3):
    path = RUNS / app / "explore" / "confirmations" / f"{CONFIRMATION_RUN_ID}-followup-s{k}" / "confirmations.jsonl"
    if not path.exists():
      continue
    for line in path.read_text(encoding="utf-8").split("\n"):
      if line.strip():
        rec = json.loads(line)
        if rec.get("candidate_id") == candidate_id and rec.get("decision") == decision and rec.get("reason"):
          return " ".join(str(rec["reason"]).split())
  return ""

def main() -> int:
  from eval.cost import CostLedger
  from eval.d5 import _verdicts
  from eval.dev_explore import BudgetedJsonClient
  from src.crawler.crawl.priority.llm_policy import LLMPolicyConfig, _build_client
  key = list(csv.DictReader((SRC / "key_do_not_share.csv").open(encoding="utf-8")))
  verdicts = _verdicts()
  client = BudgetedJsonClient(_build_client(LLMPolicyConfig(provider="openrouter", model="openai/gpt-6-luna")),
                              CostLedger(ROOT / "results" / "cost_ledger.json"), "d5-explain", stage="d5_review")
  out = {}
  for r in key:
    v = verdicts[(r["app"], r["candidate_id"])]
    decision, reason = v.get("decision"), " ".join(str(v.get("reason") or "").split())
    if v.get("followed_up"):  # the final verdict came from the follow-up re-judging: explain it with that reason
      reason = _followup_reason(r["app"], r["candidate_id"], decision) or reason
    user = f"Checker's verdict: {VERDICT.get(decision, decision)}.\nExplanation: {reason}\nSentence:"
    response = client.complete_json(system=SYSTEM, user=user, schema=SCHEMA, schema_name="plain_sentence", image_data_urls=[])
    sentence = json.loads(response.raw_content)["sentence"].strip()
    out[r["item_id"]] = {"decision": decision, "reason": reason, "sentence": sentence}
  (SRC / "explanations.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
  print(f"{len(out)} explanations, {client.misses} paid calls, ${client.spent:.4f}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
