from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.evaluation.score_seeded_experiment import main as scorer_script_main
from src.analysis.evaluation.seeded_scorer import (
  DEFAULT_REGISTRY_PATH,
  SeededScorerOptions,
  _aria_state_peer_items,
  _route_matches,
  _state_attribute_value,
  _state_matches_expected_constraints,
  _structured_value_contains,
  score_seeded_experiment,
)


def test_default_registry_path_uses_standalone_benchmark_registry():
  assert DEFAULT_REGISTRY_PATH == Path("benchmarks/registry/benchmark-case-registry.json")


def test_route_matching_and_state_constraints():
  assert _route_matches("/checkout/review", "/checkout")
  assert _route_matches("https://example.test/checkout/review", "/checkout")
  assert not _route_matches("/cart", "/checkout")
  assert _state_matches_expected_constraints(
    has_routes=True,
    route_matches=True,
    has_benchmark_state_ids=True,
    benchmark_matches=True,
  )
  assert not _state_matches_expected_constraints(
    has_routes=True,
    route_matches=True,
    has_benchmark_state_ids=True,
    benchmark_matches=False,
  )


def test_state_attribute_value_reads_visual_cue_attributes():
  assert _state_attribute_value(
    {"cue_attributes": {"aria_current": "step"}},
    "aria_current",
  ) == "step"


def test_scores_seeded_case_from_temp_registry(tmp_path):
  run_dir = _write_run(tmp_path)
  registry_path = _write_registry(tmp_path)
  _write_candidate_records(
    run_dir,
    [
      {
        "candidate_id": "cand_button",
        "candidate_type": "button-label-mismatch",
        "state_id": "state_0000",
        "state_context": {"url": "https://example.test/checkout/review", "route": "/checkout/review"},
        "evidence": {
          "primary": {
            "button": {
              "element_id": "e_button",
              "selector": "button#place-order",
              "text": "Place order",
              "accessible_name": "Place order",
            }
          }
        },
      }
    ],
  )

  result = score_seeded_experiment(
    SeededScorerOptions(
      run_dir=run_dir,
      config_id="checkout-pilot",
      registry_path=registry_path,
      score_run_id="score_one",
    ),
    generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
  )

  assert result.summary["counts"]["expected_seeds"] == 1
  assert result.summary["counts"]["recovered_seeds"] == 1
  seed_result = result.summary["results"][0]
  assert seed_result["status"] == "recovered_to_candidate"
  assert seed_result["matched_candidates"][0]["candidate_id"] == "cand_button"


def test_legacy_single_expected_evidence_non_match_does_not_recover(tmp_path):
  run_dir = _write_run(tmp_path)
  registry_path = _write_registry(tmp_path)
  _write_candidate_records(
    run_dir,
    [
      {
        "candidate_id": "cand_wrong_button",
        "candidate_type": "button-label-mismatch",
        "state_id": "state_0000",
        "state_context": {"url": "https://example.test/checkout/review"},
        "evidence": {
          "primary": {
            "button": {
              "element_id": "e_button",
              "selector": "button#place-order",
              "text": "Cancel order",
              "accessible_name": "Cancel order",
            }
          }
        },
      }
    ],
  )

  result = score_seeded_experiment(
    SeededScorerOptions(
      run_dir=run_dir,
      config_id="checkout-pilot",
      registry_path=registry_path,
      score_run_id="score_legacy_non_match",
    ),
    generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
  )

  assert result.summary["counts"]["expected_seeds"] == 1
  assert result.summary["counts"]["recovered_seeds"] == 0
  seed_result = result.summary["results"][0]
  assert seed_result["status"] == "candidate_missing"
  assert seed_result["candidate_status"] == "candidate_missing"


def test_structured_value_contains_uses_recursive_subset_semantics():
  actual = {
    "schema_version": "heading_scoped_content_v1",
    "source_element_ref": {
      "bucket": "landmarks",
      "selector": "main:nth-of-type(1)",
      "tags": ["main", {"name": "primary", "active": True}],
    },
    "text_excerpt": "Products Browse featured products and update the cart summary.",
    "truncated": False,
  }

  assert _structured_value_contains(
    actual,
    {
      "source_element_ref": {
        "tags": [{"active": True}, "main"],
      },
      "truncated": False,
    },
  )
  assert not _structured_value_contains(actual, {"source_element_ref": {"role": "main"}})
  assert not _structured_value_contains(actual, {"source_element_ref": "main"})
  assert not _structured_value_contains(actual, {"truncated": {"value": False}})
  assert not _structured_value_contains(actual, {"source_element_ref": {"tags": ["aside"]}})
  assert _structured_value_contains({"optional": None}, {"optional": None})
  assert not _structured_value_contains({}, {"optional": None})


def test_candidate_evidence_constraint_is_optional_for_existing_candidates(tmp_path):
  run_dir = _write_run(tmp_path)
  registry_path = _write_registry(tmp_path)
  _write_candidate_records(
    run_dir,
    [
      {
        "candidate_id": "cand_without_supporting_evidence",
        "candidate_type": "button-label-mismatch",
        "state_id": "state_0000",
        "state_context": {
          "url": "https://example.test/checkout/review",
          "route": "/checkout/review",
        },
        "evidence": {
          "primary": {
            "button": {
              "element_id": "e_button",
              "selector": "button#place-order",
              "text": "Place order",
              "accessible_name": "Place order",
            }
          }
        },
      }
    ],
  )

  result = score_seeded_experiment(
    SeededScorerOptions(
      run_dir=run_dir,
      config_id="checkout-pilot",
      registry_path=registry_path,
      score_run_id="score_without_candidate_evidence_constraint",
    ),
    generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
  )

  assert result.summary["counts"]["recovered_seeds"] == 1


def test_heading_candidate_evidence_constraint_control_matrix(tmp_path):
  products_intro = "Browse featured products and update the cart summary."
  scenarios = (
    {
      "name": "clean_cart",
      "route": "/cart",
      "state_heading": "Cart",
      "candidate_heading": "Cart",
      "sampled_paragraph": "Review cart items and quantity controls.",
      "expected_recovered": 0,
    },
    {
      "name": "products_source",
      "route": "/products",
      "state_heading": "Products",
      "candidate_heading": "Products",
      "sampled_paragraph": products_intro,
      "expected_recovered": 0,
    },
    {
      "name": "h1_only_mutation",
      "route": "/cart",
      "state_heading": "Products",
      "candidate_heading": "Products",
      "sampled_paragraph": "Review cart items and quantity controls.",
      "expected_recovered": 0,
    },
    {
      "name": "missing_scoped_content",
      "route": "/cart",
      "state_heading": "Products",
      "candidate_heading": "Products",
      "include_scoped_content": False,
      "sampled_paragraph": None,
      "expected_recovered": 0,
    },
    {
      "name": "wrong_scoped_content",
      "route": "/cart",
      "state_heading": "Products",
      "candidate_heading": "Products",
      "sampled_paragraph": "Enter card details for the current checkout.",
      "expected_recovered": 0,
    },
    {
      "name": "same_text_elsewhere",
      "route": "/cart",
      "state_heading": "Products",
      "candidate_heading": "Products",
      "sampled_paragraph": "Review cart items and quantity controls.",
      "elsewhere_text": products_intro,
      "expected_recovered": 0,
    },
    {
      "name": "incidental_cart_content_changed",
      "route": "/cart",
      "state_heading": "Products",
      "candidate_heading": "Products",
      "sampled_paragraph": products_intro,
      "full_scoped_text": (
        "Products Cart content with different prices, quantities, totals, "
        "and controls."
      ),
      "expected_recovered": 1,
    },
    {
      "name": "selector_changed",
      "route": "/cart",
      "state_heading": "Products",
      "candidate_heading": "Products",
      "candidate_selector": "main > h1",
      "sampled_paragraph": products_intro,
      "expected_recovered": 1,
    },
    {
      "name": "compound_stale_block",
      "route": "/cart",
      "state_heading": "Products",
      "candidate_heading": "Products",
      "sampled_paragraph": products_intro,
      "expected_recovered": 1,
    },
  )

  for scenario in scenarios:
    scenario_dir = tmp_path / str(scenario["name"])
    run_dir = _write_heading_context_run(
      scenario_dir,
      route=str(scenario["route"]),
      heading=str(scenario["state_heading"]),
    )
    registry_path = _write_heading_context_registry(scenario_dir, products_intro=products_intro)
    supporting: dict[str, object] = {
      "page": {
        "body_text_sample": str(
          scenario.get("elsewhere_text")
          or "Cart Review cart items and quantity controls."
        )
      }
    }
    if scenario.get("include_scoped_content", True):
      supporting["heading_scoped_content"] = {
        "schema_version": "heading_scoped_content_v1",
        "source": "labelledby_landmark_text_sample",
        "source_element_ref": {
          "bucket": "landmarks",
          "selector": "main:nth-of-type(1)",
          "tag": "main",
        },
        "text_excerpt": scenario.get(
          "full_scoped_text",
          "Products and Cart content that is not part of the recovery contract.",
        ),
        "truncated": False,
      }
    sampled_paragraph = scenario.get("sampled_paragraph")
    if sampled_paragraph is not None:
      supporting["heading_scope"] = {
        "sampled_items": [
          {
            "kind": "paragraph",
            "element_id": "e_route_summary",
            "tag": "p",
            "selector": "p:nth-of-type(1)",
            "text": sampled_paragraph,
          },
          {
            "kind": "list_item",
            "element_id": "e_cart_progress",
            "tag": "li",
            "selector": "li:nth-of-type(1)",
            "text": "Cart Current step",
          },
        ],
      }
    _write_candidate_records(
      run_dir,
      [
        {
          "candidate_id": f"cand_{scenario['name']}",
          "candidate_type": "heading-not-descriptive",
          "state_id": "state_0000",
          "state_context": {
            "url": f"https://example.test{scenario['route']}",
            "route": scenario["route"],
          },
          "evidence": {
            "primary": {
              "heading": {
                "element_id": "e_page_heading",
                "selector": scenario.get(
                  "candidate_selector",
                  "h1:nth-of-type(1)",
                ),
                "tag": "h1",
                "text": scenario["candidate_heading"],
                "level": 1,
                "accessible_name": scenario["candidate_heading"],
              }
            },
            "supporting": supporting,
          },
        }
      ],
    )

    result = score_seeded_experiment(
      SeededScorerOptions(
        run_dir=run_dir,
        config_id="checkout-heading-context",
        registry_path=registry_path,
        score_run_id=f"score_{scenario['name']}",
      ),
      generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
    )

    assert result.summary["counts"]["recovered_seeds"] == scenario["expected_recovered"], scenario["name"]


def test_shipping_link_destination_recovery_requires_source_and_destination(tmp_path):
  scenarios = (
    {
      "name": "shipping_to_shipping",
      "source_text": "Shipping information",
      "nearest_heading": "Shipping help",
      "nearby_text": "Learn about delivery times and available shipping options.",
      "resolved_path": "/shipping-information.html",
      "expected_recovered": 0,
    },
    {
      "name": "returns_to_returns",
      "source_text": "Returns and refunds",
      "nearest_heading": "Support",
      "nearby_text": "Need help after checkout?",
      "resolved_path": "/returns-and-refunds.html",
      "expected_recovered": 0,
    },
    {
      "name": "returns_to_shipping",
      "source_text": "Returns and refunds",
      "nearest_heading": "Support",
      "nearby_text": "Need help after checkout?",
      "resolved_path": "/shipping-information.html",
      "expected_recovered": 0,
    },
    {
      "name": "shipping_to_returns",
      "source_text": "Shipping information",
      "nearest_heading": "Shipping help",
      "nearby_text": "Learn about delivery times and available shipping options.",
      "resolved_path": "/returns-and-refunds.html",
      "expected_recovered": 1,
    },
    {
      "name": "co_sem_027_source_context",
      "source_text": "Shipping information",
      "nearest_heading": "Support",
      "nearby_text": "Need help after checkout?",
      "resolved_path": "/returns-and-refunds.html",
      "expected_recovered": 0,
    },
  )
  registry_path = Path(__file__).resolve().parents[1] / DEFAULT_REGISTRY_PATH

  for scenario in scenarios:
    run_dir = _write_shipping_link_run(
      tmp_path / str(scenario["name"]),
      source_text=str(scenario["source_text"]),
      nearest_heading=str(scenario["nearest_heading"]),
      nearby_text=str(scenario["nearby_text"]),
      resolved_path=str(scenario["resolved_path"]),
    )
    result = score_seeded_experiment(
      SeededScorerOptions(
        run_dir=run_dir,
        config_id="checkout-co-sem-101",
        registry_path=registry_path,
        score_run_id=f"score_{scenario['name']}",
      ),
      generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
    )

    assert result.summary["counts"]["expected_seeds"] == 1
    assert result.summary["counts"]["recovered_seeds"] == scenario["expected_recovered"]
    seed_result = result.summary["results"][0]
    if scenario["expected_recovered"]:
      assert seed_result["status"] == "recovered_to_candidate"
      assert [
        candidate["candidate_id"]
        for candidate in seed_result["matched_candidates"]
      ] == [f"cand_{scenario['name']}"]
    else:
      assert seed_result["status"] in {"evidence_missing", "candidate_missing"}


def test_opaque_shipping_link_recovery_requires_captured_returns_destination(tmp_path):
  scenarios = (
    {
      "name": "clean_shipping_destination",
      "source_text": "Shipping information",
      "nearest_heading": "Shipping help",
      "nearby_text": "Learn about delivery times and available shipping options.",
      "resolved_path": "/shipping-information.html",
      "destination_path": "/shipping-information.html",
      "destination_title": "Shipping information",
      "destination_heading": "Shipping information",
      "expected_recovered": 0,
    },
    {
      "name": "co_sem_101_explicit_returns_path",
      "source_text": "Shipping information",
      "nearest_heading": "Shipping help",
      "nearby_text": "Learn about delivery times and available shipping options.",
      "resolved_path": "/returns-and-refunds.html",
      "expected_recovered": 0,
    },
    {
      "name": "co_sem_102_source_only",
      "source_text": "Shipping information",
      "nearest_heading": "Shipping help",
      "nearby_text": "Learn about delivery times and available shipping options.",
      "resolved_path": "/resource.html",
      "expected_recovered": 0,
    },
    {
      "name": "opaque_shipping_destination",
      "source_text": "Shipping information",
      "nearest_heading": "Shipping help",
      "nearby_text": "Learn about delivery times and available shipping options.",
      "resolved_path": "/resource.html",
      "destination_path": "/shipping-information.html",
      "destination_title": "Shipping information",
      "destination_heading": "Shipping information",
      "expected_recovered": 0,
    },
    {
      "name": "wrong_source_returns_destination",
      "source_text": "Returns and refunds",
      "nearest_heading": "Support",
      "nearby_text": "Need help after checkout?",
      "resolved_path": "/resource.html",
      "destination_path": "/returns-and-refunds.html",
      "destination_title": "Returns and refunds",
      "destination_heading": "Returns and refunds",
      "expected_recovered": 0,
    },
    {
      "name": "opaque_shipping_to_returns",
      "source_text": "Shipping information",
      "nearest_heading": "Shipping help",
      "nearby_text": "Learn about delivery times and available shipping options.",
      "resolved_path": "/resource.html",
      "destination_path": "/returns-and-refunds.html",
      "destination_title": "Returns and refunds",
      "destination_heading": "Returns and refunds",
      "expected_recovered": 1,
    },
    {
      "name": "co_sem_027_source_context",
      "source_text": "Shipping information",
      "nearest_heading": "Support",
      "nearby_text": "Need help after checkout?",
      "resolved_path": "/resource.html",
      "destination_path": "/returns-and-refunds.html",
      "destination_title": "Returns and refunds",
      "destination_heading": "Returns and refunds",
      "expected_recovered": 0,
    },
  )
  registry_path = Path(__file__).resolve().parents[1] / DEFAULT_REGISTRY_PATH

  for scenario in scenarios:
    run_dir = _write_shipping_link_run(
      tmp_path / str(scenario["name"]),
      source_text=str(scenario["source_text"]),
      nearest_heading=str(scenario["nearest_heading"]),
      nearby_text=str(scenario["nearby_text"]),
      resolved_path=str(scenario["resolved_path"]),
      destination_path=scenario.get("destination_path"),
      destination_title=scenario.get("destination_title"),
      destination_heading=scenario.get("destination_heading"),
    )
    result = score_seeded_experiment(
      SeededScorerOptions(
        run_dir=run_dir,
        config_id="checkout-co-sem-102",
        registry_path=registry_path,
        score_run_id=f"score_{scenario['name']}",
      ),
      generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
    )

    assert result.summary["counts"]["expected_seeds"] == 1
    assert result.summary["counts"]["recovered_seeds"] == scenario["expected_recovered"], scenario["name"]


def test_co_sem_134_recovery_requires_filled_zip_pattern_failure(tmp_path):
  registry_path = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "registry"
    / "benchmark-case-registry.json"
  )
  scenarios = (
    {
      "name": "empty_required",
      "benchmark_state_id": "CO-S010",
      "has_value": False,
      "native_validity": _postal_code_native_validity(value_missing=True),
      "error_text": "ZIP code is required.",
      "expected_candidate_ids": [],
    },
    {
      "name": "clean_malformed",
      "benchmark_state_id": "CO-S022",
      "has_value": True,
      "native_validity": _postal_code_native_validity(format_mismatch=True),
      "error_text": "Enter a valid 5-digit ZIP code.",
      "expected_candidate_ids": [],
    },
    {
      "name": "valid_zip",
      "benchmark_state_id": "CO-S022",
      "has_value": True,
      "native_validity": _postal_code_native_validity(),
      "error_text": None,
      "expected_candidate_ids": [],
    },
    {
      "name": "different_wrong_message",
      "benchmark_state_id": "CO-S022",
      "has_value": True,
      "native_validity": _postal_code_native_validity(format_mismatch=True),
      "error_text": "Email is required.",
      "expected_candidate_ids": [],
    },
    {
      "name": "seeded_final",
      "benchmark_state_id": "CO-S022",
      "has_value": True,
      "native_validity": _postal_code_native_validity(format_mismatch=True),
      "error_text": "ZIP code is required.",
      "expected_candidate_ids": ["cand_seeded_final"],
    },
  )

  for scenario in scenarios:
    run_dir = _write_error_message_recovery_run(
      tmp_path / str(scenario["name"]),
      benchmark_state_id=str(scenario["benchmark_state_id"]),
      control_id="address-postalCode",
      control_name="postalCode",
      has_value=bool(scenario["has_value"]),
      native_validity=dict(scenario["native_validity"]),
      error_text=scenario["error_text"],
    )
    result = score_seeded_experiment(
      SeededScorerOptions(
        run_dir=run_dir,
        config_id="checkout-co-sem-134",
        registry_path=registry_path,
        score_run_id=f"score_{scenario['name']}",
      ),
      generated_at=datetime(2026, 10, 28, tzinfo=timezone.utc),
    )
    seed_result = result.summary["results"][0]
    assert sorted({
      candidate["candidate_id"]
      for candidate in seed_result["matched_candidates"]
    }) == scenario["expected_candidate_ids"]


