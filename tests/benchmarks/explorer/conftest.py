from __future__ import annotations

import pytest

from scripts.benchmarks.case_metadata import BenchmarkCase


@pytest.fixture
def planned_benchmark_case() -> BenchmarkCase:
  return BenchmarkCase(
    case_id="co-sem-900",
    violation_type="link-text-mismatch",
    app="checkout",
    status="planned",
    short_description="Synthetic planned Checkout case",
    pattern="synthetic-planned-case",
    tier="hard",
    baseline="The link has a correct purpose.",
    mutation="The link purpose is incorrect.",
    why_unambiguous="The synthetic fixture isolates planned-case behavior.",
    interaction_path="Products page (initial state)",
    evidence_state="initial",
    notes="",
  )


@pytest.fixture
def planned_tracker_row(planned_benchmark_case: BenchmarkCase) -> dict[str, str]:
  return {
    field: str(getattr(planned_benchmark_case, field))
    for field in (
      "case_id",
      "violation_type",
      "app",
      "short_description",
      "pattern",
      "tier",
      "baseline",
      "mutation",
      "why_unambiguous",
      "interaction_path",
      "evidence_state",
      "status",
      "notes",
    )
  }
