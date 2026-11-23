from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.analysis.candidates import build_semantic_candidates
from src.analysis.candidates.payload import stable_candidate_id
from src.analysis.candidates.taxonomy import (
  ALL_SEMANTIC_TYPES,
  CURRENT_REUSABLE_CANDIDATE_TYPES,
  EXCLUDED_LAYOUT_TYPES,
  EXCLUDED_SYNTAX_TYPES,
  OUT_OF_SCOPE_CURRENT_SEMANTIC_TYPES,
  REMOVED_OLD_SEMANTIC_TYPES,
  SEMANTIC_TAXONOMY_ENTRIES,
  SUPPORTED_CANDIDATE_TYPES,
  TEMPORARY_LEGACY_IMPLEMENTATION_TYPES,
  UNSUPPORTED_CURRENT_PIPELINE_TYPES,
  is_excluded_taxonomy_type,
  is_semantic_taxonomy_type,
  is_supported_candidate_type,
  is_temporary_legacy_implementation_type,
  require_supported_candidate_type,
)

FINAL_15_TYPES = (
  "image-alt-not-descriptive",
  "video-captions-inaccurate",
  "lang-mismatch",
  "language-of-parts-mismatch",
  "link-text-mismatch",
  "button-label-mismatch",
  "form-label-mismatch",
  "widget-label-purpose-mismatch",
  "heading-not-descriptive",
  "landmark-purpose-mismatch",
  "page-title-not-descriptive",
  "autocomplete-purpose-mismatch",
  "aria-state-mismatch",
  "table-header-association-mismatch",
  "error-message-mismatch",
)

def test_stable_candidate_id_is_deterministic_and_sorts_element_ids():
  first = stable_candidate_id(
    run_id="run_a",
    state_id="state_0001",
    candidate_type="image-alt-not-descriptive",
    element_ids=["e_b", "e_a"],
  )
  second = stable_candidate_id(
    run_id="run_a",
    state_id="state_0001",
    candidate_type="image-alt-not-descriptive",
    element_ids=["e_a", "e_b"],
  )
  assert first == second
  assert first.startswith("cand_")


def test_taxonomy_distinguishes_final_types_from_executable_rules():
  assert ALL_SEMANTIC_TYPES == FINAL_15_TYPES
  assert CURRENT_REUSABLE_CANDIDATE_TYPES == FINAL_15_TYPES
  assert SUPPORTED_CANDIDATE_TYPES == FINAL_15_TYPES
  assert len(SEMANTIC_TAXONOMY_ENTRIES) == 15
  assert TEMPORARY_LEGACY_IMPLEMENTATION_TYPES == ()
  assert OUT_OF_SCOPE_CURRENT_SEMANTIC_TYPES == ()
  assert UNSUPPORTED_CURRENT_PIPELINE_TYPES == ()
  assert not is_temporary_legacy_implementation_type("ambiguous-heading")

  assert all(is_semantic_taxonomy_type(candidate_type) for candidate_type in FINAL_15_TYPES)
  assert all(is_supported_candidate_type(candidate_type) for candidate_type in FINAL_15_TYPES)
  assert is_semantic_taxonomy_type("video-captions-inaccurate")
  assert is_supported_candidate_type("video-captions-inaccurate")

  dropped = {*REMOVED_OLD_SEMANTIC_TYPES}
  assert {
    "video-captions-not-descriptive",
    "missing-lang-tag",
    "landmark-structural-violation",
    "label-name-mismatch",
    "incorrect-semantic-tag",
    "ambiguous-heading",
  } <= dropped
  assert not any(is_supported_candidate_type(candidate_type) for candidate_type in dropped)
  for candidate_type in dropped:
    with pytest.raises(ValueError):
      require_supported_candidate_type(candidate_type)
    assert is_excluded_taxonomy_type(candidate_type)
  assert require_supported_candidate_type("video-captions-inaccurate") == "video-captions-inaccurate"
  assert not is_excluded_taxonomy_type("video-captions-inaccurate")

  assert all(is_excluded_taxonomy_type(candidate_type) for candidate_type in EXCLUDED_SYNTAX_TYPES)
  assert all(is_excluded_taxonomy_type(candidate_type) for candidate_type in EXCLUDED_LAYOUT_TYPES)


def test_builder_writes_outputs_for_current_candidate_rules(tmp_path):
  run_dir = _make_run(tmp_path)
  payload = _semantic_payload()
  payload["videos"] = [_video()]
  _write_state(run_dir, "state_0000", accessibility_context=payload)
  _write_graph(run_dir, ["state_0000"])

  summary = build_semantic_candidates(run_dir)

  manifest = _read_json(summary.output_dir / "manifest.json")
  assert manifest["schema_version"] == "1"
  assert manifest["taxonomy_scope"]["included_categories"] == ["semantic"]
  assert set(manifest["taxonomy_scope"]["candidate_types"]) == set(FINAL_15_TYPES)
  assert set(manifest["counts"]["by_type"]) == set(FINAL_15_TYPES)

  records = _read_jsonl(summary.output_dir / "candidates.jsonl")
  produced_types = {record["candidate_type"] for record in records}
  assert set(FINAL_15_TYPES) <= produced_types
  assert "ambiguous-heading" not in produced_types


def test_builder_rejects_unsupported_and_dropped_taxonomy_types(tmp_path):
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=_semantic_payload())
  _write_graph(run_dir, ["state_0000"])

  for candidate_type in REMOVED_OLD_SEMANTIC_TYPES + UNSUPPORTED_CURRENT_PIPELINE_TYPES:
    with pytest.raises(ValueError, match="Unsupported semantic candidate type"):
      build_semantic_candidates(run_dir, candidate_types=[candidate_type])

  with pytest.raises(ValueError, match="Unsupported semantic candidate type"):
    build_semantic_candidates(run_dir, candidate_types=["future-semantic-type"])


def test_video_caption_candidate_packages_ordered_cues_and_reference_neutrally(tmp_path):
  payload = _semantic_payload()
  payload["videos"] = [_video()]
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=payload)
  _write_graph(run_dir, ["state_0000"])

  summary = build_semantic_candidates(
    run_dir,
    candidate_types=["video-captions-inaccurate"],
  )
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")

  assert summary.manifest["counts"]["total_candidates"] == 1
  candidate = records[0]
  primary = candidate["evidence"]["primary"]
  assert candidate["candidate_type"] == "video-captions-inaccurate"
  assert candidate["primary_element_ref"]["element_id"] == "e_video"
  assert [cue["text"] for cue in primary["caption_track"]["cues"]] == [
    "Choose products.",
    "Review your cart.",
  ]
  assert primary["caption_text"] == "Choose products. Review your cart."
  reference = candidate["evidence"]["supporting"]["reference_evidence"]
  assert reference["available"] is True
  assert reference["reference_kind"] == "narration_transcript"
  assert reference["language"] == "en"
  assert reference["source"] == "supervisor_provided"
  assert reference["reference_transcript"].startswith("Shopping with Brightlane")
  assert reference["transcript_path"].endswith("narration-transcript.txt")
  assert reference["provenance_path"].endswith("provenance.txt")
  assert not _contains_judgment_key(candidate)


def test_video_caption_candidate_without_reference_remains_eligible(tmp_path):
  payload = _semantic_payload()
  payload["videos"] = [_video(src="/media/reference-free.mp4")]
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=payload)
  _write_graph(run_dir, ["state_0000"])

  summary = build_semantic_candidates(
    run_dir,
    candidate_types=["video-captions-inaccurate"],
  )
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")

  assert summary.manifest["counts"]["total_candidates"] == 1
  assert records[0]["evidence"]["supporting"]["reference_evidence"] == {
    "available": False
  }


def test_video_caption_candidate_preserves_multiple_track_identity_and_deduplicates(tmp_path):
  english = _caption_track("e_track_en", language="en", label="English")
  spanish = _caption_track(
    "e_track_es",
    language="es",
    label="Espanol",
    src="/media/reference-free.es.vtt",
  )
  payload = _semantic_payload()
  payload["videos"] = [_video(src="/media/reference-free.mp4", tracks=[english, spanish, english])]
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=payload)
  _write_graph(run_dir, ["state_0000"])

  first = build_semantic_candidates(
    run_dir,
    candidate_types=["video-captions-inaccurate"],
  )
  first_records = _read_jsonl(first.output_dir / "candidates.jsonl")
  second = build_semantic_candidates(
    run_dir,
    candidate_types=["video-captions-inaccurate"],
  )
  second_records = _read_jsonl(second.output_dir / "candidates.jsonl")

  assert first.manifest["counts"]["total_candidates"] == 2
  assert {record["candidate_id"] for record in first_records} == {
    record["candidate_id"] for record in second_records
  }
  tracks = [record["evidence"]["primary"]["caption_track"] for record in first_records]
  assert {(track["element_id"], track["srclang"], track["label"]) for track in tracks} == {
    ("e_track_en", "en", "English"),
    ("e_track_es", "es", "Espanol"),
  }


def test_video_caption_candidate_requires_loaded_nonempty_cue_text(tmp_path):
  payload = _semantic_payload()
  payload["videos"] = [_video(tracks=[_caption_track("e_track", cues=[])])]
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=payload)
  _write_graph(run_dir, ["state_0000"])

  summary = build_semantic_candidates(
    run_dir,
    candidate_types=["video-captions-inaccurate"],
  )

  assert summary.manifest["counts"]["total_candidates"] == 0


def test_image_alt_candidate_requires_present_text_alternative(tmp_path):
  payload = _semantic_payload()
  payload["images"] = [
    _element("e_missing_image", tag="img", selector="img#missing", text="", raw_html='<img id="missing" src="missing.png">')
  ]
  payload["images"][0]["alt"] = None
  payload["images"][0]["accessible_name"] = None
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=payload)
  _write_graph(run_dir, ["state_0000"])

  summary = build_semantic_candidates(run_dir, candidate_types=["image-alt-not-descriptive"])

  assert summary.manifest["counts"]["total_candidates"] == 0


def test_image_alt_candidate_accepts_generic_non_empty_text_alternative(tmp_path):
  payload = _semantic_payload()
  image = _element(
    "e_desk_lamp_image",
    tag="img",
    selector='[data-testid="product-image-prod-desk-lamp"]',
    alt="Image",
    raw_html='<img data-testid="product-image-prod-desk-lamp" src="/desk-lamp.svg" alt="Image">',
  )
  image["src"] = "/desk-lamp.svg"
  image["context"] = {
    "nearby_text": "Desk lamp Adjustable brass shade",
    "parent_text": "Desk lamp Adjustable brass shade $32.00 Add Desk lamp",
    "section_heading": "Featured products",
  }
  payload["images"] = [image]
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=payload)
  _write_graph(run_dir, ["state_0000"])

  summary = build_semantic_candidates(
    run_dir,
    candidate_types=["image-alt-not-descriptive"],
  )
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")

  assert summary.manifest["counts"]["total_candidates"] == 1
  primary = records[0]["evidence"]["primary"]["image"]
  assert primary["selector"] == '[data-testid="product-image-prod-desk-lamp"]'
  assert primary["alt"] == "Image"
  assert primary["text_alternative_present"] is True
  assert records[0]["evidence"]["supporting"]["context"] == image["context"]


def test_heading_candidate_preserves_cart_context_for_future_step_heading(tmp_path):
  payload = _semantic_payload()
  cart_context = (
    "Review cart items and quantity controls. Checkout progress Cart items "
    "Desk lamp Cart summary Order totals Continue to address."
  )
  heading = _element(
    "e_cart_heading",
    tag="h1",
    selector="h1:nth-of-type(1)",
    text="Shipping address",
    raw_html="<h1 tabindex=\"-1\">Shipping address</h1>",
  )
  heading.update(
    {
      "level": 1,
      "context": {
        "nearby_text": "Review cart items and quantity controls.",
        "parent_text": cart_context,
        "section_heading": "",
      },
      "heading_scope": {
        "schema_version": "heading_scope_v1",
        "strategy": "document_outline_until_next_same_or_higher_heading",
        "text_excerpt": cart_context,
        "sampled_items": [
          {"kind": "paragraph", "text": "Review cart items and quantity controls."},
          {"kind": "button", "text": "Continue to address"},
        ],
        "content_counts": {"paragraphs": 1, "buttons": 1},
      },
      "structure": {
        "nearest_landmark": {"element_id": "e_cart_main", "tag": "main"},
        "nearest_heading": {},
      },
    }
  )
  main = _element(
    "e_cart_main",
    tag="main",
    selector="main",
    text=cart_context,
  )
  main.update({"kind": "landmark", "text_sample": cart_context})
  payload["page"] = {
    "url": "https://example.com/cart",
    "title": "Cart | Brightlane Checkout",
    "document_lang": "en",
    "html_lang": "en",
    "body_text_sample": cart_context,
    "body_text_length": len(cart_context),
  }
  payload["headings"] = [heading]
  payload["landmarks"] = [main]
  payload["relationships"] = []
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=payload)
  _write_graph(run_dir, ["state_0000"])

  summary = build_semantic_candidates(
    run_dir,
    candidate_types=["heading-not-descriptive"],
  )
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")

  assert summary.manifest["counts"]["total_candidates"] == 1
  candidate = records[0]
  assert candidate["selection_reason"] == [
    "heading_with_section_context_evidence"
  ]
  assert candidate["state_context"]["url"] == "https://example.com/cart"
  assert candidate["evidence"]["primary"]["heading"] == {
    "element_id": "e_cart_heading",
    "tag": "h1",
    "role": None,
    "selector": "h1:nth-of-type(1)",
    "text": "Shipping address",
    "level": 1,
    "accessible_name": "Shipping address",
  }
  supporting = candidate["evidence"]["supporting"]
  assert supporting["page"]["title"] == "Cart | Brightlane Checkout"
  assert supporting["heading_scope"]["text_excerpt"] == cart_context
  assert supporting["heading_scoped_content"]["text_excerpt"] == cart_context


