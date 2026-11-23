"""Phase 3 dev linking: build candidates for every dev capture and tie each case to its candidates (free).

  python -m eval.dev_link

Seeded run: the student's seeded scorer (`src/analysis/evaluation/seeded_scorer.py`) finds the candidates that
recover the registry expectation. Clean twin: the candidates of the same type, in the state with the same benchmark
state id, on the same element (same XPath, else the same id- or test-id-based selector). The clean element is a
no-violation control (the clean app is semantically correct by the dataset's own acceptance rule).

Writes `results/dev/gold.csv` (one row per case: `<variant>` expects violation, `<variant>~clean` expects
no_violation) and `results/dev/links.jsonl` (which candidates in which run belong to each gold row).
A case whose clean capture failed has no clean row; this is logged in `results/exclusions.csv`.
"""
from __future__ import annotations

import csv
import json
import sys
from dataclasses import asdict, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from eval.predictions import GoldCase  # noqa: E402
from eval.runlog import RunLog  # noqa: E402

RUNS = ROOT / "runs" / "w4a-dev"
RESULTS = ROOT / "results" / "dev"
REGISTRY = ROOT / "benchmarks" / "registry" / "benchmark-case-registry.json"
PAGE_LEVEL = {"page-title-not-descriptive", "lang-mismatch"}


def _candidates(run_dir: Path) -> list[dict]:
  from src.analysis.candidates import build_semantic_candidates
  path = run_dir / "candidates" / "candidates.jsonl"
  if not path.exists():
    build_semantic_candidates(run_dir)
  return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _states(run_dir: Path) -> dict[str, dict]:
  metadata = json.loads((run_dir / "run_metadata.json").read_text(encoding="utf-8"))
  states = {s["state_id"]: s for s in metadata.get("states") or []}
  for state_id, state in states.items():  # depth = number of parents
    depth, parent = 0, state.get("parent_state_id")
    while parent and depth < 50:
      depth, parent = depth + 1, (states.get(parent) or {}).get("parent_state_id")
    state["depth"] = depth
  return states


def _element_key(candidate: dict) -> tuple[str, str, str]:
  ref = (candidate.get("element_refs") or [{}])[0]
  return str(ref.get("bucket") or ""), str(ref.get("xpath") or ""), str(ref.get("selector") or "")


def _stable_selector(selector: str) -> bool:
  return "#" in selector or "data-testid" in selector


def clean_twin_ids(seeded: list[dict], seeded_states: dict, clean: list[dict], clean_states: dict) -> list[str]:
  wanted = []
  for candidate in seeded:
    state = seeded_states.get(candidate["state_id"]) or {}
    wanted.append((candidate["candidate_type"], state.get("benchmark_state_id"), state.get("focused_state_name"),
                   *_element_key(candidate)))
  ids = []
  for candidate in clean:
    state = clean_states.get(candidate["state_id"]) or {}
    bucket, xpath, selector = _element_key(candidate)
    for ctype, bsid, fname, w_bucket, w_xpath, w_selector in wanted:
      if (candidate["candidate_type"] != ctype or state.get("benchmark_state_id") != bsid
          or state.get("focused_state_name") != fname or bucket != w_bucket):
        continue
      if (xpath and xpath == w_xpath) or (_stable_selector(selector) and selector == w_selector):
        ids.append(candidate["candidate_id"])
        break
  return ids


