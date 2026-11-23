from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from src.analysis.evaluation.benchmark_registry import load_benchmark_registry
from src.analysis.evaluation.seeded_scorer import (
  _candidate_matches_expected_evidence,
  _candidate_route_matches,
  _element_matches_expected,
  _state_matches_expected_constraints,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = REPO_ROOT / "benchmarks" / "registry" / "benchmark-case-registry.json"

EXPECTED_FAMILY_COUNTS = {
  "autocomplete-purpose-mismatch": 15,
  "aria-state-mismatch": 15,
  "button-label-mismatch": 11,
  "error-message-mismatch": 13,
  "form-label-mismatch": 12,
  "heading-not-descriptive": 10,
  "image-alt-not-descriptive": 7,
  "landmark-purpose-mismatch": 8,
  "lang-mismatch": 10,
  "language-of-parts-mismatch": 9,
  "table-header-association-mismatch": 4,
  "link-text-mismatch": 10,
  "page-title-not-descriptive": 6,
  "widget-label-purpose-mismatch": 6,
  "video-captions-inaccurate": 1,
}

EXPECTED_VARIANT_IDS = [
  "bs-sem-112",
  "bs-sem-113",
  "bs-sem-114",
  "bs-sem-115",
  "bs-sem-116",
  "bs-sem-117",
  "bs-sem-118",
  "bs-sem-119",
  "bs-sem-128",
  "bs-sem-129",
  "bs-sem-130",
  "bs-sem-135",
  "bs-sem-138",
  "bs-sem-139",
  "bs-sem-140",
  "bs-sem-151",
  "bs-sem-152",
  "bs-sem-153",
  "bs-sem-154",
  "bs-sem-155",
  "bs-sem-156",
  "bs-sem-157",
  "bs-sem-158",
  "bs-sem-159",
  "bs-sem-160",
  "bs-sem-161",
  "bs-sem-162",
  "co-sem-001",
  "co-sem-002",
  "co-sem-006",
  "co-sem-007",
  "co-sem-008",
  "co-sem-009",
  "co-sem-010",
  "co-sem-011",
  "co-sem-012",
  "co-sem-013",
  "co-sem-014",
  "co-sem-015",
  "co-sem-016",
  "co-sem-017",
  "co-sem-018",
  "co-sem-019",
  "co-sem-020",
  "co-sem-021",
  "co-sem-023",
  "co-sem-024",
  "co-sem-027",
  "co-sem-028",
  "co-sem-029",
  "co-sem-031",
  "co-sem-032",
  "co-sem-035",
  "co-sem-036",
  "co-sem-037",
  "co-sem-038",
  "co-sem-041",
  "co-sem-042",
  "co-sem-044",
  "co-sem-045",
  "co-sem-047",
  "co-sem-052",
  "co-sem-053",
  "co-sem-054",
  "co-sem-055",
  "co-sem-056",
  "co-sem-058",
  "co-sem-059",
  "co-sem-060",
  "co-sem-061",
  "co-sem-062",
  "co-sem-063",
  "co-sem-064",
  "co-sem-065",
  "co-sem-066",
  "co-sem-067",
  "co-sem-068",
  "co-sem-069",
  "co-sem-070",
  "co-sem-071",
  "co-sem-072",
  "co-sem-073",
  "co-sem-074",
  "co-sem-075",
  "co-sem-076",
  "co-sem-077",
  "co-sem-078",
  "co-sem-079",
  "co-sem-080",
  "co-sem-081",
  "co-sem-086",
  "co-sem-087",
  "co-sem-088",
  "co-sem-089",
  "co-sem-090",
  "co-sem-091",
  "co-sem-092",
  "co-sem-093",
  "co-sem-094",
  "co-sem-095",
  "co-sem-097",
  "co-sem-100",
  "co-sem-101",
  "co-sem-102",
  "co-sem-103",
  "co-sem-104",
  "co-sem-107",
  "co-sem-108",
  "co-sem-109",
  "co-sem-110",
  "co-sem-111",
  "co-sem-112",
  "co-sem-113",
  "co-sem-114",
  "co-sem-116",
  "co-sem-117",
  "co-sem-118",
  "co-sem-119",
  "co-sem-120",
  "co-sem-121",
  "co-sem-122",
  "co-sem-123",
  "co-sem-124",
  "co-sem-125",
  "co-sem-126",
  "co-sem-127",
  "co-sem-128",
  "co-sem-129",
  "co-sem-130",
  "co-sem-131",
  "co-sem-132",
  "co-sem-134",
  "co-sem-135",
  "co-sem-136",
  "co-sem-137",
  "co-sem-138",
  "co-sem-139",
]

EXPLICIT_CONFIGURATION_IDS = {
  "checkout-pilot-001",
  "checkout-co-sem-027",
}

EXPLICIT_SEED_IDS = {
  "co-sem-001",
  "co-sem-002",
  "co-sem-027",
}


def _manifest() -> dict:
  return json.loads(REGISTRY.read_text(encoding="utf-8"))


def _normal_configuration(
  variant_id: str,
  *,
  app: str = "checkout-flow",
  profile: str | None = None,
) -> dict:
  return {
    "desired_activation": "benchmark_runner_profile",
    "current_activation_status": "focused_runner_runtime_profile_injection_supported",
    "description": f"Single-case profile for implemented dataset case {variant_id}.",
    "configuration_id": profile if profile is not None else f"checkout-{variant_id}",
    "baseline_configuration": "clean",
    "individual_seed_activation_role": "debugging_and_focused_validation",
    "seed_ids": [
      variant_id,
    ],
    "intended_use": "implemented_dataset_case_not_accepted",
    "preserves_workflow_routes": True,
    "app": app,
    "status": "implemented",
    "planned_seed_count": 1,
  }


def _expected_configuration_ids() -> list[str]:
  ids: list[str] = []
  emitted_explicit: set[str] = set()
  explicit_by_seed = {
    "co-sem-001": "checkout-pilot-001",
    "co-sem-002": "checkout-pilot-001",
    "co-sem-027": "checkout-co-sem-027",
  }
  for variant_id in EXPECTED_VARIANT_IDS:
    explicit_id = explicit_by_seed.get(variant_id)
    if explicit_id is not None:
      if explicit_id not in emitted_explicit:
        ids.append(explicit_id)
        emitted_explicit.add(explicit_id)
      continue
    app_prefix = "booking" if variant_id.startswith("bs-") else "checkout"
    ids.append(f"{app_prefix}-{variant_id}")
  return ids


def test_registry_loader_returns_compatibility_shape():
  registry = load_benchmark_registry(REGISTRY)

  assert list(registry) == [
    "variants",
    "description",
    "schema_version",
    "benchmark_generation",
    "seeded_configurations",
    "notes",
  ]
  assert registry["schema_version"] == "benchmark-case-registry-v1"
  assert registry["benchmark_generation"] == "controlled-local-spas"
  assert len(registry["variants"]) == 137
  assert len(registry["seeded_configurations"]) == 136


def test_registry_manifest_stores_only_explicit_configuration_exceptions():
  manifest = _manifest()
  explicit_configurations = manifest["explicit_seeded_configurations"]

  assert "seeded_configurations" not in manifest
  assert len(explicit_configurations) == 2
  assert [
    configuration["configuration_id"]
    for configuration in explicit_configurations
  ] == ["checkout-pilot-001", "checkout-co-sem-027"]


def test_registry_loader_preserves_variant_order_and_deterministic_configuration_order():
  registry = load_benchmark_registry(REGISTRY)

  assert [variant["variant_id"] for variant in registry["variants"]] == EXPECTED_VARIANT_IDS
  configuration_ids = [
    configuration["configuration_id"]
    for configuration in registry["seeded_configurations"]
  ]
  assert configuration_ids == _expected_configuration_ids()
  assert len(configuration_ids) == len(set(configuration_ids))
  assert configuration_ids[0] == "booking-bs-sem-112"
  assert configuration_ids[-1] == "checkout-co-sem-139"


def test_registry_loader_preserves_explicit_configuration_exceptions():
  manifest = _manifest()
  registry = load_benchmark_registry(REGISTRY)
  explicit_configurations = {
    configuration["configuration_id"]: configuration
    for configuration in manifest["explicit_seeded_configurations"]
  }
  assembled_configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }

  assert assembled_configurations["checkout-pilot-001"] == explicit_configurations["checkout-pilot-001"]
  assert assembled_configurations["checkout-pilot-001"]["seed_ids"] == ["co-sem-001", "co-sem-002"]
  assert assembled_configurations["checkout-pilot-001"]["planned_seed_count"] == 2
  assert assembled_configurations["checkout-co-sem-027"] == explicit_configurations["checkout-co-sem-027"]
  assert assembled_configurations["checkout-co-sem-027"]["seed_ids"] == ["co-sem-027"]
  assert assembled_configurations["checkout-co-sem-027"]["acquisition_requirements"] == [
    "controlled_support_destination_capture"
  ]


def test_registry_loader_synthesizes_only_ordinary_single_case_configurations():
  registry = load_benchmark_registry(REGISTRY)
  configurations = registry["seeded_configurations"]
  normal_configurations = [
    configuration
    for configuration in configurations
    if configuration["configuration_id"] not in EXPLICIT_CONFIGURATION_IDS
  ]

  assert len(normal_configurations) == 134
  for configuration in normal_configurations:
    seed_ids = configuration["seed_ids"]
    assert len(seed_ids) == 1
    assert seed_ids[0] not in EXPLICIT_SEED_IDS
    if seed_ids[0].startswith("bs-"):
      assert configuration == _normal_configuration(
        seed_ids[0],
        app="booking-scheduler",
        profile=f"booking-{seed_ids[0]}",
      )
    else:
      assert configuration == _normal_configuration(seed_ids[0])


def test_registry_loader_derives_normal_configuration_from_variant_metadata(tmp_path):
  manifest = tmp_path / "benchmark-case-registry.json"
  family_dir = tmp_path / "families"
  family_dir.mkdir()
  variant = {
    "variant_id": "bs-sem-999",
    "candidate_type": "button-label-mismatch",
    "app": "booking-scheduler",
    "profile": "booking-bs-sem-999",
    "baseline_behavior": "The booking action has a descriptive label.",
    "seeded_behavior": "The booking action has a mismatched label.",
    "expected_evidence": {
      "bucket": "buttons",
      "selector_hint": "[data-testid=\"booking-action\"]",
    },
  }
  manifest.write_text(
    json.dumps(
      {
        "family_files": ["families/button-label-mismatch.json"],
        "explicit_seeded_configurations": [],
      }
    ),
    encoding="utf-8",
  )
  (family_dir / "button-label-mismatch.json").write_text(
    json.dumps(
      {
        "candidate_type": "button-label-mismatch",
        "variants": [variant],
      }
    ),
    encoding="utf-8",
  )

  registry = load_benchmark_registry(manifest)

  assert registry["variants"] == [variant]
  assert registry["variants"][0]["expected_evidence"] == variant["expected_evidence"]
  assert registry["seeded_configurations"] == [
    _normal_configuration(
      "bs-sem-999",
      app="booking-scheduler",
      profile="booking-bs-sem-999",
    )
  ]
  assert "Checkout" not in registry["seeded_configurations"][0]["description"]


def test_registry_loader_does_not_synthesize_explicitly_owned_seeds():
  registry = load_benchmark_registry(REGISTRY)
  configuration_ids = [
    configuration["configuration_id"]
    for configuration in registry["seeded_configurations"]
  ]

  assert "checkout-co-sem-001" not in configuration_ids
  assert "checkout-co-sem-002" not in configuration_ids
  assert configuration_ids.count("checkout-co-sem-027") == 1
  assert configuration_ids.count("checkout-pilot-001") == 1


def test_registry_loader_representative_normal_config_matches_legacy_shape():
  registry = load_benchmark_registry(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }

  assert configurations["checkout-co-sem-081"] == _normal_configuration("co-sem-081")
  assert configurations["checkout-co-sem-101"] == _normal_configuration("co-sem-101")
  assert configurations["checkout-co-sem-102"] == _normal_configuration("co-sem-102")
  assert configurations["checkout-co-sem-080"] == _normal_configuration("co-sem-080")
  assert configurations["checkout-co-sem-075"] == _normal_configuration("co-sem-075")
  assert configurations["checkout-co-sem-074"] == _normal_configuration("co-sem-074")
  assert configurations["checkout-co-sem-064"] == _normal_configuration("co-sem-064")
  assert configurations["checkout-co-sem-062"] == _normal_configuration("co-sem-062")
  assert configurations["checkout-co-sem-036"] == _normal_configuration("co-sem-036")


def test_bs_sem_112_uses_booking_profile_and_stable_slot_evidence():
  registry = load_benchmark_registry(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }

  assert configurations["booking-bs-sem-112"] == _normal_configuration(
    "bs-sem-112",
    app="booking-scheduler",
    profile="booking-bs-sem-112",
  )

  variant = variants["bs-sem-112"]
  expected_evidence = variant["expected_evidence"]
  action_context = expected_evidence["candidate_evidence"]["supporting"][
    "button_action_context_v1"
  ]

  assert variant["profile"] == "booking-bs-sem-112"
  assert variant["candidate_type"] == "button-label-mismatch"
  assert variant["graph_context_needed"] == "not_required"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["BS-S002"],
    "routes": ["/schedule"],
  }
  assert variant["mutation_targets"] == [
    {
      "subject": "booking.schedule.slot.0900",
      "mutation_property": "accessibleName",
    }
  ]
  assert expected_evidence["selector_hint"] == (
    '[data-testid="slot-button-0900"]'
  )
  assert expected_evidence["attributes"] == {
    "tag": "button",
    "type": "button",
    "text": "09:00 Available",
    "accessible_name": "13:00 Available",
    "aria_label": "13:00 Available",
  }
  assert action_context["action_evidence"] == {
    "button_type": "button",
    "data_testid": "slot-button-0900",
  }


