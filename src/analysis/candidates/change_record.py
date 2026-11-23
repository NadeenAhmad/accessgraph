"""Change records (C2): what an action changed, computed offline from two saved states.

For every recorded edge (source state -> target state) `change_record_v1` lists, before and after the action:
title, route and page language; headings (text, and whether the content under them changed); named landmarks
(name, content); form labels (label, purpose = type/name/autocomplete); control names; status texts; `flags` for
metadata that stayed the same while its content changed; and `added_metadata` for headings, landmarks and labels
that appear with the transition, each stored with the triggering control's name and the text of its row or card.

"Changed" means a normalised-text difference of at least CHANGE_THRESHOLD (difflib ratio). Elements are matched
across the two states by stable identifiers only (data-testid, identity, DOM path, unique selector), then by
structure (heading level + outline position; landmark role + position). Visible text alone never matches.
Change records are evidence for the judge, never verdicts.
"""
from __future__ import annotations

import copy
import hashlib
import json
from difflib import SequenceMatcher
from typing import Any

from .destination_state_context import saved_html_attributes
from .evidence_helpers import evidence_items, truncate_text
from .models import RunArtifacts, RunState, sanitize_action

SCHEMA_VERSION = "change_record_v1"
CHANGE_THRESHOLD = 0.15  # frozen parameter
MAX_ITEMS = 12
MAX_TEXT = 200
MAX_INCOMING_RECORDS_PER_ITEM = 3
IDENTIFIER_ORDER = ("element_id", "data_testid", "identity", "dom_path", "selector")
BACKWARD_TYPES = ("page-title-not-descriptive", "heading-not-descriptive", "landmark-purpose-mismatch",
                  "form-label-mismatch")
FORWARD_TYPES = ("button-label-mismatch", "link-text-mismatch", "widget-label-purpose-mismatch")
CONTROL_BUCKETS = ("buttons", "links")
STATUS_ROLES = {"alert", "status"}


def normalise(text: object) -> str:
  return " ".join(str(text or "").split()).casefold()


def text_changed(before: object, after: object) -> bool:
  a, b = normalise(before), normalise(after)
  if a == b:
    return False
  if not a or not b:
    return True
  return 1.0 - SequenceMatcher(None, a, b, autojunk=False).ratio() >= CHANGE_THRESHOLD


# --- element identity ---------------------------------------------------------------------------------------

def _identifier(element: dict[str, Any], identifier: str) -> str:
  attrs = saved_html_attributes(element.get("raw_html"))
  if identifier == "data_testid":
    return str(element.get("data_testid") or attrs.get("data-testid") or attrs.get("data-test-id") or "")
  if identifier == "dom_path":
    return str(element.get("dom_path") or element.get("xpath") or "")
  return str(element.get(identifier) or "")


def _structural_key(element: dict[str, Any], bucket: str, position: int) -> str:
  if bucket == "headings":
    return f"heading:{element.get('level')}:{position}"
  if bucket == "landmarks":
    return f"landmark:{(element.get('role') or element.get('tag') or '').lower()}:{position}"
  return ""


def match_elements(before: list[dict[str, Any]], after: list[dict[str, Any]], bucket: str
                   ) -> list[tuple[dict[str, Any] | None, dict[str, Any] | None, str]]:
  """Pairs (before, after, basis); unmatched elements appear with None on the other side."""
  def positions(items):
    counters: dict[str, int] = {}
    out = []
    for item in items:
      group = str(item.get("level")) if bucket == "headings" else (item.get("role") or item.get("tag") or "")
      counters[group] = counters.get(group, 0) + 1
      out.append(counters[group])
    return out

  b_pos, a_pos = positions(before), positions(after)
  free_b, free_a = set(range(len(before))), set(range(len(after)))
  pairs: list[tuple[dict | None, dict | None, str]] = []
  for basis in (*IDENTIFIER_ORDER, "structure"):
    def unique(items, free, pos):
      seen: dict[str, list[int]] = {}
      for i in free:
        value = (_structural_key(items[i], bucket, pos[i]) if basis == "structure" else _identifier(items[i], basis))
        if value:
          seen.setdefault(value, []).append(i)
      return {v: idx[0] for v, idx in seen.items() if len(idx) == 1}

    ub, ua = unique(before, free_b, b_pos), unique(after, free_a, a_pos)
    for value, i in ub.items():
      j = ua.get(value)
      if j is not None and i in free_b and j in free_a:
        pairs.append((before[i], after[j], basis))
        free_b.discard(i)
        free_a.discard(j)
  pairs += [(before[i], None, "") for i in sorted(free_b)]
  pairs += [(None, after[j], "") for j in sorted(free_a)]
  return pairs