def test_heading_candidate_distinguishes_payment_section_heading_from_field_label(
  tmp_path,
):
  payload = _semantic_payload()
  payment_context = (
    "Add card details before reviewing the order. Card details Cardholder name "
    "Card number Expiry Security code Continue to review."
  )
  heading = _element(
    "e_payment_method_heading",
    tag="h2",
    selector="h2#payment-form-heading",
    text="Card number",
    raw_html='<h2 id="payment-form-heading">Card number</h2>',
  )
  heading.update(
    {
      "level": 2,
      "context": {
        "nearby_text": "Add card details before reviewing the order.",
        "parent_text": payment_context,
        "section_heading": "",
      },
      "heading_scope": {
        "schema_version": "heading_scope_v1",
        "strategy": "document_outline_until_next_same_or_higher_heading",
        "text_excerpt": payment_context,
        "sampled_items": [
          {
            "kind": "paragraph",
            "text": "Add card details before reviewing the order.",
          },
          {"kind": "legend", "text": "Card details"},
          {"kind": "label", "text": "Cardholder name Required"},
          {"kind": "label", "text": "Card number Required"},
          {"kind": "label", "text": "Expiry Required"},
          {"kind": "label", "text": "Security code Required"},
          {"kind": "button", "text": "Continue to review"},
        ],
        "content_counts": {
          "paragraphs": 1,
          "legends": 1,
          "labels": 4,
          "buttons": 1,
        },
      },
      "structure": {
        "nearest_landmark": {
          "element_id": "e_payment_section",
          "tag": "section",
        },
        "nearest_heading": {},
      },
    }
  )
  payment_section = _element(
    "e_payment_section",
    tag="section",
    selector='section[aria-labelledby="payment-form-heading"]',
    text=payment_context,
  )
  payment_section.update(
    {
      "kind": "landmark",
      "accessible_name": "Card number",
      "aria_labelledby": "payment-form-heading",
      "text_sample": payment_context,
    }
  )
  payload["page"] = {
    "url": "https://example.com/checkout/payment",
    "title": "Payment | Brightlane Checkout",
    "document_lang": "en",
    "html_lang": "en",
    "body_text_sample": f"Payment Checkout progress {payment_context}",
    "body_text_length": len(payment_context),
  }
  payload["headings"] = [heading]
  payload["landmarks"] = [payment_section]
  payload["relationships"] = []
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=payload)
  _write_graph(run_dir, ["state_0000"])

  summary = build_semantic_candidates(
    run_dir,
    candidate_types=["heading-not-descriptive"],
  )
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")

  assert summary.manifest["counts"]["total_candidates"] == 1
  candidate = records[0]
  assert candidate["selection_reason"] == [
    "heading_with_section_context_evidence"
  ]
  assert candidate["state_context"]["url"] == (
    "https://example.com/checkout/payment"
  )
  assert candidate["evidence"]["primary"]["heading"] == {
    "element_id": "e_payment_method_heading",
    "tag": "h2",
    "role": None,
    "selector": "h2#payment-form-heading",
    "text": "Card number",
    "level": 2,
    "accessible_name": "Card number",
  }
  supporting = candidate["evidence"]["supporting"]
  assert supporting["page"]["title"] == "Payment | Brightlane Checkout"
  assert supporting["heading_scope"]["text_excerpt"] == payment_context
  assert supporting["heading_scoped_content"]["text_excerpt"] == payment_context
  assert "Cardholder name" in supporting["heading_scope"]["text_excerpt"]
  assert "Security code" in supporting["heading_scope"]["text_excerpt"]
  assert candidate["evidence"]["dom_snippets"] == [
    {
      "element_id": "e_payment_method_heading",
      "selector": "h2#payment-form-heading",
      "html": '<h2 id="payment-form-heading">Card number</h2>',
    }
  ]


def test_page_title_candidate_preserves_payment_context_for_premature_review_title(
  tmp_path,
):
  body_text = (
    "Payment Payment method Card details Cardholder name Card number Expiry "
    "Security code Checkout progress Payment Current step Review Not started "
    "Continue to review"
  )
  payload = _semantic_payload_for_page(
    state_id="state_0000",
    url="https://example.com/checkout/payment",
    title="Review | Brightlane Checkout",
    body_text_sample=body_text,
    heading_text="Payment",
  )
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=payload)
  metadata_path = run_dir / "states" / "state_0000" / "metadata.json"
  metadata = _read_json(metadata_path)
  metadata["route"] = "/checkout/payment"
  metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
  _write_graph(run_dir, ["state_0000"])

  summary = build_semantic_candidates(
    run_dir,
    candidate_types=["page-title-not-descriptive"],
  )
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")

  assert summary.manifest["counts"]["total_candidates"] == 1
  candidate = records[0]
  assert candidate["element_refs"] == []
  assert candidate["selection_reason"] == [
    "page_title_with_route_and_content_context"
  ]
  primary = candidate["evidence"]["primary"]["page"]
  assert primary["title"] == "Review | Brightlane Checkout"
  assert primary["url"] == "https://example.com/checkout/payment"
  supporting = candidate["evidence"]["supporting"]
  assert supporting["route"] == "/checkout/payment"
  assert supporting["headings"][0]["text"] == "Payment"
  assert "Payment method" in supporting["body_text_sample"]
  assert "Payment Current step" in supporting["body_text_sample"]
  assert "Continue to review" in supporting["body_text_sample"]


def test_page_title_candidate_preserves_shipping_context_for_billing_title(
  tmp_path,
):
  body_text = (
    "Shipping address Shipping details Enter the shipping address for this order. "
    "Full name Email Street address City State ZIP code Checkout progress "
    "Cart Completed Shipping address Current step Payment Not started "
    "Continue to payment"
  )
  payload = _semantic_payload_for_page(
    state_id="state_0000",
    url="https://example.com/checkout/address",
    title="Billing address | Brightlane Checkout",
    body_text_sample=body_text,
    heading_text="Shipping address",
  )
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=payload)
  metadata_path = run_dir / "states" / "state_0000" / "metadata.json"
  metadata = _read_json(metadata_path)
  metadata["route"] = "/checkout/address"
  metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
  _write_graph(run_dir, ["state_0000"])

  summary = build_semantic_candidates(
    run_dir,
    candidate_types=["page-title-not-descriptive"],
  )
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")

  assert summary.manifest["counts"]["total_candidates"] == 1
  candidate = records[0]
  assert candidate["element_refs"] == []
  assert candidate["selection_reason"] == [
    "page_title_with_route_and_content_context"
  ]
  primary = candidate["evidence"]["primary"]["page"]
  assert primary["title"] == "Billing address | Brightlane Checkout"
  assert primary["url"] == "https://example.com/checkout/address"
  supporting = candidate["evidence"]["supporting"]
  assert supporting["route"] == "/checkout/address"
  assert supporting["headings"][0]["text"] == "Shipping address"
  assert "Shipping details" in supporting["body_text_sample"]
  assert "Street address" in supporting["body_text_sample"]
  assert "Shipping address Current step" in supporting["body_text_sample"]
  assert "Continue to payment" in supporting["body_text_sample"]


def test_autocomplete_candidate_parses_billing_context_for_shipping_street(tmp_path):
  payload = _semantic_payload()
  body_text = (
    "Shipping address Shipping details Full name Email Street address City "
    "State ZIP code Continue to payment"
  )
  payload["page"] = {
    "url": "https://example.com/checkout/address",
    "title": "Shipping address | Brightlane Checkout",
    "document_lang": "en",
    "html_lang": "en",
    "body_text_sample": body_text,
    "body_text_length": len(body_text),
  }
  payload["headings"] = [
    {
      **_heading(),
      "text": "Shipping address",
      "accessible_name": "Shipping address",
    }
  ]
  shipping_form = _element(
    "e_shipping_form",
    tag="form",
    selector='[data-testid="address-form"]',
    text=body_text,
    raw_html='<form data-testid="address-form" aria-label="Shipping details"></form>',
  )
  shipping_form["accessible_name"] = "Shipping details"
  street_label = _element(
    "e_street_label",
    tag="label",
    selector='label[for="address-streetAddress"]',
    text="Street address",
    raw_html='<label for="address-streetAddress">Street address</label>',
  )
  street_control = _element(
    "e_street",
    tag="input",
    selector='[data-testid="address-street"]',
    raw_html=(
      '<input id="address-streetAddress" name="streetAddress" type="text" '
      'autocomplete="billing street-address" required '
      'data-testid="address-street">'
    ),
  )
  street_control.update(
    {
      "kind": "form_control",
      "type": "text",
      "name": "streetAddress",
      "id": "address-streetAddress",
      "label": "Street address",
      "accessible_name": "Street address",
      "autocomplete": "billing street-address",
      "required": True,
      "parent_form": {
        "element_id": "e_shipping_form",
        "selector": '[data-testid="address-form"]',
        "accessible_name": "Shipping details",
      },
      "context": {
        "nearby_text": "Street address City State ZIP code",
        "parent_text": body_text,
        "section_heading": "Shipping address",
      },
    }
  )
  payload["forms"] = [shipping_form]
  payload["form_controls"] = [street_control]
  payload["referenced_elements"] = [street_label]
  payload["relationships"] = [
    {
      "type": "labels",
      "from_element_id": "e_street_label",
      "to_element_id": "e_street",
      "method": "for",
    },
    {
      "type": "form_contains",
      "from_element_id": "e_shipping_form",
      "to_element_id": "e_street",
      "method": "ancestor",
    },
  ]
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=payload)
  metadata_path = run_dir / "states" / "state_0000" / "metadata.json"
  metadata = _read_json(metadata_path)
  metadata["route"] = "/checkout/address"
  metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
  _write_graph(run_dir, ["state_0000"])

  summary = build_semantic_candidates(
    run_dir,
    candidate_types=["autocomplete-purpose-mismatch"],
  )
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")

  assert summary.manifest["counts"]["total_candidates"] == 1
  candidate = records[0]
  primary = candidate["evidence"]["primary"]["form_control"]
  assert primary["selector"] == '[data-testid="address-street"]'
  assert primary["label"] == "Street address"
  assert primary["autocomplete"] == "billing street-address"
  context = candidate["evidence"]["supporting"][
    "autocomplete_purpose_context_v1"
  ]
  assert context["control"]["id"] == "address-streetAddress"
  assert context["control"]["name"] == "streetAddress"
  assert context["labeling"]["computed_accessible_name"] == "Street address"
  assert context["field_purpose_evidence"]["form_step_or_route_context"] == {
    "url": "https://example.com/checkout/address",
    "route": "/checkout/address",
    "title": "Shipping address | Brightlane Checkout",
    "section_heading": "Shipping address",
  }
  assert context["autocomplete_evidence"] == {
    "raw_value": "billing street-address",
    "tokens": ["billing", "street-address"],
    "section_tokens": [],
    "context_tokens": ["billing"],
    "purpose_token": "street-address",
    "recognized_purpose": "street address",
    "token_category": "address",
    "is_known_token": True,
    "unknown_tokens": [],
  }


@pytest.mark.parametrize(
  (
    "autocomplete",
    "target_selector",
    "target_id",
    "target_name",
    "target_label",
    "recognized_purpose",
    "other_selector",
    "other_id",
    "other_name",
    "other_label",
  ),
  (
    (
      "address-level1",
      '[data-testid="address-city"]',
      "address-city",
      "city",
      "City",
      "address administrative level 1",
      '[data-testid="address-state"]',
      "address-state",
      "state",
      "State",
    ),
    (
      "address-level2",
      '[data-testid="address-state"]',
      "address-state",
      "state",
      "State",
      "address administrative level 2",
      '[data-testid="address-city"]',
      "address-city",
      "city",
      "City",
    ),
  ),
)
def test_autocomplete_candidate_distinguishes_city_from_state_purpose(
  tmp_path,
  autocomplete,
  target_selector,
  target_id,
  target_name,
  target_label,
  recognized_purpose,
  other_selector,
  other_id,
  other_name,
  other_label,
):
  body_text = (
    "Shipping address Shipping details Full name Email Street address City "
    "State ZIP code Continue to payment"
  )
  payload = _semantic_payload_for_page(
    state_id="state_0002",
    url="https://example.com/checkout/address",
    title="Shipping address | Brightlane Checkout",
    body_text_sample=body_text,
    heading_text="Shipping address",
  )
  shipping_form = _element(
    "e_shipping_form",
    tag="form",
    selector='[data-testid="address-form"]',
    text=body_text,
    raw_html='<form data-testid="address-form"></form>',
  )
  shipping_form["accessible_name"] = "Shipping details"

  def address_control(
    element_id: str,
    *,
    test_id: str,
    name: str,
    label: str,
    autocomplete: str,
  ) -> tuple[dict[str, object], dict[str, object]]:
    input_id = f"address-{name}"
    label_element = _element(
      f"{element_id}_label",
      tag="label",
      selector=f'label[for="{input_id}"]',
      text=f"{label}Required",
      raw_html=(
        f'<label for="{input_id}"><span>{label}</span>'
        '<span class="required-marker">Required</span></label>'
      ),
    )
    control = _element(
      element_id,
      tag="input",
      selector=f'[data-testid="{test_id}"]',
      raw_html=(
        f'<input id="{input_id}" name="{name}" type="text" '
        f'autocomplete="{autocomplete}" required data-testid="{test_id}">'
      ),
    )
    control.update(
      {
        "kind": "form_control",
        "type": "text",
        "name": name,
        "id": input_id,
        "label": f"{label}Required",
        "accessible_name": f"{label}Required",
        "autocomplete": autocomplete,
        "required": True,
        "parent_form": {
          "element_id": "e_shipping_form",
          "selector": '[data-testid="address-form"]',
          "accessible_name": "Shipping details",
        },
        "context": {
          "nearby_text": "Street address City State ZIP code",
          "parent_text": body_text,
          "section_heading": "Shipping address",
        },
      }
    )
    return label_element, control

  city_label, city_control = address_control(
    "e_city",
    test_id="address-city",
    name="city",
    label="City",
    autocomplete=autocomplete,
  )
  state_label, state_control = address_control(
    "e_state",
    test_id="address-state",
    name="state",
    label="State",
    autocomplete=autocomplete,
  )
  payload["forms"] = [shipping_form]
  payload["form_controls"] = [city_control, state_control]
  payload["referenced_elements"] = [city_label, state_label]
  payload["relationships"] = [
    {
      "type": "labels",
      "from_element_id": "e_city_label",
      "to_element_id": "e_city",
      "method": "for",
    },
    {
      "type": "labels",
      "from_element_id": "e_state_label",
      "to_element_id": "e_state",
      "method": "for",
    },
    {
      "type": "form_contains",
      "from_element_id": "e_shipping_form",
      "to_element_id": "e_city",
      "method": "ancestor",
    },
    {
      "type": "form_contains",
      "from_element_id": "e_shipping_form",
      "to_element_id": "e_state",
      "method": "ancestor",
    },
  ]

  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0002", accessibility_context=payload)
  metadata_path = run_dir / "states" / "state_0002" / "metadata.json"
  metadata = _read_json(metadata_path)
  metadata["route"] = "/checkout/address"
  metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
  _write_graph(run_dir, ["state_0002"])

  summary = build_semantic_candidates(
    run_dir,
    candidate_types=["autocomplete-purpose-mismatch"],
  )
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")

  assert summary.manifest["counts"]["total_candidates"] == 2
  candidates_by_selector = {
    record["evidence"]["primary"]["form_control"]["selector"]: record
    for record in records
  }
  target_candidate = candidates_by_selector[target_selector]
  target_primary = target_candidate["evidence"]["primary"]["form_control"]
  assert target_primary["id"] == target_id
  assert target_primary["name"] == target_name
  assert target_primary["label"] == f"{target_label}Required"
  assert target_primary["accessible_name"] == f"{target_label}Required"
  assert target_primary["autocomplete"] == autocomplete

  context = target_candidate["evidence"]["supporting"][
    "autocomplete_purpose_context_v1"
  ]
  assert context["control"]["id"] == target_id
  assert context["control"]["name"] == target_name
  assert context["labeling"]["visible_label"] == f"{target_label}Required"
  assert context["labeling"]["computed_accessible_name"] == f"{target_label}Required"
  assert context["autocomplete_evidence"] == {
    "raw_value": autocomplete,
    "tokens": [autocomplete],
    "section_tokens": [],
    "context_tokens": [],
    "purpose_token": autocomplete,
    "recognized_purpose": recognized_purpose,
    "token_category": "address",
    "is_known_token": True,
    "unknown_tokens": [],
  }
  assert context["field_purpose_evidence"]["form_step_or_route_context"] == {
    "url": "https://example.com/checkout/address",
    "route": "/checkout/address",
    "title": "Shipping address | Brightlane Checkout",
    "section_heading": "Shipping address",
  }

  other_primary = candidates_by_selector[other_selector]["evidence"]["primary"][
    "form_control"
  ]
  assert other_primary["id"] == other_id
  assert other_primary["name"] == other_name
  assert other_primary["label"] == f"{other_label}Required"
  assert other_primary["autocomplete"] == autocomplete