def test_bs_sem_113_uses_booking_profile_and_current_date_context():
  registry = load_benchmark_registry(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }

  assert configurations["booking-bs-sem-113"] == _normal_configuration(
    "bs-sem-113",
    app="booking-scheduler",
    profile="booking-bs-sem-113",
  )

  variant = variants["bs-sem-113"]
  expected_evidence = variant["expected_evidence"]
  action_context = expected_evidence["candidate_evidence"]["supporting"][
    "button_action_context_v1"
  ]

  assert variant["profile"] == "booking-bs-sem-113"
  assert variant["candidate_type"] == "button-label-mismatch"
  assert variant["graph_context_needed"] == "not_required"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["BS-S002"],
    "routes": ["/schedule"],
  }
  assert variant["mutation_targets"] == [
    {
      "subject": "booking.schedule.slot.1400",
      "mutation_property": "accessibleName",
    }
  ]
  assert expected_evidence["selector_hint"] == (
    '[data-testid="slot-button-1400"]'
  )
  assert expected_evidence["attributes"] == {
    "tag": "button",
    "type": "button",
    "text": "14:00 Available",
    "accessible_name": "14:00 Available on June 16, 2026",
    "aria_label": "14:00 Available on June 16, 2026",
  }
  assert action_context["local_context"] == {
    "section_heading": "Available times for June 18, 2026",
  }
  assert action_context["action_evidence"] == {
    "button_type": "button",
    "data_testid": "slot-button-1400",
  }


def test_bs_sem_114_uses_booking_profile_and_service_link_context():
  registry = load_benchmark_registry(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }

  assert configurations["booking-bs-sem-114"] == _normal_configuration(
    "bs-sem-114",
    app="booking-scheduler",
    profile="booking-bs-sem-114",
  )

  variant = variants["bs-sem-114"]
  expected_evidence = variant["expected_evidence"]
  candidate_evidence = expected_evidence["candidate_evidence"]

  assert variant["profile"] == "booking-bs-sem-114"
  assert variant["candidate_type"] == "link-text-mismatch"
  assert variant["graph_context_needed"] == "not_required"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["BS-S004"],
    "routes": ["/review"],
  }
  assert variant["mutation_targets"] == [
    {
      "subject": "booking.review.changeService",
      "mutation_property": "text",
    }
  ]
  assert expected_evidence["selector_hint"] == (
    '[data-testid="change-service"]'
  )
  assert expected_evidence["attributes"] == {
    "tag": "a",
    "text": "Change appointment",
    "accessible_name": "Change appointment",
    "href": "/services",
  }
  assert candidate_evidence["primary"]["link"] == {
    "tag": "a",
    "text": "Change appointment",
    "accessible_name": "Change appointment",
    "href": "/services",
  }
  assert candidate_evidence["supporting"]["context"] == {
    "nearby_text": "NameConsultationDuration30 minutes",
    "section_heading": "Service",
  }
  assert candidate_evidence["supporting"][
    "link_destination_context_v1"
  ] == {
    "schema_version": "link_destination_context_v1",
    "raw_href": "/services",
    "resolved_path": "/services",
  }


def test_bs_sem_115_uses_booking_profile_and_observed_destination_context():
  registry = load_benchmark_registry(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }

  assert configurations["booking-bs-sem-115"] == _normal_configuration(
    "bs-sem-115",
    app="booking-scheduler",
    profile="booking-bs-sem-115",
  )

  variant = variants["bs-sem-115"]
  expected_evidence = variant["expected_evidence"]
  candidate_evidence = expected_evidence["candidate_evidence"]

  assert variant["profile"] == "booking-bs-sem-115"
  assert variant["candidate_type"] == "link-text-mismatch"
  assert variant["graph_context_needed"] == "required"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["BS-S004"],
    "routes": ["/review"],
  }
  assert variant["mutation_targets"] == [
    {
      "subject": "booking.review.changeAppointment",
      "mutation_property": "activationTargetRoute",
    }
  ]
  assert expected_evidence["selector_hint"] == (
    '[data-testid="change-appointment"]'
  )
  assert expected_evidence["attributes"] == {
    "tag": "a",
    "text": "Change appointment",
    "accessible_name": "Change appointment",
    "href": "/schedule",
  }
  assert candidate_evidence["primary"]["link"] == {
    "tag": "a",
    "text": "Change appointment",
    "accessible_name": "Change appointment",
    "href": "/schedule",
  }
  supporting = candidate_evidence["supporting"]
  assert supporting["context"] == {"section_heading": "Date and time"}
  assert supporting["link_destination_context_v1"] == {
    "schema_version": "link_destination_context_v1",
    "raw_href": "/schedule",
    "resolved_path": "/schedule",
  }
  assert supporting["destination_state_context_v1"] == {
    "schema_version": "destination_state_context_v1",
    "match_count": 1,
    "destinations": [
      {
        "target_route": "/services",
        "target_title": "Select service | Booking Scheduler Benchmark",
        "target_primary_headings": [
          {
            "level": 1,
            "tag": "h1",
            "text": "Select service",
            "accessible_name": "Select service",
          }
        ],
      }
    ],
  }


def test_bs_sem_116_uses_booking_profile_and_structured_service_label_evidence():
  registry = load_benchmark_registry(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }

  assert configurations["booking-bs-sem-116"] == _normal_configuration(
    "bs-sem-116",
    app="booking-scheduler",
    profile="booking-bs-sem-116",
  )

  variant = variants["bs-sem-116"]
  expected_evidence = variant["expected_evidence"]
  label_context = expected_evidence["candidate_evidence"]["supporting"][
    "form_label_context_v1"
  ]

  assert variant["profile"] == "booking-bs-sem-116"
  assert variant["candidate_type"] == "form-label-mismatch"
  assert variant["graph_context_needed"] == "not_required"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["BS-S001"],
    "routes": ["/services"],
  }
  assert variant["mutation_targets"] == [
    {
      "subject": "booking.services.consultation",
      "mutation_property": "serviceName",
    }
  ]
  assert expected_evidence["control"] == {
    "id": "service-svc-consultation",
    "name": "service",
  }
  assert label_context["labeling"]["label_sources"][0]["text_segments"] == [
    "Repair assessment",
    "30 minutes",
    "Initial planning appointment for the benchmark fixture.",
  ]


def test_bs_sem_128_uses_date_identity_and_native_time_label_evidence():
  registry = load_benchmark_registry(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }

  assert configurations["booking-bs-sem-128"] == _normal_configuration(
    "bs-sem-128",
    app="booking-scheduler",
    profile="booking-bs-sem-128",
  )

  variant = variants["bs-sem-128"]
  expected_evidence = variant["expected_evidence"]
  candidate_evidence = expected_evidence["candidate_evidence"]
  form_label_context = candidate_evidence["supporting"][
    "form_label_context_v1"
  ]

  assert variant["profile"] == "booking-bs-sem-128"
  assert variant["candidate_type"] == "form-label-mismatch"
  assert variant["graph_context_needed"] == "not_required"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["BS-S002"],
    "routes": ["/schedule"],
  }
  assert variant["mutation_targets"] == [
    {
      "mutation_property": "labelText",
      "subject": "booking.schedule.date",
    }
  ]
  assert expected_evidence["control"] == {"id": "booking-date"}
  assert expected_evidence["attributes"] == {
    "tag": "input",
    "type": "date",
    "required": False,
    "aria_describedby": "booking-date-help",
    "accessible_name": "Appointment time",
    "label": "Appointment time",
  }
  assert candidate_evidence["primary"]["form_control"] == {
    "selector": "input#booking-date",
    "tag": "input",
    "type": "date",
    "id": "booking-date",
    "required": False,
    "aria_describedby": "booking-date-help",
    "accessible_name": "Appointment time",
    "label": "Appointment time",
  }
  assert form_label_context["labeling"] == {
    "visible_label": "Appointment time",
    "computed_accessible_name": "Appointment time",
    "label_sources": [
      {
        "relationship_type": "labels",
        "method": "for",
        "text_segments": ["Appointment time"],
      }
    ],
    "visible_label_in_accessible_name": True,
  }
  assert form_label_context["field_purpose_evidence"] == {
    "type": "date",
    "id": "booking-date",
    "descriptions": [
      {
        "selector": "p#booking-date-help",
        "text": (
          "Supported fixture dates: June 16, 2026 and June 18, 2026."
        ),
        "relationship_type": "describes",
        "method": "aria-describedby",
      }
    ],
    "form_step_or_route_context": {"route": "/schedule"},
  }
  assert candidate_evidence["supporting"]["structure"] == {
    "nearest_heading": {
      "selector": "h2#schedule-heading",
      "text": "Choose a date and time",
    }
  }


def test_bs_sem_129_uses_phone_identity_and_native_email_label_evidence():
  registry = load_benchmark_registry(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }

  assert configurations["booking-bs-sem-129"] == _normal_configuration(
    "bs-sem-129",
    app="booking-scheduler",
    profile="booking-bs-sem-129",
  )

  variant = variants["bs-sem-129"]
  expected_evidence = variant["expected_evidence"]
  candidate_evidence = expected_evidence["candidate_evidence"]
  form_label_context = candidate_evidence["supporting"][
    "form_label_context_v1"
  ]

  assert variant["profile"] == "booking-bs-sem-129"
  assert variant["candidate_type"] == "form-label-mismatch"
  assert variant["graph_context_needed"] == "not_required"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["BS-S003"],
    "routes": ["/details"],
  }
  assert variant["mutation_targets"] == [
    {
      "mutation_property": "labelText",
      "subject": "booking.details.phone",
    }
  ]
  assert expected_evidence["control"] == {
    "id": "details-phone",
    "name": "phone",
  }
  assert expected_evidence["attributes"] == {
    "tag": "input",
    "type": "tel",
    "autocomplete": "tel",
    "required": True,
    "accessible_name": "EmailRequired",
    "label": "EmailRequired",
  }
  assert candidate_evidence["primary"]["form_control"] == {
    "selector": "input#details-phone",
    "tag": "input",
    "type": "tel",
    "name": "phone",
    "id": "details-phone",
    "autocomplete": "tel",
    "required": True,
    "accessible_name": "EmailRequired",
    "label": "EmailRequired",
  }
  assert form_label_context["labeling"] == {
    "visible_label": "Email REQUIRED",
    "computed_accessible_name": "EmailRequired",
    "label_sources": [
      {
        "relationship_type": "labels",
        "method": "for",
        "text_segments": ["Email", "Required"],
      }
    ],
    "visible_label_in_accessible_name": True,
  }
  assert form_label_context["field_purpose_evidence"] == {
    "type": "tel",
    "name": "phone",
    "id": "details-phone",
    "autocomplete": "tel",
    "form_step_or_route_context": {"route": "/details"},
  }


def test_bs_sem_151_uses_email_identity_and_telephone_autocomplete_evidence():
  registry = load_benchmark_registry(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }

  assert configurations["booking-bs-sem-151"] == _normal_configuration(
    "bs-sem-151",
    app="booking-scheduler",
    profile="booking-bs-sem-151",
  )

  variant = variants["bs-sem-151"]
  expected_evidence = variant["expected_evidence"]
  candidate_evidence = expected_evidence["candidate_evidence"]
  autocomplete_context = candidate_evidence["supporting"][
    "autocomplete_purpose_context_v1"
  ]

  assert variant["profile"] == "booking-bs-sem-151"
  assert variant["candidate_type"] == "autocomplete-purpose-mismatch"
  assert variant["graph_context_needed"] == "not_required"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["BS-S003"],
    "routes": ["/details"],
  }
  assert variant["mutation_targets"] == [
    {
      "subject": "booking.details.email",
      "mutation_property": "autocomplete",
    }
  ]
  assert expected_evidence["control"] == {
    "id": "details-email",
    "name": "email",
  }
  assert expected_evidence["attributes"] == {
    "tag": "input",
    "type": "email",
    "autocomplete": "tel",
    "required": True,
    "accessible_name": "EmailRequired",
    "label": "EmailRequired",
  }
  assert candidate_evidence["primary"]["form_control"] == {
    "selector": "input#details-email",
    "tag": "input",
    "type": "email",
    "name": "email",
    "id": "details-email",
    "autocomplete": "tel",
    "required": True,
    "accessible_name": "EmailRequired",
    "label": "EmailRequired",
  }
  assert autocomplete_context["control"] == {
    "selector": "input#details-email",
    "tag": "input",
    "type": "email",
    "name": "email",
    "id": "details-email",
    "autocomplete": "tel",
    "required": True,
    "value_state": "empty",
  }
  assert autocomplete_context["labeling"] == {
    "visible_label": "Email REQUIRED",
    "computed_accessible_name": "EmailRequired",
    "label_sources": [
      {
        "relationship_type": "labels",
        "method": "for",
        "text_segments": ["Email", "Required"],
      }
    ],
  }
  assert autocomplete_context["field_purpose_evidence"] == {
    "input_type": "email",
    "name": "email",
    "id": "details-email",
    "visible_label": "Email REQUIRED",
    "computed_accessible_name": "EmailRequired",
    "form_step_or_route_context": {
      "route": "/details",
      "section_heading": "Customer details",
      "title": "Booking details | Booking Scheduler Benchmark",
    },
  }
  assert autocomplete_context["autocomplete_evidence"] == {
    "raw_value": "tel",
    "tokens": ["tel"],
    "section_tokens": [],
    "context_tokens": [],
    "purpose_token": "tel",
    "recognized_purpose": "telephone number",
    "token_category": "tel",
    "is_known_token": True,
    "unknown_tokens": [],
  }


