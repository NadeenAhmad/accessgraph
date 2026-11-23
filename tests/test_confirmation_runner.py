from __future__ import annotations

import json

import pytest

from src.analysis.confirmation.providers.fake import FakeConfirmationClient
from src.analysis.confirmation.context_policy import (
  ADAPTIVE_CONTEXT_POLICY_VERSION,
  GRAPH_CONTEXT_OMITTED_EMPTY,
)
from src.analysis.confirmation.models import (
  CALIBRATED_TEXT_PROMPT_VERSION,
  CALIBRATED_VISION_PROMPT_VERSION,
  CONTEXT_MODE_ADAPTIVE,
  CONTEXT_MODE_GRAPH,
  CONTEXT_MODE_ISOLATED,
  CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT,
  ESCALATION_POLICY_NONE,
  ESCALATION_POLICY_UNCERTAIN_GRAPH,
  GUIDED_HTML_SCREENSHOT_PROMPT_VERSION,
  ConfirmationConfig,
  ConfirmationProviderResponse,
)
from src.analysis.confirmation.parser import ConfirmationParseError
from src.analysis.confirmation.runner import ConfirmationRunOptions, run_confirmation


class FailingClient:
  def confirm(self, prompt):
    raise RuntimeError("simulated provider failure")


class MinimalDecisionClient:
  def confirm(self, prompt):
    return ConfirmationProviderResponse(
      provider="fake",
      model="minimal-test",
      raw_content=json.dumps(
        {
          "decision": "violation",
          "confidence": 0.83,
          "reason": "The saved evidence supports the candidate concern.",
          "supporting_evidence": ["evidence.sample.text"],
        }
      ),
      runtime_ms=0,
      token_usage=None,
      estimated_cost_usd=None,
    )


class MismatchedIdClient:
  def confirm(self, prompt):
    return ConfirmationProviderResponse(
      provider="fake",
      model="mismatched-id-test",
      raw_content=json.dumps(
        {
          "candidate_id": "state_0001",
          "candidate_type": "semantic_candidate",
          "state_id": "other_state",
          "decision": "violation",
          "confidence": 0.77,
          "reason": "The saved evidence supports the candidate concern despite copied identifier noise.",
          "supporting_evidence": ["evidence.sample.text"],
        }
      ),
      runtime_ms=0,
      token_usage=None,
      estimated_cost_usd=None,
    )


class SequenceDecisionClient:
  def __init__(self, responses):
    self.responses = list(responses)
    self.prompts = []

  def confirm(self, prompt):
    self.prompts.append(prompt)
    if not self.responses:
      raise AssertionError("No fake response queued for confirmation attempt")
    response = self.responses.pop(0)
    if isinstance(response, str):
      raw_content = response
    else:
      payload = {
        "candidate_id": prompt.bundle.candidate_id,
        "candidate_type": prompt.bundle.candidate_type,
        "state_id": prompt.bundle.state_id,
        "decision": response["decision"],
        "confidence": response.get("confidence", 0.7),
        "reason": response.get("reason", "Queued fake decision."),
        "supporting_evidence": response.get("supporting_evidence", ["queued fake evidence"]),
      }
      raw_content = json.dumps(payload)
    return ConfirmationProviderResponse(
      provider="fake",
      model="sequence-test",
      raw_content=raw_content,
      runtime_ms=0,
      token_usage=None,
      estimated_cost_usd=None,
    )


def _candidate_record(
  *,
  candidate_type: str = "button-label-mismatch",
  candidate_id: str = "cand_button",
  state_id: str = "state_0001",
) -> dict[str, object]:
  return {
    "schema_version": "1",
    "candidate_id": candidate_id,
    "candidate_type": candidate_type,
    "state_id": state_id,
    "element_refs": [{"bucket": "buttons", "element_id": "button-1"}],
    "selection_reason": ["candidate selected for confirmation"],
    "required_context": ["element evidence", "state context"],
    "evidence": {
      "sample": {"text": candidate_type},
      "supporting": {
        "dom_snippets": [
          {
            "element_id": "button-1",
            "selector": "button",
            "html": "<button>Save task</button>",
          }
        ]
      },
      "dom_snippets": [
        {
          "element_id": "button-1",
          "selector": "button",
          "html": "<button>Save task</button>",
        }
      ],
    },
    "state_context": {
      "url": "https://example.com",
      "title": "Example",
      "depth": 1,
      "parent_state": "state_0000",
      "action_from_parent": {"type": "click", "selector": "#start"},
    },
    "graph_context": {"transition_path": []},
    "artifact_refs": {
      "accessibility_context": f"states/{state_id}/accessibility_context.json",
      "screenshot": f"states/{state_id}/screenshot.png",
    },
    "generator": {"name": "offline_semantic_candidate_builder", "version": "1"},
  }


def _write_candidates(run_dir, records: list[dict[str, object]]) -> None:
  candidate_dir = run_dir / "candidates"
  candidate_dir.mkdir(parents=True)
  with (candidate_dir / "candidates.jsonl").open("w", encoding="utf-8") as handle:
    for record in records:
      handle.write(json.dumps(record) + "\n")


def _read_jsonl(path):
  return [
    json.loads(line)
    for line in path.read_text(encoding="utf-8").splitlines()
    if line.strip()
  ]


def _prompt_candidate_payload(prompt_payload: dict[str, object]) -> dict[str, object]:
  return json.loads(str(prompt_payload["user_prompt"]).split("Candidate payload:\n", 1)[1])


