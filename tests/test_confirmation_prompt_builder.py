from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from src.analysis.candidates.taxonomy import SUPPORTED_CANDIDATE_TYPES
from src.analysis.confirmation.models import (
  CALIBRATED_TEXT_PROMPT_VERSION,
  CALIBRATED_VISION_PROMPT_VERSION,
  CONTEXT_MODE_GRAPH,
  CONTEXT_MODE_ISOLATED,
  CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT,
  GUIDED_HTML_SCREENSHOT_PROMPT_VERSION,
  ReviewBundle,
)
from src.analysis.confirmation.prompt_builder import build_confirmation_prompt, load_prompt_templates


def test_prompt_guidance_matches_supported_candidate_types():
  for prompt_version in (
    CALIBRATED_TEXT_PROMPT_VERSION,
    CALIBRATED_VISION_PROMPT_VERSION,
    GUIDED_HTML_SCREENSHOT_PROMPT_VERSION,
  ):
    templates = load_prompt_templates(prompt_version)
    assert set(templates.type_guidance) == set(SUPPORTED_CANDIDATE_TYPES)
    assert "heading-not-descriptive" in templates.type_guidance
    assert "ambiguous-heading" not in templates.type_guidance
    video_guidance = templates.type_guidance["video-captions-inaccurate"]
    assert "semantic caption content" in video_guidance
    assert "spoken narration or authoritative transcript evidence" in video_guidance
    assert "not caption presence" in video_guidance
    assert "timing accuracy" in video_guidance
    assert "Choose uncertain" in video_guidance
    if prompt_version == GUIDED_HTML_SCREENSHOT_PROMPT_VERSION:
      assert "supplied WCAG/type guidance" in templates.system_template
    else:
      assert "AccessGraph currently exposes exactly these executable semantic candidate types" in templates.system_template
    assert "missing-lang-tag" not in templates.system_template
    assert "label-name-mismatch" not in templates.system_template
    if prompt_version != GUIDED_HTML_SCREENSHOT_PROMPT_VERSION:
      assert "- video-captions-inaccurate" in templates.system_template


def test_build_confirmation_prompt_includes_candidate_payload_and_no_graph_in_isolated_mode():
  prompt = build_confirmation_prompt(_bundle(), context_mode=CONTEXT_MODE_ISOLATED)
  payload = _candidate_payload(prompt.user_prompt)

  assert prompt.prompt_version == CALIBRATED_TEXT_PROMPT_VERSION
  assert prompt.context_mode == CONTEXT_MODE_ISOLATED
  assert prompt.graph_context_included is False
  assert payload["candidate_id"] == "cand_prompt"
  assert payload["candidate_type"] == "button-label-mismatch"
  assert "graph_context" not in payload
  assert "button_action_context_v1" in prompt.user_prompt


def test_build_confirmation_prompt_keeps_graph_context_when_requested():
  prompt = build_confirmation_prompt(_heading_bundle(), context_mode=CONTEXT_MODE_GRAPH)
  payload = _candidate_payload(prompt.user_prompt)

  assert prompt.graph_context_included is True
  assert payload["candidate_type"] == "heading-not-descriptive"
  assert "transition_heading_context" in payload["graph_context"]
  assert "heading-not-descriptive" in prompt.user_prompt


def test_isolated_link_prompt_keeps_source_evidence_and_excludes_observed_destination():
  bundle = _link_transition_bundle()
  original_evidence = deepcopy(bundle.evidence)

  prompt = build_confirmation_prompt(bundle, context_mode=CONTEXT_MODE_ISOLATED)
  payload = _candidate_payload(prompt.user_prompt)
  evidence = payload["evidence"]
  supporting = evidence["supporting"]

  assert evidence["primary"]["link"] == {
    "element_id": "link-change-appointment",
    "selector": "a[data-testid='change-appointment']",
    "text": "Change appointment",
    "accessible_name": "Change appointment",
    "href": "/schedule",
  }
  assert supporting["link_destination_context_v1"] == {
    "schema_version": "link_destination_context_v1",
    "raw_href": "/schedule",
    "resolved_url": "https://example.com/schedule",
    "resolved_path": "/schedule",
    "fragment": "",
  }
  assert "destination_state_context_v1" not in supporting
  assert "OBSERVED_SERVICES_DESTINATION" not in prompt.user_prompt
  assert bundle.evidence == original_evidence