def test_bs_sem_151_matcher_rejects_semantic_and_state_counterfactuals():
  registry = load_benchmark_registry(REGISTRY)
  variant = next(
    item for item in registry["variants"] if item["variant_id"] == "bs-sem-151"
  )
  expected_evidence = variant["expected_evidence"]
  expected_routes = variant["expected_state"]["routes"]

  seeded = {
    "candidate_type": "autocomplete-purpose-mismatch",
    "state_context": {
      "route": "/details",
      "url": "http://127.0.0.1:4173/details",
    },
    "evidence": deepcopy(expected_evidence["candidate_evidence"]),
  }

  def matches(candidate: dict, *, canonical_state_matches: bool = True) -> bool:
    primary = candidate["evidence"]["primary"]["form_control"]
    return all(
      (
        _element_matches_expected(primary, expected_evidence, record=candidate),
        _candidate_matches_expected_evidence(candidate, expected_evidence),
        _candidate_route_matches(candidate, expected_routes),
        _state_matches_expected_constraints(
          has_routes=True,
          route_matches=True,
          has_benchmark_state_ids=True,
          benchmark_matches=canonical_state_matches,
        ),
      )
    )

  assert matches(seeded)

  clean = deepcopy(seeded)
  clean["evidence"]["primary"]["form_control"]["autocomplete"] = "email"
  clean_context = clean["evidence"]["supporting"][
    "autocomplete_purpose_context_v1"
  ]
  clean_context["control"]["autocomplete"] = "email"
  clean_context["autocomplete_evidence"].update(
    {
      "raw_value": "email",
      "tokens": ["email"],
      "purpose_token": "email",
      "recognized_purpose": "email address",
      "token_category": "email",
    }
  )
  assert not matches(clean)

  wrong_target = deepcopy(seeded)
  wrong_primary = wrong_target["evidence"]["primary"]["form_control"]
  wrong_primary.update(
    {
      "selector": "input#details-phone",
      "type": "tel",
      "name": "phone",
      "id": "details-phone",
      "label": "PhoneRequired",
      "accessible_name": "PhoneRequired",
    }
  )
  wrong_context = wrong_target["evidence"]["supporting"][
    "autocomplete_purpose_context_v1"
  ]
  wrong_context["control"].update(
    {
      "selector": "input#details-phone",
      "type": "tel",
      "name": "phone",
      "id": "details-phone",
    }
  )
  wrong_context["labeling"].update(
    {
      "visible_label": "Phone REQUIRED",
      "computed_accessible_name": "PhoneRequired",
    }
  )
  wrong_context["labeling"]["label_sources"][0]["text_segments"] = [
    "Phone",
    "Required",
  ]
  wrong_context["field_purpose_evidence"].update(
    {
      "input_type": "tel",
      "name": "phone",
      "id": "details-phone",
      "visible_label": "Phone REQUIRED",
      "computed_accessible_name": "PhoneRequired",
    }
  )
  assert not matches(wrong_target)

  missing_identity = deepcopy(seeded)
  del missing_identity["evidence"]["primary"]["form_control"]["id"]
  del missing_identity["evidence"]["supporting"][
    "autocomplete_purpose_context_v1"
  ]["control"]["id"]
  assert not matches(missing_identity)

  wrong_purpose = deepcopy(seeded)
  wrong_purpose["evidence"]["supporting"][
    "autocomplete_purpose_context_v1"
  ]["field_purpose_evidence"]["input_type"] = "tel"
  assert not matches(wrong_purpose)

  wrong_route = deepcopy(seeded)
  wrong_route["state_context"]["route"] = "/schedule"
  wrong_route["state_context"]["url"] = "http://127.0.0.1:4173/schedule"
  assert not matches(wrong_route)
  assert not matches(seeded, canonical_state_matches=False)


def test_bs_sem_152_uses_phone_identity_and_email_autocomplete_evidence():
  registry = load_benchmark_registry(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }

  assert configurations["booking-bs-sem-152"] == _normal_configuration(
    "bs-sem-152",
    app="booking-scheduler",
    profile="booking-bs-sem-152",
  )

  variant = variants["bs-sem-152"]
  expected_evidence = variant["expected_evidence"]
  candidate_evidence = expected_evidence["candidate_evidence"]
  autocomplete_context = candidate_evidence["supporting"][
    "autocomplete_purpose_context_v1"
  ]

  assert variant["profile"] == "booking-bs-sem-152"
  assert variant["candidate_type"] == "autocomplete-purpose-mismatch"
  assert variant["graph_context_needed"] == "not_required"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["BS-S003"],
    "routes": ["/details"],
  }
  assert variant["mutation_targets"] == [
    {
      "subject": "booking.details.phone",
      "mutation_property": "autocomplete",
    }
  ]
  assert expected_evidence["control"] == {
    "id": "details-phone",
    "name": "phone",
  }
  assert expected_evidence["attributes"] == {
    "tag": "input",
    "type": "tel",
    "autocomplete": "email",
    "required": True,
    "accessible_name": "PhoneRequired",
    "label": "PhoneRequired",
  }
  assert candidate_evidence["primary"]["form_control"] == {
    "selector": "input#details-phone",
    "tag": "input",
    "type": "tel",
    "name": "phone",
    "id": "details-phone",
    "autocomplete": "email",
    "required": True,
    "accessible_name": "PhoneRequired",
    "label": "PhoneRequired",
  }
  assert autocomplete_context["control"] == {
    "selector": "input#details-phone",
    "tag": "input",
    "type": "tel",
    "name": "phone",
    "id": "details-phone",
    "autocomplete": "email",
    "required": True,
    "value_state": "empty",
  }
  assert autocomplete_context["labeling"] == {
    "visible_label": "Phone REQUIRED",
    "computed_accessible_name": "PhoneRequired",
    "label_sources": [
      {
        "relationship_type": "labels",
        "method": "for",
        "text_segments": ["Phone", "Required"],
      }
    ],
  }
  assert autocomplete_context["field_purpose_evidence"] == {
    "input_type": "tel",
    "name": "phone",
    "id": "details-phone",
    "visible_label": "Phone REQUIRED",
    "computed_accessible_name": "PhoneRequired",
    "form_step_or_route_context": {
      "route": "/details",
      "section_heading": "Customer details",
      "title": "Booking details | Booking Scheduler Benchmark",
    },
  }
  assert autocomplete_context["autocomplete_evidence"] == {
    "raw_value": "email",
    "tokens": ["email"],
    "section_tokens": [],
    "context_tokens": [],
    "purpose_token": "email",
    "recognized_purpose": "email address",
    "token_category": "email",
    "is_known_token": True,
    "unknown_tokens": [],
  }


def test_bs_sem_152_matcher_rejects_semantic_and_state_counterfactuals():
  registry = load_benchmark_registry(REGISTRY)
  variant = next(
    item for item in registry["variants"] if item["variant_id"] == "bs-sem-152"
  )
  expected_evidence = variant["expected_evidence"]
  expected_routes = variant["expected_state"]["routes"]

  seeded = {
    "candidate_type": "autocomplete-purpose-mismatch",
    "state_context": {
      "route": "/details",
      "url": "http://127.0.0.1:4173/details",
    },
    "evidence": deepcopy(expected_evidence["candidate_evidence"]),
  }

  def matches(candidate: dict, *, canonical_state_matches: bool = True) -> bool:
    primary = candidate["evidence"]["primary"]["form_control"]
    return all(
      (
        _element_matches_expected(primary, expected_evidence, record=candidate),
        _candidate_matches_expected_evidence(candidate, expected_evidence),
        _candidate_route_matches(candidate, expected_routes),
        _state_matches_expected_constraints(
          has_routes=True,
          route_matches=True,
          has_benchmark_state_ids=True,
          benchmark_matches=canonical_state_matches,
        ),
      )
    )

  assert matches(seeded)

  clean = deepcopy(seeded)
  clean["evidence"]["primary"]["form_control"]["autocomplete"] = "tel"
  clean_context = clean["evidence"]["supporting"][
    "autocomplete_purpose_context_v1"
  ]
  clean_context["control"]["autocomplete"] = "tel"
  clean_context["autocomplete_evidence"].update(
    {
      "raw_value": "tel",
      "tokens": ["tel"],
      "purpose_token": "tel",
      "recognized_purpose": "telephone number",
      "token_category": "tel",
    }
  )
  assert not matches(clean)

  legitimate_email = deepcopy(seeded)
  email_primary = legitimate_email["evidence"]["primary"]["form_control"]
  email_primary.update(
    {
      "selector": "input#details-email",
      "type": "email",
      "name": "email",
      "id": "details-email",
      "label": "EmailRequired",
      "accessible_name": "EmailRequired",
    }
  )
  email_context = legitimate_email["evidence"]["supporting"][
    "autocomplete_purpose_context_v1"
  ]
  email_context["control"].update(
    {
      "selector": "input#details-email",
      "type": "email",
      "name": "email",
      "id": "details-email",
    }
  )
  email_context["labeling"].update(
    {
      "visible_label": "Email REQUIRED",
      "computed_accessible_name": "EmailRequired",
    }
  )
  email_context["labeling"]["label_sources"][0]["text_segments"] = [
    "Email",
    "Required",
  ]
  email_context["field_purpose_evidence"].update(
    {
      "input_type": "email",
      "name": "email",
      "id": "details-email",
      "visible_label": "Email REQUIRED",
      "computed_accessible_name": "EmailRequired",
    }
  )
  assert not matches(legitimate_email)

  missing_identity = deepcopy(seeded)
  del missing_identity["evidence"]["primary"]["form_control"]["id"]
  del missing_identity["evidence"]["supporting"][
    "autocomplete_purpose_context_v1"
  ]["control"]["id"]
  assert not matches(missing_identity)

  wrong_purpose = deepcopy(seeded)
  wrong_purpose["evidence"]["supporting"][
    "autocomplete_purpose_context_v1"
  ]["field_purpose_evidence"]["input_type"] = "email"
  assert not matches(wrong_purpose)

  wrong_type_and_name = deepcopy(seeded)
  wrong_type_and_name["evidence"]["primary"]["form_control"].update(
    {"type": "text", "name": "contact"}
  )
  assert not matches(wrong_type_and_name)

  missing_context = deepcopy(seeded)
  del missing_context["evidence"]["supporting"][
    "autocomplete_purpose_context_v1"
  ]["field_purpose_evidence"]["form_step_or_route_context"][
    "section_heading"
  ]
  assert not matches(missing_context)

  wrong_route = deepcopy(seeded)
  wrong_route["state_context"]["route"] = "/schedule"
  wrong_route["state_context"]["url"] = "http://127.0.0.1:4173/schedule"
  assert not matches(wrong_route)
  assert not matches(seeded, canonical_state_matches=False)


def test_bs_sem_153_uses_full_name_identity_and_organization_title_evidence():
  registry = load_benchmark_registry(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }

  assert configurations["booking-bs-sem-153"] == _normal_configuration(
    "bs-sem-153",
    app="booking-scheduler",
    profile="booking-bs-sem-153",
  )

  variant = variants["bs-sem-153"]
  expected_evidence = variant["expected_evidence"]
  candidate_evidence = expected_evidence["candidate_evidence"]
  autocomplete_context = candidate_evidence["supporting"][
    "autocomplete_purpose_context_v1"
  ]

  assert variant["profile"] == "booking-bs-sem-153"
  assert variant["candidate_type"] == "autocomplete-purpose-mismatch"
  assert variant["graph_context_needed"] == "not_required"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["BS-S003"],
    "routes": ["/details"],
  }
  assert variant["mutation_targets"] == [
    {
      "subject": "booking.details.fullName",
      "mutation_property": "autocomplete",
    }
  ]
  assert expected_evidence["control"] == {
    "id": "details-fullName",
    "name": "fullName",
  }
  assert expected_evidence["attributes"] == {
    "tag": "input",
    "type": "text",
    "autocomplete": "organization-title",
    "required": True,
    "accessible_name": "Full nameRequired",
    "label": "Full nameRequired",
  }
  assert candidate_evidence["primary"]["form_control"] == {
    "selector": "input#details-fullName",
    "tag": "input",
    "type": "text",
    "name": "fullName",
    "id": "details-fullName",
    "autocomplete": "organization-title",
    "required": True,
    "accessible_name": "Full nameRequired",
    "label": "Full nameRequired",
  }
  assert autocomplete_context["control"] == {
    "selector": "input#details-fullName",
    "tag": "input",
    "type": "text",
    "name": "fullName",
    "id": "details-fullName",
    "autocomplete": "organization-title",
    "required": True,
    "value_state": "empty",
  }
  assert autocomplete_context["labeling"] == {
    "visible_label": "Full name REQUIRED",
    "computed_accessible_name": "Full nameRequired",
    "label_sources": [
      {
        "relationship_type": "labels",
        "method": "for",
        "text_segments": ["Full name", "Required"],
      }
    ],
  }
  assert autocomplete_context["field_purpose_evidence"] == {
    "input_type": "text",
    "name": "fullName",
    "id": "details-fullName",
    "visible_label": "Full name REQUIRED",
    "computed_accessible_name": "Full nameRequired",
    "form_step_or_route_context": {
      "route": "/details",
      "section_heading": "Customer details",
      "title": "Booking details | Booking Scheduler Benchmark",
    },
  }
  assert autocomplete_context["autocomplete_evidence"] == {
    "raw_value": "organization-title",
    "tokens": ["organization-title"],
    "section_tokens": [],
    "context_tokens": [],
    "purpose_token": "organization-title",
    "recognized_purpose": "organization title",
    "token_category": "organization",
    "is_known_token": True,
    "unknown_tokens": [],
  }


def test_bs_sem_153_matcher_rejects_semantic_and_state_counterfactuals():
  registry = load_benchmark_registry(REGISTRY)
  variant = next(
    item for item in registry["variants"] if item["variant_id"] == "bs-sem-153"
  )
  expected_evidence = variant["expected_evidence"]
  expected_routes = variant["expected_state"]["routes"]

  seeded = {
    "candidate_type": "autocomplete-purpose-mismatch",
    "state_context": {
      "route": "/details",
      "url": "http://127.0.0.1:4173/details",
    },
    "evidence": deepcopy(expected_evidence["candidate_evidence"]),
  }

  def matches(candidate: dict, *, canonical_state_matches: bool = True) -> bool:
    primary = candidate["evidence"]["primary"]["form_control"]
    return all(
      (
        _element_matches_expected(primary, expected_evidence, record=candidate),
        _candidate_matches_expected_evidence(candidate, expected_evidence),
        _candidate_route_matches(candidate, expected_routes),
        _state_matches_expected_constraints(
          has_routes=True,
          route_matches=True,
          has_benchmark_state_ids=True,
          benchmark_matches=canonical_state_matches,
        ),
      )
    )

  assert matches(seeded)

  clean = deepcopy(seeded)
  clean["evidence"]["primary"]["form_control"]["autocomplete"] = "name"
  clean_context = clean["evidence"]["supporting"][
    "autocomplete_purpose_context_v1"
  ]
  clean_context["control"]["autocomplete"] = "name"
  clean_context["autocomplete_evidence"].update(
    {
      "raw_value": "name",
      "tokens": ["name"],
      "purpose_token": "name",
      "recognized_purpose": "full name",
      "token_category": "name",
    }
  )
  assert not matches(clean)

  legitimate_organization_title = deepcopy(seeded)
  title_primary = legitimate_organization_title["evidence"]["primary"][
    "form_control"
  ]
  title_primary.update(
    {
      "selector": "input#details-organization-title",
      "name": "organizationTitle",
      "id": "details-organization-title",
      "label": "Job title",
      "accessible_name": "Job title",
    }
  )
  title_context = legitimate_organization_title["evidence"]["supporting"][
    "autocomplete_purpose_context_v1"
  ]
  title_context["control"].update(
    {
      "selector": "input#details-organization-title",
      "name": "organizationTitle",
      "id": "details-organization-title",
    }
  )
  title_context["labeling"].update(
    {
      "visible_label": "Job title",
      "computed_accessible_name": "Job title",
    }
  )
  title_context["labeling"]["label_sources"][0]["text_segments"] = [
    "Job title"
  ]
  title_context["field_purpose_evidence"].update(
    {
      "name": "organizationTitle",
      "id": "details-organization-title",
      "visible_label": "Job title",
      "computed_accessible_name": "Job title",
    }
  )
  assert not matches(legitimate_organization_title)

  missing_identity = deepcopy(seeded)
  del missing_identity["evidence"]["primary"]["form_control"]["id"]
  del missing_identity["evidence"]["supporting"][
    "autocomplete_purpose_context_v1"
  ]["control"]["id"]
  assert not matches(missing_identity)

  wrong_type_or_name = deepcopy(seeded)
  wrong_type_or_name["evidence"]["primary"]["form_control"].update(
    {"type": "email", "name": "contact"}
  )
  assert not matches(wrong_type_or_name)

  missing_purpose = deepcopy(seeded)
  del missing_purpose["evidence"]["supporting"][
    "autocomplete_purpose_context_v1"
  ]["field_purpose_evidence"]
  assert not matches(missing_purpose)

  wrong_label = deepcopy(seeded)
  wrong_label["evidence"]["primary"]["form_control"].update(
    {"label": "Job title", "accessible_name": "Job title"}
  )
  assert not matches(wrong_label)

  wrong_route = deepcopy(seeded)
  wrong_route["state_context"]["route"] = "/schedule"
  wrong_route["state_context"]["url"] = "http://127.0.0.1:4173/schedule"
  assert not matches(wrong_route)
  assert not matches(seeded, canonical_state_matches=False)


