from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_synthetic_confirmation_run(
  run_dir: Path,
  *,
  confirmation_run_id: str = "confirm_report_source",
  include_missing_refs: bool = False,
) -> Path:
  _write_candidates(run_dir)
  _write_state_artifacts(run_dir)
  confirmation_dir = run_dir / "confirmations" / confirmation_run_id
  confirmation_dir.mkdir(parents=True)
  records = _confirmation_records(confirmation_run_id)
  if include_missing_refs:
    records.append(
      _confirmation_record(
        confirmation_run_id=confirmation_run_id,
        confirmation_id="confirmation_missing",
        candidate_id="cand_missing",
        candidate_type="page-title-not-descriptive",
        state_id="state_0002",
        decision="uncertain",
        confidence=0.1,
        parse_status="client_error",
        error="provider timed out",
        source_candidate_ref={"path": "candidates/missing.jsonl", "line_number": 1},
        artifact_refs={"metadata": "states/state_0002/missing.json"},
      )
    )
  _write_json(confirmation_dir / "manifest.json", _manifest(run_dir, confirmation_run_id, records))
  with (confirmation_dir / "confirmations.jsonl").open("w", encoding="utf-8") as handle:
    for record in records:
      handle.write(json.dumps(record, sort_keys=True) + "\n")
  return confirmation_dir


def _write_candidates(run_dir: Path) -> None:
  candidate_dir = run_dir / "candidates"
  candidate_dir.mkdir(parents=True)
  long_html = "<button>" + ("A" * 900) + "</button>"
  candidates = [
    _candidate_record(
      candidate_id="cand_violation",
      candidate_type="button-label-mismatch",
      state_id="state_0001",
      raw_html=long_html,
    ),
    _candidate_record(
      candidate_id="cand_uncertain",
      candidate_type="image-alt-not-descriptive",
      state_id="state_0001",
      raw_html="<img src=\"logo.png\" alt=\"Logo\">",
    ),
    _candidate_record(
      candidate_id="cand_error",
      candidate_type="link-text-mismatch",
      state_id="state_0001",
      raw_html="<a href=\"/report\">Read more</a>",
    ),
    _candidate_record(
      candidate_id="cand_no_violation",
      candidate_type="page-title-not-descriptive",
      state_id="state_0002",
      raw_html="<title>Settings</title>",
    ),
  ]
  with (candidate_dir / "candidates.jsonl").open("w", encoding="utf-8") as handle:
    for candidate in candidates:
      handle.write(json.dumps(candidate, sort_keys=True) + "\n")


def _write_state_artifacts(run_dir: Path) -> None:
  for state_id, url, title in (
    ("state_0001", "https://example.test/settings", "Settings"),
    ("state_0002", "https://example.test/help", "Help"),
  ):
    state_dir = run_dir / "states" / state_id
    state_dir.mkdir(parents=True)
    _write_json(
      state_dir / "metadata.json",
      {
        "state_id": state_id,
        "url": url,
        "route": "/" + url.rsplit("/", maxsplit=1)[-1],
        "title": title,
        "depth": 1,
      },
    )
    (state_dir / "screenshot.png").write_bytes(b"fake image")
    (state_dir / "dom.html").write_text("<main></main>", encoding="utf-8")
    _write_json(state_dir / "accessibility_context.json", {"state_id": state_id})


def _confirmation_records(confirmation_run_id: str) -> list[dict[str, Any]]:
  return [
    _confirmation_record(
      confirmation_run_id=confirmation_run_id,
      confirmation_id="confirmation_violation",
      candidate_id="cand_violation",
      candidate_type="button-label-mismatch",
      state_id="state_0001",
      decision="violation",
      confidence=0.88,
      parse_status="parsed",
      line_number=1,
      reason="The button label is positional and does not explain the action.",
      supporting_evidence=["button text is First visually", "section heading is Focus layout"],
    ),
    _confirmation_record(
      confirmation_run_id=confirmation_run_id,
      confirmation_id="confirmation_uncertain",
      candidate_id="cand_uncertain",
      candidate_type="image-alt-not-descriptive",
      state_id="state_0001",
      decision="uncertain",
      confidence=0.32,
      parse_status="parsed",
      line_number=2,
      reason="The saved evidence does not show enough image purpose.",
      supporting_evidence=["candidate accessible name is Logo"],
    ),
    _confirmation_record(
      confirmation_run_id=confirmation_run_id,
      confirmation_id="confirmation_error",
      candidate_id="cand_error",
      candidate_type="link-text-mismatch",
      state_id="state_0001",
      decision="uncertain",
      confidence=0.0,
      parse_status="id_mismatch",
      error="candidate_id did not match",
      line_number=3,
      reason="Response identifiers did not match the candidate.",
      supporting_evidence=[],
    ),
    _confirmation_record(
      confirmation_run_id=confirmation_run_id,
      confirmation_id="confirmation_no_violation",
      candidate_id="cand_no_violation",
      candidate_type="page-title-not-descriptive",
      state_id="state_0002",
      decision="no_violation",
      confidence=0.74,
      parse_status="parsed",
      line_number=4,
      reason="The page title describes the settings page.",
      supporting_evidence=["title is Settings"],
    ),
  ]