def test_co_sem_136_recovery_requires_filled_security_code_pattern_failure(tmp_path):
  registry_path = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "registry"
    / "benchmark-case-registry.json"
  )
  scenarios = (
    {
      "name": "empty_required",
      "benchmark_state_id": "CO-S011",
      "has_value": False,
      "native_validity": _security_code_native_validity(value_missing=True),
      "error_text": "Security code is required.",
      "expected_candidate_ids": [],
    },
    {
      "name": "clean_malformed",
      "benchmark_state_id": "CO-S023",
      "has_value": True,
      "native_validity": _security_code_native_validity(format_mismatch=True),
      "error_text": "Enter a 3 or 4 digit security code.",
      "expected_candidate_ids": [],
    },
    {
      "name": "valid_security_code",
      "benchmark_state_id": "CO-S023",
      "has_value": True,
      "native_validity": _security_code_native_validity(),
      "error_text": None,
      "expected_candidate_ids": [],
    },
    {
      "name": "different_wrong_message",
      "benchmark_state_id": "CO-S023",
      "has_value": True,
      "native_validity": _security_code_native_validity(format_mismatch=True),
      "error_text": "Card number is required.",
      "expected_candidate_ids": [],
    },
    {
      "name": "seeded_final",
      "benchmark_state_id": "CO-S023",
      "has_value": True,
      "native_validity": _security_code_native_validity(format_mismatch=True),
      "error_text": "Security code is required.",
      "expected_candidate_ids": ["cand_seeded_final"],
    },
  )

  for scenario in scenarios:
    run_dir = _write_error_message_recovery_run(
      tmp_path / str(scenario["name"]),
      benchmark_state_id=str(scenario["benchmark_state_id"]),
      control_id="payment-securityCode",
      control_name="securityCode",
      has_value=bool(scenario["has_value"]),
      native_validity=dict(scenario["native_validity"]),
      error_text=scenario["error_text"],
    )
    result = score_seeded_experiment(
      SeededScorerOptions(
        run_dir=run_dir,
        config_id="checkout-co-sem-136",
        registry_path=registry_path,
        score_run_id=f"score_{scenario['name']}",
      ),
      generated_at=datetime(2026, 10, 28, tzinfo=timezone.utc),
    )
    seed_result = result.summary["results"][0]
    assert sorted({
      candidate["candidate_id"]
      for candidate in seed_result["matched_candidates"]
    }) == scenario["expected_candidate_ids"]


def test_co_sem_135_recovery_requires_final_filled_email_format_failure(tmp_path):
  registry_path = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "registry"
    / "benchmark-case-registry.json"
  )
  scenarios = (
    {
      "name": "initial_required",
      "benchmark_state_id": "CO-S010",
      "control_id": "address-email",
      "control_name": "email",
      "has_value": False,
      "native_validity": _email_native_validity(value_missing=True),
      "error_text": "Email is required.",
      "expected_candidate_ids": [],
    },
    {
      "name": "clean_malformed",
      "benchmark_state_id": "CO-S021",
      "control_id": "address-email",
      "control_name": "email",
      "has_value": True,
      "native_validity": _email_native_validity(format_mismatch=True),
      "error_text": "Enter a valid email address.",
      "expected_candidate_ids": [],
    },
    {
      "name": "valid_email",
      "benchmark_state_id": "CO-S021",
      "control_id": "address-email",
      "control_name": "email",
      "has_value": True,
      "native_validity": _email_native_validity(),
      "error_text": None,
      "expected_candidate_ids": [],
    },
    {
      "name": "unrelated_control",
      "benchmark_state_id": "CO-S021",
      "control_id": "address-postalCode",
      "control_name": "postalCode",
      "has_value": True,
      "native_validity": _email_native_validity(format_mismatch=True),
      "error_text": "Email is required.",
      "expected_candidate_ids": [],
    },
    {
      "name": "seeded_final",
      "benchmark_state_id": "CO-S021",
      "control_id": "address-email",
      "control_name": "email",
      "has_value": True,
      "native_validity": _email_native_validity(format_mismatch=True),
      "error_text": "Email is required.",
      "expected_candidate_ids": ["cand_seeded_final"],
    },
  )

  for scenario in scenarios:
    run_dir = _write_error_message_recovery_run(
      tmp_path / str(scenario["name"]),
      benchmark_state_id=str(scenario["benchmark_state_id"]),
      control_id=str(scenario["control_id"]),
      control_name=str(scenario["control_name"]),
      has_value=bool(scenario["has_value"]),
      native_validity=dict(scenario["native_validity"]),
      error_text=scenario["error_text"],
    )
    result = score_seeded_experiment(
      SeededScorerOptions(
        run_dir=run_dir,
        config_id="checkout-co-sem-135",
        registry_path=registry_path,
        score_run_id=f"score_{scenario['name']}",
      ),
      generated_at=datetime(2026, 10, 28, tzinfo=timezone.utc),
    )
    seed_result = result.summary["results"][0]
    assert sorted({
      candidate["candidate_id"]
      for candidate in seed_result["matched_candidates"]
    }) == scenario["expected_candidate_ids"]


def test_co_sem_119_recovery_requires_cart_title_in_address_state(tmp_path):
  scenarios = (
    (
      "clean_address",
      "CO-S003",
      "/checkout/address",
      "Shipping address | Brightlane Checkout",
      0,
    ),
    (
      "source_cart",
      "CO-S002",
      "/cart",
      "Cart | Brightlane Checkout",
      0,
    ),
    (
      "related_wrong_address",
      "CO-S003",
      "/checkout/address",
      "Billing address | Brightlane Checkout",
      0,
    ),
    (
      "seeded_address",
      "CO-S003",
      "/checkout/address",
      "Cart | Brightlane Checkout",
      1,
    ),
  )
  registry_path = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "registry"
    / "benchmark-case-registry.json"
  )

  for name, benchmark_state_id, route, title, expected_recovered in scenarios:
    run_dir = _write_page_title_run(
      tmp_path / name,
      benchmark_state_id=benchmark_state_id,
      route=route,
      title=title,
    )
    result = score_seeded_experiment(
      SeededScorerOptions(
        run_dir=run_dir,
        config_id="checkout-co-sem-119",
        registry_path=registry_path,
        score_run_id=f"score_{name}",
      ),
      generated_at=datetime(2026, 10, 27, tzinfo=timezone.utc),
    )

    assert result.summary["counts"]["recovered_seeds"] == expected_recovered
    matched_ids = [
      candidate["candidate_id"]
      for candidate in result.summary["results"][0]["matched_candidates"]
    ]
    assert matched_ids == ([f"cand_{name}"] if expected_recovered else [])


def test_destination_expectations_match_same_observed_destination(tmp_path):
  result = _score_destination_candidates(
    tmp_path,
    candidates=[
      _destination_candidate(
        "cand_place_order",
        selector="button#place-order",
        accessible_name="Place order",
        destination_route="/cart",
        destination_heading="Cart",
      )
    ],
    destination_route="/cart",
    destination_heading="Cart",
    score_run_id="destination_match",
  )

  _assert_destination_candidate_ids(result, ["cand_place_order"])


def test_destination_expectations_reject_wrong_route(tmp_path):
  result = _score_destination_candidates(
    tmp_path,
    candidates=[
      _destination_candidate(
        "cand_place_order",
        selector="button#place-order",
        accessible_name="Place order",
        destination_route="/checkout/payment",
        destination_heading="Cart",
      )
    ],
    destination_route="/cart",
    destination_heading="Cart",
    score_run_id="destination_wrong_route",
  )

  _assert_destination_candidate_ids(result, [])


def test_destination_expectations_reject_missing_destination(tmp_path):
  result = _score_destination_candidates(
    tmp_path,
    candidates=[
      _destination_candidate(
        "cand_place_order",
        selector="button#place-order",
        accessible_name="Place order",
      )
    ],
    destination_route="/cart",
    destination_heading="Cart",
    score_run_id="destination_missing",
  )

  _assert_destination_candidate_ids(result, [])


def test_destination_expectations_remain_conjunctive_with_source_identity(tmp_path):
  result = _score_destination_candidates(
    tmp_path,
    candidates=[
      _destination_candidate(
        "cand_cancel_order",
        selector="button#cancel-order",
        accessible_name="Cancel order",
        destination_route="/cart",
        destination_heading="Cart",
      )
    ],
    destination_route="/cart",
    destination_heading="Cart",
    score_run_id="destination_wrong_source",
  )

  _assert_destination_candidate_ids(result, [])


def test_destination_expectations_require_all_constraints_on_same_destination(tmp_path):
  result = _score_destination_candidates(
    tmp_path,
    candidates=[
      _destination_candidate(
        "cand_place_order",
        selector="button#place-order",
        accessible_name="Place order",
        destination_route="/cart",
        destination_heading="Payment",
      )
    ],
    destination_route="/cart",
    destination_heading="Cart",
    score_run_id="destination_wrong_heading",
  )

  _assert_destination_candidate_ids(result, [])


def test_destination_constraints_do_not_match_across_different_destinations(tmp_path):
  result = _score_destination_candidates(
    tmp_path,
    candidates=[
      _destination_candidate(
        "cand_place_order",
        selector="button#place-order",
        accessible_name="Place order",
        destination_route="/cart",
        destination_heading="Payment",
        additional_destinations=[("/checkout/payment", "Cart")],
      )
    ],
    destination_route="/cart",
    destination_heading="Cart",
    score_run_id="destination_split_constraints",
  )

  _assert_destination_candidate_ids(result, [])


def test_destination_recovery_is_candidate_order_independent(tmp_path):
  result = _score_destination_candidates(
    tmp_path,
    candidates=[
      _destination_candidate(
        "cand_wrong_destination",
        selector="button#place-order",
        accessible_name="Place order",
        destination_route="/checkout/payment",
        destination_heading="Payment",
      ),
      _destination_candidate(
        "cand_expected_destination",
        selector="button#place-order",
        accessible_name="Place order",
        destination_route="/cart",
        destination_heading="Cart",
      ),
    ],
    destination_route="/cart",
    destination_heading="Cart",
    score_run_id="destination_candidate_order",
  )

  _assert_destination_candidate_ids(result, ["cand_expected_destination"])


def test_destination_heading_matches_saved_result_context(tmp_path):
  result = _score_destination_candidates(
    tmp_path,
    candidates=[
      _destination_candidate(
        "cand_place_order",
        selector="button#place-order",
        accessible_name="Place order",
        destination_route="/cart",
        destination_heading="Cart",
        result_headings=["Cart", "Shipping information"],
      )
    ],
    destination_route=None,
    destination_heading="Shipping information",
    score_run_id="destination_result_heading",
  )

  _assert_destination_candidate_ids(result, ["cand_place_order"])


def test_destination_context_is_optional_without_destination_expectations(tmp_path):
  result = _score_destination_candidates(
    tmp_path,
    candidates=[
      _destination_candidate(
        "cand_place_order",
        selector="button#place-order",
        accessible_name="Place order",
      )
    ],
    destination_route=None,
    destination_heading=None,
    score_run_id="destination_optional",
  )

  _assert_destination_candidate_ids(result, ["cand_place_order"])


def test_destination_elements_match_structured_result_state(tmp_path):
  expected_elements = [
    {
      "bucket": "visual_cues",
      "accessible_name": "Object A controls",
      "text": "- 1 +",
    },
    {
      "bucket": "visual_cues",
      "accessible_name": "Object B controls",
      "text": "- 2 +",
    },
  ]
  result = _score_destination_candidates(
    tmp_path,
    candidates=[
      _destination_candidate(
        "cand_place_order",
        selector="button#place-order",
        accessible_name="Place order",
        destination_route="/cart",
        destination_heading="Cart",
        destination_elements=expected_elements,
      )
    ],
    destination_route="/cart",
    destination_heading="Cart",
    destination_elements=expected_elements,
    score_run_id="destination_elements_match",
  )

  _assert_destination_candidate_ids(result, ["cand_place_order"])


def test_destination_elements_reject_swapped_result_values(tmp_path):
  result = _score_destination_candidates(
    tmp_path,
    candidates=[
      _destination_candidate(
        "cand_place_order",
        selector="button#place-order",
        accessible_name="Place order",
        destination_route="/cart",
        destination_heading="Cart",
        destination_elements=[
          {
            "bucket": "visual_cues",
            "accessible_name": "Object A controls",
            "text": "- 2 +",
          },
          {
            "bucket": "visual_cues",
            "accessible_name": "Object B controls",
            "text": "- 1 +",
          },
        ],
      )
    ],
    destination_route="/cart",
    destination_heading="Cart",
    destination_elements=[
      {
        "bucket": "visual_cues",
        "accessible_name": "Object A controls",
        "text": "- 1 +",
      },
      {
        "bucket": "visual_cues",
        "accessible_name": "Object B controls",
        "text": "- 2 +",
      },
    ],
    score_run_id="destination_elements_swapped",
  )

  _assert_destination_candidate_ids(result, [])


def test_destination_element_fields_must_match_same_observed_element(tmp_path):
  result = _score_destination_candidates(
    tmp_path,
    candidates=[
      _destination_candidate(
        "cand_place_order",
        selector="button#place-order",
        accessible_name="Place order",
        destination_route="/cart",
        destination_elements=[
          {
            "bucket": "visual_cues",
            "accessible_name": "Object A controls",
            "text": "- 2 +",
          },
          {
            "bucket": "visual_cues",
            "accessible_name": "Object B controls",
            "text": "- 1 +",
          },
        ],
      )
    ],
    destination_route="/cart",
    destination_heading=None,
    destination_elements=[
      {
        "bucket": "visual_cues",
        "accessible_name": "Object A controls",
        "text": "- 1 +",
      }
    ],
    score_run_id="destination_element_field_conjunction",
  )

  _assert_destination_candidate_ids(result, [])


def test_destination_elements_require_every_expected_element(tmp_path):
  result = _score_destination_candidates(
    tmp_path,
    candidates=[
      _destination_candidate(
        "cand_place_order",
        selector="button#place-order",
        accessible_name="Place order",
        destination_route="/cart",
        destination_elements=[
          {
            "bucket": "visual_cues",
            "accessible_name": "Object A controls",
            "text": "- 1 +",
          }
        ],
      )
    ],
    destination_route="/cart",
    destination_heading=None,
    destination_elements=[
      {
        "bucket": "visual_cues",
        "accessible_name": "Object A controls",
        "text": "- 1 +",
      },
      {
        "bucket": "visual_cues",
        "accessible_name": "Object B controls",
        "text": "- 2 +",
      },
    ],
    score_run_id="destination_elements_all_required",
  )

  _assert_destination_candidate_ids(result, [])


def test_destination_elements_do_not_match_across_destinations(tmp_path):
  result = _score_destination_candidates(
    tmp_path,
    candidates=[
      _destination_candidate(
        "cand_place_order",
        selector="button#place-order",
        accessible_name="Place order",
        destination_route="/cart",
        destination_heading="Cart",
        destination_elements=[
          {
            "bucket": "visual_cues",
            "accessible_name": "Object A controls",
            "text": "- 1 +",
          }
        ],
        additional_destinations=[("/other", "Other")],
        additional_destination_elements=[
          [
            {
              "bucket": "visual_cues",
              "accessible_name": "Object B controls",
              "text": "- 2 +",
            }
          ]
        ],
      )
    ],
    destination_route="/cart",
    destination_heading="Cart",
    destination_elements=[
      {
        "bucket": "visual_cues",
        "accessible_name": "Object A controls",
        "text": "- 1 +",
      },
      {
        "bucket": "visual_cues",
        "accessible_name": "Object B controls",
        "text": "- 2 +",
      },
    ],
    score_run_id="destination_elements_split_destinations",
  )

  _assert_destination_candidate_ids(result, [])


def test_destination_elements_fail_closed_without_structured_context(tmp_path):
  result = _score_destination_candidates(
    tmp_path,
    candidates=[
      _destination_candidate(
        "cand_place_order",
        selector="button#place-order",
        accessible_name="Place order",
        destination_route="/cart",
        destination_heading="Cart",
      )
    ],
    destination_route="/cart",
    destination_heading="Cart",
    destination_elements=[
      {
        "bucket": "visual_cues",
        "accessible_name": "Object A controls",
        "text": "- 1 +",
      }
    ],
    score_run_id="destination_elements_missing_context",
  )

  _assert_destination_candidate_ids(result, [])


def test_scores_seeded_case_with_paired_evidence_targets(tmp_path):
  run_dir = _write_form_label_run(tmp_path)
  registry_path = _write_paired_form_label_registry(tmp_path)
  _write_candidate_records(
    run_dir,
    [
      {
        "candidate_id": "cand_card_number",
        "candidate_type": "form-label-mismatch",
        "state_id": "state_0000",
        "state_context": {"url": "https://example.test/checkout/payment"},
        "evidence": {
          "primary": {
            "form_control": {
              "selector": '[data-testid="payment-card-number"]',
              "id": "payment-cardNumber",
              "name": "cardNumber",
              "label": "Security codeRequired",
              "autocomplete": "cc-number",
            }
          }
        },
      },
      {
        "candidate_id": "cand_security_code",
        "candidate_type": "form-label-mismatch",
        "state_id": "state_0000",
        "state_context": {"url": "https://example.test/checkout/payment"},
        "evidence": {
          "primary": {
            "form_control": {
              "selector": '[data-testid="payment-security-code"]',
              "id": "payment-securityCode",
              "name": "securityCode",
              "label": "Card numberRequired",
              "autocomplete": "cc-csc",
            }
          }
        },
      },
    ],
  )

  result = score_seeded_experiment(
    SeededScorerOptions(
      run_dir=run_dir,
      config_id="checkout-co-sem-086",
      registry_path=registry_path,
      score_run_id="score_paired",
    ),
    generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
  )

  assert result.summary["counts"]["expected_seeds"] == 1
  assert result.summary["counts"]["recovered_seeds"] == 1
  seed_result = result.summary["results"][0]
  assert seed_result["status"] == "recovered_to_candidate"
  assert {
    candidate["candidate_id"]
    for candidate in seed_result["matched_candidates"]
  } == {"cand_card_number", "cand_security_code"}