def test_bs_sem_154_uses_full_name_identity_and_given_name_evidence():
  registry = load_benchmark_registry(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }

  assert configurations["booking-bs-sem-154"] == _normal_configuration(
    "bs-sem-154",
    app="booking-scheduler",
    profile="booking-bs-sem-154",
  )

  variant = variants["bs-sem-154"]
  expected_evidence = variant["expected_evidence"]
  candidate_evidence = expected_evidence["candidate_evidence"]
  autocomplete_context = candidate_evidence["supporting"][
    "autocomplete_purpose_context_v1"
  ]

  assert variant["profile"] == "booking-bs-sem-154"
  assert variant["candidate_type"] == "autocomplete-purpose-mismatch"
  assert variant["graph_context_needed"] == "not_required"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["BS-S003"],
    "routes": ["/details"],
  }
  assert variant["mutation_targets"] == [
    {
      "subject": "booking.details.fullName",
      "mutation_property": "autocomplete",
    }
  ]
  assert expected_evidence["control"] == {
    "id": "details-fullName",
    "name": "fullName",
  }
  assert expected_evidence["attributes"] == {
    "tag": "input",
    "type": "text",
    "autocomplete": "given-name",
    "required": True,
    "accessible_name": "Full nameRequired",
    "label": "Full nameRequired",
  }
  assert candidate_evidence["primary"]["form_control"] == {
    "selector": "input#details-fullName",
    "tag": "input",
    "type": "text",
    "name": "fullName",
    "id": "details-fullName",
    "autocomplete": "given-name",
    "required": True,
    "accessible_name": "Full nameRequired",
    "label": "Full nameRequired",
  }
  assert autocomplete_context["control"] == {
    "selector": "input#details-fullName",
    "tag": "input",
    "type": "text",
    "name": "fullName",
    "id": "details-fullName",
    "autocomplete": "given-name",
    "required": True,
    "value_state": "empty",
  }
  assert autocomplete_context["labeling"] == {
    "visible_label": "Full name REQUIRED",
    "computed_accessible_name": "Full nameRequired",
    "label_sources": [
      {
        "relationship_type": "labels",
        "method": "for",
        "text_segments": ["Full name", "Required"],
      }
    ],
  }
  assert autocomplete_context["field_purpose_evidence"] == {
    "input_type": "text",
    "name": "fullName",
    "id": "details-fullName",
    "visible_label": "Full name REQUIRED",
    "computed_accessible_name": "Full nameRequired",
    "form_step_or_route_context": {
      "route": "/details",
      "section_heading": "Customer details",
      "title": "Booking details | Booking Scheduler Benchmark",
    },
  }
  assert autocomplete_context["autocomplete_evidence"] == {
    "raw_value": "given-name",
    "tokens": ["given-name"],
    "section_tokens": [],
    "context_tokens": [],
    "purpose_token": "given-name",
    "recognized_purpose": "given name",
    "token_category": "name",
    "is_known_token": True,
    "unknown_tokens": [],
  }


def test_bs_sem_154_matcher_rejects_semantic_and_state_counterfactuals():
  registry = load_benchmark_registry(REGISTRY)
  variant = next(
    item for item in registry["variants"] if item["variant_id"] == "bs-sem-154"
  )
  expected_evidence = variant["expected_evidence"]
  expected_routes = variant["expected_state"]["routes"]

  seeded = {
    "candidate_type": "autocomplete-purpose-mismatch",
    "state_context": {
      "route": "/details",
      "url": "http://127.0.0.1:4173/details",
    },
    "evidence": deepcopy(expected_evidence["candidate_evidence"]),
  }

  def matches(candidate: dict, *, canonical_state_matches: bool = True) -> bool:
    primary = candidate["evidence"]["primary"]["form_control"]
    return all(
      (
        _element_matches_expected(primary, expected_evidence, record=candidate),
        _candidate_matches_expected_evidence(candidate, expected_evidence),
        _candidate_route_matches(candidate, expected_routes),
        _state_matches_expected_constraints(
          has_routes=True,
          route_matches=True,
          has_benchmark_state_ids=True,
          benchmark_matches=canonical_state_matches,
        ),
      )
    )

  assert matches(seeded)

  clean = deepcopy(seeded)
  clean["evidence"]["primary"]["form_control"]["autocomplete"] = "name"
  clean_context = clean["evidence"]["supporting"][
    "autocomplete_purpose_context_v1"
  ]
  clean_context["control"]["autocomplete"] = "name"
  clean_context["autocomplete_evidence"].update(
    {
      "raw_value": "name",
      "tokens": ["name"],
      "purpose_token": "name",
      "recognized_purpose": "full name",
    }
  )
  assert not matches(clean)

  legitimate_given_name = deepcopy(seeded)
  given_name_primary = legitimate_given_name["evidence"]["primary"][
    "form_control"
  ]
  given_name_primary.update(
    {
      "selector": "input#details-givenName",
      "name": "givenName",
      "id": "details-givenName",
      "label": "Given nameRequired",
      "accessible_name": "Given nameRequired",
    }
  )
  given_name_context = legitimate_given_name["evidence"]["supporting"][
    "autocomplete_purpose_context_v1"
  ]
  given_name_context["control"].update(
    {
      "selector": "input#details-givenName",
      "name": "givenName",
      "id": "details-givenName",
    }
  )
  given_name_context["labeling"].update(
    {
      "visible_label": "Given name REQUIRED",
      "computed_accessible_name": "Given nameRequired",
    }
  )
  given_name_context["labeling"]["label_sources"][0]["text_segments"] = [
    "Given name",
    "Required",
  ]
  given_name_context["field_purpose_evidence"].update(
    {
      "name": "givenName",
      "id": "details-givenName",
      "visible_label": "Given name REQUIRED",
      "computed_accessible_name": "Given nameRequired",
    }
  )
  assert not matches(legitimate_given_name)

  missing_identity = deepcopy(seeded)
  del missing_identity["evidence"]["primary"]["form_control"]["id"]
  del missing_identity["evidence"]["supporting"][
    "autocomplete_purpose_context_v1"
  ]["control"]["id"]
  assert not matches(missing_identity)

  wrong_type_or_name = deepcopy(seeded)
  wrong_type_or_name["evidence"]["primary"]["form_control"].update(
    {"type": "email", "name": "contact"}
  )
  assert not matches(wrong_type_or_name)

  missing_purpose = deepcopy(seeded)
  del missing_purpose["evidence"]["supporting"][
    "autocomplete_purpose_context_v1"
  ]["field_purpose_evidence"]
  assert not matches(missing_purpose)

  wrong_label = deepcopy(seeded)
  wrong_label["evidence"]["primary"]["form_control"].update(
    {"label": "Given nameRequired", "accessible_name": "Given nameRequired"}
  )
  assert not matches(wrong_label)

  wrong_route = deepcopy(seeded)
  wrong_route["state_context"]["route"] = "/schedule"
  wrong_route["state_context"]["url"] = "http://127.0.0.1:4173/schedule"
  assert not matches(wrong_route)
  assert not matches(seeded, canonical_state_matches=False)


def test_bs_sem_155_uses_cancellation_policy_language_and_route_evidence():
  registry = load_benchmark_registry(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }

  assert configurations["booking-bs-sem-155"] == _normal_configuration(
    "bs-sem-155",
    app="booking-scheduler",
    profile="booking-bs-sem-155",
  )

  variant = variants["bs-sem-155"]
  expected_evidence = variant["expected_evidence"]
  expected_routes = variant["expected_state"]["routes"]

  assert variant["profile"] == "booking-bs-sem-155"
  assert variant["candidate_type"] == "language-of-parts-mismatch"
  assert variant["graph_context_needed"] == "not_required"
  assert variant["expected_state"] == {"routes": ["/help"]}
  assert variant["mutation_targets"] == [
    {
      "mutation_property": "lang",
      "subject": "booking.help.cancellationPolicy",
    }
  ]
  assert expected_evidence == {
    "attributes": {
      "tag": "p",
      "text": (
        "Contact the clinic at least 24 hours before your appointment if you "
        "need to cancel. Late cancellations may require a new booking."
      ),
      "root_lang": "en",
      "local_lang": "fr",
      "effective_lang": "fr",
    },
    "bucket": "language_samples",
    "primary_evidence_key": "language_sample",
    "selector_hint": '[data-testid="cancellation-policy-text"]',
    "content_markers": {
      "english": [
        (
          "Contact the clinic at least 24 hours before your appointment if "
          "you need to cancel."
        ),
        "Late cancellations may require a new booking.",
      ],
    },
  }

  seeded = {
    "candidate_type": "language-of-parts-mismatch",
    "state_context": {
      "route": "/help",
      "url": "http://127.0.0.1:4173/help",
    },
    "evidence": {
      "primary": {
        "language_sample": {
          "selector": '[data-testid="cancellation-policy-text"]',
          "tag": "p",
          "text": (
            "Contact the clinic at least 24 hours before your appointment if "
            "you need to cancel. Late cancellations may require a new booking."
          ),
          "root_lang": "en",
          "local_lang": "fr",
          "effective_lang": "fr",
        },
      },
    },
  }

  def matches(candidate):
    primary = candidate["evidence"]["primary"]["language_sample"]
    return all(
      (
        _element_matches_expected(primary, expected_evidence, record=candidate),
        _candidate_matches_expected_evidence(candidate, expected_evidence),
        _candidate_route_matches(candidate, expected_routes),
        _state_matches_expected_constraints(
          has_routes=True,
          route_matches=True,
          has_benchmark_state_ids=False,
          benchmark_matches=False,
        ),
      )
    )

  assert matches(seeded)

  clean = deepcopy(seeded)
  clean["evidence"]["primary"]["language_sample"].update(
    {"local_lang": "", "effective_lang": "en"}
  )
  assert not matches(clean)

  wrong_target = deepcopy(seeded)
  wrong_target["evidence"]["primary"]["language_sample"]["selector"] = (
    '[data-testid="rescheduling-policy-text"]'
  )
  assert not matches(wrong_target)

  legitimate_french = deepcopy(seeded)
  legitimate_french["evidence"]["primary"]["language_sample"]["text"] = (
    "Contactez la clinique au moins 24 heures avant votre rendez-vous."
  )
  assert not matches(legitimate_french)

  wrong_root = deepcopy(seeded)
  wrong_root["evidence"]["primary"]["language_sample"]["root_lang"] = "de"
  assert not matches(wrong_root)

  wrong_route = deepcopy(seeded)
  wrong_route["state_context"].update(
    {"route": "/details", "url": "http://127.0.0.1:4173/details"}
  )
  assert not matches(wrong_route)


def test_bs_sem_156_uses_confirmation_message_language_and_route_evidence():
  registry = load_benchmark_registry(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }

  assert configurations["booking-bs-sem-156"] == _normal_configuration(
    "bs-sem-156",
    app="booking-scheduler",
    profile="booking-bs-sem-156",
  )

  variant = variants["bs-sem-156"]
  expected_evidence = variant["expected_evidence"]
  expected_routes = variant["expected_state"]["routes"]

  assert variant["profile"] == "booking-bs-sem-156"
  assert variant["candidate_type"] == "language-of-parts-mismatch"
  assert variant["graph_context_needed"] == "not_required"
  assert variant["expected_state"] == {"routes": ["/confirmation"]}
  assert variant["mutation_targets"] == [
    {
      "mutation_property": "lang",
      "subject": "booking.confirmation.successMessage",
    }
  ]
  assert expected_evidence == {
    "attributes": {
      "tag": "p",
      "text": (
        "Your booking is complete. A confirmation has been prepared for the "
        "contact details below."
      ),
      "root_lang": "en",
      "local_lang": "es",
      "effective_lang": "es",
    },
    "bucket": "language_samples",
    "primary_evidence_key": "language_sample",
    "selector_hint": '[data-testid="confirmation-message"]',
    "content_markers": {
      "english": [
        "Your booking is complete.",
        "A confirmation has been prepared for the contact details below.",
      ],
    },
  }

  seeded = {
    "candidate_type": "language-of-parts-mismatch",
    "state_context": {
      "route": "/confirmation",
      "url": "http://127.0.0.1:4173/confirmation",
    },
    "evidence": {
      "primary": {
        "language_sample": {
          "selector": '[data-testid="confirmation-message"]',
          "tag": "p",
          "text": (
            "Your booking is complete. A confirmation has been prepared for "
            "the contact details below."
          ),
          "root_lang": "en",
          "local_lang": "es",
          "effective_lang": "es",
        },
      },
    },
  }

  def matches(candidate):
    primary = candidate["evidence"]["primary"]["language_sample"]
    return all(
      (
        _element_matches_expected(primary, expected_evidence, record=candidate),
        _candidate_matches_expected_evidence(candidate, expected_evidence),
        _candidate_route_matches(candidate, expected_routes),
        _state_matches_expected_constraints(
          has_routes=True,
          route_matches=True,
          has_benchmark_state_ids=False,
          benchmark_matches=False,
        ),
      )
    )

  assert matches(seeded)

  clean = deepcopy(seeded)
  clean["evidence"]["primary"]["language_sample"].update(
    {"local_lang": "", "effective_lang": "en"}
  )
  assert not matches(clean)

  wrong_target = deepcopy(seeded)
  wrong_target["evidence"]["primary"]["language_sample"]["selector"] = (
    '[data-testid="confirmation-reference"]'
  )
  assert not matches(wrong_target)

  legitimate_spanish = deepcopy(seeded)
  legitimate_spanish["evidence"]["primary"]["language_sample"]["text"] = (
    "Su reserva esta completa."
  )
  assert not matches(legitimate_spanish)

  wrong_root = deepcopy(seeded)
  wrong_root["evidence"]["primary"]["language_sample"]["root_lang"] = "fr"
  assert not matches(wrong_root)

  wrong_route = deepcopy(seeded)
  wrong_route["state_context"].update(
    {"route": "/help", "url": "http://127.0.0.1:4173/help"}
  )
  assert not matches(wrong_route)

  matching_variant_ids = []
  primary = seeded["evidence"]["primary"]["language_sample"]
  for candidate_variant in variants.values():
    if candidate_variant["candidate_type"] != "language-of-parts-mismatch":
      continue
    candidate_evidence = candidate_variant["expected_evidence"]
    candidate_routes = candidate_variant["expected_state"].get("routes", [])
    if all(
      (
        _element_matches_expected(
          primary,
          candidate_evidence,
          record=seeded,
        ),
        _candidate_matches_expected_evidence(seeded, candidate_evidence),
        _candidate_route_matches(seeded, candidate_routes),
      )
    ):
      matching_variant_ids.append(candidate_variant["variant_id"])

  assert matching_variant_ids == ["bs-sem-156"]