def test_autocomplete_candidate_distinguishes_expiry_from_security_code(tmp_path):
  body_text = (
    "Payment Payment method Card details Cardholder name Card number Expiry "
    "Security code Continue to review"
  )
  payload = _semantic_payload_for_page(
    state_id="state_0003",
    url="https://example.com/checkout/payment",
    title="Payment | Brightlane Checkout",
    body_text_sample=body_text,
    heading_text="Payment",
  )
  payment_form = _element(
    "e_payment_form",
    tag="form",
    selector='[data-testid="payment-form"]',
    text=body_text,
    raw_html='<form data-testid="payment-form"></form>',
  )
  payment_form["accessible_name"] = "Payment method"

  def payment_control(
    element_id: str,
    *,
    test_id: str,
    input_id: str,
    name: str,
    label: str,
  ) -> tuple[dict[str, object], dict[str, object]]:
    label_element = _element(
      f"{element_id}_label",
      tag="label",
      selector=f'label[for="{input_id}"]',
      text=f"{label}Required",
      raw_html=(
        f'<label for="{input_id}"><span>{label}</span>'
        '<span class="required-marker">Required</span></label>'
      ),
    )
    control = _element(
      element_id,
      tag="input",
      selector=f'[data-testid="{test_id}"]',
      raw_html=(
        f'<input id="{input_id}" name="{name}" type="text" '
        f'autocomplete="cc-csc" inputmode="numeric" required '
        f'data-testid="{test_id}">'
      ),
    )
    control.update(
      {
        "kind": "form_control",
        "type": "text",
        "name": name,
        "id": input_id,
        "label": f"{label}Required",
        "accessible_name": f"{label}Required",
        "autocomplete": "cc-csc",
        "required": True,
        "parent_form": {
          "element_id": "e_payment_form",
          "selector": '[data-testid="payment-form"]',
          "accessible_name": "Payment method",
        },
        "context": {
          "nearby_text": "Card number Expiry Security code",
          "parent_text": body_text,
          "section_heading": "Payment method",
        },
      }
    )
    return label_element, control

  expiry_label, expiry_control = payment_control(
    "e_expiry",
    test_id="payment-expiry",
    input_id="payment-expiry",
    name="expiry",
    label="Expiry",
  )
  security_label, security_control = payment_control(
    "e_security_code",
    test_id="payment-security-code",
    input_id="payment-securityCode",
    name="securityCode",
    label="Security code",
  )
  payload["forms"] = [payment_form]
  payload["form_controls"] = [expiry_control, security_control]
  payload["referenced_elements"] = [expiry_label, security_label]
  payload["relationships"] = [
    {
      "type": "labels",
      "from_element_id": "e_expiry_label",
      "to_element_id": "e_expiry",
      "method": "for",
    },
    {
      "type": "labels",
      "from_element_id": "e_security_code_label",
      "to_element_id": "e_security_code",
      "method": "for",
    },
    {
      "type": "form_contains",
      "from_element_id": "e_payment_form",
      "to_element_id": "e_expiry",
      "method": "ancestor",
    },
    {
      "type": "form_contains",
      "from_element_id": "e_payment_form",
      "to_element_id": "e_security_code",
      "method": "ancestor",
    },
  ]

  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0003", accessibility_context=payload)
  metadata_path = run_dir / "states" / "state_0003" / "metadata.json"
  metadata = _read_json(metadata_path)
  metadata["route"] = "/checkout/payment"
  metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
  _write_graph(run_dir, ["state_0003"])

  summary = build_semantic_candidates(
    run_dir,
    candidate_types=["autocomplete-purpose-mismatch"],
  )
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")

  assert summary.manifest["counts"]["total_candidates"] == 2
  candidates_by_selector = {
    record["evidence"]["primary"]["form_control"]["selector"]: record
    for record in records
  }
  expiry_candidate = candidates_by_selector['[data-testid="payment-expiry"]']
  expiry_primary = expiry_candidate["evidence"]["primary"]["form_control"]
  assert expiry_primary["id"] == "payment-expiry"
  assert expiry_primary["name"] == "expiry"
  assert expiry_primary["label"] == "ExpiryRequired"
  assert expiry_primary["accessible_name"] == "ExpiryRequired"
  assert expiry_primary["autocomplete"] == "cc-csc"

  context = expiry_candidate["evidence"]["supporting"][
    "autocomplete_purpose_context_v1"
  ]
  assert context["control"]["id"] == "payment-expiry"
  assert context["control"]["name"] == "expiry"
  assert context["labeling"]["visible_label"] == "ExpiryRequired"
  assert context["labeling"]["computed_accessible_name"] == "ExpiryRequired"
  assert context["autocomplete_evidence"] == {
    "raw_value": "cc-csc",
    "tokens": ["cc-csc"],
    "section_tokens": [],
    "context_tokens": [],
    "purpose_token": "cc-csc",
    "recognized_purpose": "payment card security code",
    "token_category": "payment",
    "is_known_token": True,
    "unknown_tokens": [],
  }
  assert context["field_purpose_evidence"]["form_step_or_route_context"] == {
    "url": "https://example.com/checkout/payment",
    "route": "/checkout/payment",
    "title": "Payment | Brightlane Checkout",
    "section_heading": "Payment method",
  }

  security_primary = candidates_by_selector[
    '[data-testid="payment-security-code"]'
  ]["evidence"]["primary"]["form_control"]
  assert security_primary["id"] == "payment-securityCode"
  assert security_primary["name"] == "securityCode"
  assert security_primary["label"] == "Security codeRequired"
  assert security_primary["accessible_name"] == "Security codeRequired"
  assert security_primary["autocomplete"] == "cc-csc"


def test_country_select_is_ready_for_label_and_autocomplete_candidates(tmp_path):
  body_text = (
    "Shipping address Shipping details City State Country/region ZIP code "
    "Continue to payment"
  )
  payload = _semantic_payload_for_page(
    state_id="state_0002",
    url="https://example.com/checkout/address",
    title="Shipping address | Brightlane Checkout",
    body_text_sample=body_text,
    heading_text="Shipping address",
  )
  shipping_form = _element(
    "e_shipping_form",
    tag="form",
    selector='[data-testid="address-form"]',
    text=body_text,
    raw_html='<form data-testid="address-form"></form>',
  )
  shipping_form["accessible_name"] = "Shipping details"
  country_label = _element(
    "e_country_label",
    tag="label",
    selector='label[for="address-country"]',
    text="Country/regionRequired",
    raw_html=(
      '<label for="address-country"><span>Country/region</span>'
      '<span class="required-marker">Required</span></label>'
    ),
  )
  country_label["text_segments"] = ["Country/region", "Required"]
  country_control = _element(
    "e_country",
    tag="select",
    selector='[data-testid="address-country"]',
    raw_html=(
      '<select id="address-country" name="country" '
      'autocomplete="country-name" required data-testid="address-country">'
      '<option selected>United States</option><option>Canada</option>'
      '<option>Germany</option></select>'
    ),
  )
  country_control.update(
    {
      "kind": "form_control",
      "type": "",
      "name": "country",
      "id": "address-country",
      "label": "Country/regionRequired",
      "accessible_name": "Country/regionRequired",
      "autocomplete": "country-name",
      "required": True,
      "has_value": True,
      "parent_form": {
        "element_id": "e_shipping_form",
        "selector": '[data-testid="address-form"]',
        "accessible_name": "Shipping details",
      },
      "context": {
        "nearby_text": "City State Country/region ZIP code",
        "parent_text": body_text,
        "section_heading": "Shipping address",
      },
    }
  )
  payload["forms"] = [shipping_form]
  payload["form_controls"] = [country_control]
  payload["referenced_elements"] = [country_label]
  payload["relationships"] = [
    {
      "type": "labels",
      "from_element_id": "e_country_label",
      "to_element_id": "e_country",
      "method": "for",
    },
    {
      "type": "form_contains",
      "from_element_id": "e_shipping_form",
      "to_element_id": "e_country",
      "method": "ancestor",
    },
  ]

  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0002", accessibility_context=payload)
  metadata_path = run_dir / "states" / "state_0002" / "metadata.json"
  metadata = _read_json(metadata_path)
  metadata["route"] = "/checkout/address"
  metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
  _write_graph(run_dir, ["state_0002"])

  summary = build_semantic_candidates(
    run_dir,
    candidate_types=[
      "form-label-mismatch",
      "autocomplete-purpose-mismatch",
    ],
  )
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")

  assert summary.manifest["counts"]["total_candidates"] == 2
  candidates_by_type = {record["candidate_type"]: record for record in records}
  for candidate in candidates_by_type.values():
    primary = candidate["evidence"]["primary"]["form_control"]
    assert primary["tag"] == "select"
    assert primary["id"] == "address-country"
    assert primary["name"] == "country"
    assert primary["label"] == "Country/regionRequired"
    assert primary["accessible_name"] == "Country/regionRequired"
    assert primary["autocomplete"] == "country-name"
    assert primary["required"] is True
    assert primary["has_value"] is True
    snippet = candidate["evidence"]["dom_snippets"][0]["html"]
    assert "United States" in snippet
    assert "Canada" in snippet
    assert "Germany" in snippet

  form_context = candidates_by_type["form-label-mismatch"]["evidence"][
    "supporting"
  ]["form_label_context_v1"]
  assert form_context["control"]["tag"] == "select"
  assert form_context["labeling"]["visible_label"] == "Country/regionRequired"
  assert form_context["labeling"]["label_sources"] == [
    {
      "element_id": "e_country_label",
      "selector": 'label[for="address-country"]',
      "text": "Country/regionRequired",
      "text_segments": ["Country/region", "Required"],
      "reference_type": None,
      "relationship_type": "labels",
      "method": "for",
    }
  ]

  autocomplete_context = candidates_by_type["autocomplete-purpose-mismatch"][
    "evidence"
  ]["supporting"]["autocomplete_purpose_context_v1"]
  assert autocomplete_context["autocomplete_evidence"] == {
    "raw_value": "country-name",
    "tokens": ["country-name"],
    "section_tokens": [],
    "context_tokens": [],
    "purpose_token": "country-name",
    "recognized_purpose": "country name",
    "token_category": "address",
    "is_known_token": True,
    "unknown_tokens": [],
  }