def test_paired_evidence_requires_card_number_target(tmp_path):
  result = _score_paired_form_label_candidates(
    tmp_path,
    [_form_label_candidate("cand_security_code", "payment-security-code")],
    score_run_id="score_paired_missing_card_number",
  )

  assert result.summary["counts"]["expected_seeds"] == 1
  assert result.summary["counts"]["recovered_seeds"] == 0
  seed_result = result.summary["results"][0]
  assert seed_result["status"] == "candidate_missing"
  assert seed_result["candidate_status"] == "candidate_missing"
  assert {
    candidate["candidate_id"]
    for candidate in seed_result["matched_candidates"]
  } == {"cand_security_code"}


def test_paired_evidence_requires_security_code_target(tmp_path):
  result = _score_paired_form_label_candidates(
    tmp_path,
    [_form_label_candidate("cand_card_number", "payment-card-number")],
    score_run_id="score_paired_missing_security_code",
  )

  assert result.summary["counts"]["expected_seeds"] == 1
  assert result.summary["counts"]["recovered_seeds"] == 0
  seed_result = result.summary["results"][0]
  assert seed_result["status"] == "candidate_missing"
  assert seed_result["candidate_status"] == "candidate_missing"
  assert {
    candidate["candidate_id"]
    for candidate in seed_result["matched_candidates"]
  } == {"cand_card_number"}


def test_paired_evidence_recovery_is_clause_order_independent(tmp_path):
  run_dir = _write_form_label_run(tmp_path)
  registry_path = _write_paired_form_label_registry(
    tmp_path,
    reverse_all_of=True,
  )
  _write_candidate_records(
    run_dir,
    [
      _form_label_candidate("cand_security_code", "payment-security-code"),
      _form_label_candidate("cand_card_number", "payment-card-number"),
    ],
  )

  result = score_seeded_experiment(
    SeededScorerOptions(
      run_dir=run_dir,
      config_id="checkout-co-sem-086",
      registry_path=registry_path,
      score_run_id="score_paired_reversed",
    ),
    generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
  )

  assert result.summary["counts"]["recovered_seeds"] == 1
  seed_result = result.summary["results"][0]
  assert seed_result["status"] == "recovered_to_candidate"
  assert {
    candidate["candidate_id"]
    for candidate in seed_result["matched_candidates"]
  } == {"cand_card_number", "cand_security_code"}


def test_reciprocal_image_alt_swap_requires_both_mismatched_images(tmp_path):
  scenarios = {
    "clean": (
      "Desk lamp with adjustable brass shade",
      "Three notebooks with blue, teal, and coral covers",
      0,
    ),
    "desk_only": (
      "Three notebooks with blue, teal, and coral covers",
      "Three notebooks with blue, teal, and coral covers",
      0,
    ),
    "notebook_only": (
      "Desk lamp with adjustable brass shade",
      "Desk lamp with adjustable brass shade",
      0,
    ),
    "reciprocal_swap": (
      "Three notebooks with blue, teal, and coral covers",
      "Desk lamp with adjustable brass shade",
      1,
    ),
  }

  for name, (desk_alt, notebook_alt, expected_recovered) in scenarios.items():
    scenario_dir = tmp_path / name
    scenario_dir.mkdir()
    result = _score_reciprocal_image_alt_swap(
      scenario_dir,
      desk_alt=desk_alt,
      notebook_alt=notebook_alt,
      score_run_id=f"score_{name}",
    )

    assert result.summary["counts"]["expected_seeds"] == 1
    assert result.summary["counts"]["recovered_seeds"] == expected_recovered
    seed_result = result.summary["results"][0]
    if expected_recovered:
      assert seed_result["status"] == "recovered_to_candidate"
      assert {
        candidate["candidate_id"]
        for candidate in seed_result["matched_candidates"]
      } == {"cand_desk", "cand_notebook"}
    else:
      assert seed_result["status"] == "evidence_missing"


def test_cardholder_visible_label_recovery_distinguishes_semantic_controls(tmp_path):
  scenarios = {
    "clean_cardholder": {
      "target_label": "Cardholder nameRequired",
      "target_accessible_name": "Cardholder nameRequired",
      "target_aria_label": None,
      "candidate_test_id": "payment-cardholder",
      "expected_status": "evidence_missing",
    },
    "genuine_card_number": {
      "target_label": "Card numberRequired",
      "target_accessible_name": "Card numberRequired",
      "target_aria_label": None,
      "candidate_test_id": "payment-card-number",
      "expected_status": "candidate_missing",
    },
    "co_sem_110": {
      "target_label": "Cardholder nameRequired",
      "target_accessible_name": "Card number",
      "target_aria_label": "Card number",
      "candidate_test_id": "payment-cardholder",
      "expected_status": "evidence_missing",
    },
    "co_sem_111": {
      "target_label": "Card numberRequired",
      "target_accessible_name": "Card numberRequired",
      "target_aria_label": None,
      "candidate_test_id": "payment-cardholder",
      "expected_status": "recovered_to_candidate",
    },
  }
  registry_path = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "registry"
    / "benchmark-case-registry.json"
  )

  for scenario, values in scenarios.items():
    run_dir = _write_cardholder_label_run(
      tmp_path / scenario,
      target_label=values["target_label"],
      target_accessible_name=values["target_accessible_name"],
      target_aria_label=values["target_aria_label"],
      candidate_test_id=values["candidate_test_id"],
    )
    result = score_seeded_experiment(
      SeededScorerOptions(
        run_dir=run_dir,
        config_id="checkout-co-sem-111",
        registry_path=registry_path,
        score_run_id=f"score_{scenario}",
      ),
      generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
    )

    expected_recovered = int(values["expected_status"] == "recovered_to_candidate")
    assert result.summary["counts"]["expected_seeds"] == 1
    assert result.summary["counts"]["recovered_seeds"] == expected_recovered
    seed_result = result.summary["results"][0]
    assert seed_result["status"] == values["expected_status"]
    if expected_recovered:
      assert [
        candidate["candidate_id"]
        for candidate in seed_result["matched_candidates"]
      ] == ["cand_payment_cardholder"]


def test_country_label_recovery_distinguishes_country_from_state_semantics(tmp_path):
  scenarios = {
    "clean_country": {
      "country_label": "Country/regionRequired",
      "country_text_segments": ["Country/region", "Required"],
      "candidate_control": "country",
      "include_unrelated_state_text": False,
      "expected_status": "candidate_missing",
    },
    "real_state": {
      "country_label": "Country/regionRequired",
      "country_text_segments": ["Country/region", "Required"],
      "candidate_control": "state",
      "include_unrelated_state_text": False,
      "expected_status": "candidate_missing",
    },
    "synthetic_filled_state": {
      "country_label": "Country/regionRequired",
      "country_text_segments": ["Country/region", "Required"],
      "candidate_control": "state",
      "state_has_value": True,
      "include_unrelated_state_text": False,
      "expected_status": "candidate_missing",
    },
    "unrelated_state_text": {
      "country_label": "Country/regionRequired",
      "country_text_segments": ["Country/region", "Required"],
      "candidate_control": "country",
      "include_unrelated_state_text": True,
      "expected_status": "candidate_missing",
    },
    "country_united_states_label": {
      "country_label": "United StatesRequired",
      "country_text_segments": ["United States", "Required"],
      "candidate_control": "country",
      "include_unrelated_state_text": False,
      "expected_status": "candidate_missing",
    },
    "country_state_province_label": {
      "country_label": "State/ProvinceRequired",
      "country_text_segments": ["State/Province", "Required"],
      "candidate_control": "country",
      "include_unrelated_state_text": False,
      "expected_status": "candidate_missing",
    },
    "country_statement_label": {
      "country_label": "StatementRequired",
      "country_text_segments": ["Statement", "Required"],
      "candidate_control": "country",
      "include_unrelated_state_text": False,
      "expected_status": "candidate_missing",
    },
    "country_country_state_label": {
      "country_label": "Country StateRequired",
      "country_text_segments": ["Country State", "Required"],
      "candidate_control": "country",
      "include_unrelated_state_text": False,
      "expected_status": "candidate_missing",
    },
    "seeded_country_accessible_name_variant": {
      "country_label": "StateRequired",
      "country_accessible_name": "State/ProvinceRequired",
      "country_text_segments": ["State", "Required"],
      "candidate_control": "country",
      "include_unrelated_state_text": False,
      "expected_status": "recovered_to_candidate",
    },
    "seeded_country_compact": {
      "country_label": "StateRequired",
      "country_text_segments": ["State", "Required"],
      "candidate_control": "country",
      "include_unrelated_state_text": False,
      "expected_status": "recovered_to_candidate",
    },
    "seeded_country_spaced": {
      "country_label": "State Required",
      "country_text_segments": ["State", "Required"],
      "candidate_control": "country",
      "include_unrelated_state_text": False,
      "expected_status": "recovered_to_candidate",
    },
    "seeded_country_uppercase_marker": {
      "country_label": "State REQUIRED",
      "country_text_segments": ["State", "Required"],
      "candidate_control": "country",
      "include_unrelated_state_text": False,
      "expected_status": "recovered_to_candidate",
    },
  }
  registry_path = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "registry"
    / "benchmark-case-registry.json"
  )

  for scenario, values in scenarios.items():
    run_dir = _write_country_label_run(
      tmp_path / scenario,
      country_label=values["country_label"],
      country_accessible_name=values.get("country_accessible_name"),
      country_text_segments=values["country_text_segments"],
      candidate_control=values["candidate_control"],
      state_has_value=values.get("state_has_value", False),
      include_unrelated_state_text=values["include_unrelated_state_text"],
    )
    result = score_seeded_experiment(
      SeededScorerOptions(
        run_dir=run_dir,
        config_id="checkout-co-sem-107",
        registry_path=registry_path,
        score_run_id=f"score_{scenario}",
      ),
      generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
    )

    expected_recovered = int(values["expected_status"] == "recovered_to_candidate")
    assert result.summary["counts"]["expected_seeds"] == 1
    assert result.summary["counts"]["recovered_seeds"] == expected_recovered
    seed_result = result.summary["results"][0]
    assert seed_result["status"] == values["expected_status"]
    if expected_recovered:
      assert [
        candidate["candidate_id"]
        for candidate in seed_result["matched_candidates"]
      ] == ["cand_country"]


def test_delivery_instructions_label_recovery_rejects_related_form_controls(tmp_path):
  scenarios = {
    "clean_empty": {
      "delivery_label": "Delivery instructions",
      "delivery_has_value": False,
      "candidate_control": "deliveryInstructions",
      "expected_status": "evidence_missing",
    },
    "clean_filled": {
      "delivery_label": "Delivery instructions",
      "delivery_has_value": True,
      "candidate_control": "deliveryInstructions",
      "expected_status": "evidence_missing",
    },
    "genuine_street_address": {
      "delivery_label": "Delivery instructions",
      "delivery_has_value": False,
      "candidate_control": "streetAddress",
      "expected_status": "evidence_missing",
    },
    "co_sem_107_country_as_state": {
      "delivery_label": "Delivery instructions",
      "delivery_has_value": False,
      "candidate_control": "country",
      "expected_status": "evidence_missing",
    },
    "co_sem_109_city_as_state": {
      "delivery_label": "Delivery instructions",
      "delivery_has_value": False,
      "candidate_control": "city",
      "expected_status": "evidence_missing",
    },
    "co_sem_087_email_as_full_name": {
      "delivery_label": "Delivery instructions",
      "delivery_has_value": False,
      "candidate_control": "email",
      "expected_status": "evidence_missing",
    },
    "seeded_empty": {
      "delivery_label": "Street address",
      "delivery_has_value": False,
      "candidate_control": "deliveryInstructions",
      "expected_status": "recovered_to_candidate",
    },
  }
  registry_path = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "registry"
    / "benchmark-case-registry.json"
  )

  for scenario, values in scenarios.items():
    run_dir = _write_delivery_instructions_label_run(
      tmp_path / scenario,
      delivery_label=values["delivery_label"],
      delivery_has_value=values["delivery_has_value"],
      candidate_control=values["candidate_control"],
    )
    result = score_seeded_experiment(
      SeededScorerOptions(
        run_dir=run_dir,
        config_id="checkout-co-sem-108",
        registry_path=registry_path,
        score_run_id=f"score_{scenario}",
      ),
      generated_at=datetime(2026, 10, 30, tzinfo=timezone.utc),
    )

    expected_recovered = int(values["expected_status"] == "recovered_to_candidate")
    assert result.summary["counts"]["expected_seeds"] == 1
    assert result.summary["counts"]["recovered_seeds"] == expected_recovered
    seed_result = result.summary["results"][0]
    assert seed_result["status"] == values["expected_status"]
    if expected_recovered:
      assert [
        candidate["candidate_id"]
        for candidate in seed_result["matched_candidates"]
      ] == ["cand_deliveryInstructions"]


def test_country_autocomplete_recovery_distinguishes_country_from_state_semantics(
  tmp_path,
):
  scenarios = {
    "clean_country": {
      "country_autocomplete": "country-name",
      "country_text_segments": ["Country/region", "Required"],
      "candidate_control": "country",
      "expected_status": "evidence_missing",
    },
    "real_state": {
      "country_autocomplete": "address-level1",
      "country_text_segments": ["Country/region", "Required"],
      "candidate_control": "state",
      "expected_status": "candidate_missing",
    },
    "synthetic_filled_state": {
      "country_autocomplete": "address-level1",
      "country_text_segments": ["Country/region", "Required"],
      "candidate_control": "state",
      "state_has_value": True,
      "expected_status": "candidate_missing",
    },
    "other_address_level1_field": {
      "country_autocomplete": "address-level1",
      "country_text_segments": ["Country/region", "Required"],
      "candidate_control": "city",
      "expected_status": "candidate_missing",
    },
    "country_label_only": {
      "country_autocomplete": "address-level1",
      "country_text_segments": ["Country", "Required"],
      "candidate_control": "country",
      "expected_status": "candidate_missing",
    },
    "region_label_only": {
      "country_autocomplete": "address-level1",
      "country_text_segments": ["Region", "Required"],
      "candidate_control": "country",
      "expected_status": "candidate_missing",
    },
    "country_region_without_slash": {
      "country_autocomplete": "address-level1",
      "country_text_segments": ["Country region", "Required"],
      "candidate_control": "country",
      "expected_status": "candidate_missing",
    },
    "country_region_code": {
      "country_autocomplete": "address-level1",
      "country_text_segments": ["Country/region code", "Required"],
      "candidate_control": "country",
      "expected_status": "candidate_missing",
    },
    "seeded_country": {
      "country_autocomplete": "address-level1",
      "country_text_segments": ["Country/region", "Required"],
      "candidate_control": "country",
      "expected_status": "recovered_to_candidate",
    },
  }
  registry_path = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "registry"
    / "benchmark-case-registry.json"
  )

  for scenario, values in scenarios.items():
    run_dir = _write_country_autocomplete_run(
      tmp_path / scenario,
      country_autocomplete=values["country_autocomplete"],
      country_text_segments=values["country_text_segments"],
      candidate_control=values["candidate_control"],
      state_has_value=values.get("state_has_value", False),
    )
    result = score_seeded_experiment(
      SeededScorerOptions(
        run_dir=run_dir,
        config_id="checkout-co-sem-126",
        registry_path=registry_path,
        score_run_id=f"score_{scenario}",
      ),
      generated_at=datetime(2026, 10, 29, tzinfo=timezone.utc),
    )

    expected_recovered = int(
      values["expected_status"] == "recovered_to_candidate"
    )
    assert result.summary["counts"]["expected_seeds"] == 1
    assert result.summary["counts"]["recovered_seeds"] == expected_recovered
    seed_result = result.summary["results"][0]
    assert seed_result["status"] == values["expected_status"]
    if expected_recovered:
      assert [
        candidate["candidate_id"]
        for candidate in seed_result["matched_candidates"]
      ] == ["cand_country"]


def test_widget_tab_swap_recovery_rejects_clean_labels(tmp_path):
  result = _score_widget_tab_swap(
    tmp_path,
    desk_label="Desk accessories",
    office_label="Office supplies",
    score_run_id="score_widget_swap_clean",
  )

  assert result.summary["counts"]["recovered_seeds"] == 0
  assert result.summary["results"][0]["status"] == "evidence_missing"


def test_widget_tab_swap_recovery_rejects_one_sided_swap(tmp_path):
  result = _score_widget_tab_swap(
    tmp_path,
    desk_label="Office supplies",
    office_label="Office supplies",
    score_run_id="score_widget_swap_partial",
  )

  assert result.summary["counts"]["recovered_seeds"] == 0
  seed_result = result.summary["results"][0]
  assert seed_result["status"] == "evidence_missing"
  assert seed_result["evidence_status"] == "evidence_missing"


def test_widget_tab_swap_recovery_requires_both_reciprocal_labels(tmp_path):
  result = _score_widget_tab_swap(
    tmp_path,
    desk_label="Office supplies",
    office_label="Desk accessories",
    score_run_id="score_widget_swap_full",
  )

  assert result.summary["counts"]["recovered_seeds"] == 1
  seed_result = result.summary["results"][0]
  assert seed_result["status"] == "recovered_to_candidate"
  assert {
    candidate["candidate_id"]
    for candidate in seed_result["matched_candidates"]
  } == {"cand_desk_tab", "cand_office_tab"}


def test_widget_tablist_name_recovery_rejects_clean_group_name(tmp_path):
  result = _score_widget_tablist_name(
    tmp_path,
    tablist_name="Product categories",
    include_tablist_candidate=True,
    score_run_id="score_widget_tablist_clean",
  )

  assert result.summary["counts"]["recovered_seeds"] == 0
  assert result.summary["results"][0]["status"] == "evidence_missing"


def test_widget_tablist_name_recovery_rejects_individual_tab_candidates(tmp_path):
  result = _score_widget_tablist_name(
    tmp_path,
    tablist_name="Payment methods",
    include_tablist_candidate=False,
    score_run_id="score_widget_tablist_children_only",
  )

  assert result.summary["counts"]["recovered_seeds"] == 0
  seed_result = result.summary["results"][0]
  assert seed_result["evidence_status"] == "evidence_found"
  assert seed_result["status"] == "candidate_missing"


def test_widget_tablist_name_recovery_matches_only_seeded_group(tmp_path):
  result = _score_widget_tablist_name(
    tmp_path,
    tablist_name="Payment methods",
    include_tablist_candidate=True,
    score_run_id="score_widget_tablist_seeded",
  )

  assert result.summary["counts"]["recovered_seeds"] == 1
  seed_result = result.summary["results"][0]
  assert seed_result["status"] == "recovered_to_candidate"
  assert [
    candidate["candidate_id"]
    for candidate in seed_result["matched_candidates"]
  ] == ["cand_product_category_tablist"]


