from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal
from urllib.parse import urlparse

if TYPE_CHECKING:
  from playwright.async_api import Page
else:
  Page = Any

try:
  from playwright.async_api import TimeoutError as PlaywrightTimeoutError
except ImportError:
  PlaywrightTimeoutError = TimeoutError

from ...graph.graph import StateGraph, state_node_dom_identity_hash, state_node_html_hash
from ...platform.readiness import wait_for_page_ready
from ...state.hashing import (
  canonicalize_url_for_state, html_hash, rendered_dom_identity_hash_for_page, state_dedup_key,
  wait_for_page_settled, wait_for_rendered_dom_stable,
)
from ..actions import ActionCandidate

ReplayFailureReason = Literal[
  "path_missing",
  "root_navigation_failed",
  "candidate_not_found",
  "action_timeout",
  "action_failed",
  "out_of_scope",
  "final_state_mismatch",
]
ReplayFailureStage = Literal["pre_replay", "step", "final_verification"]


@dataclass(frozen=True)
class ReplayRestoreResult:
  success: bool
  failure_reason: ReplayFailureReason | None = None
  failure_stage: ReplayFailureStage | None = None
  failed_step_index: int | None = None
  path_length: int = 0
  stable_match: bool = False
  same_url_soft_match: bool = False
  same_route_soft_match: bool = False


@dataclass(frozen=True)
class StateRestoreMatch:
  matched: bool
  strict: bool = False
  stable: bool = False


_TITLE_TAG_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


async def _best_effort_back(page: Page, fallback_url: str, timeout_ms: int) -> None:
  try:
    await page.go_back(wait_until="domcontentloaded", timeout=timeout_ms)
    await wait_for_page_ready(page, timeout_ms=min(timeout_ms, 5_000))
  except PlaywrightTimeoutError:
    await page.goto(fallback_url, wait_until="domcontentloaded", timeout=timeout_ms)
    await wait_for_page_ready(page, timeout_ms=min(timeout_ms, 5_000))
  except Exception:
    await page.goto(fallback_url, wait_until="domcontentloaded", timeout=timeout_ms)
    await wait_for_page_ready(page, timeout_ms=min(timeout_ms, 5_000))


async def _navigate_to_url(page: Page, url: str, timeout_ms: int) -> bool:
  try:
    await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    await wait_for_page_ready(page, timeout_ms=min(timeout_ms, 5_000))
    return True
  except PlaywrightTimeoutError:
    return False
  except Exception:
    return False


