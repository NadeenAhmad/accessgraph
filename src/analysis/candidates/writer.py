"""Write generated semantic candidate records and manifests."""

from __future__ import annotations

import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import CANDIDATE_SCHEMA_VERSION, GENERATOR_NAME, GENERATOR_VERSION
from .taxonomy import LAYOUT_CATEGORY, SEMANTIC_CATEGORY, SUPPORTED_CANDIDATE_TYPES, SYNTAX_CATEGORY


def write_candidate_outputs(
  *,
  run_dir: Path,
  candidates: list[dict[str, object]],
  skipped: dict[str, int],
  states_seen: int,
  accessibility_context_seen: int,
) -> dict[str, Any]:
  output_dir = run_dir / "candidates"
  if output_dir.exists():
    shutil.rmtree(output_dir)
  by_type_dir = output_dir / "by_type"
  by_type_dir.mkdir(parents=True, exist_ok=True)

  all_candidates_path = output_dir / "candidates.jsonl"
  _write_jsonl(all_candidates_path, candidates)

  counts = Counter(str(candidate.get("candidate_type") or "") for candidate in candidates)
  for candidate_type in SUPPORTED_CANDIDATE_TYPES:
    type_candidates = [
      candidate
      for candidate in candidates
      if candidate.get("candidate_type") == candidate_type
    ]
    _write_jsonl(by_type_dir / f"{candidate_type}.jsonl", type_candidates)

  manifest = {
    "schema_version": CANDIDATE_SCHEMA_VERSION,
    "run_dir": str(run_dir),
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "generator": {
      "name": GENERATOR_NAME,
      "version": GENERATOR_VERSION,
    },
    "taxonomy_scope": {
      "included_categories": [SEMANTIC_CATEGORY],
      "excluded_categories": [SYNTAX_CATEGORY, LAYOUT_CATEGORY],
      "candidate_types": list(SUPPORTED_CANDIDATE_TYPES),
    },
    "inputs": {
      "graph": "graph.json",
      "transitions": "transitions.json",
      "states_seen": states_seen,
      "accessibility_context_seen": accessibility_context_seen,
    },
    "outputs": {
      "all_candidates": "candidates.jsonl",
      "by_type_dir": "by_type",
    },
    "counts": {
      "total_candidates": len(candidates),
      "by_type": {candidate_type: counts.get(candidate_type, 0) for candidate_type in SUPPORTED_CANDIDATE_TYPES},
    },
    "skipped": skipped,
  }
  (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
  return manifest


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
  with path.open("w", encoding="utf-8") as handle:
    for record in records:
      handle.write(json.dumps(record, ensure_ascii=False) + "\n")