def test_runner_writes_fake_confirmation_outputs(tmp_path):
  _write_candidates(
    tmp_path,
    [
      _candidate_record(candidate_id="cand_button"),
      _candidate_record(
        candidate_id="cand_title",
        candidate_type="page-title-not-descriptive",
        state_id="state_0002",
      ),
    ],
  )

  result = run_confirmation(
    config=ConfirmationConfig(),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="run-1",
    ),
  )

  output_dir = tmp_path / "confirmations" / "run-1"
  manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
  records = _read_jsonl(output_dir / "confirmations.jsonl")
  expected_manifest_fields = {
    "schema_version",
    "confirmation_run_id",
    "generated_at",
    "run_dir",
    "output_dir",
    "provider",
    "model",
    "context_mode",
    "requested_context_mode",
    "selected_context_mode_counts",
    "resolved_context_mode",
    "context_policy_version",
    "resolved_context_mode_counts",
    "graph_context_omitted_reason_counts",
    "graph_context_included",
    "prompt_version",
    "prompt_template_hash",
    "config",
    "config_hash",
    "inputs",
    "outputs",
    "counts",
    "by_decision",
    "by_candidate_type",
    "parse_status_counts",
    "raw_logging",
    "invocation",
    "generator",
  }

  assert expected_manifest_fields <= set(manifest)
  assert result.confirmation_run_id == "run-1"
  assert manifest["generated_at"]
  assert manifest["run_dir"] == tmp_path.as_posix()
  assert manifest["output_dir"] == output_dir.as_posix()
  assert manifest["inputs"]["candidate_path"] == "candidates/candidates.jsonl"
  assert manifest["inputs"]["candidate_ids"] == []
  assert manifest["inputs"]["candidate_id_file"] is None
  assert manifest["inputs"]["selected_candidate_ids"] == ["cand_button", "cand_title"]
  assert manifest["context_mode"] == CONTEXT_MODE_GRAPH
  assert manifest["requested_context_mode"] == CONTEXT_MODE_GRAPH
  assert manifest["resolved_context_mode"] == CONTEXT_MODE_GRAPH
  assert manifest["context_policy_version"] == ADAPTIVE_CONTEXT_POLICY_VERSION
  assert manifest["selected_context_mode_counts"] == {CONTEXT_MODE_GRAPH: 2}
  assert manifest["resolved_context_mode_counts"] == {CONTEXT_MODE_GRAPH: 2}
  assert manifest["graph_context_omitted_reason_counts"] == {}
  assert manifest["graph_context_included"] is True
  assert manifest["config"]["context_mode"] == CONTEXT_MODE_GRAPH
  assert manifest["config"]["context_policy_version"] == ADAPTIVE_CONTEXT_POLICY_VERSION
  assert manifest["outputs"]["confirmations"] == "confirmations.jsonl"
  assert manifest["counts"]["confirmations_written"] == 2
  assert manifest["by_decision"] == {"uncertain": 2}
  assert manifest["parse_status_counts"] == {"parsed": 2}
  assert manifest["raw_logging"] == {"save_prompts": True, "save_raw_responses": True}
  assert "base_url" in manifest["config"]
  assert "timeout_seconds" in manifest["config"]
  assert len(records) == 2
  assert records[0]["context_mode"] == CONTEXT_MODE_GRAPH
  assert records[0]["requested_context_mode"] == CONTEXT_MODE_GRAPH
  assert records[0]["selected_context_mode"] == CONTEXT_MODE_GRAPH
  assert records[0]["resolved_context_mode"] == CONTEXT_MODE_GRAPH
  assert records[0]["context_policy_version"] == ADAPTIVE_CONTEXT_POLICY_VERSION
  assert records[0]["graph_context_included"] is True
  assert records[0]["graph_context_omitted_reason"] is None
  assert records[0]["confidence"] == 0.5
  assert (output_dir / "by_type" / "button-label-mismatch.jsonl").exists()
  assert (output_dir / "by_type" / "page-title-not-descriptive.jsonl").exists()
  assert len(list((output_dir / "prompts").glob("*.json"))) == 2
  assert len(list((output_dir / "raw_responses").glob("*.json"))) == 2


def test_runner_writes_isolated_state_context_mode_outputs(tmp_path):
  _write_candidates(tmp_path, [_candidate_record()])

  run_confirmation(
    config=ConfirmationConfig(context_mode=CONTEXT_MODE_ISOLATED),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="run-isolated",
    ),
  )

  output_dir = tmp_path / "confirmations" / "run-isolated"
  manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
  records = _read_jsonl(output_dir / "confirmations.jsonl")
  prompt_payload = json.loads(next((output_dir / "prompts").glob("*.json")).read_text(encoding="utf-8"))

  assert manifest["context_mode"] == CONTEXT_MODE_ISOLATED
  assert manifest["requested_context_mode"] == CONTEXT_MODE_ISOLATED
  assert manifest["resolved_context_mode"] == CONTEXT_MODE_ISOLATED
  assert manifest["context_policy_version"] is None
  assert manifest["resolved_context_mode_counts"] == {CONTEXT_MODE_ISOLATED: 1}
  assert manifest["graph_context_included"] is False
  assert manifest["config"]["context_mode"] == CONTEXT_MODE_ISOLATED
  assert records[0]["context_mode"] == CONTEXT_MODE_ISOLATED
  assert records[0]["requested_context_mode"] == CONTEXT_MODE_ISOLATED
  assert records[0]["resolved_context_mode"] == CONTEXT_MODE_ISOLATED
  assert records[0]["context_policy_version"] is None
  assert records[0]["graph_context_included"] is False
  assert prompt_payload["context_mode"] == CONTEXT_MODE_ISOLATED
  assert prompt_payload["requested_context_mode"] == CONTEXT_MODE_ISOLATED
  assert prompt_payload["resolved_context_mode"] == CONTEXT_MODE_ISOLATED
  assert prompt_payload["context_policy_version"] is None
  assert prompt_payload["graph_context_included"] is False
  payload = _prompt_candidate_payload(prompt_payload)
  assert "graph_context" not in payload
  assert "parent_state" not in payload["state_context"]
  assert "action_from_parent" not in payload["state_context"]
  assert "depth" not in payload["state_context"]


