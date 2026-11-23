from __future__ import annotations

import asyncio
import json
from pathlib import Path

from src.analysis.candidates import build_semantic_candidates
from src.analysis.candidates.run_reader import load_run_artifacts
from src.crawler.state.focused_run import (
  FocusedRunRecorder,
  FocusedStateSpec,
  capture_focused_transition_trigger,
)
from src.crawler.state.state_extractor import StateArtifact


def test_focused_run_recorder_writes_candidate_compatible_graph(tmp_path):
  run_dir = tmp_path / "focused_run"
  recorder = FocusedRunRecorder(
    run_dir=run_dir,
    app_name="booking-scheduler",
    benchmark_name="Booking Scheduler",
    source_script="scripts/benchmarks/run_booking_scheduler_assertion.py",
  )

  first = recorder.record_state_artifact(
    _write_artifact(run_dir, "state_0000", route="/services"),
    FocusedStateSpec(
      benchmark_state_id="BS-S0",
      focused_state_name="bs_s0_services_baseline",
      action_path=["open /services"],
      key_validated_selectors=["main", "h1"],
      active_test_id=None,
    ),
  )
  second = recorder.record_state_artifact(
    _write_artifact(run_dir, "state_0001", route="/services"),
    FocusedStateSpec(
      benchmark_state_id="BS-S1",
      focused_state_name="bs_s1_service_selected",
      action_path=["open /services", "select Consultation"],
      key_validated_selectors=['[data-testid="service-radio-svc-consultation"]'],
      active_test_id="service-radio-svc-consultation",
      parent_focused_state_name="bs_s0_services_baseline",
      transition_text="select Consultation",
    ),
  )

  manifest = recorder.write_run_artifacts()

  assert first.state_id == "state_0000"
  assert second.parent_state_id == "state_0000"
  assert manifest["state_count"] == 2
  assert manifest["transition_count"] == 1
  assert manifest["semantic_judgments_included"] is False
  assert manifest["ordinary_crawler_policy_changed"] is False

  graph = _read_json(run_dir / "graph.json")
  transitions = _read_json(run_dir / "transitions.json")
  assert graph["states"] == ["state_0000", "state_0001"]
  assert graph["nodes"][0]["benchmark_state_id"] == "BS-S0"
  assert graph["nodes"][1]["parent_state_id"] == "state_0000"
  assert transitions == [
    {
      "from": "state_0000",
      "to": "state_0001",
      "action": {
        "type": "focused_script_step",
        "text": "select Consultation",
      },
    }
  ]

  metadata = _read_json(run_dir / "states" / "state_0001" / "metadata.json")
  assert metadata["focused_acquisition"]["method"] == "focused_scripted"
  assert metadata["focused_acquisition"]["benchmark_state_id"] == "BS-S1"
  assert metadata["focused_acquisition"]["focused_state_name"] == "bs_s1_service_selected"
  assert metadata["focused_acquisition"]["active_test_id"] == "service-radio-svc-consultation"

  run = load_run_artifacts(run_dir)
  assert [state.state_id for state in run.states] == ["state_0000", "state_0001"]

  summary = build_semantic_candidates(run_dir, candidate_types=["heading-not-descriptive"])
  assert summary.manifest["inputs"]["states_seen"] == 2
  assert (summary.output_dir / "candidates.jsonl").exists()


