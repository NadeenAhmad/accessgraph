from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_synthetic_evaluation_run(
  run_dir: Path,
  *,
  confirmation_run_id: str,
  model: str = "qwen2.5:7b",
  context_mode: str = "graph_context",
  include_shared: bool = True,
  shared_decision: str = "violation",
  unique_suffix: str = "a",
) -> Path:
  confirmation_dir = run_dir / "confirmations" / confirmation_run_id
  confirmation_dir.mkdir(parents=True)
  records = _records(
    confirmation_run_id=confirmation_run_id,
    model=model,
    context_mode=context_mode,
    include_shared=include_shared,
    shared_decision=shared_decision,
    unique_suffix=unique_suffix,
  )
  _write_json(confirmation_dir / "manifest.json", _manifest(run_dir, confirmation_run_id, model, context_mode, records))
  with (confirmation_dir / "confirmations.jsonl").open("w", encoding="utf-8") as handle:
    for record in records:
      handle.write(json.dumps(record, sort_keys=True))
      handle.write("\n")
  return confirmation_dir


def _records(
  *,
  confirmation_run_id: str,
  model: str,
  context_mode: str,
  include_shared: bool,
  shared_decision: str,
  unique_suffix: str,
) -> list[dict[str, Any]]:
  records: list[dict[str, Any]] = []
  if include_shared:
    records.append(
      _record(
        confirmation_run_id=confirmation_run_id,
        confirmation_id=f"confirmation_shared_{unique_suffix}",
        candidate_id="cand_shared",
        candidate_type="button-label-mismatch",
        state_id="state_0001",
        decision=shared_decision,
        confidence=0.91 if shared_decision == "violation" else 0.67,
        parse_status="parsed",
        runtime_ms=10,
        prompt_tokens=100,
        completion_tokens=20,
        model=model,
        context_mode=context_mode,
      )
    )
  records.extend(
    [
      _record(
        confirmation_run_id=confirmation_run_id,
        confirmation_id=f"confirmation_unique_{unique_suffix}",
        candidate_id=f"cand_unique_{unique_suffix}",
        candidate_type="image-alt-not-descriptive",
        state_id="state_0001",
        decision="uncertain",
        confidence=0.4,
        parse_status="parsed",
        runtime_ms=20,
        prompt_tokens=80,
        completion_tokens=15,
        model=model,
        context_mode=context_mode,
      ),
      _record(
        confirmation_run_id=confirmation_run_id,
        confirmation_id=f"confirmation_error_{unique_suffix}",
        candidate_id=f"cand_error_{unique_suffix}",
        candidate_type="link-text-mismatch",
        state_id="state_0002",
        decision="uncertain",
        confidence=0.0,
        parse_status="id_mismatch",
        error="candidate_id did not match",
        runtime_ms=5,
        prompt_tokens=50,
        completion_tokens=10,
        model=model,
        context_mode=context_mode,
      ),
    ]
  )
  return records


def _record(
  *,
  confirmation_run_id: str,
  confirmation_id: str,
  candidate_id: str,
  candidate_type: str,
  state_id: str,
  decision: str,
  confidence: float,
  parse_status: str,
  runtime_ms: int,
  prompt_tokens: int,
  completion_tokens: int,
  model: str,
  context_mode: str,
  error: str | None = None,
) -> dict[str, Any]:
  total_tokens = prompt_tokens + completion_tokens
  return {
    "schema_version": "1",
    "confirmation_id": confirmation_id,
    "confirmation_run_id": confirmation_run_id,
    "candidate_id": candidate_id,
    "candidate_type": candidate_type,
    "state_id": state_id,
    "decision": decision,
    "confidence": confidence,
    "confidence_semantics": "model_reported_heuristic_not_calibrated",
    "reason": "Synthetic confirmation reason",
    "supporting_evidence": ["field one", "field two"],
    "provider": "ollama",
    "model": model,
    "context_mode": context_mode,
    "graph_context_included": context_mode == "graph_context",
    "prompt_version": "confirm_v4_1_text",
    "prompt_template_hash": "template-hash",
    "prompt_hash": "prompt-hash",
    "response_hash": "response-hash",
    "candidate_record_hash": "candidate-hash",
    "config_hash": "config-hash",
    "parse_status": parse_status,
    "error": error,
    "runtime_ms": runtime_ms,
    "token_usage": {
      "prompt_tokens": prompt_tokens,
      "completion_tokens": completion_tokens,
      "total_tokens": total_tokens,
    },
    "estimated_cost_usd": 0.0,
    "source_candidate_ref": {"path": "candidates/candidates.jsonl", "line_number": 1},
    "artifact_refs": {"metadata": f"states/{state_id}/metadata.json"},
    "candidate_summary": {"selection_reason": ["synthetic"], "element_ref_count": 1},
    "created_at": "2026-05-03T00:00:00Z",
    "generator": {"name": "offline_semantic_confirmation", "version": "1"},
  }


def _manifest(
  run_dir: Path,
  confirmation_run_id: str,
  model: str,
  context_mode: str,
  records: list[dict[str, Any]],
) -> dict[str, Any]:
  return {
    "schema_version": "1",
    "confirmation_run_id": confirmation_run_id,
    "generated_at": "2026-05-03T00:00:00Z",
    "run_dir": run_dir.as_posix(),
    "output_dir": (run_dir / "confirmations" / confirmation_run_id).as_posix(),
    "provider": "ollama",
    "model": model,
    "context_mode": context_mode,
    "graph_context_included": context_mode == "graph_context",
    "config_hash": "config-hash",
    "config": {"context_mode": context_mode},
    "prompt_version": "confirm_v4_1_text",
    "prompt_template_hash": "template-hash",
    "duration_ms": 1234,
    "counts": {"confirmations_written": len(records)},
  }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
  path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
