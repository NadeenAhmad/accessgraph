from __future__ import annotations

from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse

from ..destination_state_context import (
  LINK_DESTINATION_IDENTIFIER_ORDER,
  build_destination_state_context,
)
from ..evidence_helpers import (
  bounding_box_ref,
  dom_snippet,
  element_ref,
  evidence_items,
  first_present_text,
  is_visible,
)
from ..models import RunArtifacts, RunState
from ..payload import artifact_refs, build_candidate_payload

CANDIDATE_TYPE = "link-text-mismatch"
DESTINATION_CONTEXT_SCHEMA_VERSION = "link_destination_context_v1"
MAX_TARGET_HEADINGS = 5
MAX_TARGET_LANDMARKS = 5
SAME_RESOURCE_TAB_LABELS = {"my posts", "favorited posts"}


def build_link_text_candidates(
  run: RunArtifacts,
  state: RunState,
  graph_context: dict[str, object],
) -> list[dict[str, object]]:
  records: list[dict[str, object]] = []
  visible_links = [link for link in evidence_items(state, "links") if is_visible(link)]
  for link in evidence_items(state, "links"):
    if not is_visible(link):
      continue
    name = first_present_text(link, ("text", "accessible_name", "aria_label", "title"))
    href = str(link.get("href") or "")
    if not name or (not href and str(link.get("role") or "").lower() != "link"):
      continue  # role="link" elements without href (scripted links) are links to the user (W4A dev round 2)
    if _is_same_resource_profile_tab_link(state, link, name):
      continue
    snippet = dom_snippet(link)
    supporting: dict[str, object] = {
      "context": link.get("context") if isinstance(link.get("context"), dict) else {},
      "structure": link.get("structure") if isinstance(link.get("structure"), dict) else {},
      "link_destination_context_v1": _build_link_destination_context(run, state, link),
    }
    same_name = _links_with_the_same_name(link, name, visible_links)
    if same_name:
      supporting["links_with_the_same_name"] = same_name
    same_page = _same_page_target(state, supporting["link_destination_context_v1"])
    if same_page:
      supporting["same_page_target_v1"] = same_page
    destination_context = build_destination_state_context(
      run, state, link, bucket="links", identifier_order=LINK_DESTINATION_IDENTIFIER_ORDER
    )
    if destination_context:
      supporting["destination_state_context_v1"] = destination_context
    records.append(
      build_candidate_payload(
        run=run,
        state=state,
        candidate_type=CANDIDATE_TYPE,
        element_refs=[element_ref("links", link)],
        selection_reason=["visible_link_with_text_destination_and_context"],
        required_context=["link destination", "nearby text context", "route context"],
        evidence={
          "primary": {
            "link": _compact_link(link),
          },
          "supporting": supporting,
          "bounding_boxes": [bounding_box_ref(link)],
          "dom_snippets": [snippet] if snippet else [],
        },
        graph_context=graph_context,
      )
    )
  records.extend(_hidden_focusable_link_candidates(run, state, graph_context))
  return records


def _hidden_focusable_link_candidates(run: RunArtifacts, state: RunState, graph_context: dict[str, object]) -> list[dict[str, object]]:
  """W4A round 5 (WCAG 2.4.4 with 4.1.2; ACT 'Link has non-empty accessible name'): a link hidden from assistive
  technologies (aria-hidden) that keyboard users can still focus (recorded as `hidden_focusable_links`)."""
  records: list[dict[str, object]] = []
  for link in evidence_items(state, "hidden_focusable_links"):
    snippet = dom_snippet(link)
    records.append(build_candidate_payload(
      run=run, state=state, candidate_type=CANDIDATE_TYPE, element_refs=[element_ref("hidden_focusable_links", link)],
      selection_reason=["keyboard_focusable_link_hidden_from_assistive_technology"],
      required_context=["link visible text", "hidden from assistive technology", "keyboard focusability"],
      evidence={
        "primary": {"link": {**_compact_link(link), "hidden_from_assistive_technology": True, "keyboard_focusable": True}},
        "supporting": {"context": link.get("context") if isinstance(link.get("context"), dict) else {},
                       "structure": link.get("structure") if isinstance(link.get("structure"), dict) else {}},
        "bounding_boxes": [bounding_box_ref(link)],
        "dom_snippets": [snippet] if snippet else [],
      },
      graph_context=graph_context,
    ))
  return records