def test_focused_run_recorder_persists_neutral_primary_trigger_metadata(tmp_path):
  run_dir = tmp_path / "focused_run"
  recorder = FocusedRunRecorder(
    run_dir=run_dir,
    app_name="task-manager",
    benchmark_name="Task Manager",
    source_script="scripts/benchmarks/run_task_manager_scripted_smoke.py",
  )
  recorder.record_state_artifact(
    _write_artifact(run_dir, "state_0000", route="/tasks"),
    FocusedStateSpec(
      benchmark_state_id="TM-S4",
      focused_state_name="tm_s4_create_validation",
      action_path=["open /tasks", "open create dialog", "submit blank title"],
    ),
  )
  recorder.record_state_artifact(
    _write_artifact(run_dir, "state_0001", route="/tasks"),
    FocusedStateSpec(
      benchmark_state_id="TM-S6",
      focused_state_name="tm_s6_create_success",
      action_path=[
        "open /tasks",
        "open create dialog",
        "submit blank title",
        "enter Draft benchmark note",
        "save create dialog",
      ],
      parent_focused_state_name="tm_s4_create_validation",
      transition_text="enter Draft benchmark note and save create dialog",
      transition_trigger={
        "type": "click",
        "selector": '[data-testid="create-task-dialog-save"]',
        "data_testid": "create-task-dialog-save",
        "dom_path": "dialog>form>div:nth-of-type(2)>button:nth-of-type(2)",
        "text": "Save",
        "accessible_name": "Save",
        "button_type": "submit",
        "tag_name": "button",
        "expected_action": "create task",
      },
      preceding_operations=[
        {
          "type": "fill",
          "selector": '[data-testid="create-task-dialog-title-field"]',
          "data_testid": "create-task-dialog-title-field",
          "input_type": "text",
          "value": "Draft benchmark note",
        }
      ],
    ),
  )

  recorder.write_run_artifacts()

  transitions = _read_json(run_dir / "transitions.json")
  action = transitions[0]["action"]
  assert action["type"] == "focused_script_step"
  assert action["text"] == "enter Draft benchmark note and save create dialog"
  assert action["primary_trigger"] == {
    "type": "click",
    "selector": '[data-testid="create-task-dialog-save"]',
    "data_testid": "create-task-dialog-save",
    "dom_path": "dialog>form>div:nth-of-type(2)>button:nth-of-type(2)",
    "text": "Save",
    "accessible_name": "Save",
    "button_type": "submit",
    "tag_name": "button",
  }
  assert action["preceding_operations"] == [
    {
      "type": "fill",
      "selector": '[data-testid="create-task-dialog-title-field"]',
      "data_testid": "create-task-dialog-title-field",
      "input_type": "text",
    }
  ]
  assert "expected_action" not in action["primary_trigger"]
  assert "value" not in action["preceding_operations"][0]

  graph = _read_json(run_dir / "graph.json")
  assert graph["nodes"][1]["incoming_action"] == action
  metadata = _read_json(run_dir / "states" / "state_0001" / "metadata.json")
  assert metadata["action_from_parent"] == action


def test_focused_trigger_capture_records_actual_click_element_identity():
  descriptor = asyncio.run(
    capture_focused_transition_trigger(
      _FakeLocator(
        {
          "data_testid": "nav-cart",
          "dom_path": 'a[data-testid="nav-cart"]',
          "href": "/cart",
          "text": "Cart",
          "accessible_name": "Cart",
          "role": "link",
          "tag_name": "a",
          "expected_destination": "cart step",
        }
      ),
      action_type="click",
      selector='[data-testid="nav-cart"]',
    )
  )

  assert descriptor == {
    "type": "click",
    "selector": '[data-testid="nav-cart"]',
    "data_testid": "nav-cart",
    "dom_path": 'a[data-testid="nav-cart"]',
    "href": "/cart",
    "text": "Cart",
    "accessible_name": "Cart",
    "role": "link",
    "tag_name": "a",
  }
  assert "expected_destination" not in descriptor
  assert "violation" not in descriptor


class _FakeLocator:
  def __init__(self, payload: dict[str, object]) -> None:
    self.payload = payload

  async def evaluate(self, _script: str) -> dict[str, object]:
    return self.payload


def _write_artifact(run_dir: Path, state_id: str, *, route: str) -> StateArtifact:
  state_dir = run_dir / "states" / state_id
  state_dir.mkdir(parents=True, exist_ok=True)
  html_path = state_dir / "dom.html"
  screenshot_path = state_dir / "screenshot.png"
  aria_path = state_dir / "aria_snapshot.json"
  accessibility_context_path = state_dir / "accessibility_context.json"
  metadata_path = state_dir / "metadata.json"

  html_path.write_text("<main><h1>Example</h1></main>", encoding="utf-8")
  screenshot_path.write_bytes(b"fake")
  aria_path.write_text("{}", encoding="utf-8")
  accessibility_context_path.write_text(
    json.dumps({"schema_version": "1", "state_id": state_id}),
    encoding="utf-8",
  )
  metadata_path.write_text(
    json.dumps(
      {
        "state_id": state_id,
        "url": f"http://127.0.0.1:3000{route}",
        "route": route,
        "title": "Booking Scheduler",
        "html_hash": f"html-{state_id}",
        "dom_identity_hash": f"identity-{state_id}",
        "depth": 0,
      }
    ),
    encoding="utf-8",
  )
  return StateArtifact(
    url=f"http://127.0.0.1:3000{route}",
    html_hash=f"html-{state_id}",
    dom_identity_hash=f"identity-{state_id}",
    html_path=html_path,
    screenshot_path=screenshot_path,
    aria_snapshot_path=aria_path,
    accessibility_context_path=accessibility_context_path,
    metadata_path=metadata_path,
    title="Booking Scheduler",
    route=route,
  )


def _read_json(path: Path):
  return json.loads(path.read_text(encoding="utf-8"))