def test_bs_sem_157_uses_preparation_instructions_language_and_route_evidence():
  registry = load_benchmark_registry(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }

  assert configurations["booking-bs-sem-157"] == _normal_configuration(
    "bs-sem-157",
    app="booking-scheduler",
    profile="booking-bs-sem-157",
  )

  variant = variants["bs-sem-157"]
  expected_evidence = variant["expected_evidence"]
  expected_routes = variant["expected_state"]["routes"]

  assert variant["profile"] == "booking-bs-sem-157"
  assert variant["candidate_type"] == "language-of-parts-mismatch"
  assert variant["graph_context_needed"] == "not_required"
  assert variant["expected_state"] == {"routes": ["/help"]}
  assert variant["mutation_targets"] == [
    {
      "mutation_property": "lang",
      "subject": "booking.help.preparationInstructions",
    }
  ]
  assert expected_evidence == {
    "attributes": {
      "tag": "p",
      "text": (
        "Arrive 10 minutes early and bring any documents or notes relevant "
        "to the service you selected."
      ),
      "root_lang": "en",
      "local_lang": "de",
      "effective_lang": "de",
    },
    "bucket": "language_samples",
    "primary_evidence_key": "language_sample",
    "selector_hint": '[data-testid="preparation-instructions-text"]',
    "content_markers": {
      "english": [
        "Arrive 10 minutes early",
        "bring any documents or notes relevant to the service you selected.",
      ],
    },
  }

  seeded = {
    "candidate_type": "language-of-parts-mismatch",
    "state_context": {
      "route": "/help",
      "url": "http://127.0.0.1:4173/help",
    },
    "evidence": {
      "primary": {
        "language_sample": {
          "selector": '[data-testid="preparation-instructions-text"]',
          "tag": "p",
          "text": (
            "Arrive 10 minutes early and bring any documents or notes "
            "relevant to the service you selected."
          ),
          "root_lang": "en",
          "local_lang": "de",
          "effective_lang": "de",
        },
      },
    },
  }

  def matches(candidate):
    primary = candidate["evidence"]["primary"]["language_sample"]
    return all(
      (
        _element_matches_expected(primary, expected_evidence, record=candidate),
        _candidate_matches_expected_evidence(candidate, expected_evidence),
        _candidate_route_matches(candidate, expected_routes),
        _state_matches_expected_constraints(
          has_routes=True,
          route_matches=True,
          has_benchmark_state_ids=False,
          benchmark_matches=False,
        ),
      )
    )

  assert matches(seeded)

  clean = deepcopy(seeded)
  clean["evidence"]["primary"]["language_sample"].update(
    {"local_lang": "", "effective_lang": "en"}
  )
  assert not matches(clean)

  wrong_target = deepcopy(seeded)
  wrong_target["evidence"]["primary"]["language_sample"]["selector"] = (
    '[data-testid="cancellation-policy-text"]'
  )
  assert not matches(wrong_target)

  legitimate_german = deepcopy(seeded)
  legitimate_german["evidence"]["primary"]["language_sample"]["text"] = (
    "Kommen Sie 10 Minuten fruher und bringen Sie relevante Unterlagen mit."
  )
  assert not matches(legitimate_german)

  wrong_root = deepcopy(seeded)
  wrong_root["evidence"]["primary"]["language_sample"]["root_lang"] = "fr"
  assert not matches(wrong_root)

  wrong_route = deepcopy(seeded)
  wrong_route["state_context"].update(
    {"route": "/confirmation", "url": "http://127.0.0.1:4173/confirmation"}
  )
  assert not matches(wrong_route)

  missing_text = deepcopy(seeded)
  missing_text["evidence"]["primary"]["language_sample"].pop("text")
  assert not matches(missing_text)

  matching_variant_ids = []
  primary = seeded["evidence"]["primary"]["language_sample"]
  for candidate_variant in variants.values():
    if candidate_variant["candidate_type"] != "language-of-parts-mismatch":
      continue
    candidate_evidence = candidate_variant["expected_evidence"]
    candidate_routes = candidate_variant["expected_state"].get("routes", [])
    if all(
      (
        _element_matches_expected(
          primary,
          candidate_evidence,
          record=seeded,
        ),
        _candidate_matches_expected_evidence(seeded, candidate_evidence),
        _candidate_route_matches(seeded, candidate_routes),
      )
    ):
      matching_variant_ids.append(candidate_variant["variant_id"])

  assert matching_variant_ids == ["bs-sem-157"]


def test_bs_sem_158_uses_arrival_instructions_language_and_route_evidence():
  registry = load_benchmark_registry(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }

  assert configurations["booking-bs-sem-158"] == _normal_configuration(
    "bs-sem-158",
    app="booking-scheduler",
    profile="booking-bs-sem-158",
  )

  variant = variants["bs-sem-158"]
  expected_evidence = variant["expected_evidence"]
  expected_routes = variant["expected_state"]["routes"]

  assert variant["profile"] == "booking-bs-sem-158"
  assert variant["candidate_type"] == "language-of-parts-mismatch"
  assert variant["graph_context_needed"] == "not_required"
  assert variant["expected_state"] == {"routes": ["/help"]}
  assert variant["mutation_targets"] == [
    {
      "mutation_property": "lang",
      "subject": "booking.help.arrivalInstructions",
    }
  ]
  assert expected_evidence == {
    "attributes": {
      "tag": "p",
      "text": (
        "Use the Cedar Lane entrance and check in at reception on the "
        "ground floor."
      ),
      "root_lang": "en",
      "local_lang": "it",
      "effective_lang": "it",
    },
    "bucket": "language_samples",
    "primary_evidence_key": "language_sample",
    "selector_hint": '[data-testid="arrival-instructions-text"]',
    "content_markers": {
      "english": [
        "Use the Cedar Lane entrance",
        "check in at reception on the ground floor.",
      ],
    },
  }

  seeded = {
    "candidate_type": "language-of-parts-mismatch",
    "state_context": {
      "route": "/help",
      "url": "http://127.0.0.1:4173/help",
    },
    "evidence": {
      "primary": {
        "language_sample": {
          "selector": '[data-testid="arrival-instructions-text"]',
          "tag": "p",
          "text": (
            "Use the Cedar Lane entrance and check in at reception on the "
            "ground floor."
          ),
          "root_lang": "en",
          "local_lang": "it",
          "effective_lang": "it",
        },
      },
    },
  }

  def matches(candidate):
    primary = candidate["evidence"]["primary"]["language_sample"]
    return all(
      (
        _element_matches_expected(primary, expected_evidence, record=candidate),
        _candidate_matches_expected_evidence(candidate, expected_evidence),
        _candidate_route_matches(candidate, expected_routes),
        _state_matches_expected_constraints(
          has_routes=True,
          route_matches=True,
          has_benchmark_state_ids=False,
          benchmark_matches=False,
        ),
      )
    )

  assert matches(seeded)

  clean = deepcopy(seeded)
  clean["evidence"]["primary"]["language_sample"].update(
    {"local_lang": "", "effective_lang": "en"}
  )
  assert not matches(clean)

  wrong_target = deepcopy(seeded)
  wrong_target["evidence"]["primary"]["language_sample"]["selector"] = (
    '[data-testid="preparation-instructions-text"]'
  )
  assert not matches(wrong_target)

  legitimate_italian = deepcopy(seeded)
  legitimate_italian["evidence"]["primary"]["language_sample"]["text"] = (
    "Usa l'ingresso di Cedar Lane e registrati alla reception al piano terra."
  )
  assert not matches(legitimate_italian)

  wrong_root = deepcopy(seeded)
  wrong_root["evidence"]["primary"]["language_sample"]["root_lang"] = "de"
  assert not matches(wrong_root)

  wrong_route = deepcopy(seeded)
  wrong_route["state_context"].update(
    {"route": "/confirmation", "url": "http://127.0.0.1:4173/confirmation"}
  )
  assert not matches(wrong_route)

  missing_text = deepcopy(seeded)
  missing_text["evidence"]["primary"]["language_sample"].pop("text")
  assert not matches(missing_text)

  missing_local_lang = deepcopy(seeded)
  missing_local_lang["evidence"]["primary"]["language_sample"].pop("local_lang")
  assert not matches(missing_local_lang)

  matching_variant_ids = []
  primary = seeded["evidence"]["primary"]["language_sample"]
  for candidate_variant in variants.values():
    if candidate_variant["candidate_type"] != "language-of-parts-mismatch":
      continue
    candidate_evidence = candidate_variant["expected_evidence"]
    candidate_routes = candidate_variant["expected_state"].get("routes", [])
    if all(
      (
        _element_matches_expected(
          primary,
          candidate_evidence,
          record=seeded,
        ),
        _candidate_matches_expected_evidence(seeded, candidate_evidence),
        _candidate_route_matches(seeded, candidate_routes),
      )
    ):
      matching_variant_ids.append(candidate_variant["variant_id"])

  assert matching_variant_ids == ["bs-sem-158"]


def test_bs_sem_159_uses_help_page_language_and_english_content_evidence():
  registry = load_benchmark_registry(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }

  assert configurations["booking-bs-sem-159"] == _normal_configuration(
    "bs-sem-159",
    app="booking-scheduler",
    profile="booking-bs-sem-159",
  )

  variant = variants["bs-sem-159"]
  expected_evidence = variant["expected_evidence"]
  expected_routes = variant["expected_state"]["routes"]

  assert variant["profile"] == "booking-bs-sem-159"
  assert variant["candidate_type"] == "lang-mismatch"
  assert variant["graph_context_needed"] == "not_required"
  assert variant["expected_state"] == {"routes": ["/help"]}
  assert variant["mutation_targets"] == [
    {
      "mutation_property": "lang",
      "subject": "booking.page.help",
    }
  ]
  assert expected_evidence == {
    "attributes": {
      "html_lang": "de",
      "document_lang": "de",
      "title": "Help & policies | Booking Scheduler Benchmark",
    },
    "attribute_contains": {"body_text_sample": "Help & policies"},
    "bucket": "page",
    "candidate_evidence": {
      "supporting": {
        "lang_mismatch_context_v1": {
          "declared_page_language": {
            "html_lang": "de",
            "document_lang": "de",
            "route": "/help",
          },
          "page_text_evidence": {
            "strongest_marker_language_hint": "en",
          },
        },
      },
    },
    "content_markers": {
      "english": [
        "Help & policies",
        "Cancellation and rescheduling",
        "Preparing for your appointment",
        "Directions",
      ],
    },
  }

  seeded = {
    "candidate_type": "lang-mismatch",
    "state_context": {
      "route": "/help",
      "url": "http://127.0.0.1:4173/help",
    },
    "evidence": {
      "primary": {
        "page": {
          "url": "http://127.0.0.1:4173/help",
          "title": "Help & policies | Booking Scheduler Benchmark",
          "document_lang": "de",
          "html_lang": "de",
          "body_text_sample": (
            "Booking Scheduler Benchmark Help & policies Cancellation and "
            "rescheduling Preparing for your appointment Directions"
          ),
        },
      },
      "supporting": {
        "lang_mismatch_context_v1": {
          "declared_page_language": {
            "html_lang": "de",
            "document_lang": "de",
            "title": "Help & policies | Booking Scheduler Benchmark",
            "route": "/help",
          },
          "page_text_evidence": {
            "strongest_marker_language_hint": "en",
          },
        },
      },
    },
  }

  def matches(candidate, candidate_variant=variant):
    candidate_evidence = candidate_variant["expected_evidence"]
    candidate_routes = candidate_variant["expected_state"].get("routes", [])
    primary = candidate["evidence"]["primary"]["page"]
    return all(
      (
        _element_matches_expected(
          primary,
          candidate_evidence,
          record=candidate,
        ),
        _candidate_matches_expected_evidence(candidate, candidate_evidence),
        _candidate_route_matches(candidate, candidate_routes),
        _state_matches_expected_constraints(
          has_routes=True,
          route_matches=True,
          has_benchmark_state_ids=False,
          benchmark_matches=False,
        ),
      )
    )

  assert matches(seeded)

  clean = deepcopy(seeded)
  clean["evidence"]["primary"]["page"].update(
    {"document_lang": "en", "html_lang": "en"}
  )
  clean["evidence"]["supporting"]["lang_mismatch_context_v1"][
    "declared_page_language"
  ].update({"document_lang": "en", "html_lang": "en"})
  assert not matches(clean)

  wrong_content = deepcopy(seeded)
  wrong_content["evidence"]["primary"]["page"]["body_text_sample"] = (
    "Hilfe und Richtlinien Stornierung und Umbuchung"
  )
  assert not matches(wrong_content)

  wrong_language_hint = deepcopy(seeded)
  wrong_language_hint["evidence"]["supporting"]["lang_mismatch_context_v1"][
    "page_text_evidence"
  ]["strongest_marker_language_hint"] = "de"
  assert not matches(wrong_language_hint)

  wrong_title = deepcopy(seeded)
  wrong_title["evidence"]["primary"]["page"]["title"] = (
    "Services | Booking Scheduler Benchmark"
  )
  assert not matches(wrong_title)

  wrong_route = deepcopy(seeded)
  wrong_route["state_context"].update(
    {"route": "/services", "url": "http://127.0.0.1:4173/services"}
  )
  assert not matches(wrong_route)

  missing_hint = deepcopy(seeded)
  missing_hint["evidence"]["supporting"]["lang_mismatch_context_v1"][
    "page_text_evidence"
  ].pop("strongest_marker_language_hint")
  assert not matches(missing_hint)

  matching_variant_ids = [
    candidate_variant["variant_id"]
    for candidate_variant in variants.values()
    if candidate_variant["candidate_type"] == "lang-mismatch"
    and matches(seeded, candidate_variant)
  ]
  assert matching_variant_ids == ["bs-sem-159"]