def _links_with_the_same_name(link: dict[str, Any], name: str, links: list[dict[str, Any]]) -> list[dict[str, object]]:
  """Other visible links on the state with the same accessible name, with their destination and context (2.4.4:
  links that share a name and context but lead to different places leave the purpose undetermined)."""
  key = " ".join(name.lower().split())
  out = []
  for other in links:
    if other is link or other.get("element_id") == link.get("element_id"):
      continue
    other_name = first_present_text(other, ("text", "accessible_name", "aria_label", "title"))
    if other_name and " ".join(other_name.lower().split()) == key:
      context = other.get("context") if isinstance(other.get("context"), dict) else {}
      out.append({"href": other.get("href"), "programmatic_context": context.get("programmatic_context"),
                  "section_heading": context.get("section_heading")})
    if len(out) >= 8:
      break
  return out


def _same_page_target(state: RunState, destination: object) -> dict[str, object] | None:
  """C3: the heading and first 200 characters of an in-page link's target section, from the saved DOM."""
  from ..same_page_targets import same_page_target

  if not isinstance(destination, dict) or destination.get("match_status") != "same_page_fragment":
    return None
  return same_page_target(state.state_dir / "dom.html", str(destination.get("fragment") or ""))


def _compact_link(link: dict[str, Any]) -> dict[str, object]:
  return {
    "element_id": str(link.get("element_id") or ""),
    "tag": str(link.get("tag") or ""),
    "role": link.get("role"),
    "selector": str(link.get("selector") or ""),
    "text": str(link.get("text") or ""),
    "accessible_name": link.get("accessible_name"),
    "aria_label": link.get("aria_label"),
    "aria_labelledby": link.get("aria_labelledby"),
    "aria_describedby": link.get("aria_describedby"),
    "title": link.get("title"),
    "href": str(link.get("href") or ""),
    "target": link.get("target"),
  }


def _build_link_destination_context(
  run: RunArtifacts,
  source_state: RunState,
  link: dict[str, Any],
) -> dict[str, object]:
  raw_href = str(link.get("href") or "")
  source_url = _state_url(source_state)
  context: dict[str, object] = {
    "schema_version": DESTINATION_CONTEXT_SCHEMA_VERSION,
    "raw_href": raw_href,
  }
  if not raw_href:
    return {
      **context,
      "match_status": "unresolved",
      "notes": ["link href was empty"],
    }

  resolved_url, fragment = _resolve_href(raw_href, source_url)
  context["resolved_url"] = resolved_url
  context["resolved_path"] = _path_with_query(urlparse(resolved_url))
  context["fragment"] = fragment

  if fragment and _without_fragment(resolved_url) == _without_fragment(source_url):
    return {
      **context,
      "match_status": "same_page_fragment",
      "target_state_id": source_state.state_id,
      "target_state_url": source_url,
      "target_state_title": _state_title(source_state),
      "target_state_route": _state_route(source_state),
      "target_artifact_refs": artifact_refs(run.run_dir, source_state),
    }

  if not _is_same_origin_http_url(resolved_url, source_url):
    return {
      **context,
      "match_status": "external_or_out_of_scope",
      "notes": ["href resolved outside the source state origin or uses a non-http scheme"],
    }

  target_state = _match_target_state(run, source_state, resolved_url)
  if target_state is None:
    return {
      **context,
      "match_status": "unresolved",
      "notes": ["href resolved but no crawled state matched"],
    }

  return {
    **context,
    "match_status": "matched_state",
    "target_state_id": target_state.state_id,
    "target_state_url": _state_url(target_state),
    "target_state_title": _state_title(target_state),
    "target_state_route": _state_route(target_state),
    "target_state_headings": _compact_target_headings(target_state),
    "target_state_landmarks": _compact_target_landmarks(target_state),
    "target_artifact_refs": artifact_refs(run.run_dir, target_state),
  }


def _resolve_href(raw_href: str, source_url: str) -> tuple[str, str]:
  resolved = urljoin(source_url, raw_href)
  defragmented, fragment = urldefrag(resolved)
  return defragmented + (f"#{fragment}" if fragment else ""), fragment


