"""C3: history_context, adaptive_v2 with history re-judging, v5 prompts, cited-evidence check, same-page targets."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.analysis.candidates.same_page_targets import same_page_target
from src.analysis.confirmation.citation_check import check_citations, resolve_path
from src.analysis.confirmation.context_policy import TRANSITION_CAPABLE_TYPES, resolve_confirmation_context_mode
from src.analysis.confirmation.models import ConfirmationConfig, ConfirmationProviderResponse, ParsedConfirmation
from src.analysis.confirmation.prompt_builder import load_prompt_templates
from src.analysis.confirmation.runner import ConfirmationRunOptions, run_confirmation
from src.analysis.candidates.taxonomy import SUPPORTED_CANDIDATE_TYPES

CHANGE = {"schema_version": "change_record_v1", "trigger": {"name": "Remove", "row_text": "Storm Shell"},
          "flags": [{"kind": "heading_text_unchanged_content_changed"}]}


def _record(candidate_type: str, *, candidate_id: str = "c1", graph: bool = True) -> dict:
  return {
    "schema_version": "1", "candidate_id": candidate_id, "candidate_type": candidate_type, "state_id": "state_0001",
    "element_refs": [{"bucket": "headings", "element_id": "h1"}], "selection_reason": ["x"],
    "required_context": ["element evidence"], "evidence": {"primary": {"heading": {"text": "Your basket"}},
                                                           "supporting": {"heading_scope": {"text_excerpt": "Rain Coat"}}},
    "state_context": {"url": "http://127.0.0.1/", "title": "Shop", "depth": 1, "parent_state": "state_0000",
                      "action_from_parent": {"type": "click", "text": "Remove"}} if graph else
                     {"url": "http://127.0.0.1/", "title": "Shop", "depth": 0},
    "graph_context": ({"transition_path": [{"from": "state_0000", "to": "state_0001", "action": {"text": "Remove"}}],
                       "incoming_change_record_v1": CHANGE} if graph else {"transition_path": []}),
    "artifact_refs": {}, "generator": {"name": "offline_semantic_candidate_builder", "version": "1"},
  }


def _write(run_dir: Path, records: list[dict]) -> None:
  (run_dir / "candidates").mkdir(parents=True)
  (run_dir / "candidates" / "candidates.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))


class _Scripted:
  provider, model = "fake", "scripted"

  def __init__(self, answers):
    self.answers, self.prompts = list(answers), []

  def confirm(self, prompt):
    self.prompts.append(prompt)
    decision, evidence = self.answers.pop(0)
    content = json.dumps({"candidate_id": prompt.bundle.candidate_id, "candidate_type": prompt.bundle.candidate_type,
                          "state_id": prompt.bundle.state_id, "decision": decision, "confidence": 0.7, "reason": "r",
                          "supporting_evidence": evidence})
    return ConfirmationProviderResponse(provider="fake", model="scripted", raw_content=content)


def _confirmations(run_dir: Path, run_id: str) -> list[dict]:
  path = run_dir / "confirmations" / run_id / "confirmations.jsonl"
  return [json.loads(line) for line in path.read_text().splitlines()]


def test_adaptive_v2_routes_transition_types_to_history():
  assert len(TRANSITION_CAPABLE_TYPES) == 7
  heading = resolve_confirmation_context_mode("heading-not-descriptive", "adaptive_v2", _record("heading-not-descriptive"))
  assert heading.resolved_context_mode == "history_context" and heading.context_policy_version == "adaptive_v2"
  aria = resolve_confirmation_context_mode("aria-state-mismatch", "adaptive_v2", _record("aria-state-mismatch"))
  assert aria.resolved_context_mode == "isolated_state"
  empty = resolve_confirmation_context_mode("heading-not-descriptive", "adaptive_v2",
                                            _record("heading-not-descriptive", graph=False))
  assert empty.resolved_context_mode == "isolated_state" and empty.graph_context_omitted_reason


def test_history_mode_shows_change_records_graph_mode_does_not(tmp_path):
  _write(tmp_path, [_record("heading-not-descriptive")])
  for mode, run_id in (("history_context", "h"), ("graph_context", "g"), ("isolated_state", "i")):
    client = _Scripted([("no_violation", ["evidence.supporting.heading_scope.text_excerpt"])])
    run_confirmation(config=ConfirmationConfig(prompt_version="confirm_v5_text", context_mode=mode),
                     options=ConfirmationRunOptions(run_dir=tmp_path, confirmation_run_id=run_id), client=client)
    payload = client.prompts[0].user_prompt.split("Candidate payload:\n", 1)[1]
    assert ("incoming_change_record_v1" in payload) == (mode == "history_context"), mode
    assert ("transition_path" in payload) == (mode != "isolated_state"), mode


def test_uncertain_isolated_verdict_is_rejudged_with_history(tmp_path):
  _write(tmp_path, [_record("aria-state-mismatch")])
  client = _Scripted([("uncertain", []), ("violation", ["graph_context.transition_path[0].action.text"])])
  run_confirmation(config=ConfirmationConfig(prompt_version="confirm_v5_text", context_mode="adaptive_v2"),
                   options=ConfirmationRunOptions(run_dir=tmp_path, confirmation_run_id="r"), client=client)
  assert len(client.prompts) == 2
  assert client.prompts[0].resolved_context_mode == "isolated_state"
  assert client.prompts[1].resolved_context_mode == "history_context"
  record = _confirmations(tmp_path, "r")[0]
  assert record["decision"] == "violation"


def test_citation_check_downgrades_unsupported_violation_and_keeps_v4(tmp_path):
  _write(tmp_path, [_record("heading-not-descriptive", candidate_id="c1"), _record("heading-not-descriptive", candidate_id="c2")])
  client = _Scripted([("violation", ["evidence.supporting.heading_scope.text_excerpt", "made.up.path"]),
                      ("violation", ["the heading is stale", "graph_context.nope"])])
  run_confirmation(config=ConfirmationConfig(prompt_version="confirm_v5_text", context_mode="history_context"),
                   options=ConfirmationRunOptions(run_dir=tmp_path, confirmation_run_id="v5"), client=client)
  by_id = {r["candidate_id"]: r for r in _confirmations(tmp_path, "v5")}
  assert by_id["c1"]["decision"] == "violation" and by_id["c1"]["citation_check"]["missing"] == ["made.up.path"]
  assert by_id["c2"]["decision"] == "uncertain" and by_id["c2"]["citation_check"]["downgraded"] is True
  client = _Scripted([("violation", ["free text"]), ("violation", ["free text"])])
  run_confirmation(config=ConfirmationConfig(context_mode="graph_context"),
                   options=ConfirmationRunOptions(run_dir=tmp_path, confirmation_run_id="v4"), client=client)
  assert all(r["decision"] == "violation" and "citation_check" not in r for r in _confirmations(tmp_path, "v4"))
  assert resolve_path({"a": {"b": [{"c": 1}]}}, "`candidate.a.b[0].c`") and not resolve_path({"a": {}}, "a.b")


def test_v5_prompts_cover_every_type_and_differ_from_v4():
  for version in ("confirm_v5_text", "confirm_v5_vision"):
    templates = load_prompt_templates(version)
    assert set(templates.type_guidance) == set(SUPPORTED_CANDIDATE_TYPES)
    assert "History rules" in templates.system_template and "Forward rule" in templates.system_template
    assert "key paths" in templates.user_template
  assert "ambiguous to users in general" in load_prompt_templates("confirm_v5_text").type_guidance["link-text-mismatch"]
  assert "History rules" not in load_prompt_templates("confirm_v4_1_text").system_template


def test_same_page_target_heading_and_excerpt(tmp_path):
  dom = tmp_path / "dom.html"
  dom.write_text("""<html><body><a href="#main">Skip to main content</a><nav>Menu</nav>
    <main id="main"><h1>Order history</h1><p>Your last five orders are listed below with their status.</p></main>
    <h2>Help</h2><a name="contact"></a><p>Call us any weekday.</p>
    <section id="faq"><p>Questions people ask often.</p></section></body></html>""")
  main = same_page_target(dom, "main")
  assert main["target_heading"] == "Order history" and main["heading_basis"] == "first_heading_inside_target"
  assert main["text_excerpt"].startswith("Order history Your last five orders")
  contact = same_page_target(dom, "contact")
  assert contact["heading_basis"] == "nearest_preceding_heading" and contact["target_heading"] == "Help"
  assert contact["text_excerpt"].startswith("Call us") and contact["excerpt_basis"] == "text_after_empty_target"
  assert same_page_target(dom, "missing") == {"schema_version": "same_page_target_v1", "fragment": "missing",
                                              "target_found": False}
  assert same_page_target(dom, "/orders") is None
