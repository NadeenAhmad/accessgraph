from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import time
from contextlib import closing
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

import pytest

from src.analysis.candidates import build_semantic_candidates
from src.analysis.evaluation.seeded_scorer import (
  SeededScorerOptions,
  score_seeded_experiment,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKOUT_DIR = REPO_ROOT / "benchmarks" / "local-spas" / "checkout-flow"


def test_co_sem_027_profile_captures_controlled_support_destination(tmp_path):
  pytest.importorskip("playwright.async_api")
  from scripts.benchmarks.checkout import runner as checkout_runner

  _require_vite_preview()
  if not _port_available(
    checkout_runner.CONTROLLED_SUPPORT_HOST,
    checkout_runner.CONTROLLED_SUPPORT_PORT,
  ):
    pytest.skip(
      "Controlled support test requires 127.0.0.1:8771 to be available."
    )

  support_server: subprocess.Popen[str] | None = None
  vite_server: subprocess.Popen[str] | None = None
  try:
    support_server = checkout_runner._start_controlled_support_server()
    vite_port = _find_free_port()
    vite_server = checkout_runner._start_vite_preview(port=vite_port)
    base_url = f"http://127.0.0.1:{vite_port}"

    checkout_runner._wait_for_url(
      checkout_runner.CONTROLLED_SUPPORT_RETURNS_URL,
      timeout_seconds=20,
    )
    _wait_for_url(f"{base_url}/products", timeout_seconds=20)

    opt_in_run = tmp_path / "controlled_support"
    opt_in_manifest = asyncio.run(
      checkout_runner._run_capture(
        base_url=base_url,
        run_dir=opt_in_run,
        profile="checkout-co-sem-027",
        capture_controlled_support_destination=(
          checkout_runner._requires_controlled_support_destination_capture(
            "checkout-co-sem-027"
          )
        ),
      )
    )

    default_run = tmp_path / "default"
    default_manifest = asyncio.run(
      checkout_runner._run_capture(
        base_url=base_url,
        run_dir=default_run,
        profile=None,
        capture_controlled_support_destination=False,
      )
    )
  finally:
    if vite_server is not None:
      checkout_runner._stop_process(vite_server)
    if support_server is not None:
      checkout_runner._stop_process(support_server)

  assert [state["focused_state_name"] for state in opt_in_manifest["states"]] == [
    "products",
    "cart",
    "address",
    "payment",
    "review",
    checkout_runner.CONTROLLED_SUPPORT_DESTINATION_FOCUSED_STATE,
  ]
  assert opt_in_manifest["state_count"] == 6
  assert opt_in_manifest["transition_count"] == 5

  products_state = _state_by_focused_name(opt_in_manifest, "products")
  destination_state = _state_by_focused_name(
    opt_in_manifest,
    checkout_runner.CONTROLLED_SUPPORT_DESTINATION_FOCUSED_STATE,
  )
  assert (
    destination_state["benchmark_state_id"]
    == checkout_runner.CONTROLLED_SUPPORT_DESTINATION_BENCHMARK_STATE_ID
  )
  assert destination_state["parent_state_id"] == products_state["state_id"]

  transitions = _read_json(opt_in_run / "transitions.json")
  support_edge = _single(
    edge
    for edge in transitions
    if edge["from"] == products_state["state_id"]
    and edge["to"] == destination_state["state_id"]
  )
  trigger = support_edge["action"]["primary_trigger"]
  assert trigger["selector"] == checkout_runner.CONTROLLED_SUPPORT_LINK_SELECTOR
  assert trigger["data_testid"] == "support-returns"
  assert trigger["tag_name"] == "a"
  assert trigger["href"] == checkout_runner.CONTROLLED_SUPPORT_RETURNS_URL
  assert trigger["text"] == "Shipping information"
  assert trigger["accessible_name"] == "Shipping information"
  assert not any(edge["from"] == destination_state["state_id"] for edge in transitions)

  graph = _read_json(opt_in_run / "graph.json")
  node_by_id = {node["state_id"]: node for node in graph["nodes"]}
  destination_node = node_by_id[destination_state["state_id"]]
  assert destination_node["parent_state_id"] == products_state["state_id"]
  assert destination_node["url"] == checkout_runner.CONTROLLED_SUPPORT_RETURNS_URL
  assert destination_node["title"] == "Returns and refunds"

  destination_dir = opt_in_run / "states" / destination_state["state_id"]
  metadata = _read_json(destination_dir / "metadata.json")
  accessibility_context = _read_json(destination_dir / "accessibility_context.json")
  assert metadata["url"] == checkout_runner.CONTROLLED_SUPPORT_RETURNS_URL
  assert metadata["title"] == "Returns and refunds"
  assert metadata["route"] == checkout_runner.CONTROLLED_SUPPORT_RETURNS_PATH
  assert metadata["parent_state"] == products_state["state_id"]
  assert metadata["focused_acquisition"]["focused_state_name"] == (
    checkout_runner.CONTROLLED_SUPPORT_DESTINATION_FOCUSED_STATE
  )
  assert accessibility_context["page"]["url"] == (
    checkout_runner.CONTROLLED_SUPPORT_RETURNS_URL
  )
  assert accessibility_context["page"]["title"] == "Returns and refunds"
  assert any(
    heading.get("text") == "Returns and refunds"
    for heading in accessibility_context["headings"]
  )
  for filename in (
    "dom.html",
    "screenshot.png",
    "aria_snapshot.json",
    "accessibility_context.json",
    "metadata.json",
  ):
    assert (destination_dir / filename).exists()

  summary = build_semantic_candidates(
    opt_in_run,
    candidate_types=["link-text-mismatch"],
  )
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")
  support_candidate = _single(
    record
    for record in records
    if record["evidence"]["primary"]["link"]["href"]
    == checkout_runner.CONTROLLED_SUPPORT_RETURNS_URL
  )
  link = support_candidate["evidence"]["primary"]["link"]
  assert link["accessible_name"] == "Shipping information"
  assert link["href"] == checkout_runner.CONTROLLED_SUPPORT_RETURNS_URL
  supporting = support_candidate["evidence"]["supporting"]
  link_context = supporting["link_destination_context_v1"]
  assert link_context["resolved_url"] == checkout_runner.CONTROLLED_SUPPORT_RETURNS_URL
  assert link_context["resolved_path"] == (
    checkout_runner.CONTROLLED_SUPPORT_RETURNS_PATH
  )
  assert link_context["match_status"] == "external_or_out_of_scope"

  destination_context = supporting["destination_state_context_v1"]
  assert destination_context["source_state_id"] == products_state["state_id"]
  assert destination_context["match_basis"] == ["data_testid"]
  assert destination_context["match_count"] == 1
  captured_destination = destination_context["destinations"][0]
  assert captured_destination["target_state_id"] == destination_state["state_id"]
  assert captured_destination["target_url"] == (
    checkout_runner.CONTROLLED_SUPPORT_RETURNS_URL
  )
  assert captured_destination["target_title"] == "Returns and refunds"
  assert captured_destination["target_primary_headings"][0]["text"] == (
    "Returns and refunds"
  )
  assert captured_destination["trigger"]["data_testid"] == "support-returns"
  assert captured_destination["trigger"]["href"] == (
    checkout_runner.CONTROLLED_SUPPORT_RETURNS_URL
  )
  assert captured_destination["trigger"]["text"] == "Shipping information"
  assert captured_destination["trigger"]["accessible_name"] == (
    "Shipping information"
  )
  parsed_target = urlparse(captured_destination["target_url"])
  assert parsed_target.netloc == "127.0.0.1:8771"
  assert parsed_target.path == checkout_runner.CONTROLLED_SUPPORT_RETURNS_PATH

  clean_shipping_candidate = _single(
    record
    for record in records
    if urlparse(record["evidence"]["primary"]["link"]["href"]).path
    == "/shipping-information.html"
  )
  clean_shipping_link = clean_shipping_candidate["evidence"]["primary"]["link"]
  assert clean_shipping_link["text"] == "Shipping information"
  assert clean_shipping_link["accessible_name"] == "Shipping information"
  clean_shipping_context = clean_shipping_candidate["evidence"]["supporting"][
    "link_destination_context_v1"
  ]
  assert clean_shipping_context["resolved_path"] == "/shipping-information.html"
  assert clean_shipping_context["match_status"] == "external_or_out_of_scope"
  assert "destination_state_context_v1" not in clean_shipping_candidate[
    "evidence"
  ]["supporting"]

  assert [
    state["focused_state_name"]
    for state in default_manifest["states"]
  ] == ["products", "cart", "address", "payment", "review"]
  assert default_manifest["state_count"] == 5
  assert default_manifest["transition_count"] == 4
  default_transitions = _read_json(default_run / "transitions.json")
  assert not any(
    edge.get("action", {}).get("primary_trigger", {}).get("data_testid")
    == "support-returns"
    for edge in default_transitions
  )


def test_co_sem_102_requires_opaque_shipping_activation_context(tmp_path):
  pytest.importorskip("playwright.async_api")
  from scripts.benchmarks.checkout import runner as checkout_runner

  _require_vite_preview()
  if not _port_available(
    checkout_runner.CONTROLLED_SUPPORT_HOST,
    checkout_runner.CONTROLLED_SUPPORT_PORT,
  ):
    pytest.skip(
      "Controlled support test requires 127.0.0.1:8771 to be available."
    )

  support_server: subprocess.Popen[str] | None = None
  vite_server: subprocess.Popen[str] | None = None
  try:
    support_server = checkout_runner._start_controlled_support_server()
    vite_port = _find_free_port()
    vite_server = checkout_runner._start_vite_preview(port=vite_port)
    base_url = f"http://127.0.0.1:{vite_port}"

    checkout_runner._wait_for_url(
      checkout_runner.CONTROLLED_SUPPORT_RESOURCE_URL,
      timeout_seconds=20,
    )
    _wait_for_url(f"{base_url}/products", timeout_seconds=20)

    source_only_run = tmp_path / "source_only"
    source_only_manifest = asyncio.run(
      checkout_runner._run_capture(
        base_url=base_url,
        run_dir=source_only_run,
        profile="checkout-co-sem-102",
        capture_controlled_support_destination=False,
      )
    )
    destination_run = tmp_path / "destination_capture"
    destination_manifest = asyncio.run(
      checkout_runner._run_capture(
        base_url=base_url,
        run_dir=destination_run,
        profile="checkout-co-sem-102",
        capture_controlled_support_destination=True,
      )
    )
  finally:
    if vite_server is not None:
      checkout_runner._stop_process(vite_server)
    if support_server is not None:
      checkout_runner._stop_process(support_server)

  assert source_only_manifest["state_count"] == 5
  assert source_only_manifest["transition_count"] == 4
  assert destination_manifest["state_count"] == 6
  assert destination_manifest["transition_count"] == 5

  source_products = _state_by_focused_name(source_only_manifest, "products")
  destination_products = _state_by_focused_name(destination_manifest, "products")
  destination_state = _state_by_focused_name(
    destination_manifest,
    checkout_runner.CONTROLLED_SUPPORT_DESTINATION_FOCUSED_STATE,
  )
  transitions = _read_json(destination_run / "transitions.json")
  support_edge = _single(
    edge
    for edge in transitions
    if edge["from"] == destination_products["state_id"]
    and edge["to"] == destination_state["state_id"]
  )
  trigger = support_edge["action"]["primary_trigger"]
  assert trigger["selector"] == checkout_runner.CONTROLLED_SUPPORT_SHIPPING_LINK_SELECTOR
  assert trigger["data_testid"] == "support-shipping"
  assert trigger["href"] == checkout_runner.CONTROLLED_SUPPORT_RESOURCE_URL
  assert trigger["text"] == "Shipping information"
  assert trigger["accessible_name"] == "Shipping information"
  destination_metadata = _read_json(
    destination_run
    / "states"
    / destination_state["state_id"]
    / "metadata.json"
  )
  assert destination_metadata["url"] == checkout_runner.CONTROLLED_SUPPORT_RETURNS_URL
  assert destination_metadata["title"] == "Returns and refunds"

  registry_path = REPO_ROOT / "benchmarks" / "registry" / "benchmark-case-registry.json"
  scored_runs = []
  for run_dir, state_id, expected_recovered in (
    (source_only_run, source_products["state_id"], 0),
    (destination_run, destination_products["state_id"], 1),
  ):
    summary = build_semantic_candidates(run_dir)
    records = _read_jsonl(summary.output_dir / "candidates.jsonl")
    shipping_candidate = _single(
      record
      for record in records
      if record["state_id"] == state_id
      and record["candidate_type"] == "link-text-mismatch"
      and record["evidence"]["primary"]["link"]["text"]
      == "Shipping information"
      and record["evidence"]["supporting"]["structure"]["nearest_heading"][
        "text"
      ]
      == "Shipping help"
    )
    supporting = shipping_candidate["evidence"]["supporting"]
    assert supporting["context"]["nearby_text"] == (
      "Learn about delivery times and available shipping options."
    )
    assert supporting["link_destination_context_v1"]["resolved_path"] == (
      checkout_runner.CONTROLLED_SUPPORT_RESOURCE_PATH
    )
    if expected_recovered:
      destination_context = supporting["destination_state_context_v1"]
      assert destination_context["source_state_id"] == state_id
      assert destination_context["match_basis"] == ["data_testid"]
      assert destination_context["match_count"] == 1
      captured = destination_context["destinations"][0]
      assert captured["target_title"] == "Returns and refunds"
      assert captured["target_route"] == checkout_runner.CONTROLLED_SUPPORT_RETURNS_PATH
      assert captured["target_primary_headings"][0]["text"] == (
        "Returns and refunds"
      )
      assert captured["trigger"]["data_testid"] == "support-shipping"
      assert captured["trigger"]["href"] == (
        checkout_runner.CONTROLLED_SUPPORT_RESOURCE_URL
      )
    else:
      assert "destination_state_context_v1" not in supporting

    score_result = score_seeded_experiment(
      SeededScorerOptions(
        run_dir=run_dir,
        config_id="checkout-co-sem-102",
        registry_path=registry_path,
        score_run_id=f"score_{run_dir.name}",
      )
    )
    assert score_result.summary["counts"]["recovered_seeds"] == expected_recovered
    scored_runs.append((shipping_candidate["candidate_id"], expected_recovered))

  assert scored_runs[0][1] == 0
  assert scored_runs[1][1] == 1


def test_controlled_support_destination_capture_profile_membership_is_narrow():
  pytest.importorskip("playwright.async_api")
  from scripts.benchmarks.checkout import runner as checkout_runner

  assert checkout_runner._requires_controlled_support_destination_capture(
    "checkout-co-sem-027"
  )
  assert checkout_runner._requires_controlled_support_destination_capture(
    "checkout-co-sem-102"
  )
  for case_number in range(20, 27):
    assert not checkout_runner._requires_controlled_support_destination_capture(
      f"checkout-co-sem-{case_number:03d}"
    )
  assert not checkout_runner._requires_controlled_support_destination_capture(None)
  assert not checkout_runner._requires_controlled_support_destination_capture(
    "checkout-clean-v1"
  )


def test_co_sem_101_profile_keeps_shipping_context_with_returns_path(tmp_path):
  pytest.importorskip("playwright.async_api")
  from scripts.benchmarks.checkout import runner as checkout_runner

  _require_vite_preview()

  vite_server: subprocess.Popen[str] | None = None
  try:
    vite_port = _find_free_port()
    vite_server = checkout_runner._start_vite_preview(port=vite_port)
    base_url = f"http://127.0.0.1:{vite_port}"
    _wait_for_url(f"{base_url}/products", timeout_seconds=20)

    run_dir = tmp_path / "shipping_wrong_destination"
    manifest = asyncio.run(
      checkout_runner._run_capture(
        base_url=base_url,
        run_dir=run_dir,
        profile="checkout-co-sem-101",
        capture_controlled_support_destination=False,
      )
    )
  finally:
    if vite_server is not None:
      checkout_runner._stop_process(vite_server)

  assert [state["focused_state_name"] for state in manifest["states"]] == [
    "products",
    "cart",
    "address",
    "payment",
    "review",
  ]
  assert manifest["state_count"] == 5
  assert manifest["transition_count"] == 4
  products_state = _state_by_focused_name(manifest, "products")
  assert products_state["state_id"] == "state_0000"
  assert products_state["benchmark_state_id"] == "CO-S001"
  assert products_state["route"] == "/products"

  summary = build_semantic_candidates(
    run_dir,
    candidate_types=["link-text-mismatch"],
  )
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")
  shipping_candidate = _single(
    record
    for record in records
    if record["state_id"] == products_state["state_id"]
    and record["evidence"]["primary"]["link"]["text"]
    == "Shipping information"
    and record["evidence"]["supporting"]["structure"]["nearest_heading"][
      "text"
    ]
    == "Shipping help"
  )

  assert shipping_candidate["candidate_id"].startswith("cand_")
  link = shipping_candidate["evidence"]["primary"]["link"]
  assert link["tag"] == "a"
  assert link["text"] == "Shipping information"
  assert link["accessible_name"] == "Shipping information"
  assert link["aria_label"] is None
  supporting = shipping_candidate["evidence"]["supporting"]
  assert supporting["context"]["nearby_text"] == (
    "Learn about delivery times and available shipping options."
  )
  assert supporting["structure"]["nearest_heading"]["tag"] == "h3"
  destination = supporting["link_destination_context_v1"]
  assert destination["resolved_path"] == "/returns-and-refunds.html"
  assert destination["match_status"] == "external_or_out_of_scope"
  assert "destination_state_context_v1" not in supporting

  transitions = _read_json(run_dir / "transitions.json")
  assert not any(
    edge.get("action", {}).get("primary_trigger", {}).get("data_testid")
    == "support-shipping"
    for edge in transitions
  )


def test_co_sem_089_profile_captures_delivery_estimate_wrong_result(tmp_path):
  pytest.importorskip("playwright.async_api")
  from scripts.benchmarks.checkout import runner as checkout_runner

  _require_vite_preview()

  vite_server: subprocess.Popen[str] | None = None
  try:
    vite_port = _find_free_port()
    vite_server = checkout_runner._start_vite_preview(port=vite_port)
    base_url = f"http://127.0.0.1:{vite_port}"
    _wait_for_url(f"{base_url}/products", timeout_seconds=20)

    opt_in_run = tmp_path / "delivery_wrong_result"
    opt_in_manifest = asyncio.run(
      checkout_runner._run_capture(
        base_url=base_url,
        run_dir=opt_in_run,
        profile="checkout-co-sem-089",
        capture_controlled_support_destination=False,
      )
    )

    default_run = tmp_path / "default"
    default_manifest = asyncio.run(
      checkout_runner._run_capture(
        base_url=base_url,
        run_dir=default_run,
        profile=None,
        capture_controlled_support_destination=False,
      )
    )
  finally:
    if vite_server is not None:
      checkout_runner._stop_process(vite_server)

  assert [state["focused_state_name"] for state in opt_in_manifest["states"]] == [
    "products",
    "cart",
    checkout_runner.DELIVERY_ESTIMATE_WRONG_RESULT_FOCUSED_STATE,
    "address",
    "payment",
    "review",
  ]
  assert opt_in_manifest["state_count"] == 6
  assert opt_in_manifest["transition_count"] == 5

  cart_state = _state_by_focused_name(opt_in_manifest, "cart")
  destination_state = _state_by_focused_name(
    opt_in_manifest,
    checkout_runner.DELIVERY_ESTIMATE_WRONG_RESULT_FOCUSED_STATE,
  )
  assert (
    destination_state["benchmark_state_id"]
    == checkout_runner.DELIVERY_ESTIMATE_WRONG_RESULT_BENCHMARK_STATE_ID
  )
  assert destination_state["parent_state_id"] == cart_state["state_id"]

  transitions = _read_json(opt_in_run / "transitions.json")
  delivery_edge = _single(
    edge
    for edge in transitions
    if edge["from"] == cart_state["state_id"]
    and edge["to"] == destination_state["state_id"]
  )
  trigger = delivery_edge["action"]["primary_trigger"]
  assert trigger["selector"] == checkout_runner.DELIVERY_ESTIMATE_TRIGGER_SELECTOR
  assert trigger["data_testid"] == "delivery-estimate-trigger"
  assert trigger["tag_name"] == "button"
  assert trigger["button_type"] == "button"
  assert trigger["text"] == "Delivery estimate"
  assert trigger["accessible_name"] == "Delivery estimate"

  destination_dir = opt_in_run / "states" / destination_state["state_id"]
  metadata = _read_json(destination_dir / "metadata.json")
  accessibility_context = _read_json(destination_dir / "accessibility_context.json")
  assert metadata["route"] == "/cart"
  assert metadata["parent_state"] == cart_state["state_id"]
  assert metadata["focused_acquisition"]["focused_state_name"] == (
    checkout_runner.DELIVERY_ESTIMATE_WRONG_RESULT_FOCUSED_STATE
  )
  assert any(
    heading.get("text") == "Shipping information"
    for heading in accessibility_context["headings"]
  )
  assert any(
    button.get("text") == "Close"
    for button in accessibility_context["buttons"]
  )

  summary = build_semantic_candidates(
    opt_in_run,
    candidate_types=["button-label-mismatch"],
  )
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")
  delivery_candidate = _single(
    record
    for record in records
    if record["state_id"] == cart_state["state_id"]
    and record["evidence"]["supporting"]["button_action_context_v1"][
      "action_evidence"
    ]["data_testid"]
    == "delivery-estimate-trigger"
  )
  button = delivery_candidate["evidence"]["primary"]["button"]
  assert button["text"] == "Delivery estimate"
  assert button["accessible_name"] == "Delivery estimate"
  assert button["aria_label"] is None
  supporting = delivery_candidate["evidence"]["supporting"]

  destination_context = supporting["destination_state_context_v1"]
  assert destination_context["source_state_id"] == cart_state["state_id"]
  assert destination_context["match_basis"] == ["data_testid"]
  assert destination_context["match_count"] == 1
  captured_destination = destination_context["destinations"][0]
  assert captured_destination["target_state_id"] == destination_state["state_id"]
  assert captured_destination["target_route"] == "/cart"
  assert captured_destination["trigger"]["data_testid"] == "delivery-estimate-trigger"
  assert captured_destination["trigger"]["text"] == "Delivery estimate"
  assert captured_destination["trigger"]["accessible_name"] == "Delivery estimate"

  action_evidence = supporting["button_action_context_v1"]["action_evidence"]
  assert action_evidence["matched_outgoing_transition"]["from_state"] == (
    cart_state["state_id"]
  )
  assert action_evidence["matched_outgoing_transition"]["to_state"] == (
    destination_state["state_id"]
  )
  assert action_evidence["matched_outgoing_transition"]["trigger"]["data_testid"] == (
    "delivery-estimate-trigger"
  )
  assert any(
    heading == "Shipping information"
    for heading in action_evidence["result_state_context"]["headings"]
  )

  assert [
    state["focused_state_name"]
    for state in default_manifest["states"]
  ] == ["products", "cart", "address", "payment", "review"]
  assert default_manifest["state_count"] == 5
  assert default_manifest["transition_count"] == 4
  default_transitions = _read_json(default_run / "transitions.json")
  assert not any(
    edge.get("action", {}).get("primary_trigger", {}).get("data_testid")
    == "delivery-estimate-trigger"
    for edge in default_transitions
  )


def test_delivery_estimate_wrong_result_capture_profile_membership_is_narrow():
  from scripts.benchmarks.checkout import runner as checkout_runner

  assert checkout_runner._requires_delivery_estimate_result_capture(
    "checkout-co-sem-089"
  )
  for profile in (
    None,
    "checkout-clean-v1",
    "checkout-co-sem-028",
    "checkout-co-sem-029",
    "checkout-co-sem-031",
    "checkout-co-sem-032",
    "checkout-co-sem-035",
    "checkout-co-sem-088",
  ):
    assert not checkout_runner._requires_delivery_estimate_result_capture(profile)


def test_co_sem_103_profile_captures_continue_to_payment_wrong_result(tmp_path):
  pytest.importorskip("playwright.async_api")
  from scripts.benchmarks.checkout import runner as checkout_runner

  _require_vite_preview()

  vite_server: subprocess.Popen[str] | None = None
  try:
    vite_port = _find_free_port()
    vite_server = checkout_runner._start_vite_preview(port=vite_port)
    base_url = f"http://127.0.0.1:{vite_port}"
    _wait_for_url(f"{base_url}/products", timeout_seconds=20)

    opt_in_run = tmp_path / "address_wrong_result"
    opt_in_manifest = asyncio.run(
      checkout_runner._run_capture(
        base_url=base_url,
        run_dir=opt_in_run,
        profile="checkout-co-sem-103",
        capture_controlled_support_destination=False,
      )
    )

    default_run = tmp_path / "default"
    default_manifest = asyncio.run(
      checkout_runner._run_capture(
        base_url=base_url,
        run_dir=default_run,
        profile=None,
        capture_controlled_support_destination=False,
      )
    )
  finally:
    if vite_server is not None:
      checkout_runner._stop_process(vite_server)

  assert [state["focused_state_name"] for state in opt_in_manifest["states"]] == [
    "products",
    "cart",
    "address",
    checkout_runner.ADDRESS_CONTINUE_WRONG_RESULT_FOCUSED_STATE,
  ]
  assert opt_in_manifest["state_count"] == 4
  assert opt_in_manifest["transition_count"] == 3

  address_state = _state_by_focused_name(opt_in_manifest, "address")
  destination_state = _state_by_focused_name(
    opt_in_manifest,
    checkout_runner.ADDRESS_CONTINUE_WRONG_RESULT_FOCUSED_STATE,
  )
  assert address_state["benchmark_state_id"] == "CO-S003"
  assert destination_state["benchmark_state_id"] == (
    checkout_runner.ADDRESS_CONTINUE_WRONG_RESULT_BENCHMARK_STATE_ID
  )
  assert destination_state["parent_state_id"] == address_state["state_id"]

  transitions = _read_json(opt_in_run / "transitions.json")
  result_edge = _single(
    edge
    for edge in transitions
    if edge["from"] == address_state["state_id"]
    and edge["to"] == destination_state["state_id"]
  )
  trigger = result_edge["action"]["primary_trigger"]
  assert trigger["selector"] == checkout_runner.ADDRESS_CONTINUE_TO_PAYMENT_SELECTOR
  assert trigger["data_testid"] == "continue-to-payment"
  assert trigger["tag_name"] == "button"
  assert trigger["button_type"] == "submit"
  assert trigger["text"] == "Continue to payment"
  assert trigger["accessible_name"] == "Continue to payment"

  destination_dir = opt_in_run / "states" / destination_state["state_id"]
  metadata = _read_json(destination_dir / "metadata.json")
  accessibility_context = _read_json(destination_dir / "accessibility_context.json")
  assert metadata["route"] == "/cart"
  assert metadata["title"] == "Cart | Brightlane Checkout"
  assert metadata["parent_state"] == address_state["state_id"]
  assert any(
    heading.get("text") == "Cart"
    for heading in accessibility_context["headings"]
  )

  summary = build_semantic_candidates(
    opt_in_run,
    candidate_types=["button-label-mismatch"],
  )
  records = _read_jsonl(summary.output_dir / "candidates.jsonl")
  source_candidate = _single(
    record
    for record in records
    if record["state_id"] == address_state["state_id"]
    and record["evidence"]["supporting"]["button_action_context_v1"][
      "action_evidence"
    ]["data_testid"]
    == "continue-to-payment"
  )
  button = source_candidate["evidence"]["primary"]["button"]
  assert button["text"] == "Continue to payment"
  assert button["accessible_name"] == "Continue to payment"
  assert button["aria_label"] is None
  assert button["type"] == "submit"
  assert button["disabled"] is False

  supporting = source_candidate["evidence"]["supporting"]
  destination_context = supporting["destination_state_context_v1"]
  assert destination_context["source_state_id"] == address_state["state_id"]
  assert destination_context["match_basis"] == ["data_testid"]
  assert destination_context["match_count"] == 1
  captured_destination = destination_context["destinations"][0]
  assert captured_destination["target_state_id"] == destination_state["state_id"]
  assert captured_destination["target_route"] == "/cart"
  assert captured_destination["target_title"] == "Cart | Brightlane Checkout"
  assert captured_destination["target_primary_headings"][0]["text"] == "Cart"
  assert captured_destination["trigger"]["data_testid"] == "continue-to-payment"

  action_evidence = supporting["button_action_context_v1"]["action_evidence"]
  assert action_evidence["matched_outgoing_transition"]["from_state"] == (
    address_state["state_id"]
  )
  assert action_evidence["matched_outgoing_transition"]["to_state"] == (
    destination_state["state_id"]
  )
  assert action_evidence["result_state_context"]["route"] == "/cart"
  assert action_evidence["result_state_context"]["title"] == (
    "Cart | Brightlane Checkout"
  )
  assert "Cart" in action_evidence["result_state_context"]["headings"]

  assert [
    state["focused_state_name"]
    for state in default_manifest["states"]
  ] == ["products", "cart", "address", "payment", "review"]
  default_summary = build_semantic_candidates(
    default_run,
    candidate_types=["button-label-mismatch"],
  )
  default_records = _read_jsonl(default_summary.output_dir / "candidates.jsonl")
  default_address = _state_by_focused_name(default_manifest, "address")
  default_candidate = _single(
    record
    for record in default_records
    if record["state_id"] == default_address["state_id"]
    and record["evidence"]["supporting"]["button_action_context_v1"][
      "action_evidence"
    ]["data_testid"]
    == "continue-to-payment"
  )
  default_destinations = default_candidate["evidence"]["supporting"][
    "destination_state_context_v1"
  ]["destinations"]
  assert [item["target_route"] for item in default_destinations] == [
    "/checkout/payment"
  ]


def test_co_sem_104_profile_captures_wrong_object_result_and_controls(tmp_path):
  pytest.importorskip("playwright.async_api")
  from scripts.benchmarks.checkout import runner as checkout_runner

  _require_vite_preview()

  vite_server: subprocess.Popen[str] | None = None
  try:
    vite_port = _find_free_port()
    vite_server = checkout_runner._start_vite_preview(port=vite_port)
    base_url = f"http://127.0.0.1:{vite_port}"
    _wait_for_url(f"{base_url}/products", timeout_seconds=20)

    seeded_run = tmp_path / "seeded_desk_increment"
    seeded_manifest = asyncio.run(
      checkout_runner._run_capture(
        base_url=base_url,
        run_dir=seeded_run,
        profile="checkout-co-sem-104",
        capture_controlled_support_destination=False,
      )
    )

    clean_run = tmp_path / "clean_desk_increment"
    clean_manifest = asyncio.run(
      checkout_runner._run_capture(
        base_url=base_url,
        run_dir=clean_run,
        profile=checkout_runner.CLEAN_PROFILE,
        capture_controlled_support_destination=False,
        cart_quantity_result_trigger_selector=(
          checkout_runner.DESK_LAMP_INCREMENT_SELECTOR
        ),
      )
    )

    other_control_run = tmp_path / "clean_notebook_increment"
    other_control_manifest = asyncio.run(
      checkout_runner._run_capture(
        base_url=base_url,
        run_dir=other_control_run,
        profile=checkout_runner.CLEAN_PROFILE,
        capture_controlled_support_destination=False,
        cart_quantity_result_trigger_selector=(
          checkout_runner.NOTEBOOK_SET_INCREMENT_SELECTOR
        ),
      )
    )
  finally:
    if vite_server is not None:
      checkout_runner._stop_process(vite_server)

  for manifest in (seeded_manifest, clean_manifest, other_control_manifest):
    assert [state["focused_state_name"] for state in manifest["states"]] == [
      "products",
      "cart",
      checkout_runner.CART_QUANTITY_RESULT_FOCUSED_STATE,
    ]
    assert manifest["state_count"] == 3
    assert manifest["transition_count"] == 2

  source_state = _state_by_focused_name(seeded_manifest, "cart")
  result_state = _state_by_focused_name(
    seeded_manifest,
    checkout_runner.CART_QUANTITY_RESULT_FOCUSED_STATE,
  )
  assert source_state["benchmark_state_id"] == "CO-S002"
  assert result_state["benchmark_state_id"] == (
    checkout_runner.CART_QUANTITY_RESULT_BENCHMARK_STATE_ID
  )
  assert result_state["parent_state_id"] == source_state["state_id"]

  transitions = _read_json(seeded_run / "transitions.json")
  result_edge = _single(
    edge
    for edge in transitions
    if edge["from"] == source_state["state_id"]
    and edge["to"] == result_state["state_id"]
  )
  trigger = result_edge["action"]["primary_trigger"]
  assert trigger["selector"] == checkout_runner.DESK_LAMP_INCREMENT_SELECTOR
  assert trigger["data_testid"] == "cart-increment-prod-desk-lamp"
  assert trigger["tag_name"] == "button"
  assert trigger["button_type"] == "button"
  assert trigger["text"] == "+"
  assert trigger["accessible_name"] == "Increase Desk lamp quantity"

  source_context = _read_json(
    seeded_run
    / "states"
    / source_state["state_id"]
    / "accessibility_context.json"
  )
  result_context = _read_json(
    seeded_run
    / "states"
    / result_state["state_id"]
    / "accessibility_context.json"
  )

  def quantity_group(context, accessible_name):
    return _single(
      cue
      for cue in context["visual_cues"]
      if cue.get("accessible_name") == accessible_name
    )

  assert quantity_group(
    source_context,
    "Desk lamp quantity controls",
  )["text"] == "- 1 +"
  assert quantity_group(
    source_context,
    "Notebook set quantity controls",
  )["text"] == "- 1 +"
  assert quantity_group(
    result_context,
    "Desk lamp quantity controls",
  )["text"] == "- 1 +"
  assert quantity_group(
    result_context,
    "Notebook set quantity controls",
  )["text"] == "- 2 +"

  expected_destination_elements = {
    (
      "visual_cues",
      "Desk lamp quantity controls",
      "- 1 +",
    ),
    (
      "visual_cues",
      "Notebook set quantity controls",
      "- 2 +",
    ),
  }

  def build_and_find_candidate(run_dir, manifest, expected_testid):
    summary = build_semantic_candidates(
      run_dir,
      candidate_types=["button-label-mismatch"],
    )
    records = _read_jsonl(summary.output_dir / "candidates.jsonl")
    cart_state = _state_by_focused_name(manifest, "cart")
    return _single(
      record
      for record in records
      if record["state_id"] == cart_state["state_id"]
      and record["evidence"]["supporting"]["button_action_context_v1"][
        "action_evidence"
      ]["data_testid"]
      == expected_testid
    )

  seeded_candidate = build_and_find_candidate(
    seeded_run,
    seeded_manifest,
    "cart-increment-prod-desk-lamp",
  )
  button = seeded_candidate["evidence"]["primary"]["button"]
  assert button["text"] == "+"
  assert button["accessible_name"] == "Increase Desk lamp quantity"
  assert button["aria_label"] == "Increase Desk lamp quantity"
  assert button["type"] == "button"
  assert button["disabled"] is False
  supporting = seeded_candidate["evidence"]["supporting"]
  assert supporting["structure"]["nearest_heading"]["text"] == "Desk lamp"
  destination_context = supporting["destination_state_context_v1"]
  assert destination_context["source_state_id"] == source_state["state_id"]
  assert destination_context["match_basis"] == ["data_testid"]
  assert destination_context["match_count"] == 1
  captured_destination = destination_context["destinations"][0]
  assert captured_destination["target_state_id"] == result_state["state_id"]
  assert captured_destination["target_route"] == "/cart"
  assert captured_destination["target_title"] == "Cart | Brightlane Checkout"
  assert captured_destination["target_primary_headings"][0]["text"] == "Cart"
  assert captured_destination["trigger"]["data_testid"] == (
    "cart-increment-prod-desk-lamp"
  )
  compact_elements = {
    (
      element.get("bucket"),
      element.get("accessible_name"),
      element.get("text"),
    )
    for element in captured_destination["target_elements"]
  }
  assert expected_destination_elements <= compact_elements
  assert len(captured_destination["target_elements"]) <= 40

  clean_candidate = build_and_find_candidate(
    clean_run,
    clean_manifest,
    "cart-increment-prod-desk-lamp",
  )
  clean_destination = clean_candidate["evidence"]["supporting"][
    "destination_state_context_v1"
  ]["destinations"][0]
  clean_elements = {
    (element.get("accessible_name"), element.get("text"))
    for element in clean_destination["target_elements"]
  }
  assert ("Desk lamp quantity controls", "- 2 +") in clean_elements
  assert ("Notebook set quantity controls", "- 1 +") in clean_elements

  other_candidate = build_and_find_candidate(
    other_control_run,
    other_control_manifest,
    "cart-increment-prod-notebook-set",
  )
  assert other_candidate["evidence"]["primary"]["button"]["accessible_name"] == (
    "Increase Notebook set quantity"
  )

  def recovery_count(run_dir, score_run_id):
    result = score_seeded_experiment(
      SeededScorerOptions(
        run_dir=run_dir,
        config_id="checkout-co-sem-104",
        score_run_id=score_run_id,
      )
    )
    return result.summary["counts"]["recovered_seeds"]

  assert recovery_count(seeded_run, "co_sem_104_seeded") == 1
  assert recovery_count(clean_run, "co_sem_104_clean") == 0
  assert recovery_count(other_control_run, "co_sem_104_other_control") == 0


def test_cart_quantity_result_capture_profile_membership_is_narrow():
  from scripts.benchmarks.checkout import runner as checkout_runner

  assert checkout_runner._requires_cart_quantity_result_capture(
    "checkout-co-sem-104"
  )
  for profile in (
    None,
    "checkout-clean-v1",
    "checkout-co-sem-089",
    "checkout-co-sem-103",
    "checkout-co-sem-131",
  ):
    assert not checkout_runner._requires_cart_quantity_result_capture(profile)


def test_two_item_review_profile_membership_is_narrow():
  from scripts.benchmarks.checkout import runner as checkout_runner

  for profile in ("checkout-co-sem-131", "checkout-co-sem-132"):
    assert checkout_runner._requires_two_item_review(profile)
  for profile in (
    None,
    "checkout-clean-v1",
    "checkout-co-sem-074",
    "checkout-co-sem-075",
    "checkout-co-sem-138",
  ):
    assert not checkout_runner._requires_two_item_review(profile)


def test_language_switch_profile_mapping_includes_stale_result_cases():
  from scripts.benchmarks.checkout import runner as checkout_runner

  assert checkout_runner._is_language_switch_profile("checkout-co-sem-130")
  assert (
    checkout_runner.LANGUAGE_SWITCH_SPANISH_ROOT_LANG_BY_PROFILE[
      "checkout-co-sem-130"
    ]
    == "es"
  )
  assert (
    checkout_runner.LANGUAGE_SWITCH_SPANISH_ARIA_PRESSED_BY_PROFILE[
      "checkout-co-sem-130"
    ]
    == "false"
  )
  assert checkout_runner._is_language_switch_profile("checkout-co-sem-137")
  assert (
    checkout_runner.LANGUAGE_SWITCH_SPANISH_ROOT_LANG_BY_PROFILE[
      "checkout-co-sem-137"
    ]
    == "es"
  )
  assert checkout_runner._requires_language_switch_back_capture(
    "checkout-co-sem-137"
  )
  assert checkout_runner.LANGUAGE_SWITCH_BACK_BENCHMARK_STATE_ID == "CO-S020"
  for profile in (None, "checkout-clean-v1", "checkout-co-sem-129"):
    assert not checkout_runner._is_language_switch_profile(profile)
    assert not checkout_runner._requires_language_switch_back_capture(profile)


def test_address_continue_wrong_result_capture_profile_membership_is_narrow():
  from scripts.benchmarks.checkout import runner as checkout_runner

  assert checkout_runner._requires_address_continue_wrong_result_capture(
    "checkout-co-sem-103"
  )
  for profile in (
    None,
    "checkout-clean-v1",
    "checkout-co-sem-089",
    "checkout-co-sem-100",
    "checkout-co-sem-104",
  ):
    assert not checkout_runner._requires_address_continue_wrong_result_capture(profile)


def test_empty_cart_capture_profile_membership_is_narrow():
  from scripts.benchmarks.checkout import runner as checkout_runner

  assert checkout_runner._requires_empty_cart_capture("checkout-co-sem-092")
  for profile in (
    None,
    "checkout-clean-v1",
    "checkout-co-sem-047",
    "checkout-co-sem-091",
    "checkout-co-sem-093",
  ):
    assert not checkout_runner._requires_empty_cart_capture(profile)


def test_gift_receipt_enabled_capture_profile_membership_is_narrow():
  from scripts.benchmarks.checkout import runner as checkout_runner

  assert checkout_runner._requires_gift_receipt_enabled_capture(
    "checkout-co-sem-070"
  )
  for profile in (
    None,
    "checkout-clean-v1",
    "checkout-co-sem-066",
    "checkout-co-sem-067",
    "checkout-co-sem-068",
    "checkout-co-sem-069",
    "checkout-co-sem-071",
    "checkout-co-sem-072",
    "checkout-co-sem-090",
  ):
    assert not checkout_runner._requires_gift_receipt_enabled_capture(profile)


def test_save_cart_active_capture_profile_membership_is_narrow():
  from scripts.benchmarks.checkout import runner as checkout_runner

  assert checkout_runner._requires_save_cart_active_capture(
    "checkout-co-sem-072"
  )
  for profile in (
    None,
    "checkout-clean-v1",
    "checkout-co-sem-066",
    "checkout-co-sem-067",
    "checkout-co-sem-068",
    "checkout-co-sem-069",
    "checkout-co-sem-070",
    "checkout-co-sem-071",
    "checkout-co-sem-073",
    "checkout-co-sem-090",
  ):
    assert not checkout_runner._requires_save_cart_active_capture(profile)


def _require_vite_preview() -> None:
  vite_bin = CHECKOUT_DIR / "node_modules" / "vite" / "bin" / "vite.js"
  if not vite_bin.exists():
    pytest.skip(f"Vite executable is unavailable: {vite_bin}")
  dist_index = CHECKOUT_DIR / "dist" / "index.html"
  if not dist_index.exists():
    pytest.skip(f"Checkout preview build is unavailable: {dist_index}")


def _find_free_port() -> int:
  with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
    sock.bind(("127.0.0.1", 0))
    return int(sock.getsockname()[1])


def _port_available(host: str, port: int) -> bool:
  with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
    try:
      sock.bind((host, port))
    except OSError:
      return False
    return True


def _wait_for_url(url: str, *, timeout_seconds: int) -> None:
  deadline = time.perf_counter() + timeout_seconds
  last_error: Exception | None = None
  while time.perf_counter() < deadline:
    try:
      with urlopen(url, timeout=1) as response:
        if response.status == 200:
          return
    except Exception as error:
      last_error = error
      time.sleep(0.25)
  raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def _read_json(path: Path):
  return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, object]]:
  return [
    json.loads(line)
    for line in path.read_text(encoding="utf-8").splitlines()
    if line.strip()
  ]


def _state_by_focused_name(manifest: dict[str, object], focused_name: str):
  return _single(
    state
    for state in manifest["states"]
    if state["focused_state_name"] == focused_name
  )


def _single(items):
  matches = list(items)
  assert len(matches) == 1
  return matches[0]