@pytest.mark.parametrize(
  ("label", "value", "has_value", "expected_value_state"),
  [
    ("Delivery instructions", "", False, "empty"),
    (
      "Delivery instructions",
      "Leave package with concierge",
      True,
      "filled",
    ),
    ("Street address", "", False, "empty"),
  ],
)
def test_delivery_instructions_textarea_has_neutral_form_label_evidence(
  tmp_path,
  label,
  value,
  has_value,
  expected_value_state,
):
  hint_text = "Optional. Add gate codes, safe-place details, or delivery notes."
  body_text = (
    f"Shipping address Shipping details Street address {label} {hint_text} "
    "Continue to payment"
  )
  payload = _semantic_payload_for_page(
    state_id="state_0002",
    url="https://example.com/checkout/address",
    title="Shipping address | Brightlane Checkout",
    body_text_sample=body_text,
    heading_text="Shipping address",
  )
  shipping_form = _element(
    "e_shipping_form",
    tag="form",
    selector='[data-testid="address-form"]',
    text=body_text,
    raw_html='<form data-testid="address-form"></form>',
  )
  shipping_form["accessible_name"] = "Shipping details"
  textarea_label = _element(
    "e_delivery_instructions_label",
    tag="label",
    selector='label[for="address-deliveryInstructions"]',
    text=label,
    raw_html=(
      '<label for="address-deliveryInstructions">'
      f"<span>{label}</span></label>"
    ),
  )
  textarea_label["text_segments"] = [label]
  textarea_hint = _element(
    "e_delivery_instructions_description",
    tag="p",
    selector="#address-deliveryInstructions-description",
    text=hint_text,
    raw_html=(
      '<p id="address-deliveryInstructions-description">'
      f"{hint_text}</p>"
    ),
  )
  textarea = _element(
    "e_delivery_instructions",
    tag="textarea",
    selector='[data-testid="address-delivery-instructions"]',
    text=value,
    raw_html=(
      '<textarea id="address-deliveryInstructions" name="deliveryInstructions" '
      'rows="3" aria-describedby="address-deliveryInstructions-description" '
      f'data-testid="address-delivery-instructions">{value}</textarea>'
    ),
  )
  textarea.update(
    {
      "kind": "form_control",
      "type": "textarea",
      "name": "deliveryInstructions",
      "id": "address-deliveryInstructions",
      "label": label,
      "accessible_name": label,
      "aria_describedby": "address-deliveryInstructions-description",
      "autocomplete": None,
      "required": False,
      "has_value": has_value,
      "parent_form": {
        "element_id": "e_shipping_form",
        "selector": '[data-testid="address-form"]',
        "accessible_name": "Shipping details",
      },
      "context": {
        "nearby_text": f"Street address {label} {hint_text}",
        "parent_text": body_text,
        "section_heading": "Shipping address",
      },
    }
  )
  payload["forms"] = [shipping_form]
  payload["form_controls"] = [textarea]
  payload["referenced_elements"] = [textarea_label, textarea_hint]
  payload["relationships"] = [
    {
      "type": "labels",
      "from_element_id": "e_delivery_instructions_label",
      "to_element_id": "e_delivery_instructions",
      "method": "for",
    },
    {
      "type": "describes",
      "from_element_id": "e_delivery_instructions_description",
      "to_element_id": "e_delivery_instructions",
      "method": "aria-describedby",
    },
    {
      "type": "form_contains",
      "from_element_id": "e_shipping_form",
      "to_element_id": "e_delivery_instructions",
      "method": "ancestor",
    },
  ]

  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0002", accessibility_context=payload)
  metadata_path = run_dir / "states" / "state_0002" / "metadata.json"
  metadata = _read_json(metadata_path)
  metadata["route"] = "/checkout/address"
  metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
  _write_graph(run_dir, ["state_0002"])

  summary = build_semantic_candidates(
    run_dir,
    candidate_types=["form-label-mismatch"],
  )
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")

  assert summary.manifest["counts"]["total_candidates"] == 1
  candidate = records[0]
  primary = candidate["evidence"]["primary"]["form_control"]
  assert primary["tag"] == "textarea"
  assert primary["id"] == "address-deliveryInstructions"
  assert primary["name"] == "deliveryInstructions"
  assert primary["label"] == label
  assert primary["accessible_name"] == label
  assert primary["autocomplete"] is None
  assert primary["required"] is False
  assert primary["has_value"] is has_value

  context = candidate["evidence"]["supporting"]["form_label_context_v1"]
  assert context["control"]["tag"] == "textarea"
  assert context["control"]["value_state"] == expected_value_state
  assert context["labeling"]["label_sources"] == [
    {
      "element_id": "e_delivery_instructions_label",
      "selector": 'label[for="address-deliveryInstructions"]',
      "text": label,
      "text_segments": [label],
      "reference_type": None,
      "relationship_type": "labels",
      "method": "for",
    }
  ]
  descriptions = context["field_purpose_evidence"]["descriptions"]
  assert len(descriptions) == 1
  assert descriptions[0]["element_id"] == "e_delivery_instructions_description"
  assert descriptions[0]["selector"] == (
    "#address-deliveryInstructions-description"
  )
  assert descriptions[0]["text"] == hint_text
  assert descriptions[0]["relationship_type"] == "describes"
  assert descriptions[0]["method"] == "aria-describedby"


def test_form_label_candidate_distinguishes_city_from_state_control(tmp_path):
  body_text = (
    "Shipping address Shipping details Full name Email Street address State "
    "State ZIP code Continue to payment"
  )
  payload = _semantic_payload_for_page(
    state_id="state_0002",
    url="https://example.com/checkout/address",
    title="Shipping address | Brightlane Checkout",
    body_text_sample=body_text,
    heading_text="Shipping address",
  )
  shipping_form = _element(
    "e_shipping_form",
    tag="form",
    selector='[data-testid="address-form"]',
    text=body_text,
    raw_html='<form data-testid="address-form"></form>',
  )
  shipping_form["accessible_name"] = "Shipping details"

  city_label = _element(
    "e_city_label",
    tag="label",
    selector='label[for="address-city"]',
    text="StateRequired",
    raw_html=(
      '<label for="address-city"><span>State</span>'
      '<span class="required-marker">Required</span></label>'
    ),
  )
  city_control = _element(
    "e_city",
    tag="input",
    selector='[data-testid="address-city"]',
    raw_html=(
      '<input id="address-city" name="city" type="text" '
      'autocomplete="address-level2" required data-testid="address-city">'
    ),
  )
  city_control.update(
    {
      "kind": "form_control",
      "type": "text",
      "name": "city",
      "id": "address-city",
      "label": "StateRequired",
      "accessible_name": "StateRequired",
      "autocomplete": "address-level2",
      "required": True,
      "parent_form": {
        "element_id": "e_shipping_form",
        "selector": '[data-testid="address-form"]',
        "accessible_name": "Shipping details",
      },
      "context": {
        "nearby_text": "Street address State State ZIP code",
        "parent_text": body_text,
        "section_heading": "Shipping address",
      },
    }
  )

  state_label = _element(
    "e_state_label",
    tag="label",
    selector='label[for="address-state"]',
    text="StateRequired",
    raw_html=(
      '<label for="address-state"><span>State</span>'
      '<span class="required-marker">Required</span></label>'
    ),
  )
  state_control = _element(
    "e_state",
    tag="input",
    selector='[data-testid="address-state"]',
    raw_html=(
      '<input id="address-state" name="state" type="text" '
      'autocomplete="address-level1" required data-testid="address-state">'
    ),
  )
  state_control.update(
    {
      "kind": "form_control",
      "type": "text",
      "name": "state",
      "id": "address-state",
      "label": "StateRequired",
      "accessible_name": "StateRequired",
      "autocomplete": "address-level1",
      "required": True,
      "parent_form": {
        "element_id": "e_shipping_form",
        "selector": '[data-testid="address-form"]',
        "accessible_name": "Shipping details",
      },
      "context": {
        "nearby_text": "State State ZIP code",
        "parent_text": body_text,
        "section_heading": "Shipping address",
      },
    }
  )

  payload["forms"] = [shipping_form]
  payload["form_controls"] = [city_control, state_control]
  payload["referenced_elements"] = [city_label, state_label]
  payload["relationships"] = [
    {
      "type": "labels",
      "from_element_id": "e_city_label",
      "to_element_id": "e_city",
      "method": "for",
    },
    {
      "type": "labels",
      "from_element_id": "e_state_label",
      "to_element_id": "e_state",
      "method": "for",
    },
    {
      "type": "form_contains",
      "from_element_id": "e_shipping_form",
      "to_element_id": "e_city",
      "method": "ancestor",
    },
    {
      "type": "form_contains",
      "from_element_id": "e_shipping_form",
      "to_element_id": "e_state",
      "method": "ancestor",
    },
  ]

  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0002", accessibility_context=payload)
  metadata_path = run_dir / "states" / "state_0002" / "metadata.json"
  metadata = _read_json(metadata_path)
  metadata["route"] = "/checkout/address"
  metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
  _write_graph(run_dir, ["state_0002"])

  summary = build_semantic_candidates(
    run_dir,
    candidate_types=["form-label-mismatch"],
  )
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")

  assert summary.manifest["counts"]["total_candidates"] == 2
  candidates_by_selector = {
    record["evidence"]["primary"]["form_control"]["selector"]: record
    for record in records
  }
  city_candidate = candidates_by_selector['[data-testid="address-city"]']
  city_primary = city_candidate["evidence"]["primary"]["form_control"]
  assert city_primary["id"] == "address-city"
  assert city_primary["name"] == "city"
  assert city_primary["type"] == "text"
  assert city_primary["autocomplete"] == "address-level2"
  assert city_primary["label"] == "StateRequired"
  assert city_primary["accessible_name"] == "StateRequired"

  context = city_candidate["evidence"]["supporting"]["form_label_context_v1"]
  assert context["control"]["id"] == "address-city"
  assert context["control"]["name"] == "city"
  assert context["control"]["autocomplete"] == "address-level2"
  assert context["labeling"]["visible_label"] == "StateRequired"
  assert context["labeling"]["computed_accessible_name"] == "StateRequired"
  assert context["field_purpose_evidence"]["form_step_or_route_context"] == {
    "url": "https://example.com/checkout/address",
    "route": "/checkout/address",
    "title": "Shipping address | Brightlane Checkout",
    "section_heading": "Shipping address",
  }

  state_primary = candidates_by_selector[
    '[data-testid="address-state"]'
  ]["evidence"]["primary"]["form_control"]
  assert state_primary["id"] == "address-state"
  assert state_primary["name"] == "state"
  assert state_primary["autocomplete"] == "address-level1"


def test_landmark_candidate_preserves_route_links_for_copied_progress_name(tmp_path):
  payload = _semantic_payload()
  products_link = _element(
    "e_products_link",
    tag="a",
    selector='[data-testid="nav-products"]',
    text="Products",
    raw_html='<a href="/products" data-testid="nav-products">Products</a>',
  )
  products_link["href"] = "/products"
  cart_link = _element(
    "e_cart_link",
    tag="a",
    selector='[data-testid="nav-cart"]',
    text="Cart",
    raw_html=(
      '<a href="/cart" aria-current="page" data-testid="nav-cart">Cart</a>'
    ),
  )
  cart_link["href"] = "/cart"
  cart_link["aria_current"] = "page"
  navigation = _element(
    "e_route_navigation",
    tag="nav",
    selector="nav:nth-of-type(1)",
    text="Products Cart",
    raw_html=(
      '<nav aria-label="Checkout progress"><a href="/products">Products</a>'
      '<a href="/cart" aria-current="page">Cart</a></nav>'
    ),
  )
  navigation.update(
    {
      "kind": "landmark",
      "aria_label": "Checkout progress",
      "accessible_name": "Checkout progress",
      "text_sample": "Products Cart",
    }
  )
  progress_heading = _element(
    "e_progress_heading",
    tag="h2",
    selector="h2#checkout-progress-heading",
    text="Checkout progress",
  )
  progress = _element(
    "e_progress_region",
    tag="section",
    selector='[data-testid="checkout-progress"]',
    text="Checkout progress Cart Current step Shipping address Not started",
    raw_html=(
      '<section aria-labelledby="checkout-progress-heading" '
      'data-testid="checkout-progress"><h2 id="checkout-progress-heading">'
      'Checkout progress</h2></section>'
    ),
  )
  progress.update(
    {
      "kind": "landmark",
      "aria_labelledby": "checkout-progress-heading",
      "accessible_name": "Checkout progress",
      "text_sample": (
        "Checkout progress Cart Current step Shipping address Not started"
      ),
    }
  )
  payload["page"] = {
    "url": "https://example.com/cart",
    "title": "Cart | Brightlane Checkout",
    "document_lang": "en",
    "html_lang": "en",
    "body_text_sample": "Products Cart Checkout progress Cart Current step",
    "body_text_length": 50,
  }
  payload["landmarks"] = [navigation, progress]
  payload["links"] = [products_link, cart_link]
  payload["headings"] = [progress_heading]
  payload["relationships"] = [
    {
      "type": "landmark_contains",
      "from_element_id": "e_route_navigation",
      "to_element_id": "e_products_link",
      "method": "nearest",
    },
    {
      "type": "landmark_contains",
      "from_element_id": "e_route_navigation",
      "to_element_id": "e_cart_link",
      "method": "nearest",
    },
    {
      "type": "labelledby",
      "from_element_id": "e_progress_region",
      "to_element_id": "e_progress_heading",
      "method": "aria-labelledby",
    },
  ]
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=payload)
  _write_graph(run_dir, ["state_0000"])

  summary = build_semantic_candidates(
    run_dir,
    candidate_types=["landmark-purpose-mismatch"],
  )
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")
  navigation_candidate = next(
    record
    for record in records
    if record["primary_element_ref"]["selector"] == "nav:nth-of-type(1)"
  )

  assert summary.manifest["counts"]["total_candidates"] == 2
  assert navigation_candidate["selection_reason"] == [
    "visible_landmark_with_role_and_context_evidence"
  ]
  primary = navigation_candidate["evidence"]["primary"]["landmark"]
  assert primary["tag"] == "nav"
  assert primary["role"] is None
  assert primary["accessible_name"] == "Checkout progress"
  assert primary["aria_label"] == "Checkout progress"
  supporting = navigation_candidate["evidence"]["supporting"]
  assert supporting["page"]["title"] == "Cart | Brightlane Checkout"
  identity = supporting["landmark_identity_v1"]
  assert identity["possible_exposed_role"] == "navigation"
  assert identity["label_source"] == "aria-label"
  scoped = supporting["landmark_scoped_content_v1"]
  assert scoped["label_text"] == "Checkout progress"
  assert [item["text"] for item in scoped["contained_links"]] == [
    "Products",
    "Cart",
  ]
  progress_candidates = [
    record
    for record in records
    if record["primary_element_ref"]["selector"]
    == '[data-testid="checkout-progress"]'
  ]
  assert len(progress_candidates) == 1
  assert progress_candidates[0]["evidence"]["supporting"][
    "landmark_identity_v1"
  ]["possible_exposed_role"] == "region"