def test_runner_omits_empty_explicit_graph_context_and_records_reason(tmp_path):
  record = _candidate_record(
    candidate_id="cand_empty_graph",
    candidate_type="page-title-not-descriptive",
  )
  record["state_context"] = {
    "url": "https://example.com/tasks/completed",
    "title": "Task Manager Benchmark",
    "depth": 0,
    "parent_state": None,
    "action_from_parent": {},
  }
  record["graph_context"] = {
    "depth": 0,
    "transition_path": [],
    "transition_path_limit": 5,
    "incoming_action": {},
    "related_state_refs": [],
  }
  _write_candidates(tmp_path, [record])

  run_confirmation(
    config=ConfirmationConfig(context_mode=CONTEXT_MODE_GRAPH),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="run-empty-graph",
    ),
  )

  output_dir = tmp_path / "confirmations" / "run-empty-graph"
  manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
  records = _read_jsonl(output_dir / "confirmations.jsonl")
  prompt_payload = json.loads(next((output_dir / "prompts").glob("*.json")).read_text(encoding="utf-8"))

  assert manifest["context_mode"] == CONTEXT_MODE_GRAPH
  assert manifest["selected_context_mode_counts"] == {CONTEXT_MODE_GRAPH: 1}
  assert manifest["resolved_context_mode_counts"] == {CONTEXT_MODE_ISOLATED: 1}
  assert manifest["graph_context_omitted_reason_counts"] == {
    GRAPH_CONTEXT_OMITTED_EMPTY: 1,
  }
  assert manifest["graph_context_included"] is False

  assert records[0]["requested_context_mode"] == CONTEXT_MODE_GRAPH
  assert records[0]["selected_context_mode"] == CONTEXT_MODE_GRAPH
  assert records[0]["resolved_context_mode"] == CONTEXT_MODE_ISOLATED
  assert records[0]["graph_context_included"] is False
  assert records[0]["graph_context_omitted_reason"] == GRAPH_CONTEXT_OMITTED_EMPTY

  assert prompt_payload["requested_context_mode"] == CONTEXT_MODE_GRAPH
  assert prompt_payload["selected_context_mode"] == CONTEXT_MODE_GRAPH
  assert prompt_payload["resolved_context_mode"] == CONTEXT_MODE_ISOLATED
  assert prompt_payload["graph_context_included"] is False
  assert prompt_payload["graph_context_omitted_reason"] == GRAPH_CONTEXT_OMITTED_EMPTY
  payload = _prompt_candidate_payload(prompt_payload)
  assert "graph_context" not in payload
  assert "transition_path" not in payload


def test_runner_resolves_adaptive_context_per_candidate_and_records_metadata(tmp_path):
  _write_candidates(
    tmp_path,
    [
      _candidate_record(candidate_id="cand_button"),
      _candidate_record(
        candidate_id="cand_title",
        candidate_type="page-title-not-descriptive",
        state_id="state_0002",
      ),
    ],
  )
  client = SequenceDecisionClient(
    [
      {"decision": "no_violation", "confidence": 0.82},
      {"decision": "uncertain", "confidence": 0.4},
    ]
  )

  run_confirmation(
    config=ConfirmationConfig(context_mode=CONTEXT_MODE_ADAPTIVE),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="run-adaptive",
    ),
    client=client,
  )

  output_dir = tmp_path / "confirmations" / "run-adaptive"
  manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
  records = _read_jsonl(output_dir / "confirmations.jsonl")
  records_by_id = {record["candidate_id"]: record for record in records}
  prompt_payloads = [
    json.loads(path.read_text(encoding="utf-8"))
    for path in (output_dir / "prompts").glob("*.json")
  ]
  prompts_by_id = {prompt["candidate_id"]: prompt for prompt in prompt_payloads}

  assert manifest["context_mode"] == CONTEXT_MODE_ADAPTIVE
  assert manifest["requested_context_mode"] == CONTEXT_MODE_ADAPTIVE
  assert manifest["resolved_context_mode"] is None
  assert manifest["context_policy_version"] == ADAPTIVE_CONTEXT_POLICY_VERSION
  assert manifest["resolved_context_mode_counts"] == {
    CONTEXT_MODE_GRAPH: 1,
    CONTEXT_MODE_ISOLATED: 1,
  }
  assert manifest["graph_context_included"] is True
  assert manifest["config"]["context_mode"] == CONTEXT_MODE_ADAPTIVE
  assert manifest["config"]["context_policy_version"] == ADAPTIVE_CONTEXT_POLICY_VERSION
  assert manifest["config"]["escalation_policy"] == ESCALATION_POLICY_UNCERTAIN_GRAPH
  assert manifest["counts"]["attempt_count_total"] == 2
  assert manifest["counts"]["escalation_eligible_count"] == 1
  assert manifest["counts"]["escalation_triggered_count"] == 0

  assert records_by_id["cand_button"]["context_mode"] == CONTEXT_MODE_ADAPTIVE
  assert records_by_id["cand_button"]["requested_context_mode"] == CONTEXT_MODE_ADAPTIVE
  assert records_by_id["cand_button"]["resolved_context_mode"] == CONTEXT_MODE_ISOLATED
  assert records_by_id["cand_button"]["context_policy_version"] == ADAPTIVE_CONTEXT_POLICY_VERSION
  assert records_by_id["cand_button"]["graph_context_included"] is False
  assert records_by_id["cand_button"]["attempt_count"] == 1
  assert records_by_id["cand_button"]["escalation_eligible"] is True
  assert records_by_id["cand_button"]["escalation_triggered"] is False
  assert prompts_by_id["cand_button"]["context_mode"] == CONTEXT_MODE_ADAPTIVE
  assert prompts_by_id["cand_button"]["resolved_context_mode"] == CONTEXT_MODE_ISOLATED
  assert "graph_context" not in _prompt_candidate_payload(prompts_by_id["cand_button"])

  assert records_by_id["cand_title"]["context_mode"] == CONTEXT_MODE_ADAPTIVE
  assert records_by_id["cand_title"]["requested_context_mode"] == CONTEXT_MODE_ADAPTIVE
  assert records_by_id["cand_title"]["resolved_context_mode"] == CONTEXT_MODE_GRAPH
  assert records_by_id["cand_title"]["context_policy_version"] == ADAPTIVE_CONTEXT_POLICY_VERSION
  assert records_by_id["cand_title"]["graph_context_included"] is True
  assert records_by_id["cand_title"]["attempt_count"] == 1
  assert records_by_id["cand_title"]["escalation_eligible"] is False
  assert records_by_id["cand_title"]["escalation_triggered"] is False
  assert prompts_by_id["cand_title"]["context_mode"] == CONTEXT_MODE_ADAPTIVE
  assert prompts_by_id["cand_title"]["resolved_context_mode"] == CONTEXT_MODE_GRAPH
  assert "graph_context" in prompts_by_id["cand_title"]["user_prompt"]