def test_bs_sem_160_uses_confirmation_page_language_and_english_content_evidence():
  registry = load_benchmark_registry(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }

  assert configurations["booking-bs-sem-160"] == _normal_configuration(
    "bs-sem-160",
    app="booking-scheduler",
    profile="booking-bs-sem-160",
  )

  variant = variants["bs-sem-160"]
  expected_evidence = variant["expected_evidence"]
  expected_routes = variant["expected_state"]["routes"]

  assert variant["profile"] == "booking-bs-sem-160"
  assert variant["candidate_type"] == "lang-mismatch"
  assert variant["graph_context_needed"] == "not_required"
  assert variant["expected_state"] == {"routes": ["/confirmation"]}
  assert variant["mutation_targets"] == [
    {
      "mutation_property": "lang",
      "subject": "booking.page.confirmation",
    }
  ]
  assert expected_evidence == {
    "attributes": {
      "html_lang": "es",
      "document_lang": "es",
      "title": "Booking confirmed | Booking Scheduler Benchmark",
    },
    "attribute_contains": {"body_text_sample": "Booking confirmed"},
    "bucket": "page",
    "candidate_evidence": {
      "supporting": {
        "lang_mismatch_context_v1": {
          "declared_page_language": {
            "html_lang": "es",
            "document_lang": "es",
            "route": "/confirmation",
          },
          "page_text_evidence": {
            "strongest_marker_language_hint": "en",
          },
        },
      },
    },
    "content_markers": {
      "english": [
        "Booking confirmed",
        "Your appointment is confirmed",
        "Confirmed booking",
        "Contact details",
        "Book another appointment",
      ],
    },
  }

  seeded = {
    "candidate_type": "lang-mismatch",
    "state_context": {
      "route": "/confirmation",
      "url": "http://127.0.0.1:4173/confirmation",
    },
    "evidence": {
      "primary": {
        "page": {
          "url": "http://127.0.0.1:4173/confirmation",
          "title": "Booking confirmed | Booking Scheduler Benchmark",
          "document_lang": "es",
          "html_lang": "es",
          "body_text_sample": (
            "Booking confirmed Your appointment is confirmed Confirmed booking "
            "Contact details Book another appointment"
          ),
        },
      },
      "supporting": {
        "lang_mismatch_context_v1": {
          "declared_page_language": {
            "html_lang": "es",
            "document_lang": "es",
            "title": "Booking confirmed | Booking Scheduler Benchmark",
            "route": "/confirmation",
          },
          "page_text_evidence": {
            "strongest_marker_language_hint": "en",
          },
        },
      },
    },
  }

  def matches(candidate, candidate_variant=variant):
    candidate_evidence = candidate_variant["expected_evidence"]
    candidate_routes = candidate_variant["expected_state"].get("routes", [])
    primary = candidate["evidence"]["primary"]["page"]
    return all(
      (
        _element_matches_expected(
          primary,
          candidate_evidence,
          record=candidate,
        ),
        _candidate_matches_expected_evidence(candidate, candidate_evidence),
        _candidate_route_matches(candidate, candidate_routes),
        _state_matches_expected_constraints(
          has_routes=True,
          route_matches=True,
          has_benchmark_state_ids=False,
          benchmark_matches=False,
        ),
      )
    )

  assert matches(seeded)

  clean = deepcopy(seeded)
  clean["evidence"]["primary"]["page"].update(
    {"document_lang": "en", "html_lang": "en"}
  )
  clean["evidence"]["supporting"]["lang_mismatch_context_v1"][
    "declared_page_language"
  ].update({"document_lang": "en", "html_lang": "en"})
  assert not matches(clean)

  genuine_spanish = deepcopy(seeded)
  genuine_spanish["evidence"]["primary"]["page"]["body_text_sample"] = (
    "Reserva confirmada Su cita está confirmada Detalles de contacto"
  )
  genuine_spanish["evidence"]["supporting"]["lang_mismatch_context_v1"][
    "page_text_evidence"
  ]["strongest_marker_language_hint"] = "es"
  assert not matches(genuine_spanish)

  wrong_title = deepcopy(seeded)
  wrong_title["evidence"]["primary"]["page"]["title"] = (
    "Review appointment | Booking Scheduler Benchmark"
  )
  assert not matches(wrong_title)

  wrong_route = deepcopy(seeded)
  wrong_route["state_context"].update(
    {"route": "/review", "url": "http://127.0.0.1:4173/review"}
  )
  assert not matches(wrong_route)

  missing_hint = deepcopy(seeded)
  missing_hint["evidence"]["supporting"]["lang_mismatch_context_v1"][
    "page_text_evidence"
  ].pop("strongest_marker_language_hint")
  assert not matches(missing_hint)

  missing_lang = deepcopy(seeded)
  missing_lang["evidence"]["primary"]["page"].pop("html_lang")
  assert not matches(missing_lang)

  matching_variant_ids = [
    candidate_variant["variant_id"]
    for candidate_variant in variants.values()
    if candidate_variant["candidate_type"] == "lang-mismatch"
    and matches(seeded, candidate_variant)
  ]
  assert matching_variant_ids == ["bs-sem-160"]


def test_bs_sem_161_uses_details_page_language_and_english_content_evidence():
  registry = load_benchmark_registry(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }

  assert configurations["booking-bs-sem-161"] == _normal_configuration(
    "bs-sem-161",
    app="booking-scheduler",
    profile="booking-bs-sem-161",
  )

  variant = variants["bs-sem-161"]
  expected_evidence = variant["expected_evidence"]

  assert variant["profile"] == "booking-bs-sem-161"
  assert variant["candidate_type"] == "lang-mismatch"
  assert variant["graph_context_needed"] == "not_required"
  assert variant["expected_state"] == {
    "routes": ["/details"],
    "benchmark_state_ids": ["BS-S003"],
  }
  assert variant["mutation_targets"] == [
    {
      "mutation_property": "lang",
      "subject": "booking.page.details",
    }
  ]
  assert expected_evidence == {
    "attributes": {
      "html_lang": "de",
      "document_lang": "de",
      "title": "Booking details | Booking Scheduler Benchmark",
    },
    "attribute_contains": {"body_text_sample": "Booking details"},
    "bucket": "page",
    "candidate_evidence": {
      "supporting": {
        "lang_mismatch_context_v1": {
          "declared_page_language": {
            "html_lang": "de",
            "document_lang": "de",
            "route": "/details",
          },
          "page_text_evidence": {
            "strongest_marker_language_hint": "en",
          },
        },
      },
    },
    "content_markers": {
      "english": [
        "Booking details",
        "Enter required customer details for the selected appointment",
        "Customer details",
        "Full name",
        "Continue to review",
      ],
    },
  }

  seeded = {
    "candidate_type": "lang-mismatch",
    "state_context": {
      "route": "/details",
      "url": "http://127.0.0.1:4173/details",
      "benchmark_state_id": "BS-S003",
    },
    "evidence": {
      "primary": {
        "page": {
          "url": "http://127.0.0.1:4173/details",
          "title": "Booking details | Booking Scheduler Benchmark",
          "document_lang": "de",
          "html_lang": "de",
          "body_text_sample": (
            "Booking details Enter required customer details for the selected "
            "appointment Customer details Full name Email Phone Continue to review"
          ),
        },
      },
      "supporting": {
        "lang_mismatch_context_v1": {
          "declared_page_language": {
            "html_lang": "de",
            "document_lang": "de",
            "title": "Booking details | Booking Scheduler Benchmark",
            "route": "/details",
          },
          "page_text_evidence": {
            "strongest_marker_language_hint": "en",
          },
        },
      },
    },
  }

  def matches(candidate, candidate_variant=variant):
    candidate_evidence = candidate_variant["expected_evidence"]
    expected_state = candidate_variant["expected_state"]
    candidate_routes = expected_state.get("routes", [])
    candidate_benchmark_states = expected_state.get("benchmark_state_ids", [])
    route_matches = _candidate_route_matches(candidate, candidate_routes)
    benchmark_matches = (
      candidate["state_context"].get("benchmark_state_id")
      in candidate_benchmark_states
    )
    primary = candidate["evidence"]["primary"]["page"]
    return all(
      (
        _element_matches_expected(
          primary,
          candidate_evidence,
          record=candidate,
        ),
        _candidate_matches_expected_evidence(candidate, candidate_evidence),
        route_matches,
        _state_matches_expected_constraints(
          has_routes=bool(candidate_routes),
          route_matches=route_matches,
          has_benchmark_state_ids=bool(candidate_benchmark_states),
          benchmark_matches=benchmark_matches,
        ),
      )
    )

  assert matches(seeded)

  clean = deepcopy(seeded)
  clean["evidence"]["primary"]["page"].update(
    {"document_lang": "en", "html_lang": "en"}
  )
  clean["evidence"]["supporting"]["lang_mismatch_context_v1"][
    "declared_page_language"
  ].update({"document_lang": "en", "html_lang": "en"})
  assert not matches(clean)

  genuine_german = deepcopy(seeded)
  genuine_german["evidence"]["primary"]["page"]["body_text_sample"] = (
    "Buchungsdetails Geben Sie die erforderlichen Kundendaten ein"
  )
  genuine_german["evidence"]["supporting"]["lang_mismatch_context_v1"][
    "page_text_evidence"
  ]["strongest_marker_language_hint"] = "de"
  assert not matches(genuine_german)

  wrong_title = deepcopy(seeded)
  wrong_title["evidence"]["primary"]["page"]["title"] = (
    "Schedule appointment | Booking Scheduler Benchmark"
  )
  assert not matches(wrong_title)

  wrong_route = deepcopy(seeded)
  wrong_route["state_context"].update(
    {"route": "/schedule", "url": "http://127.0.0.1:4173/schedule"}
  )
  assert not matches(wrong_route)

  wrong_state = deepcopy(seeded)
  wrong_state["state_context"]["benchmark_state_id"] = "BS-S002"
  assert not matches(wrong_state)

  missing_hint = deepcopy(seeded)
  missing_hint["evidence"]["supporting"]["lang_mismatch_context_v1"][
    "page_text_evidence"
  ].pop("strongest_marker_language_hint")
  assert not matches(missing_hint)

  missing_lang = deepcopy(seeded)
  missing_lang["evidence"]["primary"]["page"].pop("html_lang")
  assert not matches(missing_lang)

  matching_variant_ids = [
    candidate_variant["variant_id"]
    for candidate_variant in variants.values()
    if candidate_variant["candidate_type"] == "lang-mismatch"
    and matches(seeded, candidate_variant)
  ]
  assert matching_variant_ids == ["bs-sem-161"]


def test_bs_sem_162_uses_review_page_language_and_english_content_evidence():
  registry = load_benchmark_registry(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }

  assert configurations["booking-bs-sem-162"] == _normal_configuration(
    "bs-sem-162",
    app="booking-scheduler",
    profile="booking-bs-sem-162",
  )

  variant = variants["bs-sem-162"]
  expected_evidence = variant["expected_evidence"]

  assert variant["profile"] == "booking-bs-sem-162"
  assert variant["candidate_type"] == "lang-mismatch"
  assert variant["graph_context_needed"] == "not_required"
  assert variant["expected_state"] == {
    "routes": ["/review"],
    "benchmark_state_ids": ["BS-S004"],
  }
  assert variant["mutation_targets"] == [
    {
      "mutation_property": "lang",
      "subject": "booking.page.review",
    }
  ]
  assert expected_evidence == {
    "attributes": {
      "html_lang": "fr",
      "document_lang": "fr",
      "title": "Review appointment | Booking Scheduler Benchmark",
    },
    "attribute_contains": {"body_text_sample": "Review appointment"},
    "bucket": "page",
    "candidate_evidence": {
      "supporting": {
        "lang_mismatch_context_v1": {
          "declared_page_language": {
            "html_lang": "fr",
            "document_lang": "fr",
            "route": "/review",
          },
          "page_text_evidence": {
            "strongest_marker_language_hint": "en",
          },
        },
      },
    },
    "content_markers": {
      "english": [
        "Review appointment",
        "Review only. No appointment has been confirmed yet",
        "Review appointment details",
        "Customer details",
      ],
    },
  }

  seeded = {
    "candidate_type": "lang-mismatch",
    "state_context": {
      "route": "/review",
      "url": "http://127.0.0.1:4173/review",
      "benchmark_state_id": "BS-S004",
    },
    "evidence": {
      "primary": {
        "page": {
          "url": "http://127.0.0.1:4173/review",
          "title": "Review appointment | Booking Scheduler Benchmark",
          "document_lang": "fr",
          "html_lang": "fr",
          "body_text_sample": (
            "Review appointment Review only. No appointment has been confirmed "
            "yet Review appointment details Customer details"
          ),
        },
      },
      "supporting": {
        "lang_mismatch_context_v1": {
          "declared_page_language": {
            "html_lang": "fr",
            "document_lang": "fr",
            "title": "Review appointment | Booking Scheduler Benchmark",
            "route": "/review",
          },
          "page_text_evidence": {
            "strongest_marker_language_hint": "en",
          },
        },
      },
    },
  }

  def matches(candidate, candidate_variant=variant):
    candidate_evidence = candidate_variant["expected_evidence"]
    expected_state = candidate_variant["expected_state"]
    candidate_routes = expected_state.get("routes", [])
    candidate_benchmark_states = expected_state.get("benchmark_state_ids", [])
    route_matches = _candidate_route_matches(candidate, candidate_routes)
    benchmark_matches = (
      candidate["state_context"].get("benchmark_state_id")
      in candidate_benchmark_states
    )
    primary = candidate["evidence"]["primary"]["page"]
    return all(
      (
        _element_matches_expected(
          primary,
          candidate_evidence,
          record=candidate,
        ),
        _candidate_matches_expected_evidence(candidate, candidate_evidence),
        route_matches,
        _state_matches_expected_constraints(
          has_routes=bool(candidate_routes),
          route_matches=route_matches,
          has_benchmark_state_ids=bool(candidate_benchmark_states),
          benchmark_matches=benchmark_matches,
        ),
      )
    )

  assert matches(seeded)

  clean = deepcopy(seeded)
  clean["evidence"]["primary"]["page"].update(
    {"document_lang": "en", "html_lang": "en"}
  )
  clean["evidence"]["supporting"]["lang_mismatch_context_v1"][
    "declared_page_language"
  ].update({"document_lang": "en", "html_lang": "en"})
  assert not matches(clean)

  genuine_french = deepcopy(seeded)
  genuine_french["evidence"]["primary"]["page"]["body_text_sample"] = (
    "Verifier le rendez-vous Aucun rendez-vous n'a encore ete confirme"
  )
  genuine_french["evidence"]["supporting"]["lang_mismatch_context_v1"][
    "page_text_evidence"
  ]["strongest_marker_language_hint"] = "fr"
  assert not matches(genuine_french)

  wrong_title = deepcopy(seeded)
  wrong_title["evidence"]["primary"]["page"]["title"] = (
    "Booking details | Booking Scheduler Benchmark"
  )
  assert not matches(wrong_title)

  wrong_route = deepcopy(seeded)
  wrong_route["state_context"].update(
    {"route": "/details", "url": "http://127.0.0.1:4173/details"}
  )
  assert not matches(wrong_route)

  wrong_state = deepcopy(seeded)
  wrong_state["state_context"]["benchmark_state_id"] = "BS-S003"
  assert not matches(wrong_state)

  missing_hint = deepcopy(seeded)
  missing_hint["evidence"]["supporting"]["lang_mismatch_context_v1"][
    "page_text_evidence"
  ].pop("strongest_marker_language_hint")
  assert not matches(missing_hint)

  missing_lang = deepcopy(seeded)
  missing_lang["evidence"]["primary"]["page"].pop("html_lang")
  assert not matches(missing_lang)

  matching_variant_ids = [
    candidate_variant["variant_id"]
    for candidate_variant in variants.values()
    if candidate_variant["candidate_type"] == "lang-mismatch"
    and matches(seeded, candidate_variant)
  ]
  assert matching_variant_ids == ["bs-sem-162"]