def test_landmark_candidates_disambiguate_progress_from_same_named_totals(tmp_path):
  payload = _semantic_payload()
  progress = _element(
    "e_progress_region",
    tag="section",
    selector='[data-testid="checkout-progress"]',
    text=(
      "Checkout progress Cart Current step Shipping address Not started "
      "Payment Not started Review Not started"
    ),
    raw_html=(
      '<section aria-label="Order totals" data-testid="checkout-progress">'
      '<h2 id="checkout-progress-heading">Checkout progress</h2>'
      '<ol><li aria-current="step">Cart Current step</li>'
      '<li>Shipping address Not started</li><li>Payment Not started</li>'
      '<li>Review Not started</li></ol></section>'
    ),
  )
  progress.update(
    {
      "kind": "landmark",
      "aria_label": "Order totals",
      "accessible_name": "Order totals",
      "text_sample": (
        "Checkout progress Cart Current step Shipping address Not started "
        "Payment Not started Review Not started"
      ),
    }
  )
  order_totals = _element(
    "e_order_totals",
    tag="aside",
    selector='[data-testid="cart-totals-region"]',
    text=(
      "Cart summary Items 1 item Subtotal $32.00 Shipping $5.00 "
      "Order total $37.00 Continue to address"
    ),
    raw_html=(
      '<aside aria-label="Order totals" data-testid="cart-totals-region">'
      '<h2>Cart summary</h2><p>Order total $37.00</p></aside>'
    ),
  )
  order_totals.update(
    {
      "kind": "landmark",
      "aria_label": "Order totals",
      "accessible_name": "Order totals",
      "text_sample": (
        "Cart summary Items 1 item Subtotal $32.00 Shipping $5.00 "
        "Order total $37.00 Continue to address"
      ),
    }
  )
  payload["page"] = {
    "url": "https://example.com/cart",
    "title": "Cart | Brightlane Checkout",
    "document_lang": "en",
    "html_lang": "en",
    "body_text_sample": (
      "Checkout progress Cart Current step Order totals Cart summary"
    ),
    "body_text_length": 65,
  }
  payload["landmarks"] = [progress, order_totals]
  payload["relationships"] = []
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=payload)
  _write_graph(run_dir, ["state_0000"])

  summary = build_semantic_candidates(
    run_dir,
    candidate_types=["landmark-purpose-mismatch"],
  )
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")
  candidates_by_selector = {
    record["primary_element_ref"]["selector"]: record for record in records
  }

  assert summary.manifest["counts"]["total_candidates"] == 2
  progress_candidate = candidates_by_selector[
    '[data-testid="checkout-progress"]'
  ]
  totals_candidate = candidates_by_selector[
    '[data-testid="cart-totals-region"]'
  ]

  progress_primary = progress_candidate["evidence"]["primary"]["landmark"]
  assert progress_primary["tag"] == "section"
  assert progress_primary["accessible_name"] == "Order totals"
  assert progress_primary["aria_label"] == "Order totals"
  progress_supporting = progress_candidate["evidence"]["supporting"]
  assert progress_supporting["landmark_identity_v1"][
    "possible_exposed_role"
  ] == "region"
  progress_excerpt = progress_supporting["landmark_scoped_content_v1"][
    "contained_content_excerpt"
  ]
  assert "Cart Current step" in progress_excerpt
  assert "Shipping address Not started" in progress_excerpt

  totals_primary = totals_candidate["evidence"]["primary"]["landmark"]
  assert totals_primary["tag"] == "aside"
  assert totals_primary["accessible_name"] == "Order totals"
  assert totals_candidate["evidence"]["supporting"]["landmark_identity_v1"][
    "possible_exposed_role"
  ] == "complementary"
  totals_excerpt = totals_candidate["evidence"]["supporting"][
    "landmark_scoped_content_v1"
  ]["contained_content_excerpt"]
  assert "Cart summary" in totals_excerpt
  assert "Order total $37.00" in totals_excerpt


def test_language_of_parts_ignores_page_language_scope_samples(tmp_path):
  payload = _semantic_payload()
  payload["language_samples"] = [
    {
      **_element(
        "e_html_lang",
        tag="html",
        selector="html",
        text="Checkout page with ordinary English content",
        raw_html='<html lang="en">Checkout page with ordinary English content</html>',
      ),
      "kind": "language_sample",
      "xpath": "/html[1]",
      "language_text": "Checkout page with ordinary English content",
      "word_count": 6,
      "root_lang": "en",
      "body_lang": "",
      "page_lang": "en",
      "local_lang": "en",
      "ancestor_lang": "",
      "effective_lang": "en",
    },
    {
      **_element(
        "e_body_lang",
        tag="body",
        selector="body:nth-of-type(1)",
        text="Checkout body with ordinary English content",
        raw_html='<body lang="en">Checkout body with ordinary English content</body>',
      ),
      "kind": "language_sample",
      "xpath": "/html[1]/body[1]",
      "language_text": "Checkout body with ordinary English content",
      "word_count": 6,
      "root_lang": "en",
      "body_lang": "en",
      "page_lang": "en",
      "local_lang": "en",
      "ancestor_lang": "",
      "effective_lang": "en",
    },
  ]
  payload["page"]["body_lang"] = "en"
  payload["page"]["page_lang"] = "en"
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=payload)
  _write_graph(run_dir, ["state_0000"])

  language_parts_summary = build_semantic_candidates(
    run_dir,
    candidate_types=["language-of-parts-mismatch"],
  )
  assert language_parts_summary.manifest["counts"]["total_candidates"] == 0

  lang_summary = build_semantic_candidates(run_dir, candidate_types=["lang-mismatch"])
  assert lang_summary.manifest["counts"]["total_candidates"] == 1


def test_language_of_parts_requires_explicit_descendant_local_language(tmp_path):
  payload = _semantic_payload()
  payload["language_samples"] = [
    _language_sample("e_plain_text", tag="p", selector="p#plain", text="sehr interessant", local_lang=""),
    _language_sample("e_local_lang", tag="span", selector="span#local-lang", text="sehr interessant", local_lang="fr"),
  ]
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=payload)
  _write_graph(run_dir, ["state_0000"])

  summary = build_semantic_candidates(run_dir, candidate_types=["language-of-parts-mismatch"])
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")

  assert summary.manifest["counts"]["total_candidates"] == 1
  assert records[0]["evidence"]["primary"]["language_sample"]["selector"] == "span#local-lang"


def test_language_of_parts_preserves_dialog_context_for_local_passage(tmp_path):
  payload = _semantic_payload()
  sample = _language_sample(
    "e_shipping_information_body",
    tag="p",
    selector='[data-testid="shipping-information-body"]',
    text=(
      "El envío estándar se calcula durante la compra. Los detalles de entrega "
      "se confirman después de ingresar la dirección de envío."
    ),
    local_lang="en",
  )
  sample.update(
    {
      "root_lang": "es",
      "page_lang": "es",
      "effective_lang": "en",
      "context": {
        "nearby_text": "Información de envío",
        "parent_text": "Información de envío Cerrar",
      },
      "structure": {
        "ancestor_chain": [
          {
            "tag": "div",
            "role": "dialog",
            "accessible_name": "Información de envío",
          }
        ]
      },
    }
  )
  payload["language_samples"] = [sample]
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=payload)
  _write_graph(run_dir, ["state_0000"])

  summary = build_semantic_candidates(
    run_dir,
    candidate_types=["language-of-parts-mismatch"],
  )
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")

  assert summary.manifest["counts"]["total_candidates"] == 1
  evidence = records[0]["evidence"]
  assert evidence["primary"]["language_sample"] == {
    "element_id": "e_shipping_information_body",
    "tag": "p",
    "role": None,
    "selector": '[data-testid="shipping-information-body"]',
    "text": sample["language_text"],
    "local_lang": "en",
    "ancestor_lang": "",
    "root_lang": "es",
    "body_lang": "",
    "page_lang": "es",
    "effective_lang": "en",
  }
  assert evidence["supporting"]["context"] == sample["context"]
  assert evidence["supporting"]["structure"] == sample["structure"]


def test_button_candidate_includes_matched_destination_state_context(tmp_path):
  source_payload = _semantic_payload()
  source_payload["buttons"] = [
    _element(
      "e_continue",
      tag="button",
      selector="button:nth-of-type(1)",
      text="Continue",
      raw_html='<button type="button" data-testid="continue-to-address">Continue</button>',
    )
  ]
  source_payload["buttons"][0]["type"] = "button"
  source_payload["links"] = []
  target_payload = _semantic_payload_for_page(
    state_id="state_0001",
    url="https://example.com/address",
    title="Address | Checkout",
    body_text_sample="Address Shipping address Full name Email Continue to payment",
    heading_text="Address",
  )
  object_a_controls = _element(
    "e_object_a_controls",
    tag="div",
    selector='[data-testid="object-a-controls"]',
    text="- 1 +",
  )
  object_a_controls.update(
    {
      "kind": "visual_cue",
      "role": "group",
      "accessible_name": "Object A controls",
    }
  )
  object_b_controls = _element(
    "e_object_b_controls",
    tag="div",
    selector='[data-testid="object-b-controls"]',
    text="- 2 +",
  )
  object_b_controls.update(
    {
      "kind": "visual_cue",
      "role": "group",
      "accessible_name": "Object B controls",
    }
  )
  target_payload["visual_cues"] = [object_a_controls, object_b_controls]
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=source_payload)
  _write_state(run_dir, "state_0001", accessibility_context=target_payload)
  _write_graph(
    run_dir,
    ["state_0000", "state_0001"],
    transitions=[
      _transition(
        "state_0000",
        "state_0001",
        {
          "type": "focused_script_step",
          "text": "Continue to address",
          "primary_trigger": {
            "type": "click",
            "selector": '[data-testid="continue-to-address"]',
            "data_testid": "continue-to-address",
            "text": "Continue",
            "accessible_name": "Continue",
            "button_type": "button",
            "tag_name": "button",
          },
        },
      )
    ],
  )

  summary = build_semantic_candidates(run_dir, candidate_types=["button-label-mismatch"])
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")

  assert len(records) == 1
  supporting = records[0]["evidence"]["supporting"]
  destination = supporting["destination_state_context_v1"]
  assert destination["source_state_id"] == "state_0000"
  assert destination["match_basis"] == ["data_testid"]
  assert destination["match_count"] == 1
  assert destination["destinations"][0]["target_state_id"] == "state_0001"
  assert destination["destinations"][0]["target_title"] == "Address | Checkout"
  assert destination["destinations"][0]["trigger"]["data_testid"] == "continue-to-address"
  assert destination["destinations"][0]["target_primary_headings"][0]["text"] == "Address"
  assert destination["destinations"][0]["target_elements"][:2] == [
    {
      "bucket": "visual_cues",
      "element_id": "e_object_a_controls",
      "kind": "visual_cue",
      "tag": "div",
      "role": "group",
      "selector": '[data-testid="object-a-controls"]',
      "text": "- 1 +",
      "accessible_name": "Object A controls",
    },
    {
      "bucket": "visual_cues",
      "element_id": "e_object_b_controls",
      "kind": "visual_cue",
      "tag": "div",
      "role": "group",
      "selector": '[data-testid="object-b-controls"]',
      "text": "- 2 +",
      "accessible_name": "Object B controls",
    },
  ]
  assert (
    supporting["button_action_context_v1"]["action_evidence"]["matched_outgoing_transition"][
      "to_state"
    ]
    == "state_0001"
  )


def test_button_candidate_with_multiple_matching_transitions_reports_all_destinations(tmp_path):
  source_payload = _semantic_payload()
  source_payload["buttons"] = [
    _element(
      "e_continue",
      tag="button",
      selector="button:nth-of-type(1)",
      text="Continue",
      raw_html='<button type="submit" data-testid="continue-to-payment">Continue</button>',
    )
  ]
  source_payload["buttons"][0]["type"] = "submit"
  target_one = _semantic_payload_for_page(
    state_id="state_0001",
    url="https://example.com/address",
    title="Address validation | Checkout",
    body_text_sample="Address ZIP code required",
    heading_text="Address",
  )
  target_two = _semantic_payload_for_page(
    state_id="state_0002",
    url="https://example.com/payment",
    title="Payment | Checkout",
    body_text_sample="Payment Card details",
    heading_text="Payment",
  )
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=source_payload)
  _write_state(run_dir, "state_0001", accessibility_context=target_one)
  _write_state(run_dir, "state_0002", accessibility_context=target_two)
  trigger = {
    "type": "click",
    "selector": '[data-testid="continue-to-payment"]',
    "data_testid": "continue-to-payment",
    "text": "Continue",
    "accessible_name": "Continue",
    "button_type": "submit",
    "tag_name": "button",
  }
  _write_graph(
    run_dir,
    ["state_0000", "state_0001", "state_0002"],
    transitions=[
      _transition(
        "state_0000",
        "state_0001",
        {"type": "focused_script_step", "text": "Validation", "primary_trigger": trigger},
      ),
      _transition(
        "state_0000",
        "state_0002",
        {"type": "focused_script_step", "text": "Payment", "primary_trigger": trigger},
      ),
    ],
  )

  summary = build_semantic_candidates(run_dir, candidate_types=["button-label-mismatch"])
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")

  assert len(records) == 1
  supporting = records[0]["evidence"]["supporting"]
  destination = supporting["destination_state_context_v1"]
  assert destination["match_basis"] == ["data_testid"]
  assert destination["match_count"] == 2
  assert [item["target_state_id"] for item in destination["destinations"]] == [
    "state_0001",
    "state_0002",
  ]
  action_evidence = supporting["button_action_context_v1"]["action_evidence"]
  assert "matched_outgoing_transition" not in action_evidence
  assert "result_state_context" not in action_evidence