def test_isolated_button_prompt_keeps_source_evidence_and_excludes_activation_result():
  bundle = _button_transition_bundle()
  original_evidence = deepcopy(bundle.evidence)

  prompt = build_confirmation_prompt(bundle, context_mode=CONTEXT_MODE_ISOLATED)
  payload = _candidate_payload(prompt.user_prompt)
  evidence = payload["evidence"]
  supporting = evidence["supporting"]
  button_context = supporting["button_action_context_v1"]

  assert evidence["primary"]["button"]["text"] == "Confirm booking"
  assert evidence["primary"]["button"]["accessible_name"] == "Confirm booking"
  assert button_context["action_evidence"] == {
    "button_type": "button",
    "data_testid": "confirm-booking",
    "form_context": {},
  }
  assert "destination_state_context_v1" not in supporting
  assert "OBSERVED_DETAILS_DESTINATION" not in prompt.user_prompt
  assert bundle.evidence == original_evidence


def test_graph_prompt_preserves_transition_evidence_after_isolated_prompt_construction():
  fixtures = (
    (_link_transition_bundle, "OBSERVED_SERVICES_DESTINATION"),
    (_button_transition_bundle, "OBSERVED_DETAILS_DESTINATION"),
  )
  for bundle_factory, destination_marker in fixtures:
    bundle = bundle_factory()
    original_evidence = deepcopy(bundle.evidence)

    isolated_prompt = build_confirmation_prompt(bundle, context_mode=CONTEXT_MODE_ISOLATED)
    graph_prompt = build_confirmation_prompt(bundle, context_mode=CONTEXT_MODE_GRAPH)

    isolated_payload = _candidate_payload(isolated_prompt.user_prompt)
    graph_payload = _candidate_payload(graph_prompt.user_prompt)

    assert "destination_state_context_v1" not in isolated_payload["evidence"]["supporting"]
    assert graph_payload["evidence"] == original_evidence
    assert graph_payload["graph_context"] == bundle.graph_context
    assert destination_marker not in isolated_prompt.user_prompt
    assert destination_marker in graph_prompt.user_prompt
    assert bundle.evidence == original_evidence

    reverse_bundle = bundle_factory()
    reverse_original_evidence = deepcopy(reverse_bundle.evidence)
    graph_first_prompt = build_confirmation_prompt(reverse_bundle, context_mode=CONTEXT_MODE_GRAPH)
    isolated_after_prompt = build_confirmation_prompt(
      reverse_bundle,
      context_mode=CONTEXT_MODE_ISOLATED,
    )

    assert (
      _candidate_payload(graph_first_prompt.user_prompt)["evidence"]
      == reverse_original_evidence
    )
    assert (
      _candidate_payload(isolated_after_prompt.user_prompt)["evidence"]
      == isolated_payload["evidence"]
    )
    assert reverse_bundle.evidence == reverse_original_evidence


def test_isolated_prompt_preserves_state_local_semantic_evidence():
  bundle = _state_local_bundle()
  original_evidence = deepcopy(bundle.evidence)

  prompt = build_confirmation_prompt(bundle, context_mode=CONTEXT_MODE_ISOLATED)
  payload = _candidate_payload(prompt.user_prompt)

  assert payload["evidence"] == original_evidence
  assert payload["state_context"] == {
    "url": "https://example.com/address",
    "title": "Shipping address",
  }
  assert "graph_context" not in payload
  assert bundle.evidence == original_evidence


