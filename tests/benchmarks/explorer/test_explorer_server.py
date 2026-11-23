from __future__ import annotations

import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from scripts.benchmarks.case_metadata import (
  BenchmarkCase,
  CaseConfigurationError,
  ExecutableConfiguration,
)
from scripts.benchmarks.explorer import server
from scripts.benchmarks.explorer.session import SessionStatus


class FakeSession:
  def __init__(self):
    self.current = SessionStatus(state="idle")
    self.opened_cases: list[str] = []
    self.stop_count = 0
    self.shutdown_count = 0

  def status(self):
    return self.current

  def open_case(self, benchmark_case):
    self.opened_cases.append(benchmark_case.case_id)
    self.current = SessionStatus(
      state="running",
      case_id=benchmark_case.case_id,
      profile=benchmark_case.executable_profile,
      url=f"http://127.0.0.1:4000/{benchmark_case.case_id}",
    )
    return self.current

  def stop(self):
    self.stop_count += 1
    self.current = SessionStatus(state="idle")
    return self.current

  def shutdown(self):
    self.shutdown_count += 1
    return self.stop()


@pytest.fixture
def explorer_server(monkeypatch, planned_benchmark_case, planned_tracker_row):
  load_tracker_cases = server.load_tracker_cases
  resolve_case = server.resolve_case

  def load_tracker_cases_with_planned_fixture():
    return {
      **load_tracker_cases(),
      planned_benchmark_case.case_id: planned_tracker_row,
    }

  def resolve_case_with_planned_fixture(case_id):
    if case_id == planned_benchmark_case.case_id:
      return planned_benchmark_case
    return resolve_case(case_id)

  monkeypatch.setattr(
    server,
    "load_tracker_cases",
    load_tracker_cases_with_planned_fixture,
  )
  monkeypatch.setattr(
    server,
    "resolve_case",
    resolve_case_with_planned_fixture,
  )
  fake_session = FakeSession()
  httpd = server.create_server("127.0.0.1", 0, session=fake_session)
  thread = threading.Thread(target=httpd.serve_forever, daemon=True)
  thread.start()
  base_url = f"http://127.0.0.1:{httpd.server_address[1]}"
  try:
    yield base_url, fake_session
  finally:
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=5)


def test_cases_api_returns_catalogue(explorer_server, planned_benchmark_case):
  base_url, _ = explorer_server

  status, data = request_json(f"{base_url}/api/cases")

  assert status == 200
  cases = data["cases"]
  co_sem_052 = single(case for case in cases if case["case_id"] == "co-sem-052")
  assert co_sem_052["launchable"] is True
  planned_case_id = planned_benchmark_case.case_id
  planned_case = single(case for case in cases if case["case_id"] == planned_case_id)
  assert planned_case["launchable"] is False
  assert planned_case["launch_error"] == "Not implemented yet."


def test_case_detail_api_returns_metadata(explorer_server):
  base_url, _ = explorer_server

  status, data = request_json(f"{base_url}/api/cases/co-sem-052")

  assert status == 200
  detail = data["case"]
  assert detail["case_id"] == "co-sem-052"
  assert detail["violation_type"] == "landmark-purpose-mismatch"
  assert detail["profile"] == "checkout-co-sem-052"
  assert detail["launchable"] is True
  assert "baseline" in detail
  assert "mutation" in detail


def test_booking_case_detail_is_launchable(explorer_server):
  base_url, _ = explorer_server

  status, data = request_json(f"{base_url}/api/cases/bs-sem-162")

  assert status == 200
  detail = data["case"]
  assert detail["app"] == "booking-scheduler"
  assert detail["profile"] == "booking-bs-sem-162"
  assert detail["launchable"] is True


def test_unknown_case_detail_returns_404(explorer_server):
  base_url, _ = explorer_server

  status, data = request_json(f"{base_url}/api/cases/co-sem-999")

  assert status == 404
  assert data["error"]["code"] == "unknown_case"