def test_paired_evidence_ignores_extra_unrelated_candidates(tmp_path):
  result = _score_paired_form_label_candidates(
    tmp_path,
    [
      _form_label_candidate("cand_expiry", "payment-expiry"),
      _form_label_candidate("cand_card_number", "payment-card-number"),
      _form_label_candidate("cand_security_code", "payment-security-code"),
    ],
    score_run_id="score_paired_extra_candidate",
  )

  assert result.summary["counts"]["expected_seeds"] == 1
  assert result.summary["counts"]["recovered_seeds"] == 1
  seed_result = result.summary["results"][0]
  assert seed_result["status"] == "recovered_to_candidate"
  assert {
    candidate["candidate_id"]
    for candidate in seed_result["matched_candidates"]
  } == {"cand_card_number", "cand_security_code"}


def test_table_data_cell_expected_evidence_recovers_matching_cell(tmp_path):
  result = _score_table_header_candidates(
    tmp_path,
    _review_table_cells(_co_sem_074_line_total_cell()),
    score_run_id="score_table_cell_match",
  )

  assert result.summary["counts"]["expected_seeds"] == 1
  assert result.summary["counts"]["recovered_seeds"] == 1
  seed_result = result.summary["results"][0]
  assert seed_result["status"] == "recovered_to_candidate"
  assert seed_result["matched_candidates"][0]["candidate_id"] == "cand_table"


def test_table_data_cell_expected_evidence_rejects_baseline_line_total(tmp_path):
  result = _score_table_header_candidates(
    tmp_path,
    _review_table_cells(_baseline_line_total_cell()),
    score_run_id="score_table_cell_baseline",
  )

  assert result.summary["counts"]["recovered_seeds"] == 0
  seed_result = result.summary["results"][0]
  assert seed_result["status"] == "evidence_missing"
  assert seed_result["matched_candidates"] == []


def test_table_data_cell_expected_evidence_rejects_future_075_collision(tmp_path):
  result = _score_table_header_candidates(
    tmp_path,
    [
      _quantity_cell(
        header_ids=[
          "review-item-header-prod-desk-lamp",
          "review-line-total-header",
        ]
      ),
      _baseline_line_total_cell(),
    ],
    score_run_id="score_table_cell_future_075",
  )

  assert result.summary["counts"]["recovered_seeds"] == 0
  seed_result = result.summary["results"][0]
  assert seed_result["status"] == "evidence_missing"
  assert seed_result["matched_candidates"] == []


def test_table_data_cell_expected_evidence_rejects_wrong_cell_same_table(tmp_path):
  result = _score_table_header_candidates(
    tmp_path,
    [
      _quantity_cell(
        header_ids=[
          "review-item-header-prod-desk-lamp",
          "review-quantity-header",
        ]
      ),
      _baseline_line_total_cell(),
    ],
    score_run_id="score_table_cell_wrong_cell",
  )

  assert result.summary["counts"]["recovered_seeds"] == 0
  seed_result = result.summary["results"][0]
  assert seed_result["status"] == "evidence_missing"
  assert seed_result["matched_candidates"] == []


def test_table_data_cell_expected_evidence_requires_resolved_headers(tmp_path):
  unresolved_line_total = {
    **_co_sem_074_line_total_cell(),
    "headers_all_resolved": False,
  }
  result = _score_table_header_candidates(
    tmp_path,
    _review_table_cells(unresolved_line_total),
    score_run_id="score_table_cell_unresolved",
  )

  assert result.summary["counts"]["recovered_seeds"] == 0
  seed_result = result.summary["results"][0]
  assert seed_result["status"] == "evidence_missing"
  assert seed_result["matched_candidates"] == []


def test_table_data_cell_header_id_order_is_not_semantic(tmp_path):
  reversed_header_ids = {
    **_co_sem_074_line_total_cell(),
    "header_ids": [
      "review-quantity-header",
      "review-item-header-prod-desk-lamp",
    ],
  }
  result = _score_table_header_candidates(
    tmp_path,
    _review_table_cells(reversed_header_ids),
    score_run_id="score_table_cell_header_order",
  )

  assert result.summary["counts"]["recovered_seeds"] == 1
  seed_result = result.summary["results"][0]
  assert seed_result["status"] == "recovered_to_candidate"


def test_paired_table_header_evidence_recovers_reciprocal_swap(tmp_path):
  result = _score_paired_table_header_candidates(
    tmp_path,
    _two_item_review_table_cells(
      desk_line_total_headers=[
        "review-item-header-prod-notebook-set",
        "review-line-total-header",
      ],
      notebook_line_total_headers=[
        "review-item-header-prod-desk-lamp",
        "review-line-total-header",
      ],
    ),
    score_run_id="score_paired_table_swap",
  )

  assert result.summary["counts"]["expected_seeds"] == 1
  assert result.summary["counts"]["recovered_seeds"] == 1
  seed_result = result.summary["results"][0]
  assert seed_result["status"] == "recovered_to_candidate"
  assert [
    candidate["candidate_id"]
    for candidate in seed_result["matched_candidates"]
  ] == ["cand_table"]


def test_paired_table_header_evidence_rejects_clean_baseline(tmp_path):
  result = _score_paired_table_header_candidates(
    tmp_path,
    _two_item_review_table_cells(
      desk_line_total_headers=[
        "review-item-header-prod-desk-lamp",
        "review-line-total-header",
      ],
      notebook_line_total_headers=[
        "review-item-header-prod-notebook-set",
        "review-line-total-header",
      ],
    ),
    score_run_id="score_paired_table_clean",
  )

  assert result.summary["counts"]["recovered_seeds"] == 0
  seed_result = result.summary["results"][0]
  assert seed_result["status"] == "evidence_missing"
  assert seed_result["matched_candidates"] == []


def test_paired_table_header_evidence_rejects_single_wrong_association(tmp_path):
  result = _score_paired_table_header_candidates(
    tmp_path,
    _two_item_review_table_cells(
      desk_line_total_headers=[
        "review-item-header-prod-notebook-set",
        "review-line-total-header",
      ],
      notebook_line_total_headers=[
        "review-item-header-prod-notebook-set",
        "review-line-total-header",
      ],
    ),
    score_run_id="score_paired_table_single_wrong",
  )

  assert result.summary["counts"]["recovered_seeds"] == 0
  seed_result = result.summary["results"][0]
  assert seed_result["status"] == "evidence_missing"
  assert seed_result["matched_candidates"] == []


def test_aria_state_expected_state_attributes_recover_supported_fields(tmp_path):
  cases = [
    ("aria_selected", "false"),
    ("aria_expanded", "true"),
    ("aria_checked", "true"),
    ("aria_pressed", "false"),
    ("aria_current", "page"),
  ]
  for field, value in cases:
    result = _score_aria_state_candidates(
      tmp_path,
      evidence_state_attributes={field: value},
      expected_state_attributes={field: value},
      candidates=[_aria_state_candidate(f"cand_{field}", {field: value})],
      score_run_id=f"score_{field}",
    )

    _assert_aria_state_candidate_ids(result, [f"cand_{field}"])


def test_aria_state_expected_state_attributes_reject_wrong_values(tmp_path):
  cases = [
    ("aria_selected", "false", "true"),
    ("aria_expanded", "true", "false"),
    ("aria_checked", "true", "false"),
    ("aria_pressed", "false", "true"),
    ("aria_current", "page", "step"),
  ]
  for field, expected_value, actual_value in cases:
    result = _score_aria_state_candidates(
      tmp_path,
      evidence_state_attributes={field: expected_value},
      expected_state_attributes={field: expected_value},
      candidates=[_aria_state_candidate(f"cand_wrong_{field}", {field: actual_value})],
      score_run_id=f"score_wrong_{field}",
    )

    _assert_aria_state_candidate_ids(result, [])


def test_aria_state_expected_state_attributes_are_optional(tmp_path):
  result = _score_aria_state_candidates(
    tmp_path,
    evidence_state_attributes={"aria_selected": "false"},
    expected_state_attributes=None,
    candidates=[_aria_state_candidate("cand_tab", {"aria_selected": "true"})],
    score_run_id="score_aria_state_optional",
  )

  _assert_aria_state_candidate_ids(result, ["cand_tab"])


def test_aria_state_expected_state_attributes_match_multiple_fields_on_same_candidate(tmp_path):
  result = _score_aria_state_candidates(
    tmp_path,
    evidence_state_attributes={"aria_selected": "false", "aria_expanded": "true"},
    expected_state_attributes={"aria_selected": "false", "aria_expanded": "true"},
    candidates=[
      _aria_state_candidate("cand_partial", {"aria_selected": "false"}),
      _aria_state_candidate("cand_complete", {"aria_selected": "false", "aria_expanded": "true"}),
    ],
    score_run_id="score_aria_state_multiple_fields",
  )

  _assert_aria_state_candidate_ids(result, ["cand_complete"])


def test_aria_state_expected_state_attributes_do_not_match_across_peer_candidates(tmp_path):
  result = _score_aria_state_candidates(
    tmp_path,
    evidence_state_attributes={"aria_selected": "false", "aria_expanded": "true"},
    expected_state_attributes={"aria_selected": "false", "aria_expanded": "true"},
    candidates=[
      _aria_state_candidate("cand_selected", {"aria_selected": "false"}),
      _aria_state_candidate("cand_expanded", {"aria_expanded": "true"}),
    ],
    score_run_id="score_aria_state_split_candidates",
  )

  _assert_aria_state_candidate_ids(result, [])


def test_aria_state_peer_recovery_requires_declared_state_absence(tmp_path):
  expected_peer_state = {
    "selector_hint": '[data-testid="peer-tab"]',
    "attributes": {"tag": "button", "text": "Peer tab"},
    "absent_state_attributes": ["aria_current"],
  }
  result = _score_aria_state_candidates(
    tmp_path,
    evidence_state_attributes={"aria_current": "step"},
    expected_state_attributes={"aria_current": "step"},
    expected_peer_state=expected_peer_state,
    candidates=[
      _aria_state_candidate(
        "cand_duplicate_current",
        {"aria_current": "step"},
        peer_items=[
          _aria_state_peer_evidence({"aria_current": "step"}),
        ],
      ),
      _aria_state_candidate(
        "cand_atomic_mapping",
        {"aria_current": "step"},
        peer_items=[_aria_state_peer_evidence({})],
      ),
    ],
    score_run_id="score_aria_state_peer_absence",
  )

  _assert_aria_state_candidate_ids(result, ["cand_atomic_mapping"])


def test_aria_state_peer_recovery_matches_generic_peer_state_context(tmp_path):
  expected_peer_state = _expected_pressed_peer_state()
  result = _score_aria_state_candidates(
    tmp_path,
    evidence_state_attributes={"aria_pressed": "true"},
    expected_state_attributes={"aria_pressed": "true"},
    expected_peer_state=expected_peer_state,
    candidates=[
      _aria_state_candidate(
        "cand_pressed_mapping",
        {"aria_pressed": "true"},
        peer_state_items=[
          _aria_state_peer_evidence({"aria_pressed": "false"}),
        ],
      ),
    ],
    score_run_id="score_aria_state_generic_pressed_peer",
  )

  _assert_aria_state_candidate_ids(result, ["cand_pressed_mapping"])


def test_aria_state_peer_recovery_rejects_wrong_generic_peer_state(tmp_path):
  result = _score_aria_state_candidates(
    tmp_path,
    evidence_state_attributes={"aria_pressed": "true"},
    expected_state_attributes={"aria_pressed": "true"},
    expected_peer_state=_expected_pressed_peer_state(),
    candidates=[
      _aria_state_candidate(
        "cand_wrong_pressed_peer",
        {"aria_pressed": "true"},
        peer_state_items=[
          _aria_state_peer_evidence({"aria_pressed": "true"}),
        ],
      ),
    ],
    score_run_id="score_aria_state_wrong_pressed_peer",
  )

  _assert_aria_state_candidate_ids(result, [])


def test_aria_state_peer_recovery_rejects_missing_generic_peer(tmp_path):
  result = _score_aria_state_candidates(
    tmp_path,
    evidence_state_attributes={"aria_pressed": "true"},
    expected_state_attributes={"aria_pressed": "true"},
    expected_peer_state=_expected_pressed_peer_state(),
    candidates=[
      _aria_state_candidate(
        "cand_missing_pressed_peer",
        {"aria_pressed": "true"},
        peer_state_items=[],
      ),
    ],
    score_run_id="score_aria_state_missing_pressed_peer",
  )

  _assert_aria_state_candidate_ids(result, [])


def test_aria_state_peer_recovery_rejects_wrong_primary_with_matching_peer(tmp_path):
  result = _score_aria_state_candidates(
    tmp_path,
    evidence_state_attributes={"aria_pressed": "true"},
    expected_state_attributes={"aria_pressed": "true"},
    expected_peer_state=_expected_pressed_peer_state(),
    candidates=[
      _aria_state_candidate(
        "cand_wrong_pressed_primary",
        {"aria_pressed": "false"},
        peer_state_items=[
          _aria_state_peer_evidence({"aria_pressed": "false"}),
        ],
      ),
    ],
    score_run_id="score_aria_state_wrong_pressed_primary",
  )

  _assert_aria_state_candidate_ids(result, [])


def test_aria_state_generic_peer_context_is_nonconstraining_without_expectation(tmp_path):
  result = _score_aria_state_candidates(
    tmp_path,
    evidence_state_attributes={"aria_pressed": "true"},
    expected_state_attributes={"aria_pressed": "true"},
    candidates=[
      _aria_state_candidate(
        "cand_pressed_without_peer_expectation",
        {"aria_pressed": "true"},
        peer_state_items=[
          _aria_state_peer_evidence({"aria_pressed": "true"}),
        ],
      ),
    ],
    score_run_id="score_aria_state_pressed_without_peer_expectation",
  )

  _assert_aria_state_candidate_ids(result, ["cand_pressed_without_peer_expectation"])


def test_aria_state_peer_lookup_deduplicates_overlapping_contexts(tmp_path):
  peer = _aria_state_peer_evidence({})
  candidate = _aria_state_candidate(
    "cand_overlapping_peer_context",
    {"aria_current": "step"},
    peer_items=[peer],
    peer_state_items=[peer],
  )

  assert _aria_state_peer_items(candidate) == [peer]

  result = _score_aria_state_candidates(
    tmp_path,
    evidence_state_attributes={"aria_current": "step"},
    expected_state_attributes={"aria_current": "step"},
    expected_peer_state={
      "selector_hint": '[data-testid="peer-tab"]',
      "attributes": {"tag": "button", "text": "Peer tab"},
      "absent_state_attributes": ["aria_current"],
    },
    candidates=[candidate],
    score_run_id="score_aria_state_overlapping_peer_context",
  )

  _assert_aria_state_candidate_ids(result, ["cand_overlapping_peer_context"])


def test_co_sem_130_recovery_requires_spanish_result_and_stale_pressed_pair(tmp_path):
  registry_path = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "registry"
    / "benchmark-case-registry.json"
  )
  controls = (
    ("clean_spanish", "CO-S007", "es", "false", "true", 0),
    ("co_sem_129_initial", "CO-S001", "en", "false", "true", 0),
    ("seeded_spanish", "CO-S007", "es", "true", "false", 1),
  )

  for run_name, benchmark_state_id, language, english_pressed, spanish_pressed, expected in controls:
    run_dir = _write_co_sem_130_language_run(
      tmp_path,
      run_name=run_name,
      benchmark_state_id=benchmark_state_id,
      language=language,
      english_pressed=english_pressed,
      spanish_pressed=spanish_pressed,
    )
    result = score_seeded_experiment(
      SeededScorerOptions(
        run_dir=run_dir,
        config_id="checkout-co-sem-130",
        registry_path=registry_path,
        score_run_id=f"score_{run_name}",
      ),
      generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
    )

    assert result.summary["counts"]["recovered_seeds"] == expected
    seed_result = result.summary["results"][0]
    if expected:
      assert seed_result["status"] == "recovered_to_candidate"
      assert [
        candidate["candidate_id"]
        for candidate in seed_result["matched_candidates"]
      ] == [f"cand_{run_name}_english"]
    else:
      assert seed_result["status"] in {"state_not_acquired", "evidence_missing"}


def test_co_sem_137_recovery_requires_final_english_with_stale_spanish_root(tmp_path):
  registry_path = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "registry"
    / "benchmark-case-registry.json"
  )
  english_body = "Products Browse featured products Language English Spanish"
  spanish_body = "Productos Explora productos destacados Idioma InglÃ©s EspaÃ±ol"
  controls = (
    ("initial_english", "CO-S001", "en", "Products | Brightlane Checkout", english_body, 0),
    (
      "spanish_intermediate",
      "CO-S007",
      "es",
      "Productos | Brightlane Checkout",
      spanish_body,
      0,
    ),
    ("clean_final_english", "CO-S020", "en", "Products | Brightlane Checkout", english_body, 0),
    (
      "co_sem_015_cross",
      "CO-S020",
      "en",
      "Productos | Brightlane Checkout",
      spanish_body,
      0,
    ),
    (
      "co_sem_130_cross",
      "CO-S007",
      "es",
      "Productos | Brightlane Checkout",
      spanish_body,
      0,
    ),
    ("seeded_final_english", "CO-S020", "es", "Products | Brightlane Checkout", english_body, 1),
  )

  for run_name, benchmark_state_id, language, title, body_text, expected in controls:
    run_dir = _write_co_sem_137_language_run(
      tmp_path,
      run_name=run_name,
      benchmark_state_id=benchmark_state_id,
      language=language,
      title=title,
      body_text_sample=body_text,
    )
    result = score_seeded_experiment(
      SeededScorerOptions(
        run_dir=run_dir,
        config_id="checkout-co-sem-137",
        registry_path=registry_path,
        score_run_id=f"score_{run_name}",
      ),
      generated_at=datetime(2026, 10, 27, tzinfo=timezone.utc),
    )

    assert result.summary["counts"]["recovered_seeds"] == expected
    seed_result = result.summary["results"][0]
    if expected:
      assert seed_result["status"] == "recovered_to_candidate"
      assert [
        candidate["candidate_id"]
        for candidate in seed_result["matched_candidates"]
      ] == [f"cand_{run_name}"]
    else:
      assert seed_result["status"] in {"state_not_acquired", "evidence_missing"}


def test_score_seeded_experiment_script_runs(tmp_path, capsys):
  run_dir = _write_run(tmp_path)
  registry_path = _write_registry(tmp_path)
  _write_candidate_records(
    run_dir,
    [
      {
        "candidate_id": "cand_button",
        "candidate_type": "button-label-mismatch",
        "state_id": "state_0000",
        "state_context": {"url": "https://example.test/checkout/review"},
        "evidence": {"primary": {"button": {"selector": "button#place-order"}}},
      }
    ],
  )

  exit_code = scorer_script_main(
    [
      "--run-dir",
      str(run_dir),
      "--config-id",
      "checkout-pilot",
      "--registry",
      str(registry_path),
      "--score-run-id",
      "script_score",
    ]
  )

  assert exit_code == 0
  assert "Seeded experiment scoring complete" in capsys.readouterr().out