def test_guided_html_screenshot_prompt_uses_local_type_guidance_without_external_glossary_dependency(tmp_path):
  run_dir = tmp_path / "run"
  state_dir = run_dir / "states" / "state_0001"
  state_dir.mkdir(parents=True)
  dom_path = state_dir / "dom.html"
  dom_path.write_text('<button id="save" aria-label="Save task">Delete</button>', encoding="utf-8")

  bundle = replace(
    _bundle(run_dir=run_dir),
    evidence={"supporting": {}},
    artifact_refs={"dom_html": "states/state_0001/dom.html"},
  )
  prompt = build_confirmation_prompt(
    bundle,
    templates=load_prompt_templates(GUIDED_HTML_SCREENSHOT_PROMPT_VERSION),
    context_mode=CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT,
  )

  assert prompt.prompt_version == GUIDED_HTML_SCREENSHOT_PROMPT_VERSION
  assert prompt.graph_context_included is False
  assert '<button id="save" aria-label="Save task">Delete</button>' in prompt.user_prompt
  assert "button-label-mismatch" in prompt.user_prompt


def test_guided_html_screenshot_prompt_requires_matching_context_mode():
  with pytest.raises(ValueError, match="requires"):
    build_confirmation_prompt(
      _bundle(),
      templates=load_prompt_templates(GUIDED_HTML_SCREENSHOT_PROMPT_VERSION),
      context_mode=CONTEXT_MODE_ISOLATED,
    )


def _bundle(*, run_dir: Path | None = None) -> ReviewBundle:
  resolved_run_dir = run_dir or Path("runs/example").resolve()
  return ReviewBundle(
    run_dir=resolved_run_dir,
    source_path=resolved_run_dir / "candidates" / "candidates.jsonl",
    source_line_number=3,
    record={"candidate_id": "cand_prompt", "candidate_type": "button-label-mismatch", "state_id": "state_0001"},
    candidate_id="cand_prompt",
    candidate_type="button-label-mismatch",
    state_id="state_0001",
    element_refs=({"bucket": "buttons", "element_id": "button-1", "selector": "#save"},),
    primary_element_ref={"bucket": "buttons", "element_id": "button-1", "selector": "#save"},
    selection_reason=("visible_button_with_label_and_context_evidence",),
    required_context=("button label", "nearby text"),
    evidence={
      "primary": {
        "button": {
          "element_id": "button-1",
          "selector": "#save",
          "text": "Delete",
          "accessible_name": "Save task",
        }
      },
      "supporting": {
        "button_action_context_v1": {
          "schema_version": "button_action_context_v1",
          "button": {"element_id": "button-1", "selector": "#save", "html": '<button id="save" aria-label="Save task">Delete</button>'},
          "labeling": {"visible_text": "Delete", "computed_accessible_name": "Save task"},
        },
        "dom_snippets": [
          {"element_id": "button-1", "selector": "#save", "html": '<button id="save" aria-label="Save task">Delete</button>'}
        ],
      },
      "dom_snippets": [
        {"element_id": "button-1", "selector": "#save", "html": '<button id="save" aria-label="Save task">Delete</button>'}
      ],
    },
    state_context={"url": "https://example.com/settings", "title": "Settings", "depth": 1, "parent_state": "state_0000"},
    graph_context={"transition_path": [{"from": "state_0000", "to": "state_0001"}]},
    artifact_refs={"screenshot": "states/state_0001/screenshot.png"},
    generator={"name": "offline_semantic_candidate_builder", "version": "1"},
  )


def _heading_bundle() -> ReviewBundle:
  return replace(
    _bundle(),
    record={"candidate_id": "cand_heading", "candidate_type": "heading-not-descriptive", "state_id": "state_0002"},
    candidate_id="cand_heading",
    candidate_type="heading-not-descriptive",
    state_id="state_0002",
    element_refs=({"bucket": "headings", "element_id": "heading-1", "selector": "h2#slot-list-heading"},),
    primary_element_ref={"bucket": "headings", "element_id": "heading-1", "selector": "h2#slot-list-heading"},
    evidence={"primary": {"heading": {"text": "Available times", "level": 2}}, "supporting": {}},
    graph_context={"transition_heading_context": {"current_heading": {"text": "Available times"}}},
  )