def test_button_candidate_without_reliable_transition_match_omits_destination_context(tmp_path):
  source_payload = _semantic_payload()
  source_payload["buttons"] = [
    _element(
      "e_continue",
      tag="button",
      selector="button:nth-of-type(1)",
      text="Continue",
      raw_html='<button type="button" data-testid="continue-to-address">Continue</button>',
    )
  ]
  source_payload["buttons"][0]["type"] = "button"
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=source_payload)
  _write_state(
    run_dir,
    "state_0001",
    accessibility_context=_semantic_payload_for_page(
      state_id="state_0001",
      url="https://example.com/payment",
      title="Payment | Checkout",
      body_text_sample="Payment Card details",
      heading_text="Payment",
    ),
  )
  _write_graph(
    run_dir,
    ["state_0000", "state_0001"],
    transitions=[
      _transition(
        "state_0000",
        "state_0001",
        {
          "type": "focused_script_step",
          "text": "Unrelated click",
          "primary_trigger": {
            "type": "click",
            "data_testid": "unrelated-control",
            "text": "Continue",
            "tag_name": "button",
          },
        },
      )
    ],
  )

  summary = build_semantic_candidates(run_dir, candidate_types=["button-label-mismatch"])
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")

  assert len(records) == 1
  supporting = records[0]["evidence"]["supporting"]
  assert "destination_state_context_v1" not in supporting
  action_evidence = supporting["button_action_context_v1"]["action_evidence"]
  assert "matched_outgoing_transition" not in action_evidence
  assert "result_state_context" not in action_evidence


def test_link_candidate_includes_graph_destination_context_when_transition_matches(tmp_path):
  source_payload = _semantic_payload_for_page(
    state_id="state_0000",
    url="https://example.com/products",
    title="Products | Checkout",
    body_text_sample="Products Product list Cart",
    heading_text="Products",
  )
  source_payload["links"] = [
    _element(
      "e_cart_link",
      tag="a",
      selector="a:nth-of-type(1)",
      text="Cart",
      raw_html='<a href="/cart" data-testid="nav-cart">Cart</a>',
    )
  ]
  source_payload["links"][0]["href"] = "/cart"
  target_payload = _semantic_payload_for_page(
    state_id="state_0001",
    url="https://example.com/cart",
    title="Cart | Checkout",
    body_text_sample="Cart Cart items Continue to address",
    heading_text="Cart",
  )
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=source_payload)
  _write_state(run_dir, "state_0001", accessibility_context=target_payload)
  _write_graph(
    run_dir,
    ["state_0000", "state_0001"],
    transitions=[
      _transition(
        "state_0000",
        "state_0001",
        {
          "type": "focused_script_step",
          "text": "Open cart",
          "primary_trigger": {
            "type": "click",
            "selector": '[data-testid="nav-cart"]',
            "data_testid": "nav-cart",
            "href": "/cart",
            "text": "Cart",
            "accessible_name": "Cart",
            "tag_name": "a",
          },
        },
      )
    ],
  )

  summary = build_semantic_candidates(run_dir, candidate_types=["link-text-mismatch"])
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")

  assert len(records) == 1
  supporting = records[0]["evidence"]["supporting"]
  assert supporting["link_destination_context_v1"]["match_status"] == "matched_state"
  destination = supporting["destination_state_context_v1"]
  assert destination["match_basis"] == ["data_testid"]
  assert destination["destinations"][0]["target_state_id"] == "state_0001"
  assert destination["destinations"][0]["trigger"]["href"] == "/cart"
  assert destination["destinations"][0]["target_primary_headings"][0]["text"] == "Cart"


def test_link_candidates_keep_products_identity_when_products_and_cart_share_destination(
  tmp_path,
):
  source_payload = _semantic_payload_for_page(
    state_id="state_0000",
    url="https://example.com/products",
    title="Products | Brightlane Checkout",
    body_text_sample="Products Cart Featured products",
    heading_text="Products",
  )
  products_link = _element(
    "e_products_link",
    tag="a",
    selector='[data-testid="nav-products"]',
    text="Products",
    raw_html='<a href="/cart" data-testid="nav-products">Products</a>',
  )
  products_link.update({"accessible_name": "Products", "href": "/cart"})
  cart_link = _element(
    "e_cart_link",
    tag="a",
    selector='[data-testid="nav-cart"]',
    text="Cart",
    raw_html='<a href="/cart" data-testid="nav-cart">Cart</a>',
  )
  cart_link.update({"accessible_name": "Cart", "href": "/cart"})
  source_payload["links"] = [products_link, cart_link]

  target_payload = _semantic_payload_for_page(
    state_id="state_0001",
    url="https://example.com/cart",
    title="Cart | Brightlane Checkout",
    body_text_sample="Cart Cart items Continue to address",
    heading_text="Cart",
  )
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=source_payload)
  _write_state(run_dir, "state_0001", accessibility_context=target_payload)
  _write_graph(run_dir, ["state_0000", "state_0001"])

  summary = build_semantic_candidates(
    run_dir,
    candidate_types=["link-text-mismatch"],
  )
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")
  candidates_by_selector = {
    record["evidence"]["primary"]["link"]["selector"]: record
    for record in records
  }

  assert set(candidates_by_selector) == {
    '[data-testid="nav-products"]',
    '[data-testid="nav-cart"]',
  }
  products_candidate = candidates_by_selector['[data-testid="nav-products"]']
  products_primary = products_candidate["evidence"]["primary"]["link"]
  assert products_primary["text"] == "Products"
  assert products_primary["accessible_name"] == "Products"
  assert products_primary["href"] == "/cart"
  destination = products_candidate["evidence"]["supporting"][
    "link_destination_context_v1"
  ]
  assert destination["match_status"] == "matched_state"
  assert destination["target_state_route"] == "/cart"

  cart_primary = candidates_by_selector['[data-testid="nav-cart"]']["evidence"][
    "primary"
  ]["link"]
  assert cart_primary["text"] == "Cart"
  assert cart_primary["accessible_name"] == "Cart"
  assert cart_primary["href"] == "/cart"


def test_widget_candidate_keeps_same_state_controlled_content_without_transition(tmp_path):
  payload = _semantic_payload()
  payload["buttons"] = [
    _element(
      "e_profile_tab",
      tag="button",
      selector="button#account-tab",
      text="Profile",
      raw_html=(
        '<button id="account-tab" role="tab" aria-controls="panel-a" '
        'aria-selected="false">Profile</button>'
      ),
    )
  ]
  payload["buttons"][0]["role"] = "tab"
  payload["buttons"][0]["aria_controls"] = "panel-a"
  payload["buttons"][0]["aria_selected"] = "false"
  payload["relationships"] = [
    {
      "type": "controls",
      "from_element_id": "e_profile_tab",
      "to_element_id": "e_panel",
      "method": "aria-controls",
    }
  ]
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=payload)
  _write_graph(run_dir, ["state_0000"])

  summary = build_semantic_candidates(run_dir, candidate_types=["widget-label-purpose-mismatch"])
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")

  assert len(records) == 1
  supporting = records[0]["evidence"]["supporting"]
  controlled = supporting["widget_label_purpose_context_v1"]["controlled_or_revealed_content"]
  assert controlled == [
    {
      "relationship_type": "controls",
      "bucket": "referenced_elements",
      "element_id": "e_panel",
      "tag": "div",
      "role": None,
      "selector": "div#panel-a",
      "text_excerpt": "Billing address and payment history",
      "visible": True,
    }
  ]
  assert "destination_state_context_v1" not in supporting


def test_widget_candidate_emits_generic_tablist_with_child_context(tmp_path):
  payload = _semantic_payload_for_page(
    state_id="state_0000",
    url="https://example.com/account",
    title="Account | Example",
    body_text_sample="Account sections Profile Security",
    heading_text="Account",
  )
  tablist = _element(
    "e_account_tablist",
    tag="div",
    selector='[data-testid="account-sections"]',
    text="Profile Security",
    raw_html=(
      '<div role="tablist" aria-label="Account sections" '
      'data-testid="account-sections">'
      '<button role="tab" aria-controls="profile-panel">Profile</button>'
      '<button role="tab" aria-controls="security-panel">Security</button>'
      "</div>"
    ),
  )
  tablist.update(
    {
      "role": "tablist",
      "accessible_name": "Account sections",
      "aria_label": "Account sections",
    }
  )
  payload["visual_cues"] = [tablist]
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=payload)
  _write_graph(run_dir, ["state_0000"])

  summary = build_semantic_candidates(
    run_dir,
    candidate_types=["widget-label-purpose-mismatch"],
  )
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")

  assert len(records) == 1
  record = records[0]
  primary = record["evidence"]["primary"]["widget"]
  assert primary == {
    "bucket": "visual_cues",
    "element_id": "e_account_tablist",
    "tag": "div",
    "role": "tablist",
    "selector": '[data-testid="account-sections"]',
    "text": "Profile Security",
    "accessible_name": "Account sections",
    "aria_label": "Account sections",
    "aria_labelledby": "",
    "title": "",
    "href": "",
    "type": "",
    "aria_controls": "",
    "aria_expanded": "",
    "aria_selected": "",
    "aria_checked": "",
    "aria_pressed": "",
  }
  assert record["candidate_id"] == stable_candidate_id(
    run_id=run_dir.name,
    state_id="state_0000",
    candidate_type="widget-label-purpose-mismatch",
    element_ids=["e_account_tablist"],
  )
  context = record["evidence"]["supporting"]["widget_label_purpose_context_v1"]
  assert context["widget"] == primary
  assert context["labeling"]["computed_accessible_name"] == "Account sections"
  snippet = record["evidence"]["dom_snippets"][0]["html"]
  assert 'data-testid="account-sections"' in snippet
  assert '<button role="tab" aria-controls="profile-panel">Profile</button>' in snippet
  assert '<button role="tab" aria-controls="security-panel">Security</button>' in snippet
  serialized = json.dumps(record)
  for judgment_field in (
    "expected_group_purpose",
    "wrong_group_name",
    "violation",
    "payment_wrong",
    "category_correct",
  ):
    assert judgment_field not in serialized


def test_widget_candidate_emits_checkout_tablist_without_suppressing_tabs(tmp_path):
  payload = _semantic_payload_for_page(
    state_id="state_0000",
    url="https://example.com/products",
    title="Products | Brightlane Checkout",
    body_text_sample=(
      "Featured products Product categories Desk accessories Office supplies"
    ),
    heading_text="Products",
  )
  tablist = _element(
    "e_product_category_tablist",
    tag="div",
    selector='div[role="tablist"]',
    text="Desk accessories Office supplies",
    raw_html=(
      '<div role="tablist" aria-label="Product categories" '
      'data-testid="product-category-tablist">'
      '<button role="tab" id="desk-accessories-tab" aria-selected="true" '
      'aria-controls="desk-accessories-panel">Desk accessories</button>'
      '<button role="tab" id="office-supplies-tab" aria-selected="false" '
      'aria-controls="office-supplies-panel">Office supplies</button>'
      "</div>"
    ),
  )
  tablist.update(
    {
      "role": "tablist",
      "accessible_name": "Product categories",
      "aria_label": "Product categories",
      "context": {
        "nearby_text": "Lighting and cable tools for a tidy workspace.",
        "parent_text": (
          "Browse by category Desk accessories Office supplies "
          "Lighting and cable tools for a tidy workspace."
        ),
        "section_heading": "Featured products",
      },
    }
  )
  desk_tab = _element(
    "e_desk_tab",
    tag="button",
    selector="button#desk-accessories-tab",
    text="Desk accessories",
    raw_html=(
      '<button role="tab" id="desk-accessories-tab" aria-selected="true" '
      'aria-controls="desk-accessories-panel" '
      'data-testid="product-category-tab-desk-accessories">'
      "Desk accessories</button>"
    ),
  )
  desk_tab.update(
    {
      "role": "tab",
      "aria_controls": "desk-accessories-panel",
      "aria_selected": "true",
    }
  )
  office_tab = _element(
    "e_office_tab",
    tag="button",
    selector="button#office-supplies-tab",
    text="Office supplies",
    raw_html=(
      '<button role="tab" id="office-supplies-tab" aria-selected="false" '
      'aria-controls="office-supplies-panel" '
      'data-testid="product-category-tab-office-supplies">'
      "Office supplies</button>"
    ),
  )
  office_tab.update(
    {
      "role": "tab",
      "aria_controls": "office-supplies-panel",
      "aria_selected": "false",
    }
  )
  desk_panel = _element(
    "e_desk_panel",
    tag="div",
    selector="div#desk-accessories-panel",
    text="Lighting and cable tools for a tidy workspace.",
  )
  office_panel = _element(
    "e_office_panel",
    tag="div",
    selector="div#office-supplies-panel",
    text="Everyday supplies for notes and planning.",
  )
  payload["visual_cues"] = [tablist]
  payload["buttons"] = [desk_tab, office_tab]
  payload["referenced_elements"] = [desk_panel, office_panel]
  payload["relationships"] = [
    {
      "type": "controls",
      "from_element_id": "e_desk_tab",
      "to_element_id": "e_desk_panel",
      "method": "aria-controls",
    },
    {
      "type": "controls",
      "from_element_id": "e_office_tab",
      "to_element_id": "e_office_panel",
      "method": "aria-controls",
    },
  ]
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=payload)
  _write_graph(run_dir, ["state_0000"])

  summary = build_semantic_candidates(
    run_dir,
    candidate_types=["widget-label-purpose-mismatch"],
  )
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")
  records_by_element_id = {
    record["evidence"]["primary"]["widget"]["element_id"]: record
    for record in records
  }

  assert set(records_by_element_id) == {
    "e_product_category_tablist",
    "e_desk_tab",
    "e_office_tab",
  }
  tablist_candidates = [
    record
    for record in records
    if record["evidence"]["primary"]["widget"]["role"] == "tablist"
  ]
  assert len(tablist_candidates) == 1
  tablist_record = tablist_candidates[0]
  tablist_primary = tablist_record["evidence"]["primary"]["widget"]
  assert tablist_primary["element_id"] == "e_product_category_tablist"
  assert tablist_primary["selector"] == 'div[role="tablist"]'
  assert tablist_primary["accessible_name"] == "Product categories"
  assert tablist_primary["text"] == "Desk accessories Office supplies"
  assert tablist_record["state_context"]["url"] == "https://example.com/products"
  assert 'data-testid="product-category-tablist"' in (
    tablist_record["evidence"]["dom_snippets"][0]["html"]
  )

  desk_primary = records_by_element_id["e_desk_tab"]["evidence"]["primary"][
    "widget"
  ]
  assert desk_primary["role"] == "tab"
  assert desk_primary["accessible_name"] == "Desk accessories"
  assert desk_primary["aria_controls"] == "desk-accessories-panel"
  office_primary = records_by_element_id["e_office_tab"]["evidence"]["primary"][
    "widget"
  ]
  assert office_primary["role"] == "tab"
  assert office_primary["accessible_name"] == "Office supplies"
  assert office_primary["aria_controls"] == "office-supplies-panel"


