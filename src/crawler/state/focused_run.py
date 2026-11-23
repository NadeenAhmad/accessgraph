from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
  from playwright.async_api import Locator, Page
else:
  Locator = Page = Any

from src.crawler.graph.graph import StateGraph
from src.crawler.state.hashing import state_dedup_key

from .state_extractor import StateArtifact, capture_state_artifacts


SCHEMA_VERSION = "1"
DEFAULT_GENERATOR = "focused_scripted_state_normalizer"
FOCUSED_TRANSITION_DESCRIPTOR_KEYS = (
  "type",
  "selector",
  "data_testid",
  "dom_path",
  "href",
  "text",
  "accessible_name",
  "button_type",
  "input_type",
  "role",
  "tag_name",
)


@dataclass(frozen=True)
class FocusedStateSpec:
  """Neutral metadata for a focused/scripted benchmark state capture."""

  benchmark_state_id: str
  focused_state_name: str
  action_path: list[str]
  key_validated_selectors: list[str] = field(default_factory=list)
  active_test_id: str | None = None
  parent_focused_state_name: str | None = None
  transition_text: str | None = None
  transition_trigger: dict[str, object] = field(default_factory=dict)
  preceding_operations: list[dict[str, object]] = field(default_factory=list)


@dataclass(frozen=True)
class FocusedStateRecord:
  state_id: str
  benchmark_state_id: str
  focused_state_name: str
  route: str
  parent_state_id: str | None

  def as_dict(self) -> dict[str, object]:
    return {
      "state_id": self.state_id,
      "benchmark_state_id": self.benchmark_state_id,
      "focused_state_name": self.focused_state_name,
      "route": self.route,
      "parent_state_id": self.parent_state_id,
    }


class FocusedRunRecorder:
  """Write focused/scripted states into a crawl-like Accessibility context run."""

  def __init__(
    self,
    *,
    run_dir: Path,
    app_name: str,
    benchmark_name: str,
    source_script: str,
    source_assertion_run_dir: Path | None = None,
    generator: str = DEFAULT_GENERATOR,
  ) -> None:
    self.run_dir = run_dir
    self.app_name = app_name
    self.benchmark_name = benchmark_name
    self.source_script = source_script
    self.source_assertion_run_dir = source_assertion_run_dir
    self.generator = generator
    self.graph = StateGraph()
    self.records: list[FocusedStateRecord] = []
    self._state_by_focused_name: dict[str, str] = {}

  async def capture_page_state(self, page: Page, spec: FocusedStateSpec) -> FocusedStateRecord:
    state_id = self.next_state_id()
    parent_state_id = self._state_by_focused_name.get(spec.parent_focused_state_name or "")
    action_from_parent = self._action_from_spec(spec) if parent_state_id else None
    depth = self._depth_for_parent(parent_state_id)

    artifact = await capture_state_artifacts(
      page,
      self.run_dir,
      state_id=state_id,
      depth=depth,
      parent_state=parent_state_id,
      action_from_parent=action_from_parent,
      enable_tile_screenshots=False,
    )
    return self.record_state_artifact(artifact, spec)

  def next_state_id(self) -> str:
    return f"state_{len(self.records):04d}"

  def record_state_artifact(
    self,
    artifact: StateArtifact,
    spec: FocusedStateSpec,
  ) -> FocusedStateRecord:
    state_id = artifact.metadata_path.parent.name
    parent_state_id = self._state_by_focused_name.get(spec.parent_focused_state_name or "")
    action_from_parent = self._action_from_spec(spec) if parent_state_id else None

    metadata = _read_json_object(artifact.metadata_path)
    metadata["parent_state"] = parent_state_id
    metadata["action_from_parent"] = action_from_parent
    metadata["depth"] = self._depth_for_parent(parent_state_id)
    metadata["focused_acquisition"] = {
      "schema_version": SCHEMA_VERSION,
      "method": "focused_scripted",
      "app_name": self.app_name,
      "benchmark_name": self.benchmark_name,
      "benchmark_state_id": spec.benchmark_state_id,
      "focused_state_name": spec.focused_state_name,
      "action_path": spec.action_path,
      "active_test_id": spec.active_test_id,
      "key_validated_selectors": spec.key_validated_selectors,
      "source_script": self.source_script,
    }
    _write_json(artifact.metadata_path, metadata)

    self.graph.add_state(
      state_id,
      artifact.url,
      artifact.html_hash,
      dom_identity_hash=artifact.dom_identity_hash,
      stable_state_key=state_dedup_key(dom_identity_hash=artifact.dom_identity_hash, url=artifact.url),
      title=artifact.title,
      route=artifact.route,
    )
    node = self.graph.nodes[state_id]
    node["depth"] = int(metadata.get("depth") or 0)
    node["acquisition_method"] = "focused_scripted"
    node["benchmark_state_id"] = spec.benchmark_state_id
    node["focused_state_name"] = spec.focused_state_name

    if parent_state_id:
      action = action_from_parent or {}
      self.graph.set_state_parent(state_id, parent_state_id, action)
      self.graph.add_edge(parent_state_id, state_id, action)

    record = FocusedStateRecord(
      state_id=state_id,
      benchmark_state_id=spec.benchmark_state_id,
      focused_state_name=spec.focused_state_name,
      route=artifact.route,
      parent_state_id=parent_state_id,
    )
    self.records.append(record)
    self._state_by_focused_name[spec.focused_state_name] = state_id
    return record

  def write_run_artifacts(self) -> dict[str, object]:
    self.run_dir.mkdir(parents=True, exist_ok=True)
    self.graph.metrics = {
      "acquisition_method": "focused_scripted",
      "app_name": self.app_name,
      "benchmark_name": self.benchmark_name,
      "state_count": len(self.records),
      "transition_count": len(self.graph.edges),
    }
    self.graph.save_json(self.run_dir / "graph.json")
    self.graph.save_transitions_json(self.run_dir / "transitions.json")

    manifest: dict[str, object] = {
      "schema_version": SCHEMA_VERSION,
      "generated_at_utc": datetime.now(timezone.utc).isoformat(),
      "run_id": self.run_dir.name,
      "run_dir": str(self.run_dir),
      "generator": self.generator,
      "acquisition_method": "focused_scripted",
      "app_name": self.app_name,
      "benchmark_name": self.benchmark_name,
      "source_script": self.source_script,
      "source_assertion_run_dir": (
        str(self.source_assertion_run_dir) if self.source_assertion_run_dir else None
      ),
      "ordinary_crawler_policy_changed": False,
      "semantic_judgments_included": False,
      "state_count": len(self.records),
      "transition_count": len(self.graph.edges),
      "states": [record.as_dict() for record in self.records],
    }
    _write_json(self.run_dir / "run_metadata.json", manifest)
    return manifest

  def _depth_for_parent(self, parent_state_id: str | None) -> int:
    if not parent_state_id:
      return 0
    parent_node = self.graph.nodes.get(parent_state_id, {})
    try:
      return int(parent_node.get("depth") or 0) + 1
    except (TypeError, ValueError):
      return 1

  def _action_from_spec(self, spec: FocusedStateSpec) -> dict[str, object]:
    text = spec.transition_text or (spec.action_path[-1] if spec.action_path else "")
    action: dict[str, object] = {
      "type": "focused_script_step",
      "text": text,
    }
    primary_trigger = _sanitize_transition_descriptor(spec.transition_trigger)
    if primary_trigger:
      action["primary_trigger"] = primary_trigger
    preceding_operations = [
      descriptor
      for raw in spec.preceding_operations
      if (descriptor := _sanitize_transition_descriptor(raw))
    ]
    if preceding_operations:
      action["preceding_operations"] = preceding_operations
    return action


