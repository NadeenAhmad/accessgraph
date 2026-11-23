from __future__ import annotations

import asyncio

import pytest

from scripts.benchmarks.case_metadata import (
  BenchmarkCase,
  CaseConfigurationError,
  ExecutableConfiguration,
  LAUNCHABLE_STATUSES,
  load_tracker_cases,
  resolve_case,
)
from scripts.benchmarks.explorer.session import (
  BenchmarkExplorerSession,
  booking_target_state,
  CaseNotLaunchableError,
  LaunchError,
  SessionStatus,
  UnsupportedAppError,
)


async def _fake_runner(benchmark_case, skip_build, stop_event, on_ready, logger):
  on_ready(
    SessionStatus(
      state="running",
      case_id=benchmark_case.case_id,
      profile=benchmark_case.executable_profile,
      url=f"http://127.0.0.1:4000/{benchmark_case.case_id}",
    )
  )
  while not stop_event.is_set():
    await asyncio.sleep(0.01)


def test_session_starts_and_stops_case():
  session = BenchmarkExplorerSession(skip_build=True, variant_runner=_fake_runner)

  status = session.open_case(resolve_case("co-sem-052"))

  assert status.state == "running"
  assert status.case_id == "co-sem-052"
  assert status.profile == "checkout-co-sem-052"
  assert session.stop().state == "idle"


def test_session_replaces_active_case():
  stopped_cases: list[str] = []

  async def fake_runner(benchmark_case, skip_build, stop_event, on_ready, logger):
    try:
      await _fake_runner(benchmark_case, skip_build, stop_event, on_ready, logger)
    finally:
      stopped_cases.append(benchmark_case.case_id)

  session = BenchmarkExplorerSession(skip_build=True, variant_runner=fake_runner)

  first = session.open_case(resolve_case("co-sem-052"))
  second = session.open_case(resolve_case("co-sem-047"))

  assert first.case_id == "co-sem-052"
  assert second.case_id == "co-sem-047"
  assert stopped_cases == ["co-sem-052"]
  assert session.shutdown().state == "idle"
  assert stopped_cases == ["co-sem-052", "co-sem-047"]


def test_session_dispatches_checkout_and_booking_cases_to_app_runners():
  opened_apps: list[str] = []

  async def app_runner(benchmark_case, skip_build, stop_event, on_ready, logger):
    opened_apps.append(benchmark_case.app)
    await _fake_runner(benchmark_case, skip_build, stop_event, on_ready, logger)

  session = BenchmarkExplorerSession(
    skip_build=True,
    variant_runners={
      "checkout": app_runner,
      "booking-scheduler": app_runner,
    },
  )

  session.open_case(resolve_case("co-sem-052"))
  status = session.open_case(resolve_case("bs-sem-155"))

  assert opened_apps == ["checkout", "booking-scheduler"]
  assert status.case_id == "bs-sem-155"
  assert status.profile == "booking-bs-sem-155"
  assert session.shutdown().state == "idle"


@pytest.mark.parametrize(
  ("case_id", "target_state"),
  [
    ("bs-sem-116", "services"),
    ("bs-sem-112", "schedule"),
    ("bs-sem-151", "details"),
    ("bs-sem-162", "review"),
    ("bs-sem-160", "confirmation"),
    ("bs-sem-155", "help"),
  ],
)
def test_booking_cases_resolve_registry_route_to_functional_state(
  case_id,
  target_state,
):
  assert booking_target_state(resolve_case(case_id)) == target_state


def test_all_implemented_booking_cases_have_supported_functional_states():
  booking_case_ids = [
    case_id
    for case_id, row in load_tracker_cases().items()
    if row["app"] == "booking-scheduler"
    and row["status"] in LAUNCHABLE_STATUSES
  ]

  assert len(booking_case_ids) == 27
  assert {
    booking_target_state(resolve_case(case_id))
    for case_id in booking_case_ids
  } == {"services", "schedule", "details", "review", "confirmation", "help"}


def test_session_rejects_planned_case(planned_benchmark_case):
  session = BenchmarkExplorerSession(skip_build=True, variant_runner=_fake_runner)

  with pytest.raises(CaseNotLaunchableError):
    session.open_case(planned_benchmark_case)


def test_session_rejects_unsupported_app():
  benchmark_case = BenchmarkCase(
    case_id="tm-sem-001",
    violation_type="link-text-mismatch",
    app="task-manager",
    status="implemented",
    short_description="Booking fixture",
    pattern="fixture",
    tier="hard",
    baseline="Correct baseline.",
    mutation="Incorrect mutation.",
    why_unambiguous="The application source is unavailable.",
    interaction_path="Initial state",
    evidence_state="initial",
    notes="",
    executable_configuration=ExecutableConfiguration(
      configuration_id="task-manager-tm-sem-001",
      app="task-manager",
      seed_ids=("tm-sem-001",),
      status="implemented",
    ),
  )
  session = BenchmarkExplorerSession(skip_build=True, variant_runner=_fake_runner)

  with pytest.raises(UnsupportedAppError):
    session.open_case(benchmark_case)


def test_booking_case_without_registry_route_reports_configuration_error():
  benchmark_case = BenchmarkCase(
    case_id="bs-sem-900",
    violation_type="link-text-mismatch",
    app="booking-scheduler",
    status="implemented",
    short_description="Booking fixture",
    pattern="fixture",
    tier="hard",
    baseline="Correct baseline.",
    mutation="Incorrect mutation.",
    why_unambiguous="Route metadata is required for faithful state setup.",
    interaction_path="Initial state",
    evidence_state="initial",
    notes="",
    executable_configuration=ExecutableConfiguration(
      configuration_id="booking-bs-sem-900",
      app="booking-scheduler",
      seed_ids=("bs-sem-900",),
      status="implemented",
    ),
  )

  with pytest.raises(CaseConfigurationError, match="exactly one expected route"):
    booking_target_state(benchmark_case)

  session = BenchmarkExplorerSession(skip_build=True)
  with pytest.raises(LaunchError, match="exactly one expected route"):
    session.open_case(benchmark_case)
  assert session.status().state == "error"
  assert session.stop().state == "idle"


def test_session_records_launch_failure_and_can_stop_after_error():
  async def failing_runner(benchmark_case, skip_build, stop_event, on_ready, logger):
    raise RuntimeError("launch failed")

  session = BenchmarkExplorerSession(skip_build=True, variant_runner=failing_runner)

  with pytest.raises(LaunchError, match="launch failed"):
    session.open_case(resolve_case("co-sem-052"))

  error_status = session.status()
  assert error_status.state == "error"
  assert error_status.case_id == "co-sem-052"
  assert error_status.message == "launch failed"
  assert session.stop().state == "idle"


def test_session_passes_controlled_support_case_to_runner():
  opened_cases: list[str] = []

  async def fake_runner(benchmark_case, skip_build, stop_event, on_ready, logger):
    opened_cases.append(benchmark_case.case_id)
    await _fake_runner(benchmark_case, skip_build, stop_event, on_ready, logger)

  session = BenchmarkExplorerSession(skip_build=True, variant_runner=fake_runner)

  status = session.open_case(resolve_case("co-sem-027"))

  assert status.case_id == "co-sem-027"
  assert opened_cases == ["co-sem-027"]
  assert session.shutdown().state == "idle"