# --- per-kind summaries ---------------------------------------------------------------------------------------

def _text(element: dict[str, Any] | None, *keys: str) -> str:
  if not element:
    return ""
  for key in keys:
    value = element.get(key)
    if value:
      return truncate_text(value, max_length=MAX_TEXT)
  return ""


def _heading_content(element: dict[str, Any] | None) -> str:
  scope = (element or {}).get("heading_scope")
  return str(scope.get("text_excerpt") or "") if isinstance(scope, dict) else ""


def _landmark_name(element: dict[str, Any] | None) -> str:
  if not element:
    return ""
  if element.get("aria_label"):
    return truncate_text(element["aria_label"], max_length=MAX_TEXT)
  if element.get("aria_labelledby"):
    return _text(element, "accessible_name")
  return ""


def _purpose(element: dict[str, Any] | None) -> dict[str, str]:
  attrs = (element or {}).get("attributes") if isinstance((element or {}).get("attributes"), dict) else {}
  return {key: str(attrs.get(key) or "") for key in ("type", "name", "autocomplete")}


def _status_texts(state: RunState) -> list[str]:
  texts = []
  for item in evidence_items(state, "visual_cues"):
    if str(item.get("role") or "").lower() in STATUS_ROLES or item.get("aria_live"):
      text = _text(item, "text", "accessible_name")
      if text and text not in texts:
        texts.append(text)
  return texts[:MAX_ITEMS]


def _page(state: RunState) -> dict[str, Any]:
  page = state.accessibility_context.get("page")
  return page if isinstance(page, dict) else {}


def _route(state: RunState) -> str:
  from urllib.parse import urlparse

  url = str(_page(state).get("url") or state.metadata.get("url") or "")
  parsed = urlparse(url)
  return str(state.metadata.get("route") or (parsed.path + (f"#{parsed.fragment}" if parsed.fragment else "")))


def _trigger(run: RunArtifacts, source: RunState, edge: dict[str, Any]) -> dict[str, Any]:
  """The control that triggered the edge, with the text of its row/card in the source state when found.

  The trigger is located inside the source state only: by data-testid or HTML id from the recorded action,
  else by a unique (tag, accessible name) match in that same state.
  """
  raw_action = edge.get("action") if isinstance(edge.get("action"), dict) else {}
  primary = raw_action.get("primary_trigger")
  action = primary if isinstance(primary, dict) and primary else raw_action
  trigger: dict[str, Any] = {"type": action.get("type") or raw_action.get("type") or "",
                             "name": truncate_text(action.get("accessible_name") or action.get("text")
                                                   or raw_action.get("text"), max_length=120)}
  if raw_action.get("value_set_kind"):
    trigger["value_set_kind"] = raw_action["value_set_kind"]
  elements = [e for bucket in (*CONTROL_BUCKETS, "form_controls", "visual_cues") for e in evidence_items(source, bucket)]
  wanted_testid = str(action.get("data_testid") or "")
  path = str(action.get("dom_path") or "")
  wanted_html_id = path.rsplit("#", 1)[1].split(">")[0] if "#" in path.rsplit(">", 1)[-1] else ""
  found, basis = None, ""
  for element in elements:
    attrs = saved_html_attributes(element.get("raw_html"))
    if wanted_testid and _identifier(element, "data_testid") == wanted_testid:
      found, basis = element, "data_testid"
      break
    if wanted_html_id and attrs.get("id") == wanted_html_id:
      found, basis = element, "html_id"
      break
  if found is None and trigger["name"]:
    tag = str(action.get("tag_name") or "").lower()
    same = [e for e in elements if normalise(e.get("accessible_name") or e.get("text")) == normalise(trigger["name"])
            and (not tag or str(e.get("tag") or "").lower() == tag)]
    if len(same) == 1:
      found, basis = same[0], "name_in_source_state"
  if found is not None:
    context = found.get("context") if isinstance(found.get("context"), dict) else {}
    trigger["name"] = _text(found, "accessible_name", "text") or trigger["name"]
    trigger["row_text"] = truncate_text(context.get("parent_text") or context.get("nearby_text"), max_length=MAX_TEXT)
    trigger["element_id"] = found.get("element_id")
    trigger["located_by"] = basis
  return trigger