def test_runner_adaptive_isolated_uncertain_candidate_retries_with_graph_context(tmp_path):
  _write_candidates(
    tmp_path,
    [
      _candidate_record(
        candidate_id="cand_button",
        candidate_type="button-label-mismatch",
      )
    ],
  )
  client = SequenceDecisionClient(
    [
      {"decision": "uncertain", "confidence": 0.4},
      {"decision": "violation", "confidence": 0.91},
    ]
  )

  run_confirmation(
    config=ConfirmationConfig(context_mode=CONTEXT_MODE_ADAPTIVE),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="run-escalated",
    ),
    client=client,
  )

  output_dir = tmp_path / "confirmations" / "run-escalated"
  manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
  records = _read_jsonl(output_dir / "confirmations.jsonl")
  attempts = _read_jsonl(output_dir / "confirmation_attempts.jsonl")

  assert len(records) == 1
  record = records[0]
  assert record["decision"] == "violation"
  assert record["parse_status"] == "parsed"
  assert record["context_mode"] == CONTEXT_MODE_ADAPTIVE
  assert record["requested_context_mode"] == CONTEXT_MODE_ADAPTIVE
  assert record["resolved_context_mode"] == CONTEXT_MODE_GRAPH
  assert record["graph_context_included"] is True
  assert record["escalation_policy"] == ESCALATION_POLICY_UNCERTAIN_GRAPH
  assert record["attempt_count"] == 2
  assert record["escalation_eligible"] is True
  assert record["escalation_triggered"] is True
  assert record["final_decision_source"] == "graph_retry"
  assert record["final_attempt_index"] == 2
  assert record["initial_context_mode"] == CONTEXT_MODE_ISOLATED
  assert record["initial_decision"] == "uncertain"
  assert record["initial_parse_status"] == "parsed"
  assert record["retry_context_mode"] == CONTEXT_MODE_GRAPH
  assert record["retry_decision"] == "violation"
  assert record["retry_parse_status"] == "parsed"
  assert record["retry_error"] is None
  assert record["escalation_reason"] == "initial_uncertain"

  assert manifest["escalation_policy"] == ESCALATION_POLICY_UNCERTAIN_GRAPH
  assert manifest["escalation_policy_version"] == ESCALATION_POLICY_UNCERTAIN_GRAPH
  assert manifest["context_mode"] == CONTEXT_MODE_ADAPTIVE
  assert manifest["initial_context_mode"] == CONTEXT_MODE_ADAPTIVE
  assert manifest["retry_context_mode"] == CONTEXT_MODE_GRAPH
  assert manifest["counts"]["confirmations_written"] == 1
  assert manifest["counts"]["attempt_count_total"] == 2
  assert manifest["counts"]["escalation_eligible_count"] == 1
  assert manifest["counts"]["escalation_triggered_count"] == 1
  assert manifest["counts"]["retry_error_count"] == 0
  assert manifest["by_decision"] == {"violation": 1}
  assert manifest["final_by_decision"] == {"violation": 1}
  assert manifest["resolved_context_mode_counts"] == {CONTEXT_MODE_GRAPH: 1}
  assert manifest["attempt_resolved_context_mode_counts"] == {
    CONTEXT_MODE_GRAPH: 1,
    CONTEXT_MODE_ISOLATED: 1,
  }
  assert manifest["retry_parse_status_counts"] == {"parsed": 1}
  assert manifest["final_decision_source_counts"] == {"graph_retry": 1}
  assert manifest["outputs"]["confirmation_attempts"] == "confirmation_attempts.jsonl"

  assert len(attempts) == 2
  assert [attempt["attempt_role"] for attempt in attempts] == ["initial_attempt", "graph_retry"]
  assert [attempt["resolved_context_mode"] for attempt in attempts] == [
    CONTEXT_MODE_ISOLATED,
    CONTEXT_MODE_GRAPH,
  ]
  assert all(attempt["prompt_ref"] for attempt in attempts)
  assert all(attempt["response_ref"] for attempt in attempts)
  assert len({record["candidate_id"] for record in records}) == 1
  assert [prompt.resolved_context_mode for prompt in client.prompts] == [
    CONTEXT_MODE_ISOLATED,
    CONTEXT_MODE_GRAPH,
  ]


def test_runner_fixed_isolated_mode_does_not_retry_uncertain_candidate(tmp_path):
  _write_candidates(tmp_path, [_candidate_record(candidate_type="button-label-mismatch")])
  client = SequenceDecisionClient([{"decision": "uncertain", "confidence": 0.4}])

  run_confirmation(
    config=ConfirmationConfig(
      context_mode=CONTEXT_MODE_ISOLATED,
      escalation_policy=ESCALATION_POLICY_UNCERTAIN_GRAPH,
    ),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="run-no-local-escalation",
    ),
    client=client,
  )

  output_dir = tmp_path / "confirmations" / "run-no-local-escalation"
  manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
  record = _read_jsonl(output_dir / "confirmations.jsonl")[0]
  attempts = _read_jsonl(output_dir / "confirmation_attempts.jsonl")

  assert record["decision"] == "uncertain"
  assert record["context_mode"] == CONTEXT_MODE_ISOLATED
  assert record["resolved_context_mode"] == CONTEXT_MODE_ISOLATED
  assert record["escalation_policy"] == ESCALATION_POLICY_NONE
  assert record["attempt_count"] == 1
  assert record["escalation_eligible"] is False
  assert record["escalation_triggered"] is False
  assert record["final_decision_source"] == "initial_attempt"
  assert record["retry_context_mode"] is None
  assert manifest["counts"]["attempt_count_total"] == 1
  assert manifest["counts"]["escalation_eligible_count"] == 0
  assert manifest["counts"]["escalation_triggered_count"] == 0
  assert manifest["final_decision_source_counts"] == {"initial_attempt": 1}
  assert len(attempts) == 1
  assert len(client.prompts) == 1


