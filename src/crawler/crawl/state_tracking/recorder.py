from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Protocol

if TYPE_CHECKING:
  from playwright.async_api import Page
else:
  Page = Any

from ...graph.graph import StateGraph
from ...state.hashing import state_dedup_key
from ..crawl_config import CrawlConfig
from ..metrics.recorder import CrawlMetricsRecorder
from ..priority import ActionKey
from .registry import StateRegistry


class CaptureStateArtifactsFn(Protocol):
  def __call__(
    self,
    page: Page,
    run_dir: Path,
    *,
    state_id: str,
    depth: int,
    parent_state: str | None,
    action_from_parent: dict[str, object] | None,
    enable_tile_screenshots: bool,
  ) -> Awaitable[Any]:
    ...


def _serialize_action_keys(keys: set[ActionKey]) -> list[list[str]]:
  normalized = sorted({tuple(key) for key in keys if key})
  return [list(key) for key in normalized]


class CrawlStateRecorder:
  """Persist crawl states and graph metadata without owning traversal flow."""

  def __init__(
    self,
    *,
    page: Page,
    run_dir: Path,
    cfg: CrawlConfig,
    graph_getter: Callable[[], StateGraph],
    state_registry: StateRegistry,
    metrics_recorder: CrawlMetricsRecorder,
    capture_state_artifacts_fn: CaptureStateArtifactsFn,
  ) -> None:
    self.page = page
    self.run_dir = run_dir
    self.cfg = cfg
    self._graph_getter = graph_getter
    self.state_registry = state_registry
    self.metrics_recorder = metrics_recorder
    self.capture_state_artifacts = capture_state_artifacts_fn

  @property
  def graph(self) -> StateGraph:
    return self._graph_getter()

  def seed_root_for_state(self, state_id: str) -> str:
    node = self.graph.nodes.get(state_id, {})
    seed_root = node.get("seed_root_state_id")
    if isinstance(seed_root, str) and seed_root:
      return seed_root
    return state_id

  def set_state_metadata(self, state_id: str, **values: object) -> None:
    node = self.graph.nodes.get(state_id)
    if not isinstance(node, dict):
      return
    for key, value in values.items():
      node[key] = value

  def record_attempted_action(self, state_id: str, action_key: ActionKey) -> None:
    if not self.state_registry.record_attempted_action(state_id, action_key):
      return
    self.set_state_metadata(
      state_id,
      attempted_action_keys=_serialize_action_keys(self.state_registry.attempted_actions_for_state(state_id)),
    )

  def record_state_expansion_result(self, state_id: str, *, depth: int, stop_reason: str) -> None:
    self.set_state_metadata(
      state_id,
      depth=depth,
      expansion_stop_reason=stop_reason,
    )

  async def save_state(
    self,
    state_id: str,
    *,
    depth: int,
    parent_state: str | None,
    action_from_parent: dict[str, object] | None,
    active_root_state_id: str | None,
  ) -> str:
    artifact = await self.capture_state_artifacts(
      self.page,
      self.run_dir,
      state_id=state_id,
      depth=depth,
      parent_state=parent_state,
      action_from_parent=action_from_parent,
      enable_tile_screenshots=self.cfg.enable_tile_screenshots,
    )
    dom_identity_hash = artifact.dom_identity_hash
    key = state_dedup_key(dom_identity_hash=dom_identity_hash, url=artifact.url)
    self.graph.add_state(state_id, artifact.url, artifact.html_hash, dom_identity_hash, key, artifact.title, artifact.route)
    self.set_state_metadata(
      state_id,
      seed_root_state_id=active_root_state_id or state_id,
      imported=False,
      attempted_action_keys=[],
    )
    self.state_registry.initialize_attempts(state_id)
    self.state_registry.remember_state_key(key, state_id)
    self.metrics_recorder.increment_coverage("new_states_discovered")
    return key

  async def save_new_state_from_action(
    self,
    *,
    current_state_id: str,
    current_depth: int,
    action_meta: dict[str, object],
    active_root_state_id: str | None,
  ) -> str:
    next_state_id = self.state_registry.next_state_id()
    await self.save_state(
      next_state_id,
      depth=current_depth + 1,
      parent_state=current_state_id,
      action_from_parent=action_meta,
      active_root_state_id=active_root_state_id,
    )
    return next_state_id

  def record_action_transition(
    self,
    *,
    current_state_id: str,
    next_state_id: str,
    action_meta: dict[str, object],
    discovered_new_state: bool,
  ) -> str:
    self.metrics_recorder.increment_coverage("actions_succeeded")
    transition_id = f"transition_{len(self.graph.edges):04d}"
    self.graph.add_edge(current_state_id, next_state_id, action=action_meta)
    if not discovered_new_state:
      return transition_id

    self.graph.set_state_parent(next_state_id, current_state_id, action_meta)
    self.set_state_metadata(
      next_state_id,
      seed_root_state_id=self.seed_root_for_state(current_state_id),
    )
    return transition_id