def test_open_endpoint_dispatches_to_session(explorer_server):
  base_url, fake_session = explorer_server

  status, data = request_json(
    f"{base_url}/api/session/open",
    method="POST",
    body={"case_id": "co-sem-052"},
  )

  assert status == 200
  assert fake_session.opened_cases == ["co-sem-052"]
  assert data["session"]["state"] == "running"
  assert data["session"]["case_id"] == "co-sem-052"


def test_open_endpoint_rejects_planned_case(
  explorer_server,
  planned_benchmark_case,
):
  base_url, fake_session = explorer_server
  planned_case_id = planned_benchmark_case.case_id

  status, data = request_json(
    f"{base_url}/api/session/open",
    method="POST",
    body={"case_id": planned_case_id},
  )

  assert status == 409
  assert data["error"]["code"] == "case_not_launchable"
  assert "Not implemented yet" in data["error"]["message"]
  assert fake_session.opened_cases == []


def test_stop_endpoint_is_idempotent(explorer_server):
  base_url, fake_session = explorer_server

  status, data = request_json(f"{base_url}/api/session/stop", method="POST")

  assert status == 200
  assert data["session"]["state"] == "idle"
  assert fake_session.stop_count == 1


def test_session_status_endpoint(explorer_server):
  base_url, fake_session = explorer_server
  fake_session.current = SessionStatus(
    state="running",
    case_id="co-sem-052",
    profile="checkout-co-sem-052",
  )

  status, data = request_json(f"{base_url}/api/session/status")

  assert status == 200
  assert data["session"]["state"] == "running"
  assert data["session"]["case_id"] == "co-sem-052"


def test_static_files_are_served(explorer_server):
  base_url, _ = explorer_server

  index_status, index_html = request_text(f"{base_url}/")
  js_status, app_js = request_text(f"{base_url}/app.js")

  assert index_status == 200
  assert "AccessGraph Benchmark SPA Explorer" in index_html
  assert "Checkout or Booking variants" in index_html
  assert js_status == 200
  assert "/api/cases" in app_js


def test_configuration_error_payload(monkeypatch):
  def fake_resolve_case(case_id):
    raise CaseConfigurationError("registry mismatch")

  monkeypatch.setattr(server, "resolve_case", fake_resolve_case)
  monkeypatch.setattr(
    server,
    "load_tracker_cases",
    lambda: {
      "co-sem-900": {
        "case_id": "co-sem-900",
        "violation_type": "link-text-mismatch",
        "app": "checkout",
        "status": "implemented",
        "tier": "hard",
        "evidence_state": "initial",
        "short_description": "Mismatch fixture",
        "pattern": "fixture",
        "baseline": "Correct baseline.",
        "mutation": "Incorrect mutation.",
        "why_unambiguous": "Mismatch is clear.",
        "interaction_path": "Initial state",
      }
    },
  )

  payload = server.case_payload("co-sem-900", detail=True)

  assert payload["launchable"] is False
  assert payload["config_error"] is True
  assert payload["launch_error"] == "Configuration error: registry mismatch"


def test_unsupported_app_payload_is_not_launchable():
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
    why_unambiguous="Unavailable app fixture.",
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

  payload = server._launchability_payload(benchmark_case)

  assert payload["launchable"] is False
  assert payload["launch_error"] == "Explorer launcher not available for this app yet."


def request_json(url, *, method="GET", body=None):
  data = None
  headers = {}
  if body is not None:
    data = json.dumps(body).encode("utf-8")
    headers["Content-Type"] = "application/json"
  request = Request(url, data=data, headers=headers, method=method)
  try:
    with urlopen(request, timeout=5) as response:
      return response.status, json.loads(response.read().decode("utf-8"))
  except HTTPError as exc:
    return exc.code, json.loads(exc.read().decode("utf-8"))


def request_text(url):
  with urlopen(url, timeout=5) as response:
    return response.status, response.read().decode("utf-8")


def single(items):
  matches = list(items)
  assert len(matches) == 1
  return matches[0]