def test_runner_adaptive_isolated_candidate_does_not_retry_no_violation(tmp_path):
  _write_candidates(
    tmp_path,
    [_candidate_record(candidate_type="button-label-mismatch")],
  )
  client = SequenceDecisionClient([{"decision": "no_violation", "confidence": 0.8}])

  run_confirmation(
    config=ConfirmationConfig(context_mode=CONTEXT_MODE_ADAPTIVE),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="run-no-decision-escalation",
    ),
    client=client,
  )

  output_dir = tmp_path / "confirmations" / "run-no-decision-escalation"
  record = _read_jsonl(output_dir / "confirmations.jsonl")[0]
  attempts = _read_jsonl(output_dir / "confirmation_attempts.jsonl")

  assert record["decision"] == "no_violation"
  assert record["attempt_count"] == 1
  assert record["escalation_eligible"] is True
  assert record["escalation_triggered"] is False
  assert record["final_decision_source"] == "initial_attempt"
  assert len(attempts) == 1
  assert len(client.prompts) == 1


def test_runner_adaptive_isolated_candidate_does_not_retry_violation(tmp_path):
  _write_candidates(
    tmp_path,
    [_candidate_record(candidate_type="button-label-mismatch")],
  )
  client = SequenceDecisionClient([{"decision": "violation", "confidence": 0.8}])

  run_confirmation(
    config=ConfirmationConfig(context_mode=CONTEXT_MODE_ADAPTIVE),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="run-violation-no-escalation",
    ),
    client=client,
  )

  output_dir = tmp_path / "confirmations" / "run-violation-no-escalation"
  record = _read_jsonl(output_dir / "confirmations.jsonl")[0]
  attempts = _read_jsonl(output_dir / "confirmation_attempts.jsonl")

  assert record["decision"] == "violation"
  assert record["attempt_count"] == 1
  assert record["escalation_eligible"] is True
  assert record["escalation_triggered"] is False
  assert record["final_decision_source"] == "initial_attempt"
  assert len(attempts) == 1
  assert len(client.prompts) == 1


def test_runner_adaptive_graph_policy_candidate_does_not_retry_uncertain_result(tmp_path):
  _write_candidates(
    tmp_path,
    [_candidate_record(candidate_type="page-title-not-descriptive")],
  )
  client = SequenceDecisionClient([{"decision": "uncertain", "confidence": 0.4}])

  run_confirmation(
    config=ConfirmationConfig(context_mode=CONTEXT_MODE_ADAPTIVE),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="run-graph-policy-no-escalation",
    ),
    client=client,
  )

  output_dir = tmp_path / "confirmations" / "run-graph-policy-no-escalation"
  record = _read_jsonl(output_dir / "confirmations.jsonl")[0]
  attempts = _read_jsonl(output_dir / "confirmation_attempts.jsonl")

  assert record["decision"] == "uncertain"
  assert record["resolved_context_mode"] == CONTEXT_MODE_GRAPH
  assert record["graph_context_included"] is True
  assert record["attempt_count"] == 1
  assert record["escalation_eligible"] is False
  assert record["escalation_triggered"] is False
  assert len(attempts) == 1
  assert len(client.prompts) == 1


def test_runner_fixed_graph_mode_does_not_retry_uncertain_candidate(tmp_path):
  _write_candidates(tmp_path, [_candidate_record(candidate_type="button-label-mismatch")])
  client = SequenceDecisionClient([{"decision": "uncertain", "confidence": 0.4}])

  run_confirmation(
    config=ConfirmationConfig(
      context_mode=CONTEXT_MODE_GRAPH,
      escalation_policy=ESCALATION_POLICY_UNCERTAIN_GRAPH,
    ),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="run-fixed-graph-no-escalation",
    ),
    client=client,
  )

  output_dir = tmp_path / "confirmations" / "run-fixed-graph-no-escalation"
  record = _read_jsonl(output_dir / "confirmations.jsonl")[0]
  attempts = _read_jsonl(output_dir / "confirmation_attempts.jsonl")

  assert record["decision"] == "uncertain"
  assert record["context_mode"] == CONTEXT_MODE_GRAPH
  assert record["resolved_context_mode"] == CONTEXT_MODE_GRAPH
  assert record["escalation_policy"] == ESCALATION_POLICY_NONE
  assert record["attempt_count"] == 1
  assert record["escalation_eligible"] is False
  assert record["escalation_triggered"] is False
  assert len(attempts) == 1
  assert len(client.prompts) == 1


def test_runner_keeps_initial_uncertain_when_graph_retry_fails(tmp_path):
  _write_candidates(
    tmp_path,
    [_candidate_record(candidate_type="button-label-mismatch")],
  )
  client = SequenceDecisionClient(
    [
      {"decision": "uncertain", "confidence": 0.42},
      "{not valid json",
    ]
  )

  run_confirmation(
    config=ConfirmationConfig(context_mode=CONTEXT_MODE_ADAPTIVE),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="run-retry-failure",
    ),
    client=client,
  )

  output_dir = tmp_path / "confirmations" / "run-retry-failure"
  manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
  record = _read_jsonl(output_dir / "confirmations.jsonl")[0]
  attempts = _read_jsonl(output_dir / "confirmation_attempts.jsonl")

  assert record["decision"] == "uncertain"
  assert record["parse_status"] == "parsed"
  assert record["resolved_context_mode"] == CONTEXT_MODE_ISOLATED
  assert record["attempt_count"] == 2
  assert record["escalation_triggered"] is True
  assert record["final_decision_source"] == "initial_attempt"
  assert record["retry_context_mode"] == CONTEXT_MODE_GRAPH
  assert record["retry_decision"] == "uncertain"
  assert record["retry_parse_status"] == "malformed_json"
  assert "not valid JSON" in record["retry_error"]
  assert manifest["by_decision"] == {"uncertain": 1}
  assert manifest["parse_status_counts"] == {"parsed": 1}
  assert manifest["retry_parse_status_counts"] == {"malformed_json": 1}
  assert manifest["counts"]["retry_error_count"] == 1
  assert manifest["final_decision_source_counts"] == {"initial_attempt": 1}
  assert len(attempts) == 2
  assert attempts[1]["parse_status"] == "malformed_json"