def test_bs_sem_130_uses_accessibility_textarea_identity_and_native_phone_label_evidence():
  registry = load_benchmark_registry(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }

  assert configurations["booking-bs-sem-130"] == _normal_configuration(
    "bs-sem-130",
    app="booking-scheduler",
    profile="booking-bs-sem-130",
  )

  variant = variants["bs-sem-130"]
  expected_evidence = variant["expected_evidence"]
  candidate_evidence = expected_evidence["candidate_evidence"]
  form_label_context = candidate_evidence["supporting"][
    "form_label_context_v1"
  ]

  assert variant["profile"] == "booking-bs-sem-130"
  assert variant["candidate_type"] == "form-label-mismatch"
  assert variant["graph_context_needed"] == "not_required"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["BS-S003"],
    "routes": ["/details"],
  }
  assert variant["mutation_targets"] == [
    {
      "mutation_property": "labelText",
      "subject": "booking.details.accessibilityNeeds",
    }
  ]
  assert expected_evidence["control"] == {
    "id": "details-accessibilityNeeds",
    "name": "accessibilityNeeds",
  }
  assert expected_evidence["attributes"] == {
    "tag": "textarea",
    "required": False,
    "aria_describedby": "details-accessibilityNeeds-hint",
    "placeholder": "Accessibility needs, preparation notes, or special requests",
    "accessible_name": "PhoneOptional",
    "label": "PhoneOptional",
  }
  assert candidate_evidence["primary"]["form_control"] == {
    "selector": "textarea#details-accessibilityNeeds",
    "tag": "textarea",
    "name": "accessibilityNeeds",
    "id": "details-accessibilityNeeds",
    "placeholder": "Accessibility needs, preparation notes, or special requests",
    "required": False,
    "aria_describedby": "details-accessibilityNeeds-hint",
    "accessible_name": "PhoneOptional",
    "label": "PhoneOptional",
  }
  assert form_label_context["labeling"] == {
    "visible_label": "Phone OPTIONAL",
    "computed_accessible_name": "PhoneOptional",
    "label_sources": [
      {
        "relationship_type": "labels",
        "method": "for",
        "text_segments": ["Phone", "Optional"],
      }
    ],
    "visible_label_in_accessible_name": True,
  }
  assert form_label_context["field_purpose_evidence"] == {
    "name": "accessibilityNeeds",
    "id": "details-accessibilityNeeds",
    "placeholder": "Accessibility needs, preparation notes, or special requests",
    "descriptions": [
      {
        "selector": "p#details-accessibilityNeeds-hint",
        "text": (
          "Share accessibility needs, preparation notes, or special requests "
          "for this appointment."
        ),
        "relationship_type": "describes",
        "method": "aria-describedby",
      }
    ],
    "form_step_or_route_context": {"route": "/details"},
  }


def test_bs_sem_117_uses_selected_slot_state_and_explicit_false_evidence():
  registry = load_benchmark_registry(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }

  assert configurations["booking-bs-sem-117"] == _normal_configuration(
    "bs-sem-117",
    app="booking-scheduler",
    profile="booking-bs-sem-117",
  )

  variant = variants["bs-sem-117"]
  expected_evidence = variant["expected_evidence"]
  candidate_evidence = expected_evidence["candidate_evidence"]

  assert variant["profile"] == "booking-bs-sem-117"
  assert variant["candidate_type"] == "aria-state-mismatch"
  assert variant["graph_context_needed"] == "not_required"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["BS-S002"],
    "routes": ["/schedule"],
  }
  assert variant["mutation_targets"] == [
    {
      "mutation_property": "ariaPressed",
      "subject": "booking.schedule.slot.0900",
    }
  ]
  assert expected_evidence["attributes"] == {
    "tag": "button",
    "text": "09:00 Selected",
    "accessible_name": "09:00 Selected",
  }
  assert expected_evidence["state_attributes"] == {
    "aria_pressed": "false",
  }
  assert candidate_evidence["primary"]["aria_state"] == {
    "bucket": "buttons",
    "tag": "button",
    "text": "09:00 Selected",
    "accessible_name": "09:00 Selected",
    "state_attributes": {"aria_pressed": "false"},
  }


def test_bs_sem_135_uses_unselected_slot_state_evidence():
  registry = load_benchmark_registry(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }

  assert configurations["booking-bs-sem-135"] == _normal_configuration(
    "bs-sem-135",
    app="booking-scheduler",
    profile="booking-bs-sem-135",
  )

  variant = variants["bs-sem-135"]
  expected_evidence = variant["expected_evidence"]
  candidate_evidence = expected_evidence["candidate_evidence"]

  assert variant["profile"] == "booking-bs-sem-135"
  assert variant["candidate_type"] == "aria-state-mismatch"
  assert variant["graph_context_needed"] == "not_required"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["BS-S002"],
    "routes": ["/schedule"],
  }
  assert variant["mutation_targets"] == [
    {
      "mutation_property": "ariaPressed",
      "subject": "booking.schedule.slot.1300",
    }
  ]
  assert expected_evidence["attributes"] == {
    "tag": "button",
    "text": "13:00 Available",
    "accessible_name": "13:00 Available",
  }
  assert expected_evidence["state_attributes"] == {
    "aria_pressed": "true",
  }
  assert candidate_evidence["primary"]["aria_state"] == {
    "bucket": "buttons",
    "tag": "button",
    "text": "13:00 Available",
    "accessible_name": "13:00 Available",
    "state_attributes": {"aria_pressed": "true"},
  }


def test_bs_sem_118_uses_service_heading_and_scoped_panel_evidence():
  registry = load_benchmark_registry(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }

  assert configurations["booking-bs-sem-118"] == _normal_configuration(
    "bs-sem-118",
    app="booking-scheduler",
    profile="booking-bs-sem-118",
  )

  variant = variants["bs-sem-118"]
  expected_evidence = variant["expected_evidence"]
  candidate_evidence = expected_evidence["candidate_evidence"]

  assert variant["profile"] == "booking-bs-sem-118"
  assert variant["candidate_type"] == "heading-not-descriptive"
  assert variant["graph_context_needed"] == "not_required"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["BS-S004"],
    "routes": ["/review"],
  }
  assert variant["mutation_targets"] == [
    {
      "mutation_property": "text",
      "subject": "booking.review.serviceHeading",
    }
  ]
  assert expected_evidence["selector_hint"] == "h3#review-service-heading"
  assert expected_evidence["attributes"] == {
    "tag": "h3",
    "text": "Date and time",
    "level": 3,
    "accessible_name": "Date and time",
  }
  assert candidate_evidence["primary"]["heading"] == {
    "tag": "h3",
    "selector": "h3#review-service-heading",
    "text": "Date and time",
    "level": 3,
    "accessible_name": "Date and time",
  }
  assert candidate_evidence["supporting"]["context"] == {
    "nearby_text": "NameConsultationDuration30 minutes",
    "parent_text": (
      "Date and timeNameConsultationDuration30 minutesChange service"
    ),
    "section_heading": "Date and time",
  }
  assert candidate_evidence["supporting"]["heading_scoped_content"] == {
    "schema_version": "heading_scoped_content_v1",
    "source": "labelledby_landmark_text_sample",
    "source_element_ref": {
      "bucket": "landmarks",
      "tag": "section",
    },
    "text_excerpt": (
      "Date and time Name Consultation Duration 30 minutes Change service"
    ),
    "truncated": False,
  }


def test_bs_sem_119_uses_phone_control_and_associated_error_evidence():
  registry = load_benchmark_registry(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }

  assert configurations["booking-bs-sem-119"] == _normal_configuration(
    "bs-sem-119",
    app="booking-scheduler",
    profile="booking-bs-sem-119",
  )

  variant = variants["bs-sem-119"]
  expected_evidence = variant["expected_evidence"]
  control_evidence, error_evidence = expected_evidence["all_of"]
  assert "candidate_evidence" not in expected_evidence
  candidate_evidence = error_evidence["candidate_evidence"]

  assert variant["profile"] == "booking-bs-sem-119"
  assert variant["candidate_type"] == "error-message-mismatch"
  assert variant["graph_context_needed"] == "not_required"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["BS-S003"],
    "routes": ["/details"],
  }
  assert variant["mutation_targets"] == [
    {
      "mutation_property": "validationMessage",
      "subject": "booking.details.phone",
    }
  ]
  assert control_evidence["primary_evidence_key"] == "form_control"
  assert control_evidence["control"] == {
    "id": "details-phone",
    "name": "phone",
  }
  assert control_evidence["attributes"]["type"] == "tel"
  assert control_evidence["attributes"]["autocomplete"] == "tel"
  assert control_evidence["attributes"]["required"] is True
  assert control_evidence["attributes"]["has_value"] is False
  assert control_evidence["attributes"]["native_validity"]["value_missing"] is True
  assert control_evidence["attribute_contains"] == {
    "label": "Phone",
    "accessible_name": "Phone",
  }
  assert error_evidence == {
    "bucket": "referenced_elements",
    "selector_hint": "p#details-phone-error",
    "attributes": {
      "text": "Choose a date and available time before entering booking details."
    },
    "primary_evidence_key": "error_message",
    "candidate_evidence": candidate_evidence,
  }
  assert candidate_evidence["primary"]["error_message"] == {
    "selector": "p#details-phone-error",
    "text": "Choose a date and available time before entering booking details.",
    "relationship_type": "describes",
    "method": "aria-describedby",
  }
  assert candidate_evidence["supporting"]["error_message_context_v1"][
    "control"
  ]["value_state"] == "empty"


def test_bs_sem_138_uses_full_name_control_and_associated_error_evidence():
  registry = load_benchmark_registry(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }

  assert configurations["booking-bs-sem-138"] == _normal_configuration(
    "bs-sem-138",
    app="booking-scheduler",
    profile="booking-bs-sem-138",
  )

  variant = variants["bs-sem-138"]
  expected_evidence = variant["expected_evidence"]
  control_evidence, error_evidence = expected_evidence["all_of"]
  assert "candidate_evidence" not in expected_evidence
  candidate_evidence = error_evidence["candidate_evidence"]

  assert variant["profile"] == "booking-bs-sem-138"
  assert variant["candidate_type"] == "error-message-mismatch"
  assert variant["graph_context_needed"] == "not_required"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["BS-S003"],
    "routes": ["/details"],
  }
  assert variant["mutation_targets"] == [
    {
      "mutation_property": "validationMessage",
      "subject": "booking.details.fullName",
    }
  ]
  assert control_evidence["primary_evidence_key"] == "form_control"
  assert control_evidence["control"] == {
    "id": "details-fullName",
    "name": "fullName",
  }
  assert control_evidence["attributes"]["type"] == "text"
  assert control_evidence["attributes"]["autocomplete"] == "name"
  assert control_evidence["attributes"]["required"] is True
  assert control_evidence["attributes"]["has_value"] is False
  assert control_evidence["attributes"]["native_validity"][
    "value_missing"
  ] is True
  assert control_evidence["attribute_contains"] == {
    "label": "Full name",
    "accessible_name": "Full name",
  }
  assert error_evidence == {
    "bucket": "referenced_elements",
    "selector_hint": "p#details-fullName-error",
    "attributes": {"text": "Email is required."},
    "primary_evidence_key": "error_message",
    "candidate_evidence": candidate_evidence,
  }
  assert candidate_evidence["primary"]["error_message"] == {
    "selector": "p#details-fullName-error",
    "text": "Email is required.",
    "relationship_type": "describes",
    "method": "aria-describedby",
  }
  assert candidate_evidence["supporting"]["error_message_context_v1"][
    "control"
  ]["value_state"] == "empty"