# --- the record -----------------------------------------------------------------------------------------------

def build_change_record(run: RunArtifacts, source: RunState, target: RunState, edge: dict[str, Any]) -> dict[str, Any]:
  before_page, after_page = _page(source), _page(target)
  record: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "change_threshold": CHANGE_THRESHOLD,
    "from_state": source.state_id,
    "to_state": target.state_id,
    "trigger": _trigger(run, source, edge),
  }
  for key, before, after in (
    ("title", before_page.get("title"), after_page.get("title")),
    ("route", _route(source), _route(target)),
    ("lang", before_page.get("page_lang") or before_page.get("html_lang"),
     after_page.get("page_lang") or after_page.get("html_lang")),
  ):
    record[key] = {"before": truncate_text(before, max_length=MAX_TEXT), "after": truncate_text(after, max_length=MAX_TEXT),
                   "changed": text_changed(before, after)}
  body_changed = text_changed(before_page.get("body_text_sample"), after_page.get("body_text_sample"))
  record["body_text_changed"] = body_changed

  flags: list[dict[str, Any]] = []
  added: list[dict[str, Any]] = []
  trigger = record["trigger"]

  def add_metadata(kind: str, element: dict[str, Any], text: str) -> None:
    if text:
      added.append({"kind": kind, "element_id": element.get("element_id"), "text": text,
                    "trigger_name": trigger.get("name", ""), "trigger_row_text": trigger.get("row_text", "")})

  headings = []
  for b, a, basis in match_elements(evidence_items(source, "headings"), evidence_items(target, "headings"), "headings"):
    if a is not None and b is None:
      add_metadata("heading", a, _text(a, "accessible_name", "text"))
      continue
    if a is None or b is None:
      continue
    entry = {"match_basis": basis, "element_id_after": a.get("element_id"), "level": a.get("level"),
             "before": _text(b, "accessible_name", "text"), "after": _text(a, "accessible_name", "text"),
             "text_changed": text_changed(_text(b, "accessible_name", "text"), _text(a, "accessible_name", "text")),
             "content_changed": text_changed(_heading_content(b), _heading_content(a))}
    headings.append(entry)
    if not entry["text_changed"] and entry["content_changed"]:
      flags.append({"kind": "heading_text_unchanged_content_changed", "element_id": a.get("element_id"),
                    "text": entry["after"]})
  record["headings"] = headings[:MAX_ITEMS]

  landmarks = []
  for b, a, basis in match_elements(evidence_items(source, "landmarks"), evidence_items(target, "landmarks"), "landmarks"):
    if a is not None and b is None:
      add_metadata("landmark", a, _landmark_name(a))
      continue
    if a is None or b is None or not (_landmark_name(a) or _landmark_name(b)):
      continue
    entry = {"match_basis": basis, "element_id_after": a.get("element_id"), "role": a.get("role") or a.get("tag"),
             "before": _landmark_name(b), "after": _landmark_name(a),
             "name_changed": text_changed(_landmark_name(b), _landmark_name(a)),
             "content_changed": text_changed(_text(b, "text_sample", "text"), _text(a, "text_sample", "text"))}
    landmarks.append(entry)
    if not entry["name_changed"] and entry["content_changed"]:
      flags.append({"kind": "landmark_name_unchanged_content_changed", "element_id": a.get("element_id"),
                    "text": entry["after"]})
  record["landmarks"] = landmarks[:MAX_ITEMS]

  labels = []
  for b, a, basis in match_elements(evidence_items(source, "form_controls"), evidence_items(target, "form_controls"),
                                    "form_controls"):
    if a is not None and b is None:
      add_metadata("form_label", a, _text(a, "accessible_name"))
      continue
    if a is None or b is None:
      continue
    entry = {"match_basis": basis, "element_id_after": a.get("element_id"),
             "before": _text(b, "accessible_name"), "after": _text(a, "accessible_name"),
             "label_changed": text_changed(_text(b, "accessible_name"), _text(a, "accessible_name")),
             "purpose_before": _purpose(b), "purpose_after": _purpose(a)}
    entry["purpose_changed"] = entry["purpose_before"] != entry["purpose_after"]
    labels.append(entry)
    if not entry["label_changed"] and entry["purpose_changed"]:
      flags.append({"kind": "form_label_unchanged_purpose_changed", "element_id": a.get("element_id"),
                    "text": entry["after"]})
  record["form_labels"] = labels[:MAX_ITEMS]

  controls = []
  for bucket in CONTROL_BUCKETS:
    for b, a, basis in match_elements(evidence_items(source, bucket), evidence_items(target, bucket), bucket):
      if a is None or b is None:
        continue
      if text_changed(_text(b, "accessible_name", "text"), _text(a, "accessible_name", "text")):
        controls.append({"bucket": bucket, "match_basis": basis, "element_id_after": a.get("element_id"),
                         "before": _text(b, "accessible_name", "text"), "after": _text(a, "accessible_name", "text")})
  record["control_names_changed"] = controls[:MAX_ITEMS]

  before_status, after_status = _status_texts(source), _status_texts(target)
  record["status_texts"] = {"before": before_status, "after": after_status,
                            "added": [t for t in after_status if t not in before_status],
                            "removed": [t for t in before_status if t not in after_status]}

  title = record["title"]
  if not title["changed"] and (record["route"]["changed"] or body_changed):
    flags.append({"kind": "title_unchanged_route_or_content_changed", "text": title["after"]})
  if title["after"] and not title["before"]:
    add_metadata("title", {}, title["after"])
  record["flags"] = flags
  record["added_metadata"] = added[:MAX_ITEMS]
  return record