def test_runner_filters_and_limits_candidates(tmp_path):
  _write_candidates(
    tmp_path,
    [
      _candidate_record(candidate_id="cand_button_1"),
      _candidate_record(candidate_id="cand_button_2"),
      _candidate_record(candidate_id="cand_title", candidate_type="page-title-not-descriptive"),
    ],
  )

  run_confirmation(
    config=ConfirmationConfig(),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="run-filtered",
      candidate_types=("button-label-mismatch",),
      limit=1,
    ),
  )

  output_dir = tmp_path / "confirmations" / "run-filtered"
  manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
  records = _read_jsonl(output_dir / "confirmations.jsonl")

  assert manifest["counts"]["candidates_available"] == 2
  assert manifest["counts"]["candidates_selected"] == 1
  assert [record["candidate_id"] for record in records] == ["cand_button_1"]


def test_runner_filters_by_single_candidate_id(tmp_path):
  _write_candidates(
    tmp_path,
    [
      _candidate_record(candidate_id="cand_button_1"),
      _candidate_record(candidate_id="cand_button_2"),
    ],
  )

  run_confirmation(
    config=ConfirmationConfig(),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="run-candidate-id",
      candidate_ids=("cand_button_2",),
    ),
  )

  output_dir = tmp_path / "confirmations" / "run-candidate-id"
  manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
  records = _read_jsonl(output_dir / "confirmations.jsonl")

  assert manifest["inputs"]["candidate_ids"] == ["cand_button_2"]
  assert manifest["inputs"]["selected_candidate_ids"] == ["cand_button_2"]
  assert manifest["counts"]["candidates_available"] == 1
  assert [record["candidate_id"] for record in records] == ["cand_button_2"]


def test_runner_filters_by_repeated_candidate_ids(tmp_path):
  _write_candidates(
    tmp_path,
    [
      _candidate_record(candidate_id="cand_button_1"),
      _candidate_record(candidate_id="cand_button_2"),
      _candidate_record(candidate_id="cand_title", candidate_type="page-title-not-descriptive"),
    ],
  )

  run_confirmation(
    config=ConfirmationConfig(),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="run-candidate-ids",
      candidate_ids=("cand_button_2", "cand_title"),
    ),
  )

  output_dir = tmp_path / "confirmations" / "run-candidate-ids"
  manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
  records = _read_jsonl(output_dir / "confirmations.jsonl")

  assert manifest["inputs"]["candidate_ids"] == ["cand_button_2", "cand_title"]
  assert manifest["inputs"]["selected_candidate_ids"] == ["cand_button_2", "cand_title"]
  assert [record["candidate_id"] for record in records] == ["cand_button_2", "cand_title"]


def test_runner_rejects_missing_requested_candidate_id(tmp_path):
  _write_candidates(tmp_path, [_candidate_record(candidate_id="cand_button")])

  with pytest.raises(ValueError, match="Requested candidate ids were not found.*cand_missing"):
    run_confirmation(
      config=ConfirmationConfig(),
      options=ConfirmationRunOptions(
        run_dir=tmp_path,
        confirmation_run_id="run-missing-id",
        candidate_ids=("cand_button", "cand_missing"),
      ),
    )


def test_runner_candidate_id_and_candidate_type_filters_both_apply(tmp_path):
  _write_candidates(
    tmp_path,
    [
      _candidate_record(candidate_id="cand_button"),
      _candidate_record(candidate_id="cand_title", candidate_type="page-title-not-descriptive"),
      _candidate_record(candidate_id="cand_other"),
    ],
  )

  run_confirmation(
    config=ConfirmationConfig(),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="run-id-and-type",
      candidate_ids=("cand_button", "cand_title"),
      candidate_types=("button-label-mismatch",),
    ),
  )

  output_dir = tmp_path / "confirmations" / "run-id-and-type"
  manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
  records = _read_jsonl(output_dir / "confirmations.jsonl")

  assert manifest["inputs"]["candidate_types"] == ["button-label-mismatch"]
  assert manifest["inputs"]["candidate_ids"] == ["cand_button", "cand_title"]
  assert manifest["inputs"]["selected_candidate_ids"] == ["cand_button"]
  assert [record["candidate_id"] for record in records] == ["cand_button"]


def test_runner_candidate_id_selection_preserves_limit_behavior(tmp_path):
  _write_candidates(
    tmp_path,
    [
      _candidate_record(candidate_id="cand_button_1"),
      _candidate_record(candidate_id="cand_button_2"),
      _candidate_record(candidate_id="cand_button_3"),
    ],
  )

  run_confirmation(
    config=ConfirmationConfig(),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="run-id-limit",
      candidate_ids=("cand_button_1", "cand_button_2", "cand_button_3"),
      limit=2,
    ),
  )

  output_dir = tmp_path / "confirmations" / "run-id-limit"
  manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
  records = _read_jsonl(output_dir / "confirmations.jsonl")

  assert manifest["counts"]["candidates_available"] == 3
  assert manifest["counts"]["candidates_selected"] == 2
  assert manifest["inputs"]["selected_candidate_ids"] == ["cand_button_1", "cand_button_2"]
  assert [record["candidate_id"] for record in records] == ["cand_button_1", "cand_button_2"]


def test_runner_real_provider_safety_accepts_candidate_id_selection(tmp_path):
  _write_candidates(tmp_path, [_candidate_record(candidate_id="cand_button")])

  result = run_confirmation(
    config=ConfirmationConfig(
      provider="ollama",
      model="qwen2.5:7b",
      base_url="http://localhost:11434/api",
    ),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="run-real-provider-id",
      candidate_ids=("cand_button",),
      dry_run=True,
    ),
    client=FailingClient(),
  )

  assert result.manifest["counts"]["candidates_selected"] == 1
  assert result.manifest["inputs"]["candidate_ids"] == ["cand_button"]


