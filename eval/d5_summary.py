"""D5 descriptive summary (before expert labels): exploration, candidates, verdicts on the sample. Free.

  python -m eval.d5_summary

Weighted figures use the stored sampling weights (stratum size / sampled), i.e. estimates for all candidates.
"Among AccessGraph's findings" always: no figure here is a precision; that needs the expert labels.
Output: results/d5/SUMMARY.md + summary.json.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict

from eval import d5


def main() -> int:
  apps = d5.apps()
  population = json.loads((d5.OUT / "population.json").read_text())
  with (d5.OUT / "sample.csv").open(encoding="utf-8") as stream:
    sample = list(csv.DictReader(stream))
  verdicts = d5._verdicts()
  per_app = {}
  for name, spec in apps.items():
    graph_path = d5.RUNS / name / "explore" / "graph.json"
    graph = json.loads(graph_path.read_text()) if graph_path.exists() else {"nodes": [], "edges": []}
    depths = [n.get("depth") for n in graph["nodes"] if n.get("depth") is not None]
    per_app[name] = {"framework": spec.get("framework", ""), "states": len(graph["nodes"]),
                     "transitions": len(graph["edges"]), "states_depth_1plus": sum(1 for d in depths if d >= 1),
                     "candidates": population["by_app"].get(name, 0), "judged": 0, "violation": 0}
  key = lambda r: (r["app"], r["candidate_id"])  # noqa: E731
  decision = {key(r): str(verdicts.get(key(r), {}).get("decision", "missing")) for r in sample}
  followed = sum(1 for r in sample if verdicts.get(key(r), {}).get("followed_up"))
  counts = Counter(decision.values())
  by_dir, by_depth, by_type = defaultdict(Counter), defaultdict(Counter), defaultdict(Counter)
  weighted = Counter()
  for r in sample:
    d = decision[key(r)]
    per_app[r["app"]]["judged"] += 1
    per_app[r["app"]]["violation"] += d == "violation"
    by_dir[r["direction"]][d] += 1
    by_depth["0" if r["depth"] == "0" else ">=1"][d] += 1
    by_type[r["type"]][d] += 1
    weighted[d] += float(r["weight"])
  violations = [r for r in sample if decision[key(r)] == "violation"]
  w_viol = sum(float(r["weight"]) for r in violations)
  w_deep = sum(float(r["weight"]) for r in violations if r["depth"] != "0")
  w_trans = sum(float(r["weight"]) for r in violations if r["direction"] != "state-local")
  export_dir = d5.OUT / "export"
  exported = 0
  if (export_dir / "labelling_sheet.csv").exists():
    with (export_dir / "labelling_sheet.csv").open(encoding="utf-8") as stream:
      exported = sum(1 for _ in csv.DictReader(stream))
  out = {
    "apps": per_app, "candidates": population["candidates"], "sampled": len(sample), "decisions": dict(counts),
    "followed_up": followed,
    "violations_depth_1plus": sum(1 for r in violations if r["depth"] != "0"),
    "violations_by_direction": {k: v["violation"] for k, v in by_dir.items()},
    "weighted_share_violation": w_viol / sum(weighted.values()) if weighted else None,
    "weighted_share_of_violations_depth_1plus": w_deep / w_viol if w_viol else None,
    "weighted_share_of_violations_transition_evidence": w_trans / w_viol if w_viol else None,
    "exported": exported,
  }
  lines = ["# D5 summary (before expert labels)", "",
           f"{len(apps)} apps; {sum(a['states'] for a in per_app.values())} states, "
           f"{sum(a['transitions'] for a in per_app.values())} transitions; {population['candidates']:,} candidates; "
           f"{len(sample)} judged (stratified sample); {exported} exported for the experts.", "",
           "| App | States (depth >= 1) | Transitions | Candidates | Judged | Violation verdicts |", "|---|---|---|---|---|---|"]
  for name, a in per_app.items():
    lines.append(f"| {name} | {a['states']} ({a['states_depth_1plus']}) | {a['transitions']} | {a['candidates']:,} | "
                 f"{a['judged']} | {a['violation']} |")
  lines += ["", f"Verdicts on the sample: {dict(counts)} ({followed} uncertain first verdicts resolved by follow-up).", "",
            "| Direction | " + " | ".join(sorted(counts)) + " |", "|---|" + "---|" * len(counts)]
  for k, c in sorted(by_dir.items()):
    lines.append(f"| {k} | " + " | ".join(str(c[d]) for d in sorted(counts)) + " |")
  lines += ["", "| Depth | " + " | ".join(sorted(counts)) + " |", "|---|" + "---|" * len(counts)]
  for k, c in sorted(by_depth.items()):
    lines.append(f"| {k} | " + " | ".join(str(c[d]) for d in sorted(counts)) + " |")
  lines += ["", "| Type | " + " | ".join(sorted(counts)) + " |", "|---|" + "---|" * len(counts)]
  for k, c in sorted(by_type.items()):
    lines.append(f"| {k} | " + " | ".join(str(c[d]) for d in sorted(counts)) + " |")
  fmt = lambda x: "–" if x is None else f"{100 * x:.1f}%"  # noqa: E731
  lines += ["", "Weighted estimates over all candidates (sampling weights):",
            f"- share of candidates judged a violation: {fmt(out['weighted_share_violation'])}",
            f"- among AccessGraph's violation verdicts, share at depth >= 1: "
            f"{fmt(out['weighted_share_of_violations_depth_1plus'])}",
            f"- among AccessGraph's violation verdicts, share whose evidence is a transition (backward or forward): "
            f"{fmt(out['weighted_share_of_violations_transition_evidence'])}"]
  (d5.OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
  (d5.OUT / "summary.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
  print("\n".join(lines))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