def _match_target_state(
  run: RunArtifacts,
  source_state: RunState,
  resolved_url: str,
) -> RunState | None:
  source_url = _state_url(source_state)
  resolved_no_fragment = _without_fragment(resolved_url)
  resolved_path = _path_with_query(urlparse(resolved_no_fragment))
  for state in run.states:
    state_url = _without_fragment(_state_url(state))
    if not state_url:
      continue
    if not _is_same_origin_http_url(state_url, source_url):
      continue
    if state_url == resolved_no_fragment:
      return state
    if _path_with_query(urlparse(state_url)) == resolved_path:
      return state
  return None


def _state_url(state: RunState) -> str:
  page = state.accessibility_context.get("page") if isinstance(state.accessibility_context.get("page"), dict) else {}
  return str(page.get("url") or state.metadata.get("url") or "")


def _state_title(state: RunState) -> str:
  page = state.accessibility_context.get("page") if isinstance(state.accessibility_context.get("page"), dict) else {}
  return str(page.get("title") or state.metadata.get("title") or "")


def _state_route(state: RunState) -> str:
  route = str(state.metadata.get("route") or "")
  if route:
    return route
  return _path_with_query(urlparse(_state_url(state)))


def _is_same_resource_profile_tab_link(state: RunState, link: dict[str, Any], name: str) -> bool:
  normalized_name = _normalized_link_label(name)
  if normalized_name not in SAME_RESOURCE_TAB_LABELS:
    return False

  source_url = _state_url(state)
  raw_href = str(link.get("href") or "")
  if not source_url or not raw_href:
    return False

  resolved_url, fragment = _resolve_href(raw_href, source_url)
  if fragment or not _is_same_origin_http_url(resolved_url, source_url):
    return False

  source_path = _normalized_path(urlparse(_without_fragment(source_url)).path)
  target_path = _normalized_path(urlparse(_without_fragment(resolved_url)).path)
  if not source_path or not target_path or source_path == target_path:
    return False
  if not _same_route_family(source_path, target_path):
    return False

  context = link.get("context") if isinstance(link.get("context"), dict) else {}
  parent_text = _normalized_link_label(context.get("parent_text"))
  return not parent_text or normalized_name in parent_text


def _same_route_family(first_path: str, second_path: str) -> bool:
  return first_path.startswith(f"{second_path}/") or second_path.startswith(f"{first_path}/")


def _normalized_path(path: str) -> str:
  cleaned = "/" + "/".join(segment for segment in str(path or "").split("/") if segment)
  return cleaned if cleaned != "/" else ""


def _normalized_link_label(value: object) -> str:
  return " ".join(str(value or "").casefold().split())


def _without_fragment(url: str) -> str:
  return urldefrag(url)[0]


def _path_with_query(parsed_url) -> str:
  path = parsed_url.path or "/"
  if parsed_url.query:
    return f"{path}?{parsed_url.query}"
  return path


def _is_same_origin_http_url(resolved_url: str, source_url: str) -> bool:
  resolved = urlparse(resolved_url)
  source = urlparse(source_url)
  if resolved.scheme not in ("http", "https") or source.scheme not in ("http", "https"):
    return False
  return (resolved.scheme, resolved.netloc) == (source.scheme, source.netloc)


def _compact_target_headings(state: RunState) -> list[dict[str, object]]:
  headings = state.accessibility_context.get("headings")
  if not isinstance(headings, list):
    return []
  compact: list[dict[str, object]] = []
  for heading in headings:
    if not isinstance(heading, dict) or heading.get("visible") is False:
      continue
    compact.append(
      {
        "element_id": str(heading.get("element_id") or ""),
        "level": heading.get("level"),
        "tag": str(heading.get("tag") or ""),
        "text": str(heading.get("text") or ""),
        "accessible_name": heading.get("accessible_name"),
      }
    )
    if len(compact) >= MAX_TARGET_HEADINGS:
      break
  return compact


def _compact_target_landmarks(state: RunState) -> list[dict[str, object]]:
  landmarks = state.accessibility_context.get("landmarks")
  if not isinstance(landmarks, list):
    return []
  compact: list[dict[str, object]] = []
  for landmark in landmarks:
    if not isinstance(landmark, dict) or landmark.get("visible") is False:
      continue
    compact.append(
      {
        "element_id": str(landmark.get("element_id") or ""),
        "tag": str(landmark.get("tag") or ""),
        "role": landmark.get("role"),
        "text": str(landmark.get("text") or ""),
        "accessible_name": landmark.get("accessible_name"),
        "selector": str(landmark.get("selector") or ""),
      }
    )
    if len(compact) >= MAX_TARGET_LANDMARKS:
      break
  return compact