def _candidate_record(
  *,
  candidate_id: str,
  candidate_type: str,
  state_id: str,
  raw_html: str,
) -> dict[str, Any]:
  return {
    "schema_version": "1",
    "candidate_id": candidate_id,
    "candidate_type": candidate_type,
    "state_id": state_id,
    "element_refs": [{"bucket": "buttons", "element_id": "e_1"}],
    "primary_element_ref": {"bucket": "buttons", "element_id": "e_1", "selector": "#target"},
    "selection_reason": ["test_reason"],
    "required_context": ["label purpose", "section context"],
    "evidence": {
      "primary": {"html": raw_html},
      "supporting": {"nearby_text": "Nearby context"},
    },
    "state_context": {
      "url": f"https://example.test/{state_id}",
      "title": f"Candidate title {state_id}",
      "depth": 1,
    },
    "graph_context": {"transition_path": []},
    "artifact_refs": _artifact_refs(state_id),
    "generator": {"name": "offline_semantic_candidate_builder", "version": "1"},
  }


def _confirmation_record(
  *,
  confirmation_run_id: str,
  confirmation_id: str,
  candidate_id: str,
  candidate_type: str,
  state_id: str,
  decision: str,
  confidence: float,
  parse_status: str,
  reason: str = "Reason",
  supporting_evidence: list[str] | None = None,
  error: str | None = None,
  line_number: int = 1,
  source_candidate_ref: dict[str, Any] | None = None,
  artifact_refs: dict[str, str] | None = None,
) -> dict[str, Any]:
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
    "reason": reason,
    "supporting_evidence": supporting_evidence or [],
    "provider": "fake",
    "model": "fake-confirmation-model",
    "context_mode": "adaptive_context",
    "requested_context_mode": "adaptive_context",
    "selected_context_mode": "isolated_state",
    "resolved_context_mode": "isolated_state",
    "context_policy_version": "context_policy_v1",
    "graph_context_included": False,
    "graph_context_omitted_reason": "selected_isolated_context",
    "prompt_version": "confirm_v4_1_text",
    "prompt_template_hash": "template-hash",
    "prompt_hash": "prompt-hash",
    "response_hash": "response-hash",
    "candidate_record_hash": "candidate-hash",
    "config_hash": "config-hash",
    "parse_status": parse_status,
    "error": error,
    "runtime_ms": 1,
    "token_usage": None,
    "estimated_cost_usd": 0.0,
    "attempt_count": 1,
    "escalation_triggered": False,
    "final_decision_source": "initial_attempt",
    "final_attempt_index": 1,
    "initial_context_mode": "isolated_state",
    "initial_decision": decision,
    "initial_parse_status": parse_status,
    "retry_context_mode": None,
    "retry_decision": None,
    "retry_parse_status": None,
    "retry_error": None,
    "source_candidate_ref": source_candidate_ref or {"path": "candidates/candidates.jsonl", "line_number": line_number},
    "artifact_refs": artifact_refs or _artifact_refs(state_id),
    "candidate_summary": {
      "selection_reason": ["test_reason"],
      "required_context": ["label purpose"],
      "element_ref_count": 1,
      "has_graph_context": True,
      "has_artifact_refs": True,
    },
    "created_at": "2026-05-02T00:00:00Z",
    "generator": {"name": "offline_semantic_confirmation", "version": "1"},
  }


def _artifact_refs(state_id: str) -> dict[str, str]:
  return {
    "metadata": f"states/{state_id}/metadata.json",
    "screenshot": f"states/{state_id}/screenshot.png",
    "dom_html": f"states/{state_id}/dom.html",
    "accessibility_context": f"states/{state_id}/accessibility_context.json",
  }


def _manifest(run_dir: Path, confirmation_run_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
  return {
    "schema_version": "1",
    "confirmation_run_id": confirmation_run_id,
    "generated_at": "2026-05-02T00:00:00Z",
    "run_dir": run_dir.as_posix(),
    "output_dir": (run_dir / "confirmations" / confirmation_run_id).as_posix(),
    "provider": "fake",
    "model": "fake-confirmation-model",
    "config_hash": "config-hash",
    "prompt_version": "confirm_v4_1_text",
    "prompt_template_hash": "template-hash",
    "inputs": {"candidate_path": "candidates/candidates.jsonl"},
    "counts": {"confirmations_written": len(records)},
    "by_decision": {},
    "by_candidate_type": {},
    "parse_status_counts": {},
    "raw_logging": {"save_prompts": False, "save_raw_responses": False},
  }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
  path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