def test_runner_dry_run_does_not_write_outputs(tmp_path):
  _write_candidates(tmp_path, [_candidate_record()])

  result = run_confirmation(
    config=ConfirmationConfig(),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="dry-run",
      dry_run=True,
    ),
    client=FailingClient(),
  )

  assert result.dry_run is True
  assert result.manifest["counts"]["candidates_selected"] == 1
  assert not (tmp_path / "confirmations" / "dry-run").exists()


def test_runner_preserves_explicit_context_metadata_when_no_candidates_are_selected(tmp_path):
  _write_candidates(tmp_path, [_candidate_record()])

  graph_result = run_confirmation(
    config=ConfirmationConfig(context_mode=CONTEXT_MODE_GRAPH),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="dry-run-zero-graph",
      limit=0,
      dry_run=True,
    ),
  )
  isolated_result = run_confirmation(
    config=ConfirmationConfig(context_mode=CONTEXT_MODE_ISOLATED),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="dry-run-zero-isolated",
      limit=0,
      dry_run=True,
    ),
  )

  assert graph_result.manifest["counts"]["candidates_selected"] == 0
  assert graph_result.manifest["context_mode"] == CONTEXT_MODE_GRAPH
  assert graph_result.manifest["requested_context_mode"] == CONTEXT_MODE_GRAPH
  assert graph_result.manifest["resolved_context_mode"] == CONTEXT_MODE_GRAPH
  assert graph_result.manifest["resolved_context_mode_counts"] == {}
  assert graph_result.manifest["graph_context_included"] is True

  assert isolated_result.manifest["counts"]["candidates_selected"] == 0
  assert isolated_result.manifest["context_mode"] == CONTEXT_MODE_ISOLATED
  assert isolated_result.manifest["requested_context_mode"] == CONTEXT_MODE_ISOLATED
  assert isolated_result.manifest["resolved_context_mode"] == CONTEXT_MODE_ISOLATED
  assert isolated_result.manifest["resolved_context_mode_counts"] == {}
  assert isolated_result.manifest["graph_context_included"] is False


def test_runner_dry_run_uses_explicit_calibrated_text_prompt(tmp_path):
  _write_candidates(tmp_path, [_candidate_record()])

  result = run_confirmation(
    config=ConfirmationConfig(prompt_version=CALIBRATED_TEXT_PROMPT_VERSION),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="dry-run-calibrated-text",
      dry_run=True,
    ),
    client=FailingClient(),
  )

  assert result.manifest["prompt_version"] == CALIBRATED_TEXT_PROMPT_VERSION
  assert result.manifest["config"]["prompt_version"] == CALIBRATED_TEXT_PROMPT_VERSION


def test_runner_guided_html_screenshot_uncertain_does_not_trigger_adaptive_retry(tmp_path):
  _write_candidates(tmp_path, [_candidate_record(candidate_id="cand_minimal_vision")])
  client = SequenceDecisionClient(
    [
      {
        "decision": "uncertain",
        "confidence": 0.4,
        "reason": "The supplied HTML and screenshot are insufficient.",
        "supporting_evidence": ["candidate HTML", "attached screenshot"],
      },
      {"decision": "violation"},
    ]
  )

  run_confirmation(
    config=ConfirmationConfig(
      provider="openai-vision",
      model="gpt-5.4-mini",
      prompt_version=GUIDED_HTML_SCREENSHOT_PROMPT_VERSION,
      context_mode=CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT,
    ),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="minimal-html-screenshot-output",
      candidate_ids=("cand_minimal_vision",),
    ),
    client=client,
  )

  output_dir = tmp_path / "confirmations" / "minimal-html-screenshot-output"
  manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
  record = _read_jsonl(output_dir / "confirmations.jsonl")[0]

  assert len(client.prompts) == 1
  assert manifest["context_mode"] == CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT
  assert manifest["resolved_context_mode"] == CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT
  assert manifest["escalation_policy"] == ESCALATION_POLICY_NONE
  assert manifest["counts"]["attempt_count_total"] == 1
  assert manifest["counts"]["escalation_triggered_count"] == 0
  assert record["decision"] == "uncertain"
  assert record["resolved_context_mode"] == CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT


def test_runner_guided_html_screenshot_missing_candidate_html_is_input_error(tmp_path):
  screenshot_path = tmp_path / "states" / "state_0001" / "screenshot.png"
  screenshot_path.parent.mkdir(parents=True)
  screenshot_path.write_bytes(b"\x89PNG\r\nminimal-input-error")
  record = _candidate_record(candidate_id="cand_missing_html")
  record["evidence"].pop("dom_snippets", None)
  record["evidence"]["supporting"].pop("dom_snippets", None)
  _write_candidates(tmp_path, [record])
  client = SequenceDecisionClient([{"decision": "violation"}])

  run_confirmation(
    config=ConfirmationConfig(
      provider="openai-vision",
      model="gpt-5.4-mini",
      prompt_version=GUIDED_HTML_SCREENSHOT_PROMPT_VERSION,
      context_mode=CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT,
    ),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="minimal-html-missing-input",
      candidate_ids=("cand_missing_html",),
    ),
    client=client,
  )

  output_dir = tmp_path / "confirmations" / "minimal-html-missing-input"
  manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
  confirmation = _read_jsonl(output_dir / "confirmations.jsonl")[0]
  attempt = _read_jsonl(output_dir / "confirmation_attempts.jsonl")[0]

  assert client.prompts == []
  assert manifest["parse_status_counts"] == {"client_error": 1}
  assert manifest["counts"]["attempt_count_total"] == 1
  assert confirmation["decision"] == "uncertain"
  assert confirmation["parse_status"] == "client_error"
  assert confirmation["final_decision_source"] == "input_error"
  assert "Input error: minimal_html_screenshot requires candidate HTML" in confirmation["error"]
  assert confirmation["image_source"] == "state_screenshot"
  assert confirmation["image_input"]["screenshot"] == "states/state_0001/screenshot.png"
  assert attempt["attempt_role"] == "input_error"