def _assert_aria_state_candidate_ids(result, expected_candidate_ids: list[str]) -> None:
  assert result.summary["counts"]["expected_seeds"] == 1
  assert result.summary["counts"]["recovered_seeds"] == (1 if expected_candidate_ids else 0)
  seed_result = result.summary["results"][0]
  expected_status = "recovered_to_candidate" if expected_candidate_ids else "candidate_missing"
  assert seed_result["status"] == expected_status
  assert [
    candidate["candidate_id"]
    for candidate in seed_result["matched_candidates"]
  ] == expected_candidate_ids


def _score_aria_state_candidates(
  tmp_path: Path,
  *,
  evidence_state_attributes: dict[str, object],
  expected_state_attributes: dict[str, object] | None,
  expected_peer_state: dict[str, object] | None = None,
  candidates: list[dict[str, object]],
  score_run_id: str,
):
  run_dir = _write_aria_state_run(
    tmp_path,
    evidence_state_attributes=evidence_state_attributes,
    run_name=score_run_id,
  )
  registry_path = _write_aria_state_registry(
    tmp_path,
    expected_state_attributes=expected_state_attributes,
    expected_peer_state=expected_peer_state,
    registry_name=score_run_id,
  )
  _write_candidate_records(run_dir, candidates)

  return score_seeded_experiment(
    SeededScorerOptions(
      run_dir=run_dir,
      config_id="checkout-co-sem-aria-state",
      registry_path=registry_path,
      score_run_id=score_run_id,
    ),
    generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
  )


def _write_aria_state_registry(
  tmp_path: Path,
  *,
  expected_state_attributes: dict[str, object] | None,
  expected_peer_state: dict[str, object] | None,
  registry_name: str,
) -> Path:
  expected_evidence = {
    "bucket": "buttons",
    "selector_hint": '[data-testid="sample-tab"]',
    "primary_evidence_key": "aria_state",
    "attributes": {
      "tag": "button",
      "role": "tab",
      "text": "Sample tab",
      "accessible_name": "Sample tab",
    },
  }
  if expected_state_attributes is not None:
    expected_evidence["state_attributes"] = expected_state_attributes
  if expected_peer_state is not None:
    expected_evidence["peer_state"] = expected_peer_state
  registry_path = tmp_path / f"{registry_name}-registry.json"
  registry_path.write_text(
    json.dumps(
      {
        "schema_version": "1",
        "variants": [
          {
            "variant_id": "co-sem-aria-state",
            "app": "checkout-flow",
            "candidate_type": "aria-state-mismatch",
            "expected_human_judgment": "violation",
            "expected_state": {
              "routes": ["/products"],
              "benchmark_state_ids": ["CO-S001"],
            },
            "expected_candidate": {"type": "aria-state-mismatch"},
            "expected_evidence": expected_evidence,
          }
        ],
        "seeded_configurations": [
          {
            "configuration_id": "checkout-co-sem-aria-state",
            "app": "checkout-flow",
            "seed_ids": ["co-sem-aria-state"],
          }
        ],
      }
    ),
    encoding="utf-8",
  )
  return registry_path


def _write_aria_state_run(
  tmp_path: Path,
  *,
  evidence_state_attributes: dict[str, object],
  run_name: str,
) -> Path:
  run_dir = tmp_path / f"{run_name}-run"
  state_dir = run_dir / "states" / "state_0000"
  state_dir.mkdir(parents=True)
  button = _aria_state_button_evidence(evidence_state_attributes)
  payload = {
    "schema_version": "1",
    "state_id": "state_0000",
    "state_context": {"route": "/products"},
    "page": {"url": "https://example.test/products", "title": "Products"},
    "buttons": [button],
  }
  state_dir.joinpath("accessibility_context.json").write_text(json.dumps(payload), encoding="utf-8")
  state_dir.joinpath("metadata.json").write_text(
    json.dumps(
      {
        "state_id": "state_0000",
        "url": "https://example.test/products",
        "route": "/products",
        "title": "Products",
        "focused_acquisition": {"benchmark_state_id": "CO-S001", "focused_state_name": "products"},
      }
    ),
    encoding="utf-8",
  )
  run_dir.joinpath("graph.json").write_text(json.dumps({"states": ["state_0000"]}), encoding="utf-8")
  run_dir.joinpath("transitions.json").write_text("[]", encoding="utf-8")
  return run_dir


def _score_table_header_candidates(
  tmp_path: Path,
  data_cells: list[dict[str, object]],
  *,
  score_run_id: str,
):
  run_dir = _write_table_header_run(tmp_path, data_cells)
  registry_path = _write_table_header_registry(tmp_path)
  _write_candidate_records(
    run_dir,
    [_table_header_candidate("cand_table", data_cells)],
  )

  return score_seeded_experiment(
    SeededScorerOptions(
      run_dir=run_dir,
      config_id="checkout-co-sem-074",
      registry_path=registry_path,
      score_run_id=score_run_id,
    ),
    generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
  )


def _score_paired_table_header_candidates(
  tmp_path: Path,
  data_cells: list[dict[str, object]],
  *,
  score_run_id: str,
):
  run_dir = _write_table_header_run(tmp_path, data_cells)
  registry_path = _write_paired_table_header_registry(tmp_path)
  _write_candidate_records(
    run_dir,
    [_table_header_candidate("cand_table", data_cells)],
  )

  return score_seeded_experiment(
    SeededScorerOptions(
      run_dir=run_dir,
      config_id="checkout-co-sem-132",
      registry_path=registry_path,
      score_run_id=score_run_id,
    ),
    generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
  )


def _write_table_header_registry(tmp_path: Path) -> Path:
  registry_path = tmp_path / "table-header-registry.json"
  registry_path.write_text(
    json.dumps(
      {
        "schema_version": "1",
        "variants": [
          {
            "variant_id": "co-sem-074",
            "app": "checkout-flow",
            "candidate_type": "table-header-association-mismatch",
            "expected_human_judgment": "violation",
            "expected_state": {
              "routes": ["/checkout/review"],
              "benchmark_state_ids": ["CO-S005"],
            },
            "expected_candidate": {
              "type": "table-header-association-mismatch",
            },
            "expected_evidence": {
              "bucket": "tables",
              "selector_hint": "table:nth-of-type(1)",
              "primary_evidence_key": "table",
              "attributes": {
                "caption": "Product quantities and totals",
                "header_count": 4,
                "data_cell_count": 2,
              },
              "data_cell": {
                "text": "$32.00",
                "header_ids": [
                  "review-item-header-prod-desk-lamp",
                  "review-quantity-header",
                ],
                "headers_all_resolved": True,
                "row_index": 1,
                "column_index": 2,
              },
            },
          }
        ],
        "seeded_configurations": [
          {
            "configuration_id": "checkout-co-sem-074",
            "app": "checkout-flow",
            "seed_ids": ["co-sem-074"],
          }
        ],
      }
    ),
    encoding="utf-8",
  )
  return registry_path


def _write_paired_table_header_registry(tmp_path: Path) -> Path:
  registry_path = tmp_path / "paired-table-header-registry.json"
  common_evidence = {
    "bucket": "tables",
    "selector_hint": "table:nth-of-type(1)",
    "primary_evidence_key": "table",
    "attributes": {
      "caption": "Product quantities and totals",
      "header_count": 5,
      "data_cell_count": 4,
    },
  }
  registry_path.write_text(
    json.dumps(
      {
        "schema_version": "1",
        "variants": [
          {
            "variant_id": "co-sem-132",
            "app": "checkout-flow",
            "candidate_type": "table-header-association-mismatch",
            "expected_human_judgment": "violation",
            "expected_state": {
              "routes": ["/checkout/review"],
              "benchmark_state_ids": ["CO-S005"],
            },
            "expected_candidate": {
              "type": "table-header-association-mismatch",
            },
            "expected_evidence": {
              "bucket": "tables",
              "selector_hint": "table:nth-of-type(1)",
              "all_of": [
                {
                  **common_evidence,
                  "data_cell": {
                    "text": "$32.00",
                    "header_ids": [
                      "review-item-header-prod-notebook-set",
                      "review-line-total-header",
                    ],
                    "headers_all_resolved": True,
                    "row_index": 1,
                    "column_index": 2,
                  },
                },
                {
                  **common_evidence,
                  "data_cell": {
                    "text": "$18.00",
                    "header_ids": [
                      "review-item-header-prod-desk-lamp",
                      "review-line-total-header",
                    ],
                    "headers_all_resolved": True,
                    "row_index": 2,
                    "column_index": 2,
                  },
                },
              ],
            },
          }
        ],
        "seeded_configurations": [
          {
            "configuration_id": "checkout-co-sem-132",
            "app": "checkout-flow",
            "seed_ids": ["co-sem-132"],
          }
        ],
      }
    ),
    encoding="utf-8",
  )
  return registry_path


def _write_table_header_run(
  tmp_path: Path,
  data_cells: list[dict[str, object]],
) -> Path:
  run_dir = tmp_path / "table-header-run"
  state_dir = run_dir / "states" / "state_0000"
  state_dir.mkdir(parents=True)
  payload = {
    "schema_version": "1",
    "state_id": "state_0000",
    "state_context": {"route": "/checkout/review"},
    "page": {"url": "https://example.test/checkout/review", "title": "Review"},
    "tables": [
      _review_table_evidence(data_cells),
    ],
  }
  state_dir.joinpath("accessibility_context.json").write_text(
    json.dumps(payload),
    encoding="utf-8",
  )
  state_dir.joinpath("metadata.json").write_text(
    json.dumps(
      {
        "state_id": "state_0000",
        "url": "https://example.test/checkout/review",
        "route": "/checkout/review",
        "title": "Review",
        "focused_acquisition": {
          "benchmark_state_id": "CO-S005",
          "focused_state_name": "review",
        },
      }
    ),
    encoding="utf-8",
  )
  run_dir.joinpath("graph.json").write_text(json.dumps({"states": ["state_0000"]}), encoding="utf-8")
  run_dir.joinpath("transitions.json").write_text("[]", encoding="utf-8")
  return run_dir


def _table_header_candidate(
  candidate_id: str,
  data_cells: list[dict[str, object]],
) -> dict[str, object]:
  table = _review_table_evidence(data_cells)
  return {
    "candidate_id": candidate_id,
    "candidate_type": "table-header-association-mismatch",
    "state_id": "state_0000",
    "state_context": {
      "url": "https://example.test/checkout/review",
      "title": "Review",
    },
    "evidence": {
      "primary": {
        "table": {
          "element_id": table["element_id"],
          "tag": table["tag"],
          "role": table["role"],
          "selector": table["selector"],
          "accessible_name": table["accessible_name"],
          "caption": table["caption"],
          "header_count": table["header_count"],
          "data_cell_count": table["data_cell_count"],
          "associated_data_cell_count": len(data_cells),
        }
      },
      "supporting": {
        "table_header_association_context_v1": {
          "schema_version": "table_header_association_context_v1",
          "table": {
            "element_id": table["element_id"],
            "tag": table["tag"],
            "role": table["role"],
            "selector": table["selector"],
            "accessible_name": table["accessible_name"],
            "caption": table["caption"],
            "header_count": table["header_count"],
            "data_cell_count": table["data_cell_count"],
            "associated_data_cell_count": len(data_cells),
          },
          "headers": table["headers"],
          "associated_data_cells": [
            _candidate_context_cell(cell)
            for cell in data_cells
          ],
          "relationship_summary": {
            "uses_headers_attribute": True,
            "all_included_associations_resolved": True,
          },
        }
      },
    },
  }


def _aria_state_candidate(
  candidate_id: str,
  state_attributes: dict[str, object],
  *,
  peer_items: list[dict[str, object]] | None = None,
  peer_state_items: list[dict[str, object]] | None = None,
) -> dict[str, object]:
  candidate = {
    "candidate_id": candidate_id,
    "candidate_type": "aria-state-mismatch",
    "state_id": "state_0000",
    "state_context": {
      "url": "https://example.test/products",
      "route": "/products",
    },
    "evidence": {
      "primary": {
        "aria_state": {
          **_aria_state_button_evidence({}),
          "bucket": "buttons",
          "aria_label": "",
          "href": "",
          "state_attributes": state_attributes,
        }
      }
    },
  }
  aria_state_context = {}
  if peer_items is not None:
    aria_state_context["current_item_context"] = {"peer_items": peer_items}
  if peer_state_items is not None:
    aria_state_context["peer_state_context"] = peer_state_items
  if aria_state_context:
    candidate["evidence"]["supporting"] = {
      "aria_state_context_v1": aria_state_context,
    }
  return candidate


def _write_co_sem_130_language_run(
  tmp_path: Path,
  *,
  run_name: str,
  benchmark_state_id: str,
  language: str,
  english_pressed: str,
  spanish_pressed: str,
) -> Path:
  run_dir = tmp_path / run_name
  state_dir = run_dir / "states" / "state_0000"
  state_dir.mkdir(parents=True)
  is_spanish = language == "es"
  english_label = "Inglés" if is_spanish else "English"
  spanish_label = "Español" if is_spanish else "Spanish"
  title = (
    "Productos | Brightlane Checkout"
    if is_spanish
    else "Products | Brightlane Checkout"
  )
  english = _language_state_button(
    element_id="e_language_en",
    selector="button#products-language-en",
    label=english_label,
    aria_pressed=english_pressed,
  )
  spanish = _language_state_button(
    element_id="e_language_es",
    selector="button#products-language-es",
    label=spanish_label,
    aria_pressed=spanish_pressed,
  )

  state_dir.joinpath("accessibility_context.json").write_text(
    json.dumps(
      {
        "schema_version": "1",
        "state_id": "state_0000",
        "state_context": {"route": "/products"},
        "page": {
          "url": "https://example.test/products",
          "title": title,
          "document_lang": language,
          "html_lang": language,
          "body_text_sample": (
            "Productos Explora productos destacados Idioma Inglés Español"
            if is_spanish
            else "Products Browse featured products Language English Spanish"
          ),
        },
        "buttons": [english, spanish],
      },
      ensure_ascii=False,
    ),
    encoding="utf-8",
  )
  state_dir.joinpath("metadata.json").write_text(
    json.dumps(
      {
        "state_id": "state_0000",
        "url": "https://example.test/products",
        "route": "/products",
        "title": title,
        "focused_acquisition": {
          "benchmark_state_id": benchmark_state_id,
          "focused_state_name": (
            "products_spanish" if is_spanish else "products"
          ),
        },
      },
      ensure_ascii=False,
    ),
    encoding="utf-8",
  )
  run_dir.joinpath("graph.json").write_text(
    json.dumps({"states": ["state_0000"]}),
    encoding="utf-8",
  )
  run_dir.joinpath("transitions.json").write_text("[]", encoding="utf-8")
  _write_candidate_records(
    run_dir,
    [
      {
        "candidate_id": f"cand_{run_name}_english",
        "candidate_type": "aria-state-mismatch",
        "state_id": "state_0000",
        "state_context": {
          "url": "https://example.test/products",
          "route": "/products",
        },
        "evidence": {
          "primary": {
            "aria_state": {
              **english,
              "state_attributes": {"aria_pressed": english_pressed},
            }
          },
          "supporting": {
            "page": {
              "url": "https://example.test/products",
              "title": title,
              "document_lang": language,
              "html_lang": language,
            },
            "aria_state_context_v1": {
              "declared_state": {"aria_pressed": english_pressed},
              "peer_state_context": [
                {
                  **spanish,
                  "state_attributes": {"aria_pressed": spanish_pressed},
                }
              ],
            },
          },
        },
      }
    ],
  )
  return run_dir


def _write_co_sem_137_language_run(
  tmp_path: Path,
  *,
  run_name: str,
  benchmark_state_id: str,
  language: str,
  title: str,
  body_text_sample: str,
) -> Path:
  run_dir = tmp_path / run_name
  state_dir = run_dir / "states" / "state_0000"
  state_dir.mkdir(parents=True)
  page_evidence = {
    "url": "https://example.test/products",
    "title": title,
    "document_lang": language,
    "html_lang": language,
    "body_text_sample": body_text_sample,
  }
  state_dir.joinpath("accessibility_context.json").write_text(
    json.dumps(
      {
        "schema_version": "1",
        "state_id": "state_0000",
        "state_context": {"route": "/products"},
        "page": page_evidence,
      },
      ensure_ascii=False,
    ),
    encoding="utf-8",
  )
  state_dir.joinpath("metadata.json").write_text(
    json.dumps(
      {
        "state_id": "state_0000",
        "url": "https://example.test/products",
        "route": "/products",
        "title": title,
        "focused_acquisition": {
          "benchmark_state_id": benchmark_state_id,
          "focused_state_name": run_name,
        },
      },
      ensure_ascii=False,
    ),
    encoding="utf-8",
  )
  run_dir.joinpath("graph.json").write_text(
    json.dumps({"states": ["state_0000"]}),
    encoding="utf-8",
  )
  run_dir.joinpath("transitions.json").write_text("[]", encoding="utf-8")
  _write_candidate_records(
    run_dir,
    [
      {
        "candidate_id": f"cand_{run_name}",
        "candidate_type": "lang-mismatch",
        "state_id": "state_0000",
        "state_context": {
          "url": "https://example.test/products",
          "route": "/products",
        },
        "evidence": {
          "primary": {"page": page_evidence},
          "supporting": {"body_text_sample": body_text_sample},
        },
      }
    ],
  )
  return run_dir


def _language_state_button(
  *,
  element_id: str,
  selector: str,
  label: str,
  aria_pressed: str,
) -> dict[str, object]:
  return {
    "bucket": "buttons",
    "element_id": element_id,
    "tag": "button",
    "role": "button",
    "selector": selector,
    "text": label,
    "accessible_name": label,
    "aria_label": "",
    "href": "",
    "aria_pressed": aria_pressed,
  }


def _expected_pressed_peer_state() -> dict[str, object]:
  return {
    "selector_hint": '[data-testid="peer-tab"]',
    "attributes": {"tag": "button", "text": "Peer tab"},
    "state_attributes": {"aria_pressed": "false"},
  }


def _aria_state_button_evidence(state_attributes: dict[str, object]) -> dict[str, object]:
  return {
    "element_id": "e_sample_tab",
    "tag": "button",
    "role": "tab",
    "selector": '[data-testid="sample-tab"]',
    "text": "Sample tab",
    "accessible_name": "Sample tab",
    **state_attributes,
  }