class StateRestorer:
  def __init__(
    self,
    *,
    page: Page,
    graph: StateGraph,
    start_url: str,
    back_timeout_ms: int,
    replay_candidate_scan_limit: int,
    in_scope: Callable[[str], bool],
    root_state_id_getter: Callable[[], str | None],
    increment_coverage: Callable[[str, int], None],
    record_replay_attempt_metrics: Callable[[ReplayRestoreResult], None],
    record_replay_failure: Callable[[ReplayRestoreResult], None],
    get_action_candidates_fn: Callable[[Page, int], Awaitable[list[ActionCandidate]]],
    perform_action_fn: Callable[[ActionCandidate], Awaitable[bool]],
    action_timeout_type: type[Exception],
    navigate_to_url_fn: Callable[[Page, str, int], Awaitable[bool]],
    best_effort_back_fn: Callable[[Page, str, int], Awaitable[None]],
    state_html_loader: Callable[[str], str | None] | None = None,
  ) -> None:
    self.page = page
    self.graph = graph
    self.state_html_loader = state_html_loader
    self.start_url = start_url
    self.back_timeout_ms = back_timeout_ms
    self.replay_candidate_scan_limit = replay_candidate_scan_limit
    self.in_scope = in_scope
    self._root_state_id_getter = root_state_id_getter
    self._increment_coverage = increment_coverage
    self._record_replay_attempt_metrics = record_replay_attempt_metrics
    self._record_replay_failure = record_replay_failure
    self._get_action_candidates = get_action_candidates_fn
    self._perform_action = perform_action_fn
    self._action_timeout_type = action_timeout_type
    self._navigate_to_url = navigate_to_url_fn
    self._best_effort_back = best_effort_back_fn
    # Set by the crawl session after an action that can change stored app data (form submit, remove, ...)
    # on an allowed local host. The next restore then clears the origin's storage and replays the path.
    self.storage_dirty = False
    self.storage_reset_allowed: Callable[[str], bool] = lambda _url: False

  async def _clear_origin_storage(self) -> bool:
    """Clear cookies, localStorage, sessionStorage and IndexedDB of the current origin (local apps only)."""
    try:
      await self.page.context.clear_cookies()
      await self.page.evaluate(
        """async () => {
          try { localStorage.clear(); } catch (e) {}
          try { sessionStorage.clear(); } catch (e) {}
          try {
            if (indexedDB && indexedDB.databases) {
              for (const db of await indexedDB.databases()) { if (db.name) indexedDB.deleteDatabase(db.name); }
            }
          } catch (e) {}
        }"""
      )
      self._increment_coverage("state_restore_storage_resets", 1)
      return True
    except Exception:
      self._increment_coverage("state_restore_storage_reset_failures", 1)
      return False

  def _root_state_id(self) -> str | None:
    return self._root_state_id_getter()

  def _state_meta(self, state_id: str) -> dict[str, object]:
    raw = self.graph.nodes.get(state_id, {})
    if isinstance(raw, dict):
      return raw
    return {}

  def _state_artifact_dedup_key(self, state_id: str) -> str | None:
    state_meta = self.graph.nodes.get(state_id)
    if not state_meta:
      return None
    html_hash_value = state_node_html_hash(state_meta)
    url = state_meta.get("url")
    if not html_hash_value or not isinstance(url, str):
      return None
    return state_dedup_key(dom_identity_hash=html_hash_value, url=url)

  def _state_dom_identity_hash(self, state_id: str) -> str:
    state_meta = self._state_meta(state_id)
    return state_node_dom_identity_hash(state_meta)

  def _canonical_state_url(self, state_id: str) -> str:
    state_meta = self._state_meta(state_id)
    raw_url = str(state_meta.get("url") or "")
    if not raw_url:
      return ""
    return canonicalize_url_for_state(raw_url)

  def _state_route(self, state_id: str) -> str:
    state_meta = self._state_meta(state_id)
    raw_route = str(state_meta.get("route") or "")
    return raw_route or "/"

  def _state_title(self, state_id: str) -> str:
    state_meta = self._state_meta(state_id)
    return str(state_meta.get("title") or "").strip()

  def _route_for_url(self, url: str) -> str:
    return urlparse(url).path or "/"

  def _title_from_html(self, html: str) -> str:
    match = _TITLE_TAG_RE.search(html)
    if not match:
      return ""
    return " ".join(match.group(1).split())

  async def _current_page_has_open_modal(self) -> bool:
    evaluate = getattr(self.page, "evaluate", None)
    if evaluate is not None:
      try:
        result = await evaluate(
          """
          () => {
            const candidates = Array.from(document.querySelectorAll('dialog[open], [aria-modal="true"]'));
            return candidates.some((el) => {
              if (el.hidden) return false;
              const style = window.getComputedStyle(el);
              if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) {
                return false;
              }
              return true;
            });
          }
          """
        )
        return bool(result)
      except Exception:
        pass

    try:
      html = await self.page.content()
    except Exception:
      return False
    lowered = html.lower()
    return bool(
      re.search(r"<dialog\b[^>]*\bopen(?:\s|=|>|$)", lowered)
      or re.search(r"\baria-modal\s*=\s*['\"]true['\"]", lowered)
    )

  def _incoming_action_meta(self, state_id: str) -> dict[str, object]:
    state_meta = self._state_meta(state_id)
    raw = state_meta.get("incoming_action")
    if isinstance(raw, dict):
      return raw
    return {}

  def _should_allow_url_title_restore_match(self, state_id: str) -> bool:
    if not self._state_title(state_id):
      return False

    if state_id == self._root_state_id():
      return True

    state_meta = self._state_meta(state_id)
    parent_state_id = state_meta.get("parent_state_id")
    if not isinstance(parent_state_id, str):
      return False

    incoming_action = self._incoming_action_meta(state_id)
    if str(incoming_action.get("type") or "") != "click":
      return False

    href = str(incoming_action.get("href") or "")
    if not href or href.startswith("#"):
      return False

    state_url = self._canonical_state_url(state_id)
    parent_url = self._canonical_state_url(parent_state_id)
    if state_url and parent_url and state_url == parent_url:
      return False

    return True

  async def _current_page_restore_match(self, state_id: str) -> StateRestoreMatch:
    expected_key = self._state_artifact_dedup_key(state_id)
    if not expected_key:
      return StateRestoreMatch(matched=False)

    expected_dom_identity_hash = self._state_dom_identity_hash(state_id)
    expected_html_hash = state_node_html_hash(self._state_meta(state_id))
    expected_url = self._canonical_state_url(state_id)
    expected_route = self._state_route(state_id)
    stable_state_key = str(self._state_meta(state_id).get("stable_state_key") or "")
    actual_html = await self.page.content()
    expected_rendered_key = (
      state_dedup_key(dom_identity_hash=expected_dom_identity_hash, url=expected_url)
      if expected_dom_identity_hash and expected_url
      else ""
    )
    has_rendered_dom_identity = bool(
      expected_dom_identity_hash
      and expected_dom_identity_hash != expected_html_hash
      and stable_state_key == expected_rendered_key
    )
    if has_rendered_dom_identity and expected_url:
      actual_dom_identity_hash = await rendered_dom_identity_hash_for_page(self.page)
      actual_url = canonicalize_url_for_state(self.page.url)
      if actual_dom_identity_hash != expected_dom_identity_hash and actual_url == expected_url:
        # the page may still be settling (loading indicators, focus or transition effects): decide on the settled DOM
        await wait_for_page_settled(self.page)
        actual_dom_identity_hash = await rendered_dom_identity_hash_for_page(self.page)
      if actual_dom_identity_hash == expected_dom_identity_hash and actual_url == expected_url:
        return StateRestoreMatch(matched=True, stable=True)
      if state_id != self._root_state_id() and self._should_allow_url_title_restore_match(state_id):
        actual_title = self._title_from_html(actual_html)
        actual_route = self._route_for_url(self.page.url)
        if actual_url == expected_url and actual_route == expected_route and actual_title == self._state_title(state_id):
          if await self._current_page_has_open_modal():
            return StateRestoreMatch(matched=False)
          return StateRestoreMatch(matched=True)
      return StateRestoreMatch(matched=False)

    actual_key = state_dedup_key(dom_identity_hash=html_hash(actual_html), url=self.page.url)
    if actual_key == expected_key:
      return StateRestoreMatch(matched=True, strict=True)

    return StateRestoreMatch(matched=False)

  async def current_page_matches_state(self, state_id: str) -> bool:
    return (await self._current_page_restore_match(state_id)).matched

  async def _current_page_soft_restore_match(self, state_id: str) -> tuple[bool, bool]:
    expected_url = self._canonical_state_url(state_id)
    expected_route = self._state_route(state_id)
    actual_url = canonicalize_url_for_state(self.page.url)
    actual_route = self._route_for_url(self.page.url)

    same_url = bool(expected_url) and actual_url == expected_url
    same_route = bool(expected_route) and actual_route == expected_route and not same_url
    return same_url, same_route

  def _replay_path(self, state_id: str) -> list[dict[str, object]] | None:
    path: list[dict[str, object]] = []
    current_state_id = state_id
    root_state_id = self._root_state_id()
    visited: set[str] = set()

    while root_state_id and current_state_id != root_state_id:
      if current_state_id in visited:
        return None
      visited.add(current_state_id)
      state_meta = self.graph.nodes.get(current_state_id)
      if not state_meta:
        return None

      parent_state_id = state_meta.get("parent_state_id")
      incoming_action = state_meta.get("incoming_action")
      if not isinstance(parent_state_id, str) or not isinstance(incoming_action, dict):
        return None
      if parent_state_id == current_state_id:
        return None

      path.append(incoming_action)
      current_state_id = parent_state_id

    path.reverse()
    return path

  def _should_prefer_replay_restore(self, state_id: str) -> bool:
    state_meta = self._state_meta(state_id)
    parent_state_id = state_meta.get("parent_state_id")
    if not isinstance(parent_state_id, str):
      return True

    state_url = self._canonical_state_url(state_id)
    parent_url = self._canonical_state_url(parent_state_id)
    if state_url and parent_url and state_url == parent_url:
      return True

    incoming_action = self._incoming_action_meta(state_id)
    action_type = str(incoming_action.get("type") or "")
    if action_type and action_type != "click":
      return True

    href = str(incoming_action.get("href") or "")
    if not href or href.startswith("#"):
      return True

    strategy = str(incoming_action.get("strategy") or "")
    if strategy in {"buttons", "button_inputs", "role_button"}:
      return True

    selection_group = str(incoming_action.get("selection_group") or "")
    if selection_group in {"control", "main_control"}:
      return True

    return False

  async def _restore_via_url(self, fallback_url: str) -> bool:
    self._increment_coverage("state_restore_url_attempts")
    ok = await self._navigate_to_url(self.page, fallback_url, self.back_timeout_ms)
    if ok:
      self._increment_coverage("state_restore_url_successes")
    else:
      self._increment_coverage("state_restore_url_failures")
    return ok

  def _replay_candidate_matches(
    self,
    candidate: ActionCandidate,
    replay_action: dict[str, object],
  ) -> bool:
    replay_type = str(replay_action.get("type") or "")
    if replay_type and candidate.action_type != replay_type:
      return False

    replay_identity = str(replay_action.get("identity") or "")
    if replay_identity and candidate.identity:
      return candidate.identity == replay_identity

    replay_strategy = str(replay_action.get("strategy") or "")
    replay_href = str(replay_action.get("href") or "")
    replay_text = str(replay_action.get("text") or "")[:80]
    replay_input_type = str(replay_action.get("input_type") or "")

    return (
      candidate.strategy_name == replay_strategy
      and (candidate.href or "") == replay_href
      and candidate.text[:80] == replay_text
      and (candidate.input_type or "") == replay_input_type
    )

  async def _replay_to_state(self, state_id: str) -> ReplayRestoreResult:
    root_state_id = self._root_state_id()
    if not root_state_id:
      return ReplayRestoreResult(
        success=False,
        failure_reason="path_missing",
        failure_stage="pre_replay",
      )

    replay_path = self._replay_path(state_id)
    if replay_path is None:
      return ReplayRestoreResult(
        success=False,
        failure_reason="path_missing",
        failure_stage="pre_replay",
      )

    path_length = len(replay_path)

    root_meta = self.graph.nodes.get(root_state_id, {})
    root_url = str(root_meta.get("url") or self.start_url)
    if not await self._navigate_to_url(self.page, root_url, self.back_timeout_ms):
      return ReplayRestoreResult(
        success=False,
        failure_reason="root_navigation_failed",
        failure_stage="pre_replay",
        path_length=path_length,
      )

    for step_index, replay_action in enumerate(replay_path, start=1):
      if replay_action.get("type") == "fill_submit":
        from ..actions.forms import candidate_from_replay_meta

        selected = candidate_from_replay_meta(self.page, replay_action)
      else:
        candidates = await self._get_action_candidates(self.page, limit=self.replay_candidate_scan_limit)
        selected = next(
          (candidate for candidate in candidates if self._replay_candidate_matches(candidate, replay_action)),
          None,
        )
      if selected is None:
        return ReplayRestoreResult(
          success=False,
          failure_reason="candidate_not_found",
          failure_stage="step",
          failed_step_index=step_index,
          path_length=path_length,
        )
      try:
        ok = await self._perform_action(selected)
      except self._action_timeout_type:
        return ReplayRestoreResult(
          success=False,
          failure_reason="action_timeout",
          failure_stage="step",
          failed_step_index=step_index,
          path_length=path_length,
        )
      if not ok:
        return ReplayRestoreResult(
          success=False,
          failure_reason="action_failed",
          failure_stage="step",
          failed_step_index=step_index,
          path_length=path_length,
        )
      if not self.in_scope(self.page.url):
        return ReplayRestoreResult(
          success=False,
          failure_reason="out_of_scope",
          failure_stage="step",
          failed_step_index=step_index,
          path_length=path_length,
        )

    match = await self._current_page_restore_match(state_id)
    if match.matched:
      return ReplayRestoreResult(success=True, path_length=path_length, stable_match=match.stable)
    same_url_soft_match, same_route_soft_match = await self._current_page_soft_restore_match(state_id)
    if same_url_soft_match and await self._replayed_text_matches(state_id):
      self._increment_coverage("state_restore_replay_text_matches")
      return ReplayRestoreResult(success=True, path_length=path_length, stable_match=False)
    return ReplayRestoreResult(
      success=False,
      failure_reason="final_state_mismatch",
      failure_stage="final_verification",
      failed_step_index=path_length or None,
      path_length=path_length,
      same_url_soft_match=same_url_soft_match,
      same_route_soft_match=same_route_soft_match,
    )

  async def _replayed_text_matches(self, state_id: str) -> bool:
    """W4A phase 1: after the recorded path was replayed in full, the page is the state when URL and title match and
    its visible words, numbers left out, are at least 97% the same as the recorded state's (live data such as counts,
    dates or random figures changes the rendering, not the state)."""
    if self.state_html_loader is None:
      return False
    expected = self.state_html_loader(state_id)
    if not expected:
      return False
    actual = await self.page.content()
    if self._title_from_html(actual) != self._state_title(state_id):
      return False
    return _word_similarity(expected, actual) >= 0.97

  async def _fresh_root_load_matches(self, state_id: str) -> bool:
    """W4A dev round 2: right after a fresh load of the start URL, the page is the start state even when live data
    (random or time-based numbers, development overlays, carousels) changed its rendering. Accept same URL, route and
    title. Used only after such a reload, never to decide whether the current page is already the state."""
    if not self._state_title(state_id):
      return False
    actual_url = canonicalize_url_for_state(self.page.url)
    if actual_url != self._canonical_state_url(state_id) or self._route_for_url(self.page.url) != self._state_route(state_id):
      return False
    if self._title_from_html(await self.page.content()) != self._state_title(state_id):
      return False
    # no open-dialog check here: after a fresh load, a dialog (e.g. a cookie banner) is part of the start state
    self._increment_coverage("state_restore_root_reload_soft_matches")
    return True

  async def restore_state(self, state_id: str, fallback_url: str, *, force: bool = False) -> bool:
    if self.storage_dirty and self.storage_reset_allowed(self.page.url):
      return await self._restore_with_storage_reset(state_id, fallback_url)
    if not force:
      current_match = await self._current_page_restore_match(state_id)
      if current_match.matched:
        return True

    if state_id == self._root_state_id():
      if not await self._restore_via_url(fallback_url):
        return False
      url_match = await self._current_page_restore_match(state_id)
      if not url_match.matched:
        return await self._fresh_root_load_matches(state_id)
      if url_match.stable:
        self._increment_coverage("state_restore_url_stable_successes")
      return True

    prefer_replay = self._should_prefer_replay_restore(state_id)

    if not prefer_replay:
      self._increment_coverage("state_restore_url_first_attempts")
      if await self._restore_via_url(fallback_url):
        url_match = await self._current_page_restore_match(state_id)
        if url_match.matched:
          if url_match.stable:
            self._increment_coverage("state_restore_url_stable_successes")
          return True

    if prefer_replay:
      self._increment_coverage("state_restore_replay_first_attempts")

    self._increment_coverage("state_restore_replay_attempts")
    replay_result = await self._replay_to_state(state_id)
    self._record_replay_attempt_metrics(replay_result)
    if replay_result.success:
      if replay_result.stable_match:
        self._increment_coverage("state_restore_replay_stable_successes")
      self._increment_coverage("state_restore_replay_successes")
      return True
    if replay_result.failure_reason is not None:
      self._record_replay_failure(replay_result)

    if prefer_replay:
      self._increment_coverage("state_restore_url_fallbacks")
      return await self._restore_via_url(fallback_url)

    return False

  async def _restore_with_storage_reset(self, state_id: str, fallback_url: str) -> bool:
    """Reload with the origin's storage cleared, then replay the recorded path (the path's own actions
    rebuild the app data the state depends on)."""
    self._increment_coverage("state_restore_storage_reset_attempts", 1)
    if not await self._clear_origin_storage():
      return False
    self.storage_dirty = False
    if state_id == self._root_state_id():
      if not await self._restore_via_url(fallback_url):
        return False
      if (await self._current_page_restore_match(state_id)).matched:
        return True
      return await self._fresh_root_load_matches(state_id)
    replay_result = await self._replay_to_state(state_id)
    self._record_replay_attempt_metrics(replay_result)
    if replay_result.success:
      self._increment_coverage("state_restore_replay_successes", 1)
      return True
    if replay_result.failure_reason is not None:
      self._record_replay_failure(replay_result)
    return False

  async def restore_state_with_back_fallback(self, state_id: str, fallback_url: str) -> bool:
    if self.storage_dirty and self.storage_reset_allowed(self.page.url):
      return await self.restore_state(state_id, fallback_url)
    await self._best_effort_back(self.page, fallback_url, self.back_timeout_ms)
    if await self.current_page_matches_state(state_id):
      return True
    return await self.restore_state(state_id, fallback_url)


def _visible_words(html: str) -> set[str]:
  import re
  text = re.sub(r"<(script|style|noscript|template)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
  text = re.sub(r"<[^>]+>", " ", text)
  return {w for w in re.findall(r"[^\W\d_]{2,}", text.lower())}


def _word_similarity(a: str, b: str) -> float:
  wa, wb = _visible_words(a), _visible_words(b)
  if not wa and not wb:
    return 1.0
  return len(wa & wb) / max(1, len(wa | wb))

