from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.analysis.confirmation.providers.fake import FakeConfirmationClient
from src.analysis.confirmation.context_policy import ADAPTIVE_CONTEXT_POLICY_VERSION
from src.analysis.confirmation.hashing import config_hash
from src.analysis.confirmation.models import (
  CONTEXT_MODE_ADAPTIVE,
  CONTEXT_MODE_GRAPH,
  CONTEXT_MODE_ISOLATED,
  ESCALATION_POLICY_UNCERTAIN_GRAPH,
  ConfirmationConfig,
  ReviewBundle,
)
from src.analysis.confirmation.parser import parse_confirmation_response
from src.analysis.confirmation.prompt_builder import build_confirmation_prompt
from src.analysis.confirmation.writer import (
  ConfirmationRunWriter,
  build_confirmation_id,
  build_confirmation_record,
)


def _bundle() -> ReviewBundle:
  record = {
    "candidate_id": "cand_button",
    "candidate_type": "button-label-mismatch",
    "state_id": "state_0001",
    "element_refs": [{"bucket": "buttons", "element_id": "button-1"}],
    "selection_reason": ["button needs confirmation"],
    "required_context": ["button label", "nearby text"],
    "evidence": {"button": {"label": "Save"}},
    "state_context": {"url": "https://example.com/settings", "title": "Settings"},
    "graph_context": {"transition_path": []},
    "artifact_refs": {"accessibility_context": "states/state_0001/accessibility_context.json"},
    "generator": {"name": "offline_semantic_candidate_builder", "version": "1"},
  }
  return ReviewBundle(
    run_dir=Path("runs/example"),
    source_path=Path("runs/example/candidates/candidates.jsonl"),
    source_line_number=1,
    record=record,
    candidate_id="cand_button",
    candidate_type="button-label-mismatch",
    state_id="state_0001",
    element_refs=tuple(record["element_refs"]),
    selection_reason=tuple(record["selection_reason"]),
    required_context=tuple(record["required_context"]),
    evidence=record["evidence"],
    state_context=record["state_context"],
    graph_context=record["graph_context"],
    artifact_refs=record["artifact_refs"],
    generator=record["generator"],
  )