def _aria_state_peer_evidence(
  state_attributes: dict[str, object],
) -> dict[str, object]:
  return {
    "element_id": "e_peer_tab",
    "tag": "button",
    "role": "tab",
    "selector": '[data-testid="peer-tab"]',
    "text": "Peer tab",
    "accessible_name": "Peer tab",
    "state_attributes": state_attributes,
  }

def _candidate_context_cell(cell: dict[str, object]) -> dict[str, object]:
  return {
    key: value
    for key, value in cell.items()
    if key != "headers_all_resolved"
  }


def _review_table_evidence(data_cells: list[dict[str, object]]) -> dict[str, object]:
  has_notebook_row = any(cell.get("row_index") == 2 for cell in data_cells)
  headers = [
    _table_header("review-item-header", "Item", "col", 0, 0),
    _table_header("review-quantity-header", "Quantity", "col", 0, 1),
    _table_header("review-line-total-header", "Line total", "col", 0, 2),
    _table_header("review-item-header-prod-desk-lamp", "Desk lamp", "row", 1, 0),
  ]
  if has_notebook_row:
    headers.append(
      _table_header(
        "review-item-header-prod-notebook-set",
        "Notebook set",
        "row",
        2,
        0,
      )
    )
  return {
    "element_id": "e_table",
    "kind": "table",
    "tag": "table",
    "role": None,
    "selector": "table:nth-of-type(1)",
    "text": "Product quantities and totals Item Quantity Line total Desk lamp 1 $32.00",
    "accessible_name": "Product quantities and totals Item Quantity Line total Desk lamp 1 $32.00",
    "caption": "Product quantities and totals",
    "header_count": len(headers),
    "data_cell_count": len(data_cells),
    "headers": headers,
    "data_cells": data_cells,
  }


def _review_table_cells(line_total_cell: dict[str, object]) -> list[dict[str, object]]:
  return [
    _quantity_cell(
      header_ids=[
        "review-item-header-prod-desk-lamp",
        "review-quantity-header",
      ]
    ),
    line_total_cell,
  ]


def _two_item_review_table_cells(
  *,
  desk_line_total_headers: list[str],
  notebook_line_total_headers: list[str],
) -> list[dict[str, object]]:
  return [
    _quantity_cell(
      header_ids=[
        "review-item-header-prod-desk-lamp",
        "review-quantity-header",
      ]
    ),
    _line_total_cell(header_ids=desk_line_total_headers),
    _table_data_cell(
      text="1",
      header_ids=[
        "review-item-header-prod-notebook-set",
        "review-quantity-header",
      ],
      row_index=2,
      column_index=1,
      selector="td:nth-of-type(1)",
    ),
    _table_data_cell(
      text="$18.00",
      header_ids=notebook_line_total_headers,
      row_index=2,
      column_index=2,
      selector="td:nth-of-type(2)",
    ),
  ]


def _co_sem_074_line_total_cell() -> dict[str, object]:
  return _line_total_cell(
    header_ids=[
      "review-item-header-prod-desk-lamp",
      "review-quantity-header",
    ]
  )


def _baseline_line_total_cell() -> dict[str, object]:
  return _line_total_cell(
    header_ids=[
      "review-item-header-prod-desk-lamp",
      "review-line-total-header",
    ]
  )


def _quantity_cell(*, header_ids: list[str]) -> dict[str, object]:
  return _table_data_cell(
    text="1",
    header_ids=header_ids,
    row_index=1,
    column_index=1,
    selector="td:nth-of-type(1)",
  )


def _line_total_cell(*, header_ids: list[str]) -> dict[str, object]:
  return _table_data_cell(
    text="$32.00",
    header_ids=header_ids,
    row_index=1,
    column_index=2,
    selector="td:nth-of-type(2)",
  )


def _table_data_cell(
  *,
  text: str,
  header_ids: list[str],
  row_index: int,
  column_index: int,
  selector: str,
) -> dict[str, object]:
  return {
    "text": text,
    "header_ids": header_ids,
    "headers_all_resolved": True,
    "associated_headers": [
      _associated_header(header_id)
      for header_id in header_ids
    ],
    "row_index": row_index,
    "column_index": column_index,
    "selector": selector,
  }


def _table_header(
  header_id: str,
  text: str,
  scope: str,
  row_index: int,
  column_index: int,
) -> dict[str, object]:
  return {
    "id": header_id,
    "text": text,
    "scope": scope,
    "row_index": row_index,
    "column_index": column_index,
    "selector": f"th#{header_id}",
  }


def _associated_header(header_id: str) -> dict[str, object]:
  headers = {
    "review-item-header-prod-desk-lamp": _table_header(
      "review-item-header-prod-desk-lamp",
      "Desk lamp",
      "row",
      1,
      0,
    ),
    "review-item-header-prod-notebook-set": _table_header(
      "review-item-header-prod-notebook-set",
      "Notebook set",
      "row",
      2,
      0,
    ),
    "review-quantity-header": _table_header(
      "review-quantity-header",
      "Quantity",
      "col",
      0,
      1,
    ),
    "review-line-total-header": _table_header(
      "review-line-total-header",
      "Line total",
      "col",
      0,
      2,
    ),
  }
  return headers[header_id]


def _score_paired_form_label_candidates(
  tmp_path: Path,
  candidates: list[dict[str, object]],
  *,
  score_run_id: str,
):
  run_dir = _write_form_label_run(tmp_path)
  registry_path = _write_paired_form_label_registry(tmp_path)
  _write_candidate_records(run_dir, candidates)

  return score_seeded_experiment(
    SeededScorerOptions(
      run_dir=run_dir,
      config_id="checkout-co-sem-086",
      registry_path=registry_path,
      score_run_id=score_run_id,
    ),
    generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
  )


def _form_label_candidate(candidate_id: str, test_id: str) -> dict[str, object]:
  form_controls = {
    "payment-card-number": {
      "selector": '[data-testid="payment-card-number"]',
      "id": "payment-cardNumber",
      "name": "cardNumber",
      "label": "Security codeRequired",
      "autocomplete": "cc-number",
    },
    "payment-security-code": {
      "selector": '[data-testid="payment-security-code"]',
      "id": "payment-securityCode",
      "name": "securityCode",
      "label": "Card numberRequired",
      "autocomplete": "cc-csc",
    },
    "payment-expiry": {
      "selector": '[data-testid="payment-expiry"]',
      "id": "payment-expiry",
      "name": "expiry",
      "label": "ExpiryRequired",
      "autocomplete": "cc-exp",
    },
  }
  form_control = form_controls[test_id]
  return {
    "candidate_id": candidate_id,
    "candidate_type": "form-label-mismatch",
    "state_id": "state_0000",
    "state_context": {"url": "https://example.test/checkout/payment"},
    "evidence": {"primary": {"form_control": form_control}},
  }


def _write_paired_form_label_registry(
  tmp_path: Path,
  *,
  reverse_all_of: bool = False,
) -> Path:
  registry_path = tmp_path / "paired-registry.json"
  all_of = [
    {
      "bucket": "form_controls",
      "selector_hint": '[data-testid="payment-card-number"]',
      "control": {"id": "payment-cardNumber", "name": "cardNumber"},
      "attributes": {
        "autocomplete": "cc-number",
      },
      "attribute_contains": {"label": "Security code"},
    },
    {
      "bucket": "form_controls",
      "selector_hint": '[data-testid="payment-security-code"]',
      "control": {"id": "payment-securityCode", "name": "securityCode"},
      "attributes": {
        "autocomplete": "cc-csc",
      },
      "attribute_contains": {"label": "Card number"},
    },
  ]
  if reverse_all_of:
    all_of.reverse()
  registry_path.write_text(
    json.dumps(
      {
        "schema_version": "1",
        "variants": [
          {
            "variant_id": "co-sem-086",
            "app": "checkout-flow",
            "candidate_type": "form-label-mismatch",
            "expected_human_judgment": "violation",
            "expected_state": {
              "routes": ["/checkout/payment"],
              "benchmark_state_ids": ["CO-S004"],
            },
            "expected_candidate": {"type": "form-label-mismatch"},
            "expected_evidence": {
              "bucket": "form_controls",
              "selector_hint": '[data-testid="payment-card-number"]',
              "all_of": all_of,
            },
          }
        ],
        "seeded_configurations": [
          {
            "configuration_id": "checkout-co-sem-086",
            "app": "checkout-flow",
            "seed_ids": ["co-sem-086"],
          }
        ],
      }
    ),
    encoding="utf-8",
  )
  return registry_path


def _score_reciprocal_image_alt_swap(
  tmp_path: Path,
  *,
  desk_alt: str,
  notebook_alt: str,
  score_run_id: str,
):
  run_dir = tmp_path / "image-alt-run"
  state_dir = run_dir / "states" / "state_0000"
  state_dir.mkdir(parents=True)
  images = [
    {
      "element_id": "e_desk",
      "selector": "img#desk",
      "src": "https://example.test/assets/desk-lamp.svg",
      "alt": desk_alt,
    },
    {
      "element_id": "e_notebook",
      "selector": "img#notebook",
      "src": "https://example.test/assets/notebook-set.svg",
      "alt": notebook_alt,
    },
    {
      "element_id": "e_unrelated",
      "selector": "img#unrelated",
      "src": "https://example.test/assets/unrelated.svg",
      "alt": "Unrelated product",
    },
  ]
  state_dir.joinpath("accessibility_context.json").write_text(
    json.dumps(
      {
        "schema_version": "1",
        "state_id": "state_0000",
        "state_context": {"route": "/products"},
        "page": {
          "url": "https://example.test/products",
          "title": "Products",
        },
        "images": images,
      }
    ),
    encoding="utf-8",
  )
  state_dir.joinpath("metadata.json").write_text(
    json.dumps(
      {
        "state_id": "state_0000",
        "url": "https://example.test/products",
        "route": "/products",
        "title": "Products",
        "focused_acquisition": {
          "benchmark_state_id": "CO-S001",
          "focused_state_name": "products",
        },
      }
    ),
    encoding="utf-8",
  )
  run_dir.joinpath("graph.json").write_text(
    json.dumps({"states": ["state_0000"]}),
    encoding="utf-8",
  )
  run_dir.joinpath("transitions.json").write_text("[]", encoding="utf-8")
  _write_candidate_records(
    run_dir,
    [
      _image_alt_candidate("cand_desk", images[0]),
      _image_alt_candidate("cand_notebook", images[1]),
      _image_alt_candidate("cand_unrelated", images[2]),
    ],
  )

  registry_path = tmp_path / "image-alt-registry.json"
  registry_path.write_text(
    json.dumps(
      {
        "schema_version": "1",
        "variants": [
          {
            "variant_id": "co-sem-097",
            "app": "checkout-flow",
            "candidate_type": "image-alt-not-descriptive",
            "expected_human_judgment": "violation",
            "expected_state": {
              "routes": ["/products"],
              "benchmark_state_ids": ["CO-S001"],
            },
            "expected_candidate": {"type": "image-alt-not-descriptive"},
            "expected_evidence": {
              "all_of": [
                {
                  "bucket": "images",
                  "attributes": {
                    "alt": "Three notebooks with blue, teal, and coral covers"
                  },
                  "attribute_contains": {"src": "/desk-lamp.svg"},
                },
                {
                  "bucket": "images",
                  "attributes": {
                    "alt": "Desk lamp with adjustable brass shade"
                  },
                  "attribute_contains": {"src": "/notebook-set.svg"},
                },
              ]
            },
          }
        ],
        "seeded_configurations": [
          {
            "configuration_id": "checkout-co-sem-097",
            "app": "checkout-flow",
            "seed_ids": ["co-sem-097"],
          }
        ],
      }
    ),
    encoding="utf-8",
  )

  return score_seeded_experiment(
    SeededScorerOptions(
      run_dir=run_dir,
      config_id="checkout-co-sem-097",
      registry_path=registry_path,
      score_run_id=score_run_id,
    ),
    generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
  )


def _image_alt_candidate(
  candidate_id: str,
  image: dict[str, object],
) -> dict[str, object]:
  return {
    "candidate_id": candidate_id,
    "candidate_type": "image-alt-not-descriptive",
    "state_id": "state_0000",
    "state_context": {"url": "https://example.test/products"},
    "evidence": {"primary": {"image": image}},
  }


def _write_registry(tmp_path: Path) -> Path:
  registry_path = tmp_path / "registry.json"
  registry_path.write_text(
    json.dumps(
      {
        "schema_version": "1",
        "variants": [
          {
            "variant_id": "co-sem-001",
            "app": "checkout-flow",
            "candidate_type": "button-label-mismatch",
            "expected_human_judgment": "violation",
            "expected_state": {"routes": ["/checkout/review"], "benchmark_state_ids": ["CO-S004"]},
            "expected_candidate": {"type": "button-label-mismatch"},
            "expected_evidence": {
              "bucket": "buttons",
              "selector_hint": "button#place-order",
              "attributes": {"accessible_name": "Place order"},
            },
          }
        ],
        "seeded_configurations": [
          {"configuration_id": "checkout-pilot", "app": "checkout-flow", "seed_ids": ["co-sem-001"]}
        ],
      }
    ),
    encoding="utf-8",
  )
  return registry_path


def _write_cardholder_label_run(
  tmp_path: Path,
  *,
  target_label: str,
  target_accessible_name: str,
  target_aria_label: str | None,
  candidate_test_id: str,
) -> Path:
  run_dir = tmp_path / "cardholder-label-run"
  state_dir = run_dir / "states" / "state_0000"
  state_dir.mkdir(parents=True)
  form_controls = {
    "payment-cardholder": {
      "element_id": "e_cardholder",
      "selector": '[data-testid="payment-cardholder"]',
      "id": "payment-cardholder",
      "name": "cardholder",
      "label": target_label,
      "accessible_name": target_accessible_name,
      "aria_label": target_aria_label,
      "type": "text",
      "autocomplete": "cc-name",
      "required": True,
    },
    "payment-card-number": {
      "element_id": "e_card_number",
      "selector": '[data-testid="payment-card-number"]',
      "id": "payment-cardNumber",
      "name": "cardNumber",
      "label": "Card numberRequired",
      "accessible_name": "Card numberRequired",
      "aria_label": None,
      "type": "text",
      "autocomplete": "cc-number",
      "required": True,
    },
  }
  state_dir.joinpath("accessibility_context.json").write_text(
    json.dumps(
      {
        "schema_version": "1",
        "state_id": "state_0000",
        "state_context": {"route": "/checkout/payment"},
        "page": {
          "url": "https://example.test/checkout/payment",
          "title": "Payment | Brightlane Checkout",
        },
        "form_controls": list(form_controls.values()),
      }
    ),
    encoding="utf-8",
  )
  state_dir.joinpath("metadata.json").write_text(
    json.dumps(
      {
        "state_id": "state_0000",
        "url": "https://example.test/checkout/payment",
        "route": "/checkout/payment",
        "title": "Payment | Brightlane Checkout",
        "focused_acquisition": {
          "benchmark_state_id": "CO-S004",
          "focused_state_name": "payment",
        },
      }
    ),
    encoding="utf-8",
  )
  run_dir.joinpath("graph.json").write_text(
    json.dumps({"states": ["state_0000"]}),
    encoding="utf-8",
  )
  run_dir.joinpath("transitions.json").write_text("[]", encoding="utf-8")
  _write_candidate_records(
    run_dir,
    [
      {
        "candidate_id": f"cand_{candidate_test_id.replace('-', '_')}",
        "candidate_type": "form-label-mismatch",
        "state_id": "state_0000",
        "state_context": {
          "url": "https://example.test/checkout/payment",
          "route": "/checkout/payment",
        },
        "evidence": {
          "primary": {
            "form_control": form_controls[candidate_test_id],
          }
        },
      }
    ],
  )
  return run_dir


def _write_country_label_run(
  tmp_path: Path,
  *,
  country_label: str,
  country_accessible_name: str | None,
  country_text_segments: list[str],
  candidate_control: str,
  state_has_value: bool,
  include_unrelated_state_text: bool,
) -> Path:
  run_dir = tmp_path / "country-label-run"
  state_dir = run_dir / "states" / "state_0000"
  state_dir.mkdir(parents=True)
  controls = {
    "country": {
      "element_id": "e_country",
      "tag": "select",
      "selector": "select#address-country",
      "id": "address-country",
      "name": "country",
      "label": country_label,
      "accessible_name": country_accessible_name or country_label,
      "autocomplete": "country-name",
      "required": True,
      "has_value": True,
    },
    "state": {
      "element_id": "e_state",
      "tag": "input",
      "selector": "input#address-state",
      "id": "address-state",
      "name": "state",
      "label": "StateRequired",
      "accessible_name": "StateRequired",
      "type": "text",
      "autocomplete": "address-level1",
      "required": True,
      "has_value": state_has_value,
    },
  }
  text_segments = {
    "country": country_text_segments,
    "state": ["State", "Required"],
  }
  payload = {
    "schema_version": "1",
    "state_id": "state_0000",
    "state_context": {"route": "/checkout/address"},
    "page": {
      "url": "https://example.test/checkout/address",
      "title": "Shipping address | Brightlane Checkout",
    },
    "form_controls": list(controls.values()),
  }
  if include_unrelated_state_text:
    payload["referenced_elements"] = [
      {
        "element_id": "e_unrelated_state_text",
        "tag": "p",
        "selector": "p#unrelated-state-text",
        "text": "State",
        "accessible_name": "State",
      }
    ]
  state_dir.joinpath("accessibility_context.json").write_text(
    json.dumps(payload),
    encoding="utf-8",
  )
  state_dir.joinpath("metadata.json").write_text(
    json.dumps(
      {
        "state_id": "state_0000",
        "url": "https://example.test/checkout/address",
        "route": "/checkout/address",
        "title": "Shipping address | Brightlane Checkout",
        "focused_acquisition": {
          "benchmark_state_id": "CO-S003",
          "focused_state_name": "address",
        },
      }
    ),
    encoding="utf-8",
  )
  run_dir.joinpath("graph.json").write_text(
    json.dumps({"states": ["state_0000"]}),
    encoding="utf-8",
  )
  run_dir.joinpath("transitions.json").write_text("[]", encoding="utf-8")

  control = controls[candidate_control]
  context_control = {
    "tag": control["tag"],
    "name": control["name"],
    "autocomplete": control["autocomplete"],
    "required": control["required"],
    "value_state": "filled" if control["has_value"] else "empty",
  }
  _write_candidate_records(
    run_dir,
    [
      {
        "candidate_id": f"cand_{candidate_control}",
        "candidate_type": "form-label-mismatch",
        "state_id": "state_0000",
        "state_context": {
          "url": "https://example.test/checkout/address",
          "route": "/checkout/address",
        },
        "evidence": {
          "primary": {"form_control": control},
          "supporting": {
            "form_label_context_v1": {
              "schema_version": "form_label_context_v1",
              "control": context_control,
              "field_purpose_evidence": {
                "name": control["name"],
                "autocomplete": control["autocomplete"],
              },
              "labeling": {
                "label_sources": [
                  {
                    "relationship_type": "labels",
                    "method": "for",
                    "text_segments": text_segments[candidate_control],
                  }
                ]
              },
            }
          },
        },
      }
    ],
  )
  return run_dir


