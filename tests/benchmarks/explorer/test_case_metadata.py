from __future__ import annotations

import csv
import json
from collections import Counter

import pytest

from scripts.benchmarks import case_metadata
from scripts.benchmarks.explorer import server


def test_resolve_implemented_checkout_case_uses_registry_profile():
  benchmark_case = case_metadata.resolve_case("co-sem-052")

  assert benchmark_case.case_id == "co-sem-052"
  assert benchmark_case.app == "checkout"
  assert benchmark_case.registry_app == "checkout-flow"
  assert benchmark_case.status == "implemented"
  assert benchmark_case.violation_type == "landmark-purpose-mismatch"
  assert benchmark_case.pattern == "landmark-navigation-wrong-accessible-label"
  assert benchmark_case.tier == "hard"
  assert benchmark_case.evidence_state == "initial"
  assert benchmark_case.executable_profile == "checkout-co-sem-052"
  assert benchmark_case.is_launchable


def test_resolve_implemented_booking_case_uses_registry_profile_and_route():
  benchmark_case = case_metadata.resolve_case("bs-sem-162")

  assert benchmark_case.app == "booking-scheduler"
  assert benchmark_case.registry_app == "booking-scheduler"
  assert benchmark_case.executable_profile == "booking-bs-sem-162"
  assert benchmark_case.expected_routes == ("/review",)
  assert benchmark_case.is_launchable


def test_resolve_planned_case_is_not_launchable(
  tmp_path,
  planned_benchmark_case,
  planned_tracker_row,
):
  tracker_path = tmp_path / "case-tracker.csv"
  registry_path = tmp_path / "benchmark-case-registry.json"
  with tracker_path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=case_metadata.TRACKER_FIELDS)
    writer.writeheader()
    writer.writerow(planned_tracker_row)
  registry_path.write_text(
    json.dumps({"seeded_configurations": []}),
    encoding="utf-8",
  )

  benchmark_case = case_metadata.resolve_case(
    planned_benchmark_case.case_id,
    tracker_path=tracker_path,
    registry_path=registry_path,
  )

  assert benchmark_case.case_id == planned_benchmark_case.case_id
  assert benchmark_case.status == "planned"
  assert benchmark_case.executable_profile is None
  assert not benchmark_case.is_launchable


def test_current_tracker_catalogue_matches_registry_and_explorer_capabilities():
  tracker_cases = case_metadata.load_tracker_cases()
  cases = {
    case_id: case_metadata.resolve_case(case_id)
    for case_id in tracker_cases
  }
  configurations = case_metadata.load_executable_configurations()

  assert Counter(case.status for case in cases.values()) == Counter(
    row["status"] for row in tracker_cases.values()
  )

  expected_executable_ids = {
    case_id
    for case_id, row in tracker_cases.items()
    if row["status"] in case_metadata.LAUNCHABLE_STATUSES
  }
  tracked_configuration_ids = set(configurations).intersection(tracker_cases)
  assert tracked_configuration_ids == expected_executable_ids
  assert {
    case_id for case_id, case in cases.items() if case.is_launchable
  } == expected_executable_ids

  expected_explorer_ids = {
    case_id
    for case_id in expected_executable_ids
    if tracker_cases[case_id]["app"] in server.SUPPORTED_EXPLORER_APPS
  }
  actual_explorer_ids = {
    case_id
    for case_id, case in cases.items()
    if server._launchability_payload(case)["launchable"]
  }
  assert actual_explorer_ids == expected_explorer_ids

  assert Counter(cases[case_id].app for case_id in actual_explorer_ids) == Counter(
    {"checkout": 108, "booking-scheduler": 27}
  )
  assert set(configurations).difference(tracker_cases) == {
    "co-sem-001",
    "co-sem-002",
  }


@pytest.mark.parametrize(
  ("case_id", "status"),
  [
    ("bs-sem-120", "planned"),
    ("co-sem-099", "blocked"),
    ("co-sem-098", "rejected"),
  ],
)
def test_non_implemented_statuses_are_not_explorer_launchable(case_id, status):
  benchmark_case = case_metadata.resolve_case(case_id)

  assert benchmark_case.status == status
  assert server._launchability_payload(benchmark_case)["launchable"] is False


def test_unknown_case_reports_available_ids():
  with pytest.raises(case_metadata.UnknownBenchmarkCaseError) as exc_info:
    case_metadata.resolve_case("co-sem-999")

  assert exc_info.value.case_id == "co-sem-999"
  assert "co-sem-052" in exc_info.value.available_case_ids


def test_tracker_registry_app_mismatch_is_rejected(tmp_path):
  tracker_path = tmp_path / "case-tracker.csv"
  registry_path = tmp_path / "benchmark-case-registry.json"
  with tracker_path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=case_metadata.TRACKER_FIELDS)
    writer.writeheader()
    writer.writerow(
      {
        "case_id": "co-sem-900",
        "violation_type": "landmark-purpose-mismatch",
        "app": "checkout",
        "short_description": "Mismatch fixture",
        "pattern": "mismatch-fixture",
        "tier": "hard",
        "baseline": "Correct landmark.",
        "mutation": "Wrong landmark.",
        "why_unambiguous": "The app values disagree.",
        "interaction_path": "Products page (initial state)",
        "evidence_state": "initial",
        "status": "implemented",
        "notes": "",
      }
    )

  registry_path.write_text(
    json.dumps(
      {
        "seeded_configurations": [
          {
            "configuration_id": "booking-co-sem-900",
            "app": "booking-flow",
            "seed_ids": ["co-sem-900"],
            "status": "implemented",
          }
        ]
      }
    ),
    encoding="utf-8",
  )

  with pytest.raises(case_metadata.CaseConfigurationError, match="tracker app"):
    case_metadata.resolve_case(
      "co-sem-900",
      tracker_path=tracker_path,
      registry_path=registry_path,
    )
