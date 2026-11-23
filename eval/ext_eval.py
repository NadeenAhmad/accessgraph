"""Our 121 extension cases (course portal, finance portal): collect captures, link cases, judge (PI decision
2026-11-18: look at all datasets, incl. D1 cases, for the failure analysis).

  python -m eval.ext_eval collect     # captures from the extension tests' --basetemp (runs/w4a-ext/pytest)
  python -m eval.ext_eval link        # results/ext/gold.csv + links.jsonl (same rules as eval/dev_link.py)
  python -m eval.ext_eval judge --stage phase3_final --tag v11   # AG-main via eval/dev_judge.py

The extension (copied untracked from the dataset-extension branch into ./extension) captures each case clean and
seeded with the w4a-eval code. Linking and scoring follow the dev set exactly: the seeded run's case-linked candidates
are the positive, the same element in the clean run is the no-violation control.
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import sys
from dataclasses import asdict, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from eval.dev_link import PAGE_LEVEL, _candidates, _states, clean_twin_ids  # noqa: E402
from eval.predictions import GoldCase  # noqa: E402

RUNS = ROOT / "runs" / "w4a-ext"
RESULTS = ROOT / "results" / "ext"
APPS = {"cp": "course-portal", "fp": "finance-portal"}


def registry(app: str) -> Path:
  return ROOT / "extension" / "registry" / app / "benchmark-case-registry.json"


def collect() -> None:
  base = RUNS / "pytest"
  found = 0
  for metadata in sorted(base.rglob("run_metadata.json")):
    source = metadata.parent
    match = re.search(r"(cp|fp)_sem_(\d+)", str(source.relative_to(base)))
    if not match or source.name not in ("clean", "seeded"):
      continue
    app = APPS[match.group(1)]
    profile = f"{app}-{match.group(1)}-sem-{match.group(2)}"
    target = RUNS / app / profile / source.name
    if target.exists():
      shutil.rmtree(target)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("candidates", "confirmations", "scores"))
    found += 1
  print(f"collected {found} captures")


def link() -> None:
  from src.analysis.evaluation.benchmark_registry import load_benchmark_registry
  from src.analysis.evaluation.seeded_scorer import SeededScorerOptions, score_seeded_experiment
  gold, links, missing = [], [], []
  for app in APPS.values():
    reg = load_benchmark_registry(registry(app))
    variants = {v["variant_id"]: v for v in reg["variants"]}
    for configuration in reg["seeded_configurations"]:
      profile = configuration["configuration_id"]
      seeded_dir, clean_dir = RUNS / app / profile / "seeded", RUNS / app / profile / "clean"
      if not (seeded_dir / "run_metadata.json").exists():
        missing += configuration["seed_ids"]
        continue
      seeded_all = {c["candidate_id"]: c for c in _candidates(seeded_dir)}
      seeded_states = _states(seeded_dir)
      score = score_seeded_experiment(SeededScorerOptions(run_dir=seeded_dir, config_id=profile,
                                                          registry_path=registry(app), score_run_id="ext_link",
                                                          overwrite=True))
      clean_ok = (clean_dir / "run_metadata.json").exists()
      clean_all = _candidates(clean_dir) if clean_ok else []
      clean_states = _states(clean_dir) if clean_ok else {}
      for result in score.summary["results"]:
        seed = result["seed_id"]
        variant = variants[seed]
        ctype = result["candidate_type"]
        matched = [m["candidate_id"] for m in result.get("matched_candidates") or []]
        clones = [cid for cid, c in seeded_all.items() if c.get("incoming_variant_of") in matched]
        seeded_ids = sorted(set(matched + clones))
        matched_states = result.get("matched_states") or []
        depth = max((seeded_states.get(s["state_id"], {}).get("depth", 0) for s in matched_states), default=0)
        common = dict(dataset="dev", app=app, candidate_type=ctype, direction="none",
                      subgroup=str(variant.get("graph_context_needed") or ""), requires_input=False, depth=depth,
                      split="dev", page_level=ctype in PAGE_LEVEL)
        gold.append(GoldCase(case_id=seed, expected="violation", case_kind="seeded_positive", **common))
        links.append({"case_id": seed, "profile": profile, "kind": "seeded",
                      "run_dir": str(seeded_dir.relative_to(ROOT)), "candidate_ids": seeded_ids,
                      "status": result["status"]})
        if not clean_ok:
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
  (RESULTS / "links.jsonl").write_text("".join(json.dumps(l) + "\n" for l in links), encoding="utf-8")
  positives = sum(1 for g in gold if g.expected == "violation")
  no_cand = sum(1 for l in links if l["kind"] == "seeded" and not l["candidate_ids"])
  print(f"gold: {positives} seeded + {len(gold) - positives} clean; seeded without candidate: {no_cand}; "
        f"missing captures: {len(missing)} {missing[:10]}")


def main(argv: list[str] | None = None) -> int:
  argv = list(sys.argv[1:] if argv is None else argv)
  step, rest = argv[0], argv[1:]
  if step == "collect":
    collect()
  elif step == "link":
    link()
  elif step == "judge":
    from eval import dev_judge
    dev_judge.DEV = RESULTS
    return dev_judge.main(["--model", "openai/gpt-6-luna", *rest])
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