def _write_delivery_instructions_label_run(
  tmp_path: Path,
  *,
  delivery_label: str,
  delivery_has_value: bool,
  candidate_control: str,
) -> Path:
  run_dir = tmp_path / "delivery-instructions-label-run"
  state_dir = run_dir / "states" / "state_0000"
  state_dir.mkdir(parents=True)
  hint_text = "Optional. Add gate codes, safe-place details, or delivery notes."
  controls = {
    "deliveryInstructions": {
      "element_id": "e_delivery_instructions",
      "tag": "textarea",
      "selector": "textarea#synthetic-delivery-instructions",
      "id": "synthetic-delivery-instructions",
      "name": "deliveryInstructions",
      "label": delivery_label,
      "accessible_name": delivery_label,
      "aria_describedby": "synthetic-delivery-instructions-description",
      "autocomplete": None,
      "required": False,
      "has_value": delivery_has_value,
    },
    "streetAddress": {
      "element_id": "e_street_address",
      "tag": "input",
      "selector": "input#synthetic-street-address",
      "id": "synthetic-street-address",
      "name": "streetAddress",
      "label": "Street addressRequired",
      "accessible_name": "Street addressRequired",
      "type": "text",
      "autocomplete": "street-address",
      "required": True,
      "has_value": False,
    },
    "country": {
      "element_id": "e_country",
      "tag": "select",
      "selector": "select#synthetic-country",
      "id": "synthetic-country",
      "name": "country",
      "label": "StateRequired",
      "accessible_name": "StateRequired",
      "autocomplete": "country-name",
      "required": True,
      "has_value": True,
    },
    "city": {
      "element_id": "e_city",
      "tag": "input",
      "selector": "input#synthetic-city",
      "id": "synthetic-city",
      "name": "city",
      "label": "StateRequired",
      "accessible_name": "StateRequired",
      "type": "text",
      "autocomplete": "address-level2",
      "required": True,
      "has_value": False,
    },
    "email": {
      "element_id": "e_email",
      "tag": "input",
      "selector": "input#synthetic-email",
      "id": "synthetic-email",
      "name": "email",
      "label": "Full nameRequired",
      "accessible_name": "Full nameRequired",
      "type": "email",
      "autocomplete": "email",
      "required": True,
      "has_value": False,
    },
  }
  state_dir.joinpath("accessibility_context.json").write_text(
    json.dumps(
      {
        "schema_version": "1",
        "state_id": "state_0000",
        "state_context": {"route": "/checkout/address"},
        "page": {
          "url": "https://example.test/checkout/address",
          "title": "Shipping address | Brightlane Checkout",
        },
        "form_controls": list(controls.values()),
      }
    ),
    encoding="utf-8",
  )
  state_dir.joinpath("metadata.json").write_text(
    json.dumps(
      {
        "state_id": "state_0000",
        "url": "https://example.test/checkout/address",
        "route": "/checkout/address",
        "title": "Shipping address | Brightlane Checkout",
        "focused_acquisition": {
          "benchmark_state_id": "CO-S003",
          "focused_state_name": "address",
        },
      }
    ),
    encoding="utf-8",
  )
  run_dir.joinpath("graph.json").write_text(
    json.dumps({"states": ["state_0000"]}),
    encoding="utf-8",
  )
  run_dir.joinpath("transitions.json").write_text("[]", encoding="utf-8")

  control = controls[candidate_control]
  descriptions = []
  if candidate_control == "deliveryInstructions":
    descriptions.append(
      {
        "text": hint_text,
        "relationship_type": "describes",
        "method": "aria-describedby",
      }
    )
  _write_candidate_records(
    run_dir,
    [
      {
        "candidate_id": f"cand_{candidate_control}",
        "candidate_type": "form-label-mismatch",
        "state_id": "state_0000",
        "state_context": {
          "url": "https://example.test/checkout/address",
          "route": "/checkout/address",
        },
        "evidence": {
          "primary": {"form_control": control},
          "supporting": {
            "form_label_context_v1": {
              "schema_version": "form_label_context_v1",
              "control": {
                "tag": control["tag"],
                "name": control["name"],
                "required": control["required"],
                "value_state": "filled" if control["has_value"] else "empty",
              },
              "field_purpose_evidence": {
                "name": control["name"],
                "descriptions": descriptions,
              },
              "labeling": {
                "visible_label": control["label"],
                "computed_accessible_name": control["accessible_name"],
                "label_sources": [
                  {
                    "relationship_type": "labels",
                    "method": "for",
                    "text_segments": [delivery_label]
                    if candidate_control == "deliveryInstructions"
                    else [control["label"]],
                  }
                ],
              },
            }
          },
        },
      }
    ],
  )
  return run_dir


def _write_country_autocomplete_run(
  tmp_path: Path,
  *,
  country_autocomplete: str,
  country_text_segments: list[str],
  candidate_control: str,
  state_has_value: bool,
) -> Path:
  run_dir = tmp_path / "country-autocomplete-run"
  state_dir = run_dir / "states" / "state_0000"
  state_dir.mkdir(parents=True)
  country_label = "".join(country_text_segments)
  controls = {
    "country": {
      "element_id": "e_country",
      "tag": "select",
      "selector": "select#synthetic-country",
      "id": "synthetic-country",
      "name": "country",
      "label": country_label,
      "accessible_name": country_label,
      "autocomplete": country_autocomplete,
      "required": True,
      "has_value": True,
    },
    "state": {
      "element_id": "e_state",
      "tag": "input",
      "selector": "input#synthetic-state",
      "id": "synthetic-state",
      "name": "state",
      "label": "StateRequired",
      "accessible_name": "StateRequired",
      "type": "text",
      "autocomplete": "address-level1",
      "required": True,
      "has_value": state_has_value,
    },
    "city": {
      "element_id": "e_city",
      "tag": "input",
      "selector": "input#synthetic-city",
      "id": "synthetic-city",
      "name": "city",
      "label": "CityRequired",
      "accessible_name": "CityRequired",
      "type": "text",
      "autocomplete": "address-level1",
      "required": True,
      "has_value": True,
    },
  }
  label_segments = {
    "country": country_text_segments,
    "state": ["State", "Required"],
    "city": ["City", "Required"],
  }
  payload = {
    "schema_version": "1",
    "state_id": "state_0000",
    "state_context": {"route": "/checkout/address"},
    "page": {
      "url": "https://example.test/checkout/address",
      "title": "Shipping address | Brightlane Checkout",
    },
    "form_controls": list(controls.values()),
  }
  state_dir.joinpath("accessibility_context.json").write_text(
    json.dumps(payload),
    encoding="utf-8",
  )
  state_dir.joinpath("metadata.json").write_text(
    json.dumps(
      {
        "state_id": "state_0000",
        "url": "https://example.test/checkout/address",
        "route": "/checkout/address",
        "title": "Shipping address | Brightlane Checkout",
        "focused_acquisition": {
          "benchmark_state_id": "CO-S003",
          "focused_state_name": "address",
        },
      }
    ),
    encoding="utf-8",
  )
  run_dir.joinpath("graph.json").write_text(
    json.dumps({"states": ["state_0000"]}),
    encoding="utf-8",
  )
  run_dir.joinpath("transitions.json").write_text("[]", encoding="utf-8")

  control = controls[candidate_control]
  autocomplete_purposes = {
    "address-level1": ("address administrative level 1", "address"),
    "country-name": ("country name", "address"),
  }
  recognized_purpose, token_category = autocomplete_purposes[
    control["autocomplete"]
  ]
  _write_candidate_records(
    run_dir,
    [
      {
        "candidate_id": f"cand_{candidate_control}",
        "candidate_type": "autocomplete-purpose-mismatch",
        "state_id": "state_0000",
        "state_context": {
          "url": "https://example.test/checkout/address",
          "route": "/checkout/address",
        },
        "evidence": {
          "primary": {"form_control": control},
          "supporting": {
            "autocomplete_purpose_context_v1": {
              "schema_version": "autocomplete_purpose_context_v1",
              "control": {
                "tag": control["tag"],
                "name": control["name"],
                "autocomplete": control["autocomplete"],
                "required": control["required"],
                "value_state": "filled" if control["has_value"] else "empty",
              },
              "labeling": {
                "label_sources": [
                  {
                    "relationship_type": "labels",
                    "method": "for",
                    "text_segments": label_segments[candidate_control],
                  }
                ]
              },
              "field_purpose_evidence": {"name": control["name"]},
              "autocomplete_evidence": {
                "raw_value": control["autocomplete"],
                "tokens": [control["autocomplete"]],
                "section_tokens": [],
                "context_tokens": [],
                "purpose_token": control["autocomplete"],
                "recognized_purpose": recognized_purpose,
                "token_category": token_category,
                "is_known_token": True,
                "unknown_tokens": [],
              },
            }
          },
        },
      }
    ],
  )
  return run_dir


def _write_form_label_run(tmp_path: Path) -> Path:
  run_dir = tmp_path / "form-label-run"
  state_dir = run_dir / "states" / "state_0000"
  state_dir.mkdir(parents=True)
  payload = {
    "schema_version": "1",
    "state_id": "state_0000",
    "state_context": {"route": "/checkout/payment"},
    "page": {"url": "https://example.test/checkout/payment", "title": "Payment"},
    "form_controls": [
      {
        "element_id": "e_card_number",
        "selector": '[data-testid="payment-card-number"]',
        "id": "payment-cardNumber",
        "name": "cardNumber",
        "label": "Security codeRequired",
        "autocomplete": "cc-number",
      },
      {
        "element_id": "e_security_code",
        "selector": '[data-testid="payment-security-code"]',
        "id": "payment-securityCode",
        "name": "securityCode",
        "label": "Card numberRequired",
        "autocomplete": "cc-csc",
      },
    ],
  }
  state_dir.joinpath("accessibility_context.json").write_text(
    json.dumps(payload),
    encoding="utf-8",
  )
  state_dir.joinpath("metadata.json").write_text(
    json.dumps(
      {
        "state_id": "state_0000",
        "url": "https://example.test/checkout/payment",
        "route": "/checkout/payment",
        "title": "Payment",
        "focused_acquisition": {
          "benchmark_state_id": "CO-S004",
          "focused_state_name": "payment",
        },
      }
    ),
    encoding="utf-8",
  )
  run_dir.joinpath("graph.json").write_text(json.dumps({"states": ["state_0000"]}), encoding="utf-8")
  run_dir.joinpath("transitions.json").write_text("[]", encoding="utf-8")
  return run_dir


def _score_widget_tab_swap(
  tmp_path: Path,
  *,
  desk_label: str,
  office_label: str,
  score_run_id: str,
):
  run_dir = _write_widget_tab_swap_run(
    tmp_path,
    desk_label=desk_label,
    office_label=office_label,
  )
  registry_path = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "registry"
    / "benchmark-case-registry.json"
  )

  return score_seeded_experiment(
    SeededScorerOptions(
      run_dir=run_dir,
      config_id="checkout-co-sem-112",
      registry_path=registry_path,
      score_run_id=score_run_id,
    ),
    generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
  )


def _score_widget_tablist_name(
  tmp_path: Path,
  *,
  tablist_name: str,
  include_tablist_candidate: bool,
  score_run_id: str,
):
  run_dir = _write_widget_tablist_name_run(
    tmp_path,
    tablist_name=tablist_name,
    include_tablist_candidate=include_tablist_candidate,
  )
  registry_path = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "registry"
    / "benchmark-case-registry.json"
  )

  return score_seeded_experiment(
    SeededScorerOptions(
      run_dir=run_dir,
      config_id="checkout-co-sem-114",
      registry_path=registry_path,
      score_run_id=score_run_id,
    ),
    generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
  )


def _write_widget_tablist_name_run(
  tmp_path: Path,
  *,
  tablist_name: str,
  include_tablist_candidate: bool,
) -> Path:
  run_dir = tmp_path / "widget-tablist-name-run"
  state_dir = run_dir / "states" / "state_0000"
  state_dir.mkdir(parents=True)
  tablist = {
    "bucket": "visual_cues",
    "element_id": "e_product_category_tablist",
    "tag": "div",
    "role": "tablist",
    "selector": '[data-testid="product-category-tablist"]',
    "text": "Desk accessories Office supplies",
    "accessible_name": tablist_name,
    "aria_label": tablist_name,
    "raw_html": (
      f'<div role="tablist" aria-label="{tablist_name}" '
      'data-testid="product-category-tablist">'
      '<button role="tab" aria-controls="desk-accessories-panel">'
      'Desk accessories</button>'
      '<button role="tab" aria-controls="office-supplies-panel">'
      'Office supplies</button></div>'
    ),
  }
  desk_tab = _widget_tab_element(
    element_id="e_desk_tab",
    test_id="product-category-tab-desk-accessories",
    label="Desk accessories",
    controls="desk-accessories-panel",
    selected="true",
  )
  office_tab = _widget_tab_element(
    element_id="e_office_tab",
    test_id="product-category-tab-office-supplies",
    label="Office supplies",
    controls="office-supplies-panel",
    selected="false",
  )
  state_dir.joinpath("accessibility_context.json").write_text(
    json.dumps(
      {
        "schema_version": "1",
        "state_id": "state_0000",
        "state_context": {"route": "/products"},
        "page": {
          "url": "https://example.test/products",
          "title": "Products | Brightlane Checkout",
        },
        "buttons": [desk_tab, office_tab],
        "visual_cues": [tablist],
      }
    ),
    encoding="utf-8",
  )
  state_dir.joinpath("metadata.json").write_text(
    json.dumps(
      {
        "state_id": "state_0000",
        "url": "https://example.test/products",
        "route": "/products",
        "title": "Products | Brightlane Checkout",
        "focused_acquisition": {
          "benchmark_state_id": "CO-S001",
          "focused_state_name": "products",
        },
      }
    ),
    encoding="utf-8",
  )
  run_dir.joinpath("graph.json").write_text(
    json.dumps({"states": ["state_0000"]}),
    encoding="utf-8",
  )
  run_dir.joinpath("transitions.json").write_text("[]", encoding="utf-8")
  candidates = [
    _widget_tab_candidate("cand_desk_tab", desk_tab),
    _widget_tab_candidate("cand_office_tab", office_tab),
  ]
  if include_tablist_candidate:
    candidates.insert(
      0,
      {
        "candidate_id": "cand_product_category_tablist",
        "candidate_type": "widget-label-purpose-mismatch",
        "state_id": "state_0000",
        "state_context": {
          "url": "https://example.test/products",
          "route": "/products",
        },
        "evidence": {"primary": {"widget": tablist}},
      },
    )
  _write_candidate_records(run_dir, candidates)
  return run_dir


def _write_widget_tab_swap_run(
  tmp_path: Path,
  *,
  desk_label: str,
  office_label: str,
) -> Path:
  run_dir = tmp_path / "widget-swap-run"
  state_dir = run_dir / "states" / "state_0000"
  state_dir.mkdir(parents=True)
  desk_tab = _widget_tab_element(
    element_id="e_desk_tab",
    test_id="product-category-tab-desk-accessories",
    label=desk_label,
    controls="desk-accessories-panel",
    selected="true",
  )
  office_tab = _widget_tab_element(
    element_id="e_office_tab",
    test_id="product-category-tab-office-supplies",
    label=office_label,
    controls="office-supplies-panel",
    selected="false",
  )
  state_dir.joinpath("accessibility_context.json").write_text(
    json.dumps(
      {
        "schema_version": "1",
        "state_id": "state_0000",
        "state_context": {"route": "/products"},
        "page": {
          "url": "https://example.test/products",
          "title": "Products | Brightlane Checkout",
        },
        "buttons": [desk_tab, office_tab],
      }
    ),
    encoding="utf-8",
  )
  state_dir.joinpath("metadata.json").write_text(
    json.dumps(
      {
        "state_id": "state_0000",
        "url": "https://example.test/products",
        "route": "/products",
        "title": "Products | Brightlane Checkout",
        "focused_acquisition": {
          "benchmark_state_id": "CO-S001",
          "focused_state_name": "products",
        },
      }
    ),
    encoding="utf-8",
  )
  run_dir.joinpath("graph.json").write_text(
    json.dumps({"states": ["state_0000"]}),
    encoding="utf-8",
  )
  run_dir.joinpath("transitions.json").write_text("[]", encoding="utf-8")
  _write_candidate_records(
    run_dir,
    [
      _widget_tab_candidate("cand_desk_tab", desk_tab),
      _widget_tab_candidate("cand_office_tab", office_tab),
    ],
  )
  return run_dir


def _widget_tab_element(
  *,
  element_id: str,
  test_id: str,
  label: str,
  controls: str,
  selected: str,
) -> dict[str, object]:
  return {
    "bucket": "buttons",
    "element_id": element_id,
    "tag": "button",
    "role": "tab",
    "selector": f'[data-testid="{test_id}"]',
    "text": label,
    "accessible_name": label,
    "aria_controls": controls,
    "aria_selected": selected,
  }


def _widget_tab_candidate(
  candidate_id: str,
  widget: dict[str, object],
) -> dict[str, object]:
  return {
    "candidate_id": candidate_id,
    "candidate_type": "widget-label-purpose-mismatch",
    "state_id": "state_0000",
    "state_context": {
      "url": "https://example.test/products",
      "route": "/products",
    },
    "evidence": {"primary": {"widget": widget}},
  }


def _email_native_validity(
  *,
  value_missing: bool = False,
  format_mismatch: bool = False,
) -> dict[str, bool]:
  return {
    "valid": not value_missing and not format_mismatch,
    "value_missing": value_missing,
    "type_mismatch": format_mismatch,
    "pattern_mismatch": format_mismatch,
    "too_long": False,
    "too_short": False,
    "range_underflow": False,
    "range_overflow": False,
    "step_mismatch": False,
    "bad_input": False,
    "custom_error": False,
  }


def _postal_code_native_validity(
  *,
  value_missing: bool = False,
  format_mismatch: bool = False,
) -> dict[str, bool]:
  return {
    "valid": not value_missing and not format_mismatch,
    "value_missing": value_missing,
    "type_mismatch": False,
    "pattern_mismatch": format_mismatch,
    "too_long": False,
    "too_short": False,
    "range_underflow": False,
    "range_overflow": False,
    "step_mismatch": False,
    "bad_input": False,
    "custom_error": False,
  }