class ChangeRecordIndex:
  """Lazily computes change records for the edges of one run."""

  def __init__(self, run: RunArtifacts):
    self.run = run
    self.states = {state.state_id: state for state in run.states}
    transitions = run.transitions or (run.graph.get("edges") if isinstance(run.graph.get("edges"), list) else [])
    self.edges = [e for e in transitions if isinstance(e, dict) and e.get("from") and e.get("to")]
    self._cache: dict[int, dict[str, Any]] = {}

  def incoming(self, state_id: str) -> list[dict[str, Any]]:
    return [e for e in self.edges if e.get("to") == state_id and e.get("from") != state_id]

  def outgoing(self, state_id: str, target_id: str) -> list[dict[str, Any]]:
    return [e for e in self.edges if e.get("from") == state_id and e.get("to") == target_id]

  def record(self, edge: dict[str, Any]) -> dict[str, Any] | None:
    key = id(edge)
    if key not in self._cache:
      source, target = self.states.get(str(edge.get("from"))), self.states.get(str(edge.get("to")))
      self._cache[key] = build_change_record(self.run, source, target, edge) if source and target else None
    return self._cache[key]

  def all_records(self) -> list[dict[str, Any]]:
    return [r for r in (self.record(e) for e in self.edges) if r]


# --- attaching to candidates ----------------------------------------------------------------------------------