def _link_transition_bundle() -> ReviewBundle:
  return replace(
    _bundle(),
    candidate_id="cand_link",
    candidate_type="link-text-mismatch",
    evidence={
      "primary": {
        "link": {
          "element_id": "link-change-appointment",
          "selector": "a[data-testid='change-appointment']",
          "text": "Change appointment",
          "accessible_name": "Change appointment",
          "href": "/schedule",
        }
      },
      "supporting": {
        "link_destination_context_v1": {
          "schema_version": "link_destination_context_v1",
          "raw_href": "/schedule",
          "resolved_url": "https://example.com/schedule",
          "resolved_path": "/schedule",
          "fragment": "",
          "match_status": "matched_state",
          "target_state_id": "state_services",
          "target_state_route": "/services",
          "target_state_title": "OBSERVED_SERVICES_DESTINATION",
          "target_state_headings": [{"text": "Choose a service"}],
        },
        "destination_state_context_v1": {
          "schema_version": "destination_state_context_v1",
          "source_state_id": "state_review",
          "match_basis": ["data_testid"],
          "destinations": [
            {
              "target_state_id": "state_services",
              "target_route": "/services",
              "target_title": "OBSERVED_SERVICES_DESTINATION",
              "action_type": "click",
              "action_text": "Change appointment",
            }
          ],
        },
      },
    },
    graph_context={
      "transition_path": [
        {
          "from": "state_review",
          "to": "state_services",
          "action": {"type": "click", "text": "Change appointment"},
        }
      ]
    },
  )


def _button_transition_bundle() -> ReviewBundle:
  return replace(
    _bundle(),
    evidence={
      "primary": {
        "button": {
          "element_id": "button-confirm-booking",
          "selector": "button[data-testid='confirm-booking']",
          "text": "Confirm booking",
          "accessible_name": "Confirm booking",
          "type": "button",
        }
      },
      "supporting": {
        "button_action_context_v1": {
          "schema_version": "button_action_context_v1",
          "button": {
            "element_id": "button-confirm-booking",
            "selector": "button[data-testid='confirm-booking']",
            "type": "button",
          },
          "labeling": {
            "visible_text": "Confirm booking",
            "computed_accessible_name": "Confirm booking",
          },
          "local_context": {"section_heading": "Review booking"},
          "action_evidence": {
            "button_type": "button",
            "data_testid": "confirm-booking",
            "form_context": {},
            "matched_outgoing_transition": {
              "from_state": "state_review",
              "to_state": "state_details",
              "match_basis": ["data_testid"],
            },
            "result_state_context": {
              "state_id": "state_details",
              "route": "/details",
              "title": "OBSERVED_DETAILS_DESTINATION",
              "headings": ["Your details"],
            },
          },
        },
        "destination_state_context_v1": {
          "schema_version": "destination_state_context_v1",
          "source_state_id": "state_review",
          "match_basis": ["data_testid"],
          "destinations": [
            {
              "target_state_id": "state_details",
              "target_route": "/details",
              "target_title": "OBSERVED_DETAILS_DESTINATION",
              "action_type": "click",
            }
          ],
        },
      },
    },
    graph_context={
      "transition_path": [
        {
          "from": "state_review",
          "to": "state_details",
          "action": {"type": "click", "data_testid": "confirm-booking"},
        }
      ]
    },
  )


def _state_local_bundle() -> ReviewBundle:
  return replace(
    _bundle(),
    candidate_id="cand_label",
    candidate_type="form-label-mismatch",
    evidence={
      "primary": {
        "control": {
          "element_id": "address-city",
          "selector": "#address-city",
          "label": "State",
          "accessible_name": "State Required",
          "name": "city",
          "autocomplete": "address-level2",
        }
      },
      "supporting": {
        "context": {
          "nearby_text": "Shipping address",
          "section_heading": "Shipping address",
        }
      },
    },
    state_context={
      "url": "https://example.com/address",
      "title": "Shipping address",
      "depth": 2,
      "parent_state": "state_cart",
      "action_from_parent": {"type": "click", "text": "Continue to shipping"},
    },
  )


def _candidate_payload(user_prompt: str) -> dict[str, object]:
  marker = "Candidate payload:"
  start = user_prompt.index(marker) + len(marker)
  raw = user_prompt[start:].strip()
  return json.loads(raw)