def _security_code_native_validity(
  *,
  value_missing: bool = False,
  format_mismatch: bool = False,
) -> dict[str, bool]:
  return {
    "valid": not value_missing and not format_mismatch,
    "value_missing": value_missing,
    "type_mismatch": False,
    "pattern_mismatch": format_mismatch,
    "too_long": False,
    "too_short": False,
    "range_underflow": False,
    "range_overflow": False,
    "step_mismatch": False,
    "bad_input": False,
    "custom_error": False,
  }


def _write_error_message_recovery_run(
  tmp_path: Path,
  *,
  benchmark_state_id: str,
  control_id: str,
  control_name: str,
  has_value: bool,
  native_validity: dict[str, bool],
  error_text: object,
) -> Path:
  run_dir = tmp_path / "run"
  state_dir = run_dir / "states" / "state_0000"
  state_dir.mkdir(parents=True)
  is_email = control_id == "address-email"
  is_security_code = control_id == "payment-securityCode"
  if is_email:
    error_id = "address-email-error"
    selector = '[data-testid="address-email"]'
    accessible_name = "EmailRequired"
    label = "Email Required"
    control_type = "email"
    autocomplete = "email"
    route = "/checkout/address"
    title = "Shipping address | Brightlane Checkout"
    focused_state_name = "address_email_format_error"
  elif is_security_code:
    error_id = "payment-securityCode-error"
    selector = '[data-testid="payment-security-code"]'
    accessible_name = "Security codeRequired"
    label = "Security code Required"
    control_type = "text"
    autocomplete = "cc-csc"
    route = "/checkout/payment"
    title = "Payment | Brightlane Checkout"
    focused_state_name = "payment_security_code_format_error"
  else:
    error_id = "address-postalCode-error"
    selector = '[data-testid="address-postal-code"]'
    accessible_name = "ZIP codeRequired"
    label = "ZIP code Required"
    control_type = "text"
    autocomplete = "postal-code"
    route = "/checkout/address"
    title = "Shipping address | Brightlane Checkout"
    focused_state_name = "address_postal_code_format_error"
  control = {
    "element_id": "e_control",
    "selector": selector,
    "tag": "input",
    "role": None,
    "text": "",
    "accessible_name": accessible_name,
    "aria_label": None,
    "aria_labelledby": None,
    "aria_describedby": error_id if error_text is not None else None,
    "label": label,
    "wrapping_label": None,
    "type": control_type,
    "name": control_name,
    "id": control_id,
    "placeholder": None,
    "autocomplete": autocomplete,
    "required": True,
    "disabled": False,
    "readonly": False,
    "aria_invalid": "true" if error_text is not None else None,
    "invalid": not native_validity["valid"],
    "native_validity": native_validity,
    "has_value": has_value,
  }
  error_message = (
    {
      "element_id": "e_error",
      "selector": f"#{error_id}",
      "text": error_text,
      "relationship_type": "aria-describedby",
      "method": "idref",
    }
    if error_text is not None
    else None
  )
  state_dir.joinpath("accessibility_context.json").write_text(
    json.dumps(
      {
        "schema_version": "1",
        "state_id": "state_0000",
        "state_context": {"route": route},
        "page": {
          "url": f"https://example.test{route}",
          "title": title,
        },
        "form_controls": [control],
        "referenced_elements": [error_message] if error_message else [],
      }
    ),
    encoding="utf-8",
  )
  state_dir.joinpath("metadata.json").write_text(
    json.dumps(
      {
        "state_id": "state_0000",
        "url": f"https://example.test{route}",
        "route": route,
        "title": title,
        "focused_acquisition": {
          "benchmark_state_id": benchmark_state_id,
          "focused_state_name": focused_state_name,
        },
      }
    ),
    encoding="utf-8",
  )
  run_dir.joinpath("graph.json").write_text(
    json.dumps({"states": ["state_0000"]}),
    encoding="utf-8",
  )
  run_dir.joinpath("transitions.json").write_text("[]", encoding="utf-8")

  candidates = []
  if error_message is not None:
    candidates.append(
      {
        "candidate_id": f"cand_{tmp_path.name}",
        "candidate_type": "error-message-mismatch",
        "state_id": "state_0000",
        "state_context": {
          "url": f"https://example.test{route}",
          "route": route,
          "title": title,
        },
        "evidence": {
          "primary": {
            "form_control": control,
            "error_message": error_message,
          }
        },
      }
    )
  _write_candidate_records(run_dir, candidates)
  return run_dir


def _write_shipping_link_run(
  tmp_path: Path,
  *,
  source_text: str,
  nearest_heading: str,
  nearby_text: str,
  resolved_path: str,
  destination_path: str | None = None,
  destination_title: str | None = None,
  destination_heading: str | None = None,
) -> Path:
  run_dir = tmp_path / "run"
  state_dir = run_dir / "states" / "state_0000"
  state_dir.mkdir(parents=True)
  href = f"https://support.example.test{resolved_path}"
  link = {
    "element_id": "e_support_link",
    "selector": "a.support-link",
    "tag": "a",
    "text": source_text,
    "accessible_name": source_text,
    "aria_label": None,
    "href": href,
  }
  supporting: dict[str, object] = {
    "context": {"nearby_text": nearby_text},
    "structure": {
      "nearest_heading": {
        "tag": "h3" if nearest_heading == "Shipping help" else "h2",
        "text": nearest_heading,
      }
    },
    "link_destination_context_v1": {
      "schema_version": "link_destination_context_v1",
      "raw_href": href,
      "resolved_url": href,
      "resolved_path": resolved_path,
      "fragment": "",
      "match_status": "external_or_out_of_scope",
    },
  }
  if destination_path and destination_title and destination_heading:
    supporting["destination_state_context_v1"] = {
      "schema_version": "destination_state_context_v1",
      "source_state_id": "state_0000",
      "match_basis": ["data_testid"],
      "match_count": 1,
      "destinations": [
        {
          "target_state_id": "state_0001",
          "target_url": f"https://support.example.test{destination_path}",
          "target_route": destination_path,
          "target_title": destination_title,
          "target_primary_headings": [
            {
              "level": 1,
              "tag": "h1",
              "text": destination_heading,
              "accessible_name": destination_heading,
            }
          ],
        }
      ],
    }
  state_dir.joinpath("accessibility_context.json").write_text(
    json.dumps(
      {
        "schema_version": "1",
        "state_id": "state_0000",
        "state_context": {"route": "/products"},
        "page": {
          "url": "https://checkout.example.test/products",
          "title": "Products | Brightlane Checkout",
        },
        "links": [link],
      }
    ),
    encoding="utf-8",
  )
  state_dir.joinpath("metadata.json").write_text(
    json.dumps(
      {
        "state_id": "state_0000",
        "url": "https://checkout.example.test/products",
        "route": "/products",
        "title": "Products | Brightlane Checkout",
        "focused_acquisition": {
          "benchmark_state_id": "CO-S001",
          "focused_state_name": "products",
        },
      }
    ),
    encoding="utf-8",
  )
  run_dir.joinpath("graph.json").write_text(
    json.dumps({"states": ["state_0000"]}),
    encoding="utf-8",
  )
  run_dir.joinpath("transitions.json").write_text("[]", encoding="utf-8")
  _write_candidate_records(
    run_dir,
    [
      {
        "candidate_id": f"cand_{tmp_path.name}",
        "candidate_type": "link-text-mismatch",
        "state_id": "state_0000",
        "selection_reason": ["visible_link_with_text_destination_and_context"],
        "state_context": {
          "url": "https://checkout.example.test/products",
          "route": "/products",
        },
        "evidence": {
          "primary": {"link": link},
          "supporting": supporting,
        },
      }
    ],
  )
  return run_dir


def _write_run(tmp_path: Path) -> Path:
  run_dir = tmp_path / "run"
  state_dir = run_dir / "states" / "state_0000"
  state_dir.mkdir(parents=True)
  payload = {
    "schema_version": "1",
    "state_id": "state_0000",
    "state_context": {"route": "/checkout/review"},
    "page": {"url": "https://example.test/checkout/review", "title": "Review"},
    "buttons": [
      {
        "element_id": "e_button",
        "selector": "button#place-order",
        "text": "Place order",
        "accessible_name": "Place order",
      }
    ],
  }
  state_dir.joinpath("accessibility_context.json").write_text(json.dumps(payload), encoding="utf-8")
  state_dir.joinpath("metadata.json").write_text(
    json.dumps(
      {
        "state_id": "state_0000",
        "url": "https://example.test/checkout/review",
        "route": "/checkout/review",
        "title": "Review",
        "focused_acquisition": {"benchmark_state_id": "CO-S004", "focused_state_name": "co_s004_review"},
      }
    ),
    encoding="utf-8",
  )
  run_dir.joinpath("graph.json").write_text(json.dumps({"states": ["state_0000"]}), encoding="utf-8")
  run_dir.joinpath("transitions.json").write_text("[]", encoding="utf-8")
  return run_dir


def _write_heading_context_run(
  tmp_path: Path,
  *,
  route: str,
  heading: str,
) -> Path:
  run_dir = tmp_path / "run"
  state_dir = run_dir / "states" / "state_0000"
  state_dir.mkdir(parents=True)
  url = f"https://example.test{route}"
  payload = {
    "schema_version": "1",
    "state_id": "state_0000",
    "state_context": {"route": route},
    "page": {"url": url, "title": f"{heading} | Brightlane Checkout"},
    "headings": [
      {
        "element_id": "e_page_heading",
        "selector": "h1:nth-of-type(1)",
        "tag": "h1",
        "text": heading,
        "level": 1,
        "accessible_name": heading,
      }
    ],
  }
  state_dir.joinpath("accessibility_context.json").write_text(
    json.dumps(payload),
    encoding="utf-8",
  )
  state_dir.joinpath("metadata.json").write_text(
    json.dumps(
      {
        "state_id": "state_0000",
        "url": url,
        "route": route,
        "title": payload["page"]["title"],
        "focused_acquisition": {
          "benchmark_state_id": "CO-S002" if route == "/cart" else "CO-S001",
          "focused_state_name": "cart" if route == "/cart" else "products",
        },
      }
    ),
    encoding="utf-8",
  )
  run_dir.joinpath("graph.json").write_text(
    json.dumps({"states": ["state_0000"]}),
    encoding="utf-8",
  )
  run_dir.joinpath("transitions.json").write_text("[]", encoding="utf-8")
  return run_dir


def _write_heading_context_registry(tmp_path: Path, *, products_intro: str) -> Path:
  registry_path = tmp_path / "registry.json"
  registry_path.write_text(
    json.dumps(
      {
        "schema_version": "1",
        "variants": [
          {
            "variant_id": "synthetic-heading-context",
            "app": "checkout-flow",
            "candidate_type": "heading-not-descriptive",
            "expected_human_judgment": "violation",
            "expected_state": {
              "routes": ["/cart"],
              "benchmark_state_ids": ["CO-S002"],
            },
            "expected_candidate": {"type": "heading-not-descriptive"},
            "expected_evidence": {
              "bucket": "headings",
              "primary_evidence_key": "heading",
              "attributes": {
                "tag": "h1",
                "text": "Products",
                "level": 1,
                "accessible_name": "Products",
              },
              "candidate_evidence": {
                "supporting": {
                  "heading_scoped_content": {
                    "schema_version": "heading_scoped_content_v1",
                    "source_element_ref": {
                      "bucket": "landmarks",
                      "tag": "main",
                    },
                    "truncated": False,
                  },
                  "heading_scope": {
                    "sampled_items": [
                      {
                        "kind": "paragraph",
                        "text": products_intro,
                      }
                    ],
                  },
                }
              },
            },
          }
        ],
        "seeded_configurations": [
          {
            "configuration_id": "checkout-heading-context",
            "app": "checkout-flow",
            "seed_ids": ["synthetic-heading-context"],
          }
        ],
      }
    ),
    encoding="utf-8",
  )
  return registry_path


def _write_page_title_run(
  tmp_path: Path,
  *,
  benchmark_state_id: str,
  route: str,
  title: str,
) -> Path:
  run_dir = tmp_path / "run"
  state_dir = run_dir / "states" / "state_0000"
  state_dir.mkdir(parents=True)
  url = f"https://example.test{route}"
  heading = "Cart" if route == "/cart" else "Shipping address"
  page = {
    "url": url,
    "title": title,
    "document_lang": "en",
    "html_lang": "en",
    "body_text_sample": f"{heading} Checkout progress Shipping details",
  }
  state_dir.joinpath("accessibility_context.json").write_text(
    json.dumps(
      {
        "schema_version": "1",
        "state_id": "state_0000",
        "state_context": {"route": route},
        "page": page,
        "headings": [{"level": 1, "text": heading, "selector": "h1"}],
      }
    ),
    encoding="utf-8",
  )
  state_dir.joinpath("metadata.json").write_text(
    json.dumps(
      {
        "state_id": "state_0000",
        "url": url,
        "route": route,
        "title": title,
        "focused_acquisition": {
          "benchmark_state_id": benchmark_state_id,
          "focused_state_name": "cart" if route == "/cart" else "address",
        },
      }
    ),
    encoding="utf-8",
  )
  run_dir.joinpath("graph.json").write_text(
    json.dumps({"states": ["state_0000"]}),
    encoding="utf-8",
  )
  run_dir.joinpath("transitions.json").write_text("[]", encoding="utf-8")
  _write_candidate_records(
    run_dir,
    [
      {
        "candidate_id": f"cand_{tmp_path.name}",
        "candidate_type": "page-title-not-descriptive",
        "state_id": "state_0000",
        "state_context": {"url": url, "route": route, "title": title},
        "evidence": {"primary": {"page": page}},
      }
    ],
  )
  return run_dir


def _write_candidate_records(run_dir: Path, records: list[dict[str, object]]) -> None:
  candidates_dir = run_dir / "candidates"
  candidates_dir.mkdir()
  candidates_dir.joinpath("candidates.jsonl").write_text(
    "".join(json.dumps(record) + "\n" for record in records),
    encoding="utf-8",
  )


def _score_destination_candidates(
  tmp_path: Path,
  *,
  candidates: list[dict[str, object]],
  destination_route: str | None,
  destination_heading: str | None,
  score_run_id: str,
  destination_elements: list[dict[str, object]] | None = None,
):
  run_dir = _write_run(tmp_path)
  registry_path = _write_destination_registry(
    tmp_path,
    destination_route=destination_route,
    destination_heading=destination_heading,
    destination_elements=destination_elements,
  )
  _write_candidate_records(run_dir, candidates)

  return score_seeded_experiment(
    SeededScorerOptions(
      run_dir=run_dir,
      config_id="checkout-destination",
      registry_path=registry_path,
      score_run_id=score_run_id,
    ),
    generated_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
  )


def _assert_destination_candidate_ids(result, expected_candidate_ids: list[str]) -> None:
  assert result.summary["counts"]["recovered_seeds"] == (1 if expected_candidate_ids else 0)
  seed_result = result.summary["results"][0]
  expected_status = "recovered_to_candidate" if expected_candidate_ids else "candidate_missing"
  assert seed_result["status"] == expected_status
  assert [
    candidate["candidate_id"]
    for candidate in seed_result["matched_candidates"]
  ] == expected_candidate_ids


def _destination_candidate(
  candidate_id: str,
  *,
  selector: str,
  accessible_name: str,
  destination_route: str | None = None,
  destination_heading: str | None = None,
  additional_destinations: list[tuple[str, str]] | None = None,
  destination_elements: list[dict[str, object]] | None = None,
  additional_destination_elements: list[list[dict[str, object]]] | None = None,
  result_headings: list[str] | None = None,
) -> dict[str, object]:
  candidate: dict[str, object] = {
    "candidate_id": candidate_id,
    "candidate_type": "button-label-mismatch",
    "state_id": "state_0000",
    "state_context": {"url": "https://example.test/checkout/review"},
    "evidence": {
      "primary": {
        "button": {
          "element_id": "e_button",
          "selector": selector,
          "text": accessible_name,
          "accessible_name": accessible_name,
        }
      }
    },
  }
  if (
    destination_route is None
    and destination_heading is None
    and not additional_destinations
    and destination_elements is None
    and result_headings is None
  ):
    return candidate

  destinations = []
  destination_specs = [
    (
      destination_route,
      destination_heading,
      destination_elements,
    ),
    *[
      (
        route,
        heading,
        (
          additional_destination_elements[index]
          if additional_destination_elements
          and index < len(additional_destination_elements)
          else None
        ),
      )
      for index, (route, heading) in enumerate(additional_destinations or [])
    ],
  ]
  for route, heading, elements in destination_specs:
    destination = {
      "target_route": route,
      "target_primary_headings": [
        {
          "text": heading,
          "accessible_name": heading,
        }
      ],
    }
    if elements is not None:
      destination["target_elements"] = elements
    destinations.append(destination)
  supporting = {
    "destination_state_context_v1": {
      "schema_version": "destination_state_context_v1",
      "destinations": destinations,
    }
  }
  if result_headings is not None:
    supporting["button_action_context_v1"] = {
      "action_evidence": {
        "result_state_context": {
          "state_id": "state_destination",
          "route": destination_route,
          "title": "Destination",
          "headings": result_headings,
        }
      }
    }
  candidate["evidence"]["supporting"] = supporting
  return candidate


def _write_destination_registry(
  tmp_path: Path,
  *,
  destination_route: str | None,
  destination_heading: str | None,
  destination_elements: list[dict[str, object]] | None = None,
) -> Path:
  expected_candidate: dict[str, object] = {"type": "button-label-mismatch"}
  if destination_route is not None:
    expected_candidate["destination_route"] = destination_route
  if destination_heading is not None:
    expected_candidate["destination_heading"] = destination_heading
  if destination_elements is not None:
    expected_candidate["destination_elements"] = destination_elements

  registry_path = tmp_path / "destination-registry.json"
  registry_path.write_text(
    json.dumps(
      {
        "schema_version": "1",
        "variants": [
          {
            "variant_id": "co-sem-destination",
            "app": "checkout-flow",
            "candidate_type": "button-label-mismatch",
            "expected_human_judgment": "violation",
            "expected_state": {
              "routes": ["/checkout/review"],
              "benchmark_state_ids": ["CO-S004"],
            },
            "expected_candidate": expected_candidate,
            "expected_evidence": {
              "bucket": "buttons",
              "selector_hint": "button#place-order",
              "attributes": {"accessible_name": "Place order"},
            },
          }
        ],
        "seeded_configurations": [
          {
            "configuration_id": "checkout-destination",
            "app": "checkout-flow",
            "seed_ids": ["co-sem-destination"],
          }
        ],
      }
    ),
    encoding="utf-8",
  )
  return registry_path