def test_aria_state_candidate_includes_generic_aria_current_context(tmp_path):
  payload = _semantic_payload_for_page(
    state_id="state_0000",
    url="https://example.com/section-b",
    title="Section B | Example",
    body_text_sample="Section B content Navigation Section A Section B",
    heading_text="Section B",
  )
  current_link = _element(
    "e_section_a_link",
    tag="a",
    selector='a[data-testid="section-a"]',
    text="Section A",
    raw_html=(
      '<a href="/section-a" data-testid="section-a" '
      'aria-current="page">Section A</a>'
    ),
  )
  current_link["href"] = "/section-a"
  peer_link = _element(
    "e_section_b_link",
    tag="a",
    selector='a[data-testid="section-b"]',
    text="Section B",
    raw_html='<a href="/section-b" data-testid="section-b">Section B</a>',
  )
  peer_link["href"] = "/section-b"
  payload["links"] = [current_link, peer_link]
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=payload)
  _write_graph(run_dir, ["state_0000"])

  summary = build_semantic_candidates(run_dir, candidate_types=["aria-state-mismatch"])
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")

  assert len(records) == 1
  primary = records[0]["evidence"]["primary"]["aria_state"]
  assert primary["bucket"] == "links"
  assert primary["selector"] == 'a[data-testid="section-a"]'
  assert primary["text"] == "Section A"
  assert primary["accessible_name"] == "Section A"
  assert primary["href"] == "/section-a"
  assert primary["state_attributes"] == {"aria_current": "page"}
  assert "expected_current" not in primary

  context = records[0]["evidence"]["supporting"]["aria_state_context_v1"]
  current_context = context["current_item_context"]
  assert current_context["page"]["url"] == "https://example.com/section-b"
  assert current_context["headings"][0]["text"] == "Section B"
  assert current_context["current_item"]["href"] == "/section-a"
  assert current_context["current_item"]["state_attributes"] == {
    "aria_current": "page"
  }
  assert current_context["peer_items"] == [
    {
      "bucket": "links",
      "element_id": "e_section_b_link",
      "tag": "a",
      "role": None,
      "selector": 'a[data-testid="section-b"]',
      "raw_html": '<a href="/section-b" data-testid="section-b">Section B</a>',
      "text": "Section B",
      "accessible_name": "Section B",
      "href": "/section-b",
      "state_attributes": {},
    }
  ]


def test_aria_state_candidate_includes_noncurrent_language_sample_peers(tmp_path):
  payload = _semantic_payload_for_page(
    state_id="state_0000",
    url="https://example.com/cart",
    title="Cart | Brightlane Checkout",
    body_text_sample=(
      "Cart Checkout progress Cart Current step Shipping address Not started "
      "Payment Not started Review Not started"
    ),
    heading_text="Cart",
  )
  landmark = {
    "element_id": "e_checkout_progress",
    "selector": '[data-testid="checkout-progress"]',
  }

  def progress_step(
    element_id: str,
    step_id: str,
    text: str,
    *,
    aria_current: bool = False,
  ) -> dict[str, object]:
    aria_attribute = ' aria-current="step"' if aria_current else ""
    step = _element(
      element_id,
      tag="li",
      selector=f'[data-testid="checkout-progress-{step_id}"]',
      text=text,
      raw_html=(
        f'<li data-testid="checkout-progress-{step_id}"{aria_attribute}>'
        f"{text}</li>"
      ),
    )
    step["structure"] = {"nearest_landmark": landmark}
    return step

  shipping_current = progress_step(
    "e_progress_address",
    "address",
    "Shipping address Not started",
    aria_current=True,
  )
  payload["visual_cues"] = [shipping_current]
  payload["language_samples"] = [
    progress_step("e_progress_cart", "cart", "Cart Current step"),
    shipping_current,
    progress_step("e_progress_payment", "payment", "Payment Not started"),
    progress_step("e_progress_review", "review", "Review Not started"),
  ]
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=payload)
  _write_graph(run_dir, ["state_0000"])

  summary = build_semantic_candidates(
    run_dir,
    candidate_types=["aria-state-mismatch"],
  )
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")

  assert len(records) == 1
  primary = records[0]["evidence"]["primary"]["aria_state"]
  assert primary["selector"] == '[data-testid="checkout-progress-address"]'
  assert primary["state_attributes"] == {"aria_current": "step"}
  context = records[0]["evidence"]["supporting"]["aria_state_context_v1"]
  peers = {
    peer["selector"]: peer
    for peer in context["current_item_context"]["peer_items"]
  }
  assert peers['[data-testid="checkout-progress-cart"]']["text"] == (
    "Cart Current step"
  )
  assert peers['[data-testid="checkout-progress-cart"]']["state_attributes"] == {}
  assert peers['[data-testid="checkout-progress-payment"]']["state_attributes"] == {}
  assert peers['[data-testid="checkout-progress-review"]']["state_attributes"] == {}


def test_aria_state_candidate_includes_generic_pressed_peer_context(tmp_path):
  payload = _semantic_payload_for_page(
    state_id="state_0000",
    url="https://example.com/products",
    title="Products | Example",
    body_text_sample="Products Language English Spanish",
    heading_text="Products",
  )
  english = _element(
    "e_language_en",
    tag="button",
    selector="button#products-language-en",
    text="English",
    raw_html=(
      '<button id="products-language-en" role="button" aria-pressed="false" '
      'data-testid="products-language-en">English</button>'
    ),
  )
  english["role"] = "button"
  spanish = _element(
    "e_language_es",
    tag="button",
    selector="button#products-language-es",
    text="Spanish",
    raw_html=(
      '<button id="products-language-es" role="button" aria-pressed="true" '
      'data-testid="products-language-es">Spanish</button>'
    ),
  )
  spanish["role"] = "button"
  payload["buttons"] = [english, spanish]
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=payload)
  _write_graph(run_dir, ["state_0000"])

  summary = build_semantic_candidates(
    run_dir,
    candidate_types=["aria-state-mismatch"],
  )
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")
  spanish_record = next(
    record
    for record in records
    if record["evidence"]["primary"]["aria_state"]["text"] == "Spanish"
  )
  supporting = spanish_record["evidence"]["supporting"]
  peer_context = supporting["aria_state_context_v1"]["peer_state_context"]
  peers = {peer["selector"]: peer for peer in peer_context}

  assert supporting["page"]["document_lang"] == "en"
  assert supporting["page"]["title"] == "Products | Example"
  assert peers["button#products-language-en"][
    "state_attributes"
  ] == {"aria_pressed": "false"}
  assert peers["button#products-language-es"][
    "state_attributes"
  ] == {"aria_pressed": "true"}


def test_aria_state_candidate_keeps_legacy_state_attribute_support(tmp_path):
  payload = _semantic_payload_for_page(
    state_id="state_0000",
    url="https://example.com/widgets",
    title="Widgets | Example",
    body_text_sample="Widgets Details Profile Save Alerts",
    heading_text="Widgets",
  )
  expanded = _element(
    "e_disclosure",
    tag="button",
    selector="button#details",
    text="Details",
    raw_html='<button id="details" aria-expanded="false">Details</button>',
  )
  selected = _element(
    "e_tab",
    tag="button",
    selector="button#profile",
    text="Profile",
    raw_html='<button id="profile" role="tab" aria-selected="true">Profile</button>',
  )
  selected["role"] = "tab"
  checked = _element(
    "e_switch",
    tag="button",
    selector="button#alerts",
    text="Alerts",
    raw_html='<button id="alerts" role="switch" aria-checked="false">Alerts</button>',
  )
  checked["role"] = "switch"
  pressed = _element(
    "e_toggle",
    tag="button",
    selector="button#save",
    text="Save",
    raw_html='<button id="save" aria-pressed="true">Save</button>',
  )
  payload["buttons"] = [expanded, selected, checked, pressed]
  run_dir = _make_run(tmp_path)
  _write_state(run_dir, "state_0000", accessibility_context=payload)
  _write_graph(run_dir, ["state_0000"])

  summary = build_semantic_candidates(run_dir, candidate_types=["aria-state-mismatch"])
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")

  state_attributes = {
    record["evidence"]["primary"]["aria_state"]["selector"]:
    record["evidence"]["primary"]["aria_state"]["state_attributes"]
    for record in records
  }
  assert state_attributes == {
    "button#details": {"aria_expanded": "false"},
    "button#profile": {"aria_selected": "true"},
    "button#alerts": {"aria_checked": "false"},
    "button#save": {"aria_pressed": "true"},
  }


def _make_run(tmp_path: Path) -> Path:
  run_dir = tmp_path / "20260429_120000"
  run_dir.mkdir()
  return run_dir