def test_bs_sem_139_uses_empty_email_missing_value_and_associated_format_error_evidence():
  registry = load_benchmark_registry(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }

  assert configurations["booking-bs-sem-139"] == _normal_configuration(
    "bs-sem-139",
    app="booking-scheduler",
    profile="booking-bs-sem-139",
  )

  variant = variants["bs-sem-139"]
  expected_evidence = variant["expected_evidence"]
  control_evidence, error_evidence = expected_evidence["all_of"]
  assert "candidate_evidence" not in expected_evidence
  candidate_evidence = error_evidence["candidate_evidence"]

  assert variant["profile"] == "booking-bs-sem-139"
  assert variant["candidate_type"] == "error-message-mismatch"
  assert variant["graph_context_needed"] == "not_required"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["BS-S003"],
    "routes": ["/details"],
  }
  assert variant["mutation_targets"] == [
    {
      "mutation_property": "validationMessage",
      "subject": "booking.details.email",
    }
  ]
  assert control_evidence["primary_evidence_key"] == "form_control"
  assert control_evidence["control"] == {
    "id": "details-email",
    "name": "email",
  }
  assert control_evidence["attributes"]["type"] == "email"
  assert control_evidence["attributes"]["autocomplete"] == "email"
  assert control_evidence["attributes"]["required"] is True
  assert control_evidence["attributes"]["has_value"] is False
  assert control_evidence["attributes"]["native_validity"] == {
    "valid": False,
    "value_missing": True,
    "type_mismatch": False,
    "pattern_mismatch": False,
    "too_long": False,
    "too_short": False,
    "range_underflow": False,
    "range_overflow": False,
    "step_mismatch": False,
    "bad_input": False,
    "custom_error": False,
  }
  assert control_evidence["attribute_contains"] == {
    "label": "Email",
    "accessible_name": "Email",
  }
  assert error_evidence == {
    "bucket": "referenced_elements",
    "selector_hint": "p#details-email-error",
    "attributes": {"text": "Email format is invalid."},
    "primary_evidence_key": "error_message",
    "candidate_evidence": candidate_evidence,
  }
  assert candidate_evidence["primary"]["form_control"][
    "native_validity"
  ] == {
    "valid": False,
    "value_missing": True,
    "type_mismatch": False,
  }
  assert candidate_evidence["primary"]["error_message"] == {
    "selector": "p#details-email-error",
    "text": "Email format is invalid.",
    "relationship_type": "describes",
    "method": "aria-describedby",
  }
  error_context = candidate_evidence["supporting"][
    "error_message_context_v1"
  ]
  assert error_context["control"]["selector"] == "input#details-email"
  assert error_context["control"]["value_state"] == "empty"
  assert error_context["control"]["native_validity"] == {
    "valid": False,
    "value_missing": True,
    "type_mismatch": False,
  }


def test_bs_sem_140_uses_required_phone_and_associated_optional_error_evidence():
  registry = load_benchmark_registry(REGISTRY)
  configurations = {
    configuration["configuration_id"]: configuration
    for configuration in registry["seeded_configurations"]
  }
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }

  assert configurations["booking-bs-sem-140"] == _normal_configuration(
    "bs-sem-140",
    app="booking-scheduler",
    profile="booking-bs-sem-140",
  )

  variant = variants["bs-sem-140"]
  expected_evidence = variant["expected_evidence"]
  control_evidence, error_evidence = expected_evidence["all_of"]
  assert "candidate_evidence" not in expected_evidence
  candidate_evidence = error_evidence["candidate_evidence"]

  assert variant["profile"] == "booking-bs-sem-140"
  assert variant["candidate_type"] == "error-message-mismatch"
  assert variant["graph_context_needed"] == "not_required"
  assert variant["expected_state"] == {
    "benchmark_state_ids": ["BS-S003"],
    "routes": ["/details"],
  }
  assert variant["mutation_targets"] == [
    {
      "mutation_property": "validationMessage",
      "subject": "booking.details.phone",
    }
  ]
  assert control_evidence["primary_evidence_key"] == "form_control"
  assert control_evidence["control"] == {
    "id": "details-phone",
    "name": "phone",
  }
  assert control_evidence["attributes"]["type"] == "tel"
  assert control_evidence["attributes"]["autocomplete"] == "tel"
  assert control_evidence["attributes"]["required"] is True
  assert control_evidence["attributes"]["has_value"] is False
  assert control_evidence["attributes"]["native_validity"] == {
    "valid": False,
    "value_missing": True,
    "type_mismatch": False,
    "pattern_mismatch": False,
    "too_long": False,
    "too_short": False,
    "range_underflow": False,
    "range_overflow": False,
    "step_mismatch": False,
    "bad_input": False,
    "custom_error": False,
  }
  assert control_evidence["attribute_contains"] == {
    "label": "Phone",
    "accessible_name": "Phone",
  }
  assert error_evidence == {
    "bucket": "referenced_elements",
    "selector_hint": "p#details-phone-error",
    "attributes": {"text": "Phone is optional."},
    "primary_evidence_key": "error_message",
    "candidate_evidence": candidate_evidence,
  }
  assert candidate_evidence["primary"]["form_control"][
    "native_validity"
  ] == {
    "valid": False,
    "value_missing": True,
    "type_mismatch": False,
  }
  assert candidate_evidence["primary"]["error_message"] == {
    "selector": "p#details-phone-error",
    "text": "Phone is optional.",
    "relationship_type": "describes",
    "method": "aria-describedby",
  }
  error_context = candidate_evidence["supporting"][
    "error_message_context_v1"
  ]
  assert error_context["control"]["selector"] == "input#details-phone"
  assert error_context["control"]["value_state"] == "empty"
  assert error_context["control"]["native_validity"] == {
    "valid": False,
    "value_missing": True,
    "type_mismatch": False,
  }


def test_co_sem_101_uses_semantic_shipping_context_and_stable_destination_path():
  registry = load_benchmark_registry(REGISTRY)
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }
  variant = variants["co-sem-101"]
  expected_candidate = variant["expected_candidate"]
  expected_evidence = variant["expected_evidence"]

  assert variant["profile"] == "checkout-co-sem-101"
  assert variant["graph_context_needed"] == "helpful_not_required"
  assert variant["mutation_targets"] == [
    {
      "mutation_property": "href",
      "subject": "checkout.support.shippingInformation",
    }
  ]
  assert expected_candidate == {
    "candidate_type": "link-text-mismatch",
    "selection_reason": "visible_link_with_text_destination_and_context",
    "type": "link-text-mismatch",
    "text": "Shipping information",
    "accessible_name": "Shipping information",
  }
  assert "selector_hint" not in expected_evidence
  assert "destination_context" not in expected_evidence
  assert expected_evidence["attributes"] == {
    "tag": "a",
    "text": "Shipping information",
    "accessible_name": "Shipping information",
  }
  candidate_evidence = expected_evidence["candidate_evidence"]
  assert candidate_evidence["supporting"]["context"] == {
    "nearby_text": "Learn about delivery times and available shipping options."
  }
  assert candidate_evidence["supporting"]["structure"]["nearest_heading"] == {
    "tag": "h3",
    "text": "Shipping help",
  }
  assert candidate_evidence["supporting"]["link_destination_context_v1"] == {
    "schema_version": "link_destination_context_v1",
    "resolved_path": "/returns-and-refunds.html",
    "match_status": "external_or_out_of_scope",
  }
  serialized_recovery_contract = json.dumps(
    {"expected_candidate": expected_candidate, "expected_evidence": expected_evidence}
  )
  for identity_only_value in (
    "support-shipping",
    "checkout.support.shippingInformation",
    "candidate_id",
    "selector_hint",
    "127.0.0.1:8771",
  ):
    assert identity_only_value not in serialized_recovery_contract


def test_co_sem_102_requires_shipping_source_and_captured_returns_destination():
  registry = load_benchmark_registry(REGISTRY)
  variants = {
    variant["variant_id"]: variant
    for variant in registry["variants"]
  }
  variant = variants["co-sem-102"]
  expected_evidence = variant["expected_evidence"]

  assert variant["profile"] == "checkout-co-sem-102"
  assert variant["graph_context_needed"] == "required"
  assert variant["mutation_targets"] == [
    {
      "mutation_property": "href",
      "subject": "checkout.support.shippingInformation",
    }
  ]
  assert variant["expected_candidate"] == {
    "candidate_type": "link-text-mismatch",
    "selection_reason": "visible_link_with_text_destination_and_context",
    "type": "link-text-mismatch",
    "text": "Shipping information",
    "accessible_name": "Shipping information",
  }
  assert "selector_hint" not in expected_evidence
  candidate_evidence = expected_evidence["candidate_evidence"]
  supporting = candidate_evidence["supporting"]
  assert supporting["context"] == {
    "nearby_text": "Learn about delivery times and available shipping options."
  }
  assert supporting["structure"]["nearest_heading"] == {
    "tag": "h3",
    "text": "Shipping help",
  }
  assert supporting["link_destination_context_v1"] == {
    "schema_version": "link_destination_context_v1",
    "resolved_path": "/resource.html",
    "match_status": "external_or_out_of_scope",
  }
  assert supporting["destination_state_context_v1"] == {
    "schema_version": "destination_state_context_v1",
    "match_count": 1,
    "destinations": [
      {
        "target_route": "/returns-and-refunds.html",
        "target_title": "Returns and refunds",
        "target_primary_headings": [
          {
            "level": 1,
            "tag": "h1",
            "text": "Returns and refunds",
            "accessible_name": "Returns and refunds",
          }
        ],
      }
    ],
  }
  serialized_recovery_contract = json.dumps(candidate_evidence)
  for identity_only_value in (
    "support-shipping",
    "checkout.support.shippingInformation",
    "candidate_id",
    "selector_hint",
    "127.0.0.1:8771",
  ):
    assert identity_only_value not in serialized_recovery_contract


def test_registry_family_files_are_declared_and_type_consistent():
  manifest = _manifest()
  family_files = manifest["family_files"]

  assert len(family_files) == 15
  assert "families/table-header-association-mismatch.json" in family_files
  assert "families/video-captions-inaccurate.json" in family_files

  counts: dict[str, int] = {}
  for family_file in family_files:
    family = json.loads((REGISTRY.parent / family_file).read_text(encoding="utf-8"))
    candidate_type = family["candidate_type"]
    variants = family["variants"]
    assert family_file == f"families/{candidate_type}.json"
    assert variants
    assert all(variant["candidate_type"] == candidate_type for variant in variants)
    counts[candidate_type] = len(variants)

  assert counts == EXPECTED_FAMILY_COUNTS


def test_registry_loader_is_independent_of_current_working_directory(tmp_path, monkeypatch):
  monkeypatch.chdir(tmp_path)

  registry = load_benchmark_registry(REGISTRY)

  assert len(registry["variants"]) == 137
  assert len(registry["seeded_configurations"]) == 136


def test_registry_loader_rejects_family_candidate_type_mismatch(tmp_path):
  manifest = tmp_path / "benchmark-case-registry.json"
  family_dir = tmp_path / "families"
  family_dir.mkdir()
  manifest.write_text(
    json.dumps(
      {
        "family_files": ["families/button-label-mismatch.json"],
        "explicit_seeded_configurations": [],
      }
    ),
    encoding="utf-8",
  )
  (family_dir / "button-label-mismatch.json").write_text(
    json.dumps(
      {
        "candidate_type": "button-label-mismatch",
        "variants": [
          {
            "variant_id": "co-sem-999",
            "candidate_type": "link-text-mismatch",
          }
        ],
      }
    ),
    encoding="utf-8",
  )

  with pytest.raises(ValueError, match="candidate_type mismatch"):
    load_benchmark_registry(manifest)


def test_registry_loader_rejects_duplicate_variant_ids(tmp_path):
  manifest = tmp_path / "benchmark-case-registry.json"
  family_dir = tmp_path / "families"
  family_dir.mkdir()
  manifest.write_text(
    json.dumps(
      {
        "family_files": [
          "families/button-label-mismatch.json",
          "families/link-text-mismatch.json",
        ],
        "explicit_seeded_configurations": [],
      }
    ),
    encoding="utf-8",
  )
  for candidate_type in ("button-label-mismatch", "link-text-mismatch"):
    (family_dir / f"{candidate_type}.json").write_text(
      json.dumps(
        {
          "candidate_type": candidate_type,
          "variants": [
            {
              "variant_id": "co-sem-999",
              "candidate_type": candidate_type,
            }
          ],
        }
      ),
      encoding="utf-8",
    )

  with pytest.raises(ValueError, match="Duplicate registry variant_id"):
    load_benchmark_registry(manifest)


def _write_family(path: Path, *variant_ids: str) -> None:
  path.parent.mkdir()
  path.write_text(
    json.dumps(
      {
        "candidate_type": "button-label-mismatch",
        "variants": [
          {
            "variant_id": variant_id,
            "candidate_type": "button-label-mismatch",
          }
          for variant_id in variant_ids
        ],
      }
    ),
    encoding="utf-8",
  )


def test_registry_loader_rejects_unknown_explicit_seed_references(tmp_path):
  manifest = tmp_path / "benchmark-case-registry.json"
  family_path = tmp_path / "families" / "button-label-mismatch.json"
  manifest.write_text(
    json.dumps(
      {
        "family_files": ["families/button-label-mismatch.json"],
        "explicit_seeded_configurations": [
          {
            "configuration_id": "checkout-co-sem-998",
            "app": "checkout-flow",
            "seed_ids": ["co-sem-998"],
          }
        ],
      }
    ),
    encoding="utf-8",
  )
  _write_family(family_path, "co-sem-999")

  with pytest.raises(ValueError, match="references unknown seed ids"):
    load_benchmark_registry(manifest)


def test_registry_loader_rejects_duplicate_explicit_configuration_ids(tmp_path):
  manifest = tmp_path / "benchmark-case-registry.json"
  family_path = tmp_path / "families" / "button-label-mismatch.json"
  manifest.write_text(
    json.dumps(
      {
        "family_files": ["families/button-label-mismatch.json"],
        "explicit_seeded_configurations": [
          {
            "configuration_id": "checkout-special",
            "seed_ids": ["co-sem-998"],
          },
          {
            "configuration_id": "checkout-special",
            "seed_ids": ["co-sem-999"],
          },
        ],
      }
    ),
    encoding="utf-8",
  )
  _write_family(family_path, "co-sem-998", "co-sem-999")

  with pytest.raises(ValueError, match="Duplicate registry configuration_id"):
    load_benchmark_registry(manifest)


def test_registry_loader_rejects_overlapping_explicit_seed_ownership(tmp_path):
  manifest = tmp_path / "benchmark-case-registry.json"
  family_path = tmp_path / "families" / "button-label-mismatch.json"
  manifest.write_text(
    json.dumps(
      {
        "family_files": ["families/button-label-mismatch.json"],
        "explicit_seeded_configurations": [
          {
            "configuration_id": "checkout-special-a",
            "seed_ids": ["co-sem-999"],
          },
          {
            "configuration_id": "checkout-special-b",
            "seed_ids": ["co-sem-999"],
          },
        ],
      }
    ),
    encoding="utf-8",
  )
  _write_family(family_path, "co-sem-999")

  with pytest.raises(ValueError, match="already-owned seed ids"):
    load_benchmark_registry(manifest)