def link() -> dict:
  from src.analysis.evaluation.benchmark_registry import load_benchmark_registry
  from src.analysis.evaluation.seeded_scorer import SeededScorerOptions, score_seeded_experiment

  registry = load_benchmark_registry(REGISTRY)
  variants = {v["variant_id"]: v for v in registry["variants"]}
  log = RunLog(ROOT / "results")
  gold: list[GoldCase] = []
  links: list[dict] = []
  for configuration in registry["seeded_configurations"]:
    profile, app = configuration["configuration_id"], configuration["app"]
    base = RUNS / ("checkout" if app == "checkout-flow" else "booking") / profile
    seeded_dir, clean_dir = base / "seeded", base / "clean"
    if not (seeded_dir / "run_metadata.json").exists():
      for seed in configuration["seed_ids"]:
        log.exclude("dev", seed, "seeded capture failed", rule="dev_acquire")
      continue
    seeded_all = {c["candidate_id"]: c for c in _candidates(seeded_dir)}
    seeded_states = _states(seeded_dir)
    score = score_seeded_experiment(SeededScorerOptions(run_dir=seeded_dir, config_id=profile, registry_path=REGISTRY,
                                                        score_run_id="dev_link", overwrite=True))
    clean_ok = (clean_dir / "run_metadata.json").exists()
    clean_all = _candidates(clean_dir) if clean_ok else []
    clean_states = _states(clean_dir) if clean_ok else {}
    for result in score.summary["results"]:
      seed = result["seed_id"]
      variant = variants[seed]
      ctype = result["candidate_type"]
      matched = [m["candidate_id"] for m in result.get("matched_candidates") or []]
      # incoming-variant clones of a matched candidate show the same element; they belong to the case too
      clones = [cid for cid, c in seeded_all.items() if c.get("incoming_variant_of") in matched]
      seeded_ids = sorted(set(matched + clones))
      matched_states = result.get("matched_states") or []
      depth = max((seeded_states.get(s["state_id"], {}).get("depth", 0) for s in matched_states), default=0)
      common = dict(dataset="dev", app=app, candidate_type=ctype, direction="none",
                    subgroup=str(variant.get("graph_context_needed") or ""), requires_input=False, depth=depth,
                    split="dev", page_level=ctype in PAGE_LEVEL)
      gold.append(GoldCase(case_id=seed, expected="violation", case_kind="seeded_positive", **common))
      links.append({"case_id": seed, "profile": profile, "kind": "seeded", "run_dir": str(seeded_dir.relative_to(ROOT)),
                    "candidate_ids": seeded_ids, "status": result["status"], "state_status": result["state_status"],
                    "evidence_status": result["evidence_status"], "candidate_status": result["candidate_status"]})
      if not clean_ok:
        log.exclude("dev", f"{seed}~clean", "clean twin capture failed (runner asserts seeded behaviour)",
                    rule="dev_acquire")
        continue
      twin_ids = clean_twin_ids([seeded_all[c] for c in seeded_ids], seeded_states, clean_all, clean_states)
      gold.append(GoldCase(case_id=f"{seed}~clean", expected="no_violation", case_kind="clean_twin", **common))
      links.append({"case_id": f"{seed}~clean", "profile": profile, "kind": "clean",
                    "run_dir": str(clean_dir.relative_to(ROOT)), "candidate_ids": sorted(twin_ids),
                    "status": "linked" if twin_ids else "no_candidate_on_clean_element"})
  RESULTS.mkdir(parents=True, exist_ok=True)
  with (RESULTS / "gold.csv").open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=[f.name for f in fields(GoldCase)])
    writer.writeheader()
    for case in gold:
      writer.writerow(asdict(case))
  (RESULTS / "links.jsonl").write_text("".join(json.dumps(l, ensure_ascii=False) + "\n" for l in links),
                                       encoding="utf-8")
  seeded = [l for l in links if l["kind"] == "seeded"]
  clean = [l for l in links if l["kind"] == "clean"]
  summary = {"cases": len(seeded), "recovered": sum(bool(l["candidate_ids"]) for l in seeded),
             "clean_twins": len(clean), "clean_twins_with_candidate": sum(bool(l["candidate_ids"]) for l in clean),
             "candidates_to_judge": sum(len(l["candidate_ids"]) for l in links)}
  (RESULTS / "link_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
  return summary


if __name__ == "__main__":
  print(json.dumps(link(), indent=2))