def test_runner_calibrated_prompt_attaches_bundle_metadata_when_ids_are_misechoed(tmp_path):
  _write_candidates(tmp_path, [_candidate_record(candidate_id="cand_calibrated")])

  run_confirmation(
    config=ConfirmationConfig(prompt_version=CALIBRATED_TEXT_PROMPT_VERSION),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="calibrated-output",
    ),
    client=MismatchedIdClient(),
  )

  output_dir = tmp_path / "confirmations" / "calibrated-output"
  manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
  record = _read_jsonl(output_dir / "confirmations.jsonl")[0]
  raw_response = json.loads(next((output_dir / "raw_responses").glob("*.json")).read_text(encoding="utf-8"))

  assert manifest["prompt_version"] == CALIBRATED_TEXT_PROMPT_VERSION
  assert manifest["parse_status_counts"] == {"parsed": 1}
  assert record["candidate_id"] == "cand_calibrated"
  assert record["candidate_type"] == "button-label-mismatch"
  assert record["state_id"] == "state_0001"
  assert record["decision"] == "violation"
  assert record["parse_status"] == "parsed"
  assert '"candidate_id": "state_0001"' in raw_response["raw_content"]


def test_runner_rejects_incompatible_vision_prompt_for_text_provider(tmp_path):
  _write_candidates(tmp_path, [_candidate_record()])

  with pytest.raises(ValueError, match="incompatible"):
    run_confirmation(
      config=ConfirmationConfig(
        provider="ollama",
        model="qwen2.5:7b",
        base_url="http://localhost:11434/api",
        prompt_version=CALIBRATED_VISION_PROMPT_VERSION,
      ),
      options=ConfirmationRunOptions(
        run_dir=tmp_path,
        confirmation_run_id="bad-prompt",
        limit=1,
        dry_run=True,
      ),
      client=FailingClient(),
    )


def test_runner_rejects_guided_html_screenshot_with_text_provider(tmp_path):
  _write_candidates(tmp_path, [_candidate_record()])

  with pytest.raises(ValueError, match="incompatible with --provider 'openai'"):
    run_confirmation(
      config=ConfirmationConfig(
        provider="openai",
        model="gpt-5.4-mini",
        prompt_version=GUIDED_HTML_SCREENSHOT_PROMPT_VERSION,
        context_mode=CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT,
      ),
      options=ConfirmationRunOptions(
        run_dir=tmp_path,
        confirmation_run_id="guided-text-provider-rejected",
        candidate_ids=("cand_button",),
      ),
      client=FailingClient(),
    )


def test_runner_allows_explicit_calibrated_vision_prompt(tmp_path):
  _write_candidates(tmp_path, [_candidate_record()])

  result = run_confirmation(
    config=ConfirmationConfig(
      provider="ollama-vision",
      model="qwen2.5vl:7b",
      base_url="http://localhost:11434/api",
      prompt_version=CALIBRATED_VISION_PROMPT_VERSION,
    ),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="dry-run-calibrated-vision",
      limit=1,
      dry_run=True,
    ),
    client=FailingClient(),
  )

  assert result.manifest["prompt_version"] == CALIBRATED_VISION_PROMPT_VERSION
  assert result.manifest["input_mode"] == "vision"
  assert result.manifest["input_modalities"] == ["text", "image"]


def test_runner_converts_malformed_response_to_uncertain_by_default(tmp_path):
  _write_candidates(tmp_path, [_candidate_record()])

  run_confirmation(
    config=ConfirmationConfig(),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="malformed",
    ),
    client=FakeConfirmationClient(malformed_response=True),
  )

  record = _read_jsonl(tmp_path / "confirmations" / "malformed" / "confirmations.jsonl")[0]

  assert record["decision"] == "uncertain"
  assert record["confidence"] == 0.0
  assert record["parse_status"] == "malformed_json"
  assert record["error"]


def test_runner_fail_fast_stops_on_malformed_response(tmp_path):
  _write_candidates(tmp_path, [_candidate_record()])

  with pytest.raises(ConfirmationParseError):
    run_confirmation(
      config=ConfirmationConfig(),
      options=ConfirmationRunOptions(
        run_dir=tmp_path,
        confirmation_run_id="malformed-fast",
        fail_fast=True,
      ),
      client=FakeConfirmationClient(malformed_response=True),
    )


def test_runner_strict_parse_stops_on_malformed_response(tmp_path):
  _write_candidates(tmp_path, [_candidate_record()])

  with pytest.raises(ConfirmationParseError):
    run_confirmation(
      config=ConfirmationConfig(strict_parse=True),
      options=ConfirmationRunOptions(
        run_dir=tmp_path,
        confirmation_run_id="malformed-strict",
      ),
      client=FakeConfirmationClient(malformed_response=True),
    )


def test_runner_converts_client_error_to_uncertain_by_default(tmp_path):
  _write_candidates(tmp_path, [_candidate_record()])

  run_confirmation(
    config=ConfirmationConfig(),
    options=ConfirmationRunOptions(
      run_dir=tmp_path,
      confirmation_run_id="client-error",
    ),
    client=FailingClient(),
  )

  record = _read_jsonl(tmp_path / "confirmations" / "client-error" / "confirmations.jsonl")[0]

  assert record["decision"] == "uncertain"
  assert record["confidence"] == 0.0
  assert record["parse_status"] == "client_error"
  assert record["error"] == "simulated provider failure"


def test_runner_rejects_unsupported_provider(tmp_path):
  _write_candidates(tmp_path, [_candidate_record()])

  with pytest.raises(ValueError, match="Unsupported confirmation provider"):
    run_confirmation(
      config=ConfirmationConfig(provider="bogus", model="qwen2.5:7b"),
      options=ConfirmationRunOptions(
        run_dir=tmp_path,
        confirmation_run_id="unsupported-provider",
      ),
      client=FakeConfirmationClient(),
    )