async def capture_focused_transition_trigger(
  locator: Locator,
  *,
  action_type: str,
  selector: str,
) -> dict[str, object]:
  """Capture neutral trigger identity from the live element before an action."""
  raw = await locator.evaluate(
    """
    (element) => {
      const path = [];
      let node = element;
      let depth = 0;
      while (node && node.nodeType === Node.ELEMENT_NODE && depth < 8) {
        const tag = (node.tagName || '').toLowerCase();
        let part = tag;
        if (node.id) {
          part += `#${node.id}`;
          path.unshift(part);
          break;
        }
        const parent = node.parentElement;
        if (parent) {
          const siblings = Array.from(parent.children).filter(
            (item) => item.tagName === node.tagName,
          );
          if (siblings.length > 1) {
            part += `:nth-of-type(${siblings.indexOf(node) + 1})`;
          }
        }
        path.unshift(part);
        node = parent;
        depth += 1;
      }
      const visibleText = (element.innerText || element.value || '').trim();
      const ariaLabel = (element.getAttribute('aria-label') || '').trim();
      return {
        data_testid:
          element.getAttribute('data-testid') ||
          element.getAttribute('data-test-id') ||
          '',
        dom_path: path.join('>'),
        href: element.getAttribute('href') || '',
        text: visibleText,
        accessible_name: ariaLabel || visibleText,
        button_type: (element.getAttribute('type') || '').toLowerCase(),
        input_type:
          element.tagName === 'INPUT'
            ? (element.getAttribute('type') || 'text').toLowerCase()
            : '',
        role: element.getAttribute('role') || '',
        tag_name: (element.tagName || '').toLowerCase(),
      };
    }
    """
  )
  descriptor = raw if isinstance(raw, dict) else {}
  return _sanitize_transition_descriptor(
    {
      "type": action_type,
      "selector": selector,
      **descriptor,
    }
  )


def _sanitize_transition_descriptor(raw: object) -> dict[str, object]:
  if not isinstance(raw, dict):
    return {}
  return {
    key: raw[key]
    for key in FOCUSED_TRANSITION_DESCRIPTOR_KEYS
    if key in raw and raw[key] not in (None, "", [], {})
  }


def _read_json_object(path: Path) -> dict[str, Any]:
  try:
    payload = json.loads(path.read_text(encoding="utf-8"))
  except Exception:
    return {}
  return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, object]) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
