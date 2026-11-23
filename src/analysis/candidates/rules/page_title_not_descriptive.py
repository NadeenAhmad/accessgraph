from __future__ import annotations

from typing import Any

from ..evidence_helpers import truncate_text
from ..models import RunArtifacts, RunState
from ..payload import build_candidate_payload

CANDIDATE_TYPE = "page-title-not-descriptive"


def build_page_title_candidates(
  run: RunArtifacts,
  state: RunState,
  graph_context: dict[str, object],
) -> list[dict[str, object]]:
  page = state.accessibility_context.get("page")
  if not isinstance(page, dict):
    return []
  title = truncate_text(page.get("title"))
  if not title:
    return []
  headings = _headings(state)
  body_text_sample = truncate_text(page.get("body_text_sample"))
  route = str(state.metadata.get("route") or "")
  if not any([body_text_sample, headings, route, graph_context.get("transition_path")]):
    return []

  return [
    build_candidate_payload(
      run=run,
      state=state,
      candidate_type=CANDIDATE_TYPE,
      element_refs=[],
      selection_reason=["page_title_with_route_and_content_context"],
      required_context=["page purpose", "route context", "visible page content"],
      evidence={
        "primary": {
          "page": {
            "url": str(page.get("url") or state.metadata.get("url") or ""),
            "title": title,
            "document_lang": str(page.get("document_lang") or ""),
            "html_lang": page.get("html_lang"),
          },
        },
        "supporting": {
          "headings": headings[:10],
          "body_text_sample": body_text_sample,
          "route": route,
        },
        "bounding_boxes": [],
        "dom_snippets": [],
      },
      graph_context=graph_context,
    )
  ]


def _headings(state: RunState) -> list[dict[str, object]]:
  raw = state.accessibility_context.get("headings")
  if not isinstance(raw, list):
    return []
  headings: list[dict[str, object]] = []
  for item in raw:
    if not isinstance(item, dict):
      continue
    text = truncate_text(item.get("text"))
    if not text:
      continue
    headings.append(
      {
        "element_id": str(item.get("element_id") or ""),
        "level": item.get("level"),
        "text": text,
        "selector": str(item.get("selector") or ""),
      }
    )
  return headings