def test_writer_writes_confirmation_layout_prompt_response_and_manifest(tmp_path):
  config = ConfirmationConfig()
  cfg_hash = config_hash(config)
  bundle = _bundle()
  prompt = build_confirmation_prompt(bundle)
  response = FakeConfirmationClient().confirm(prompt)
  parsed = parse_confirmation_response(response.raw_content, bundle=bundle)
  confirmation_id = build_confirmation_id(
    candidate_id=bundle.candidate_id,
    prompt_version=prompt.prompt_version,
    provider=config.provider,
    model=config.model,
    config_hash=cfg_hash,
  )
  writer = ConfirmationRunWriter(
    tmp_path / "confirmations" / "run-1",
    save_prompts=True,
    save_raw_responses=True,
  )

  record = build_confirmation_record(
    confirmation_id=confirmation_id,
    confirmation_run_id="run-1",
    prompt=prompt,
    response=response,
    parsed=parsed,
    config_hash=cfg_hash,
    created_at="2026-05-01T00:00:00Z",
  )
  writer.write_prompt(confirmation_id, prompt)
  writer.write_raw_response(confirmation_id, response)
  writer.write_confirmation(record)
  writer.write_manifest({"confirmation_run_id": "run-1"})

  output_dir = tmp_path / "confirmations" / "run-1"
  assert (output_dir / "manifest.json").exists()
  assert (output_dir / "confirmations.jsonl").exists()
  assert (output_dir / "by_type" / "button-label-mismatch.jsonl").exists()
  assert (output_dir / "prompts" / f"{confirmation_id}.json").exists()
  assert (output_dir / "raw_responses" / f"{confirmation_id}.json").exists()

  written = json.loads((output_dir / "confirmations.jsonl").read_text(encoding="utf-8"))
  expected_fields = {
    "schema_version",
    "confirmation_id",
    "confirmation_run_id",
    "candidate_id",
    "candidate_type",
    "state_id",
    "decision",
    "confidence",
    "confidence_semantics",
    "reason",
    "supporting_evidence",
    "provider",
    "model",
    "context_mode",
    "requested_context_mode",
    "selected_context_mode",
    "resolved_context_mode",
    "context_policy_version",
    "graph_context_included",
    "graph_context_omitted_reason",
    "prompt_version",
    "prompt_template_hash",
    "prompt_hash",
    "response_hash",
    "candidate_record_hash",
    "config_hash",
    "parse_status",
    "error",
    "runtime_ms",
    "token_usage",
    "estimated_cost_usd",
    "source_candidate_ref",
    "artifact_refs",
    "candidate_summary",
    "created_at",
    "generator",
  }
  assert expected_fields <= set(written)
  assert written["confirmation_id"] == confirmation_id
  assert written["candidate_type"] == "button-label-mismatch"
  assert written["context_mode"] == CONTEXT_MODE_GRAPH
  assert written["requested_context_mode"] == CONTEXT_MODE_GRAPH
  assert written["selected_context_mode"] == CONTEXT_MODE_GRAPH
  assert written["resolved_context_mode"] == CONTEXT_MODE_GRAPH
  assert written["context_policy_version"] is None
  assert written["graph_context_included"] is True
  assert written["graph_context_omitted_reason"] is None
  assert written["decision"] == "uncertain"
  assert "fix_suggestion" not in written
  assert "record" not in written
  assert "violation_id" not in written
  raw_response = json.loads((output_dir / "raw_responses" / f"{confirmation_id}.json").read_text(encoding="utf-8"))
  assert "provider_metadata" in raw_response
  saved_prompt = json.loads((output_dir / "prompts" / f"{confirmation_id}.json").read_text(encoding="utf-8"))
  assert saved_prompt["context_mode"] == CONTEXT_MODE_GRAPH
  assert saved_prompt["requested_context_mode"] == CONTEXT_MODE_GRAPH
  assert saved_prompt["selected_context_mode"] == CONTEXT_MODE_GRAPH
  assert saved_prompt["resolved_context_mode"] == CONTEXT_MODE_GRAPH
  assert saved_prompt["context_policy_version"] is None
  assert saved_prompt["graph_context_included"] is True
  assert saved_prompt["graph_context_omitted_reason"] is None


def test_config_hash_changes_with_context_mode():
  graph_hash = config_hash(ConfirmationConfig(context_mode=CONTEXT_MODE_GRAPH))
  isolated_hash = config_hash(ConfirmationConfig(context_mode=CONTEXT_MODE_ISOLATED))
  adaptive_hash = config_hash(ConfirmationConfig(context_mode=CONTEXT_MODE_ADAPTIVE))
  escalation_hash = config_hash(
    ConfirmationConfig(
      context_mode=CONTEXT_MODE_ISOLATED,
      escalation_policy=ESCALATION_POLICY_UNCERTAIN_GRAPH,
    )
  )

  assert graph_hash != isolated_hash
  assert adaptive_hash != graph_hash
  assert adaptive_hash != isolated_hash
  assert escalation_hash != isolated_hash
  assert ConfirmationConfig(context_mode=CONTEXT_MODE_ADAPTIVE).decision_affecting_payload()[
    "context_policy_version"
  ] == ADAPTIVE_CONTEXT_POLICY_VERSION
  assert ConfirmationConfig(context_mode=CONTEXT_MODE_GRAPH).decision_affecting_payload()[
    "context_policy_version"
  ] == ADAPTIVE_CONTEXT_POLICY_VERSION
  assert ConfirmationConfig(
    context_mode=CONTEXT_MODE_ISOLATED,
    escalation_policy=ESCALATION_POLICY_UNCERTAIN_GRAPH,
  ).decision_affecting_payload()["escalation_policy_version"] == ESCALATION_POLICY_UNCERTAIN_GRAPH


def test_writer_prevents_overwrite_without_flag(tmp_path):
  output_dir = tmp_path / "confirmations" / "run-1"
  output_dir.mkdir(parents=True)
  (output_dir / "marker.txt").write_text("keep", encoding="utf-8")

  with pytest.raises(FileExistsError, match="already exists"):
    ConfirmationRunWriter(output_dir)

  ConfirmationRunWriter(output_dir, overwrite=True)

  assert not (output_dir / "marker.txt").exists()
  assert (output_dir / "by_type").exists()