def _write_state(run_dir: Path, state_id: str, *, accessibility_context: dict[str, object]) -> None:
  state_dir = run_dir / "states" / state_id
  state_dir.mkdir(parents=True)
  page = accessibility_context.get("page")
  page = page if isinstance(page, dict) else {}
  url = str(page.get("url") or f"https://example.com/{state_id}")
  route = "/" + url.rsplit("/", maxsplit=1)[-1]
  metadata = {
    "state_id": state_id,
    "url": url,
    "route": route,
    "title": page.get("title") or "",
    "depth": 0,
    "parent_state": None,
    "action_from_parent": None,
    "html_hash": f"hash-{state_id}",
    "html": "dom.html",
    "screenshot": "screenshot.png",
    "accessibility_context": "accessibility_context.json",
  }
  state_dir.joinpath("metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
  state_dir.joinpath("accessibility_context.json").write_text(json.dumps(accessibility_context), encoding="utf-8")
  state_dir.joinpath("dom.html").write_text("<html></html>", encoding="utf-8")
  state_dir.joinpath("screenshot.png").write_bytes(b"png")


def _write_graph(
  run_dir: Path,
  state_ids: list[str],
  *,
  transitions: list[dict[str, object]] | None = None,
) -> None:
  transitions = transitions or []
  nodes = [
    {
      "state_id": state_id,
      "url": f"https://example.com/{state_id}",
      "route": f"/{state_id}",
      "title": "",
      "html_hash": f"hash-{state_id}",
      "dom_identity_hash": f"identity-{state_id}",
      "stable_state_key": f"identity-{state_id}|https://example.com/{state_id}",
      "parent_state_id": None,
      "incoming_action": None,
    }
    for state_id in state_ids
  ]
  for edge in transitions:
    target = str(edge.get("to") or "")
    source = str(edge.get("from") or "")
    action = edge.get("action") if isinstance(edge.get("action"), dict) else {}
    for node in nodes:
      if node["state_id"] == target:
        node["parent_state_id"] = source
        node["incoming_action"] = action
  run_dir.joinpath("graph.json").write_text(
    json.dumps(
      {
        "start_state": state_ids[0],
        "states": state_ids,
        "nodes": nodes,
        "edges": transitions,
      }
    ),
    encoding="utf-8",
  )
  run_dir.joinpath("transitions.json").write_text(json.dumps(transitions), encoding="utf-8")


def _transition(
  source_state_id: str,
  target_state_id: str,
  action: dict[str, object],
) -> dict[str, object]:
  return {
    "from": source_state_id,
    "to": target_state_id,
    "action": action,
  }


def _semantic_payload_for_page(
  *,
  state_id: str,
  url: str,
  title: str,
  body_text_sample: str,
  heading_text: str,
) -> dict[str, object]:
  payload = _semantic_payload()
  payload["state_id"] = state_id
  payload["page"] = {
    "url": url,
    "title": title,
    "document_lang": "en",
    "html_lang": "en",
    "body_text_sample": body_text_sample,
    "body_text_length": len(body_text_sample),
  }
  payload["headings"] = [
    {
      **_heading(),
      "element_id": f"e_heading_{state_id}",
      "text": heading_text,
      "accessible_name": heading_text,
    }
  ]
  payload["landmarks"] = [
    {
      **_landmark(),
      "element_id": f"e_main_{state_id}",
      "text": body_text_sample,
      "text_sample": body_text_sample,
      "accessible_name": body_text_sample,
    }
  ]
  payload["links"] = []
  payload["buttons"] = []
  payload["forms"] = []
  payload["form_controls"] = []
  payload["visual_cues"] = []
  payload["focusables"] = []
  payload["focus_order"] = []
  payload["focus_traversal"] = []
  payload["relationships"] = []
  return payload


def _color_state_visual_cue(
  element_id: str,
  *,
  selector: str,
  text: str,
  raw_html: str,
  cue_attributes: dict[str, object],
) -> dict[str, object]:
  cue = _element(
    element_id,
    tag="button",
    selector=selector,
    text=text,
    raw_html=raw_html,
  )
  cue.update(
    {
      "kind": "visual_cue",
      "inline_style": "",
      "has_inline_color": False,
      "computed_style": {
        "display": "block",
        "color": "rgb(21, 94, 84)",
        "background_color": "rgb(227, 241, 237)",
      },
      "parent_computed_style": {
        "color": "rgb(31, 37, 40)",
        "background_color": "rgb(255, 255, 255)",
      },
      "cue_attributes": cue_attributes,
    }
  )
  return cue


def _semantic_payload() -> dict[str, object]:
  link = _element("e_link", tag="a", selector="a#docs", text="Project docs", raw_html='<a id="docs" href="/docs">Project docs</a>')
  link["href"] = "/docs"

  button = _element(
    "e_button",
    tag="button",
    selector="button#account-tab",
    text="Profile",
    raw_html='<button id="account-tab" role="tab" aria-selected="false" aria-expanded="false" aria-controls="panel-a">Profile</button>',
  )
  button["role"] = "tab"
  button["aria_selected"] = "false"
  button["aria_expanded"] = "false"
  button["aria_controls"] = "panel-a"

  control = _element("e_email", tag="input", selector="input#email", text="", raw_html='<input id="email" name="email" type="text" autocomplete="postal-code" aria-invalid="true" aria-describedby="email-error">')
  control.update(
    {
      "kind": "form_control",
      "type": "text",
      "name": "email",
      "id": "email",
      "label": "Email address",
      "placeholder": "name@example.com",
      "autocomplete": "postal-code",
      "aria_invalid": "true",
      "aria_describedby": "email-error",
      "invalid": True,
      "native_validity": {"valid": False, "type_mismatch": True},
      "has_value": True,
      "parent_form": {"element_id": "e_form", "selector": "form#account", "accessible_name": "Account form"},
    }
  )

  visual_cue = _element("e_status", tag="span", selector="span#status", text="Status", raw_html='<span id="status" class="status-danger" style="color: red">Status</span>')
  visual_cue.update(
    {
      "kind": "visual_cue",
      "inline_style": "color: red",
      "has_inline_color": True,
      "computed_style": {"color": "rgb(255, 0, 0)", "background_color": "rgba(0, 0, 0, 0)"},
      "parent_computed_style": {"color": "rgb(0, 0, 0)", "background_color": "rgba(0, 0, 0, 0)"},
      "cue_attributes": {"data_status": "requires-action"},
    }
  )

  focus_a = _focusable("e_focus_a", "input#name", "Name", y=10, tabindex=2, dom_order=0)
  focus_b = _focusable("e_focus_b", "input#newsletter", "Newsletter", y=80, tabindex=1, dom_order=1)

  return {
    "schema_version": "1",
    "state_id": "state_0000",
    "state_context": {"depth": 0, "parent_state": None, "action_from_parent": None},
    "page": {
      "url": "https://example.com/state_0000",
      "title": "Workspace dashboard",
      "document_lang": "en",
      "html_lang": "en",
      "body_text_sample": "Workspace dashboard account profile payment status Kontaktformular absenden",
      "body_text_length": 72,
    },
    "referenced_elements": [
      _element("e_label", tag="label", selector="label#email-label", text="Email address"),
      _element("e_error", tag="p", selector="p#email-error", text="Your password must contain eight characters."),
      _element("e_panel", tag="div", selector="div#panel-a", text="Billing address and payment history"),
    ],
    "images": [_element("e_image", tag="img", selector="img#hero", alt="Planning board", text="", raw_html='<img id="hero" src="board.png" alt="Planning board">')],
    "videos": [],
    "links": [link],
    "buttons": [button],
    "forms": [_element("e_form", tag="form", selector="form#account", text="Account form Email address")],
    "form_controls": [control],
    "headings": [_heading()],
    "landmarks": [_landmark()],
    "tables": [_table()],
    "language_samples": [
      {
        **_element("e_local_lang", tag="span", selector="span#local-lang", text="sehr interessant", raw_html='<span id="local-lang" lang="fr">sehr interessant</span>'),
        "kind": "language_sample",
        "language_text": "sehr interessant",
        "word_count": 2,
        "root_lang": "en",
        "local_lang": "fr",
        "ancestor_lang": "",
        "effective_lang": "fr",
      }
    ],
    "visual_cues": [visual_cue],
    "focusables": [focus_a, focus_b],
    "focus_order": [{"order": 1, "element_id": "e_focus_a"}, {"order": 2, "element_id": "e_focus_b"}],
    "focus_traversal": [
      {**focus_b, "order": 1, "accessible_name_hint": "Newsletter", "is_visible": True, "is_disabled": False},
      {**focus_a, "order": 2, "accessible_name_hint": "Name", "is_visible": True, "is_disabled": False},
    ],
    "focus_traversal_metadata": {"captured_steps": 2, "traversal_complete": True, "partial": False, "stop_reason": "cycle_detected"},
    "relationships": [
      {"type": "labels", "from_element_id": "e_label", "to_element_id": "e_email", "method": "for"},
      {"type": "describes", "from_element_id": "e_error", "to_element_id": "e_email", "method": "aria-describedby"},
      {"type": "controls", "from_element_id": "e_button", "to_element_id": "e_panel", "method": "aria-controls"},
      {"type": "landmark_contains", "from_element_id": "e_main", "to_element_id": "e_button", "method": "nearest"},
    ],
    "extraction_metadata": {"status": "success", "truncated": False, "truncation": {}, "limits": {}},
  }


def _video(
  *,
  src: str = "/media/brightlane-checkout-walkthrough.mp4",
  tracks: list[dict[str, object]] | None = None,
) -> dict[str, object]:
  video = _element(
    "e_video",
    tag="video",
    selector="video#walkthrough",
    raw_html=(
      '<video id="walkthrough" controls aria-label="Checkout walkthrough">'
      '<track kind="captions" srclang="en" label="English"></video>'
    ),
  )
  video.update(
    {
      "kind": "video",
      "accessible_name": "Checkout walkthrough",
      "src": src,
      "current_src": f"https://example.com{src}",
      "source_src": src,
      "sources": [{"src": src, "current_src": f"https://example.com{src}", "type": "video/mp4", "media": ""}],
      "controls": True,
      "preload": "metadata",
      "autoplay": False,
      "muted": False,
      "loop": False,
      "duration": 27.625,
      "ready_state": 1,
      "nearby_transcript_text": "Checkout support video",
      "tracks": tracks if tracks is not None else [_caption_track("e_track_en")],
    }
  )
  return video


def _caption_track(
  element_id: str,
  *,
  language: str = "en",
  label: str = "English",
  src: str = "/media/brightlane-checkout-walkthrough.en.vtt",
  cues: list[dict[str, object]] | None = None,
) -> dict[str, object]:
  resolved_cues = cues if cues is not None else [
    {"index": 1, "start_time": 2.0, "end_time": 3.0, "text": "Review your cart."},
    {"index": 0, "start_time": 0.0, "end_time": 1.5, "text": "Choose products."},
  ]
  return {
    "element_id": element_id,
    "selector": f"track#{element_id}",
    "xpath": "/html[1]/body[1]/video[1]/track[1]",
    "kind": "captions",
    "src": src,
    "current_src": f"https://example.com{src}",
    "srclang": language,
    "label": label,
    "default": language == "en",
    "mode": "showing" if language == "en" else "disabled",
    "ready_state": "loaded",
    "cue_status": "loaded",
    "cue_count": len(resolved_cues),
    "cues_truncated": False,
    "cues": resolved_cues,
  }


def _contains_judgment_key(value: object) -> bool:
  forbidden = {"is_inaccurate", "matches_reference", "violation", "expected_decision"}
  if isinstance(value, dict):
    return any(str(key).lower() in forbidden or _contains_judgment_key(child) for key, child in value.items())
  if isinstance(value, list):
    return any(_contains_judgment_key(item) for item in value)
  return False


def _element(
  element_id: str,
  *,
  tag: str,
  selector: str,
  text: str = "",
  alt: str | None = None,
  raw_html: str | None = None,
) -> dict[str, object]:
  name = alt or text or "Named element"
  return {
    "element_id": element_id,
    "kind": tag,
    "tag": tag,
    "role": None,
    "selector": selector,
    "xpath": f"/html[1]/body[1]/{tag}[1]",
    "text": text,
    "accessible_name": name,
    "alt": alt,
    "aria_label": None,
    "aria_labelledby": None,
    "aria_describedby": None,
    "title": None,
    "visible": True,
    "bounding_box": {"x": 1, "y": 2, "width": 30, "height": 40},
    "computed_style": {"display": "block", "color": "rgb(0, 0, 0)", "background_color": "rgba(0, 0, 0, 0)"},
    "structure": {"nearest_landmark": {"element_id": "e_main", "tag": "main"}, "nearest_heading": {"element_id": "e_heading", "text": "Workspace dashboard"}},
    "context": {"nearby_text": "Nearby context", "parent_text": "Parent context", "section_heading": "Evidence section"},
    "raw_html": raw_html or f"<{tag} id='{element_id}'>{text}</{tag}>",
  }


def _language_sample(
  element_id: str,
  *,
  tag: str,
  selector: str,
  text: str,
  local_lang: str,
) -> dict[str, object]:
  raw_html = (
    f'<{tag} id="{element_id}" lang="{local_lang}">{text}</{tag}>'
    if local_lang
    else f'<{tag} id="{element_id}">{text}</{tag}>'
  )
  sample = _element(
    element_id,
    tag=tag,
    selector=selector,
    text=text,
    raw_html=raw_html,
  )
  sample.update(
    {
      "kind": "language_sample",
      "language_text": text,
      "word_count": len(text.split()),
      "root_lang": "en",
      "body_lang": "",
      "page_lang": "en",
      "local_lang": local_lang,
      "ancestor_lang": "",
      "effective_lang": local_lang or "en",
    }
  )
  return sample


def _explicit_role_component() -> dict[str, object]:
  component = _element(
    "e_role_search",
    tag="div",
    selector='div[role="search"]',
    text="Review your order Total EUR 79 Confirm purchase",
    raw_html=(
      '<div role="search" aria-label="Product search">'
      "<h2>Review your order</h2><p>Total EUR 79</p><button>Confirm purchase</button>"
      "</div>"
    ),
  )
  component.update(
    {
      "kind": "landmark",
      "role": "search",
      "aria_label": "Product search",
      "accessible_name": "Product search",
      "text_sample": "Review your order Total EUR 79 Confirm purchase",
    }
  )
  return component


def _native_nav_landmark() -> dict[str, object]:
  nav = _element(
    "e_nav",
    tag="nav",
    selector="nav#checkout",
    text="Home Products Contact",
    raw_html='<nav id="checkout" aria-label="Footer navigation">Home Products Contact</nav>',
  )
  nav.update(
    {
      "kind": "landmark",
      "aria_label": "Footer navigation",
      "accessible_name": "Footer navigation",
      "text_sample": "Home Products Contact",
    }
  )
  return nav


def _summary_widget() -> dict[str, object]:
  summary = _element(
    "e_summary",
    tag="summary",
    selector="summary#profile",
    text="Profile",
    raw_html='<summary id="profile">Profile</summary>',
  )
  summary.update({"kind": "focusable"})
  return summary


def _plain_focusable() -> dict[str, object]:
  focusable = _element(
    "e_plain_focusable",
    tag="div",
    selector="div#plain-focusable",
    text="Focusable text",
    raw_html='<div id="plain-focusable" tabindex="0">Focusable text</div>',
  )
  focusable.update({"kind": "focusable", "tabindex": "0", "tabindex_value": 0})
  return focusable


def _status_role_element(*, kind: str) -> dict[str, object]:
  status = _element(
    "e_status_role",
    tag="div",
    selector="div#status",
    text="Saving complete",
    raw_html='<div id="status" role="status" tabindex="0">Saving complete</div>',
  )
  status.update({"kind": kind, "role": "status", "accessible_name": "Saving complete"})
  return status


def _heading() -> dict[str, object]:
  heading = _element("e_heading", tag="h1", selector="h1#dashboard", text="Workspace dashboard")
  heading["level"] = 1
  heading["heading_scope"] = {
    "schema_version": "heading_scope_v1",
    "text_excerpt": "Account profile payment status controls",
    "sampled_items": [{"kind": "paragraph", "text": "Account profile payment status controls"}],
    "content_counts": {"paragraphs": 1},
  }
  return heading


def _landmark() -> dict[str, object]:
  landmark = _element("e_main", tag="main", selector="main", text="Account profile payment status controls")
  landmark.update({"kind": "landmark", "text_sample": "Account profile payment status controls"})
  return landmark


def _table() -> dict[str, object]:
  table = _element("e_table", tag="table", selector="table#orders", text="Product Price Office chair EUR 120", raw_html='<table id="orders"><tr><th id="product">Product</th><th id="price">Price</th></tr><tr><td headers="price">Office chair</td><td headers="product">EUR 120</td></tr></table>')
  product = {"id": "product", "text": "Product", "selector": "th#product", "row_index": 0, "column_index": 0, "scope": ""}
  price = {"id": "price", "text": "Price", "selector": "th#price", "row_index": 0, "column_index": 1, "scope": ""}
  table.update(
    {
      "kind": "table",
      "caption": "Order lines",
      "header_count": 2,
      "data_cell_count": 2,
      "headers": [product, price],
      "data_cells": [
        {"text": "Office chair", "header_ids": ["price"], "headers_all_resolved": True, "associated_headers": [price], "row_index": 1, "column_index": 0, "selector": "td:nth-of-type(1)"},
        {"text": "EUR 120", "header_ids": ["product"], "headers_all_resolved": True, "associated_headers": [product], "row_index": 1, "column_index": 1, "selector": "td:nth-of-type(2)"},
      ],
    }
  )
  return table


def _focusable(element_id: str, selector: str, text: str, *, y: int, tabindex: int, dom_order: int) -> dict[str, object]:
  item = _element(element_id, tag="input", selector=selector, text="", raw_html=f'<input id="{element_id}" tabindex="{tabindex}">')
  item.update(
    {
      "kind": "focusable",
      "text": text,
      "accessible_name": text,
      "type": "text",
      "tabindex": str(tabindex),
      "tabindex_value": tabindex,
      "dom_order_index": dom_order,
      "bounding_box": {"x": 10, "y": y, "width": 100, "height": 20},
    }
  )
  return item


def _read_json(path: Path) -> dict[str, object]:
  return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, object]]:
  return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