def scoped_record(record: dict[str, Any], candidate_type: str, element_id: str) -> dict[str, Any]:
  """The part of a change record that concerns one candidate (its element, or the page title)."""
  scoped = {key: record[key] for key in ("schema_version", "change_threshold", "from_state", "to_state", "trigger",
                                          "title", "route")}
  scoped["scope"] = candidate_type
  if candidate_type == "page-title-not-descriptive":
    scoped["body_text_changed"] = record["body_text_changed"]
    scoped["flags"] = [f for f in record["flags"] if f["kind"].startswith("title_")]
    scoped["added_metadata"] = [m for m in record["added_metadata"] if m["kind"] == "title"]
    return scoped
  section = {"heading-not-descriptive": "headings", "landmark-purpose-mismatch": "landmarks",
             "form-label-mismatch": "form_labels"}[candidate_type]
  scoped["element"] = next((e for e in record[section] if e.get("element_id_after") == element_id), None)
  scoped["flags"] = [f for f in record["flags"] if f.get("element_id") == element_id]
  scoped["added_metadata"] = [m for m in record["added_metadata"] if m.get("element_id") == element_id]
  return scoped


def _signature(scoped: dict[str, Any]) -> str:
  payload = {k: v for k, v in scoped.items() if k not in ("from_state", "to_state")}
  payload["trigger"] = {k: v for k, v in scoped["trigger"].items() if k in ("name", "row_text", "type", "value_set_kind")}
  return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _primary_element_id(candidate: dict[str, Any]) -> str:
  refs = candidate.get("element_refs") or []
  return str(refs[0].get("element_id") or "") if refs and isinstance(refs[0], dict) else ""


def attach_change_records(candidates: list[dict[str, Any]], index: ChangeRecordIndex) -> list[dict[str, Any]]:
  """Add change records to candidates; backward types get one candidate per distinct incoming record (max 3)."""
  out: list[dict[str, Any]] = []
  for candidate in candidates:
    candidate_type = str(candidate.get("candidate_type") or "")
    state_id = str(candidate.get("state_id") or "")
    if candidate_type in BACKWARD_TYPES:
      element_id = _primary_element_id(candidate)
      distinct: list[tuple[dict[str, Any], dict[str, Any]]] = []
      seen: set[str] = set()
      for edge in index.incoming(state_id):
        record = index.record(edge)
        if record is None:
          continue
        scoped = scoped_record(record, candidate_type, element_id)
        signature = _signature(scoped)
        if signature in seen:
          continue
        seen.add(signature)
        distinct.append((edge, scoped))
        if len(distinct) >= MAX_INCOMING_RECORDS_PER_ITEM:
          break
      if not distinct:
        candidate["evidence_scope"] = "state"
        out.append(candidate)
        continue
      for k, (edge, scoped) in enumerate(distinct):
        clone = candidate if k == 0 else copy.deepcopy(candidate)
        if k > 0:
          clone["candidate_id"] = f"{candidate['candidate_id']}_in{k + 1}"
          clone["incoming_variant_of"] = candidate["candidate_id"]
        graph_context = clone.setdefault("graph_context", {})
        graph_context["incoming_change_record_v1"] = scoped
        graph_context["incoming_edge_action"] = sanitize_action(edge.get("action") if isinstance(edge.get("action"), dict) else {})
        clone["evidence_scope"] = "incoming"
        out.append(clone)
      continue
    if candidate_type in FORWARD_TYPES:
      supporting = (candidate.get("evidence") or {}).get("supporting") or {}
      destinations = supporting.get("destination_state_context_v1")
      if isinstance(destinations, dict) and destinations.get("destinations"):
        v2 = copy.deepcopy(destinations)
        v2["schema_version"] = "destination_state_context_v2"
        for destination in v2["destinations"]:
          edges = index.outgoing(state_id, str(destination.get("target_state_id")))
          record = index.record(edges[0]) if edges else None
          destination["change_record"] = record
        candidate.setdefault("graph_context", {})["destination_state_context_v2"] = v2
        candidate["evidence_scope"] = "outgoing"
        out.append(candidate)
        continue
    candidate["evidence_scope"] = "state"
    out.append(candidate)
  return out
