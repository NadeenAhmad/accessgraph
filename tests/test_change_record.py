"""C2: change records computed offline from saved states, attached to backward and forward candidates."""
from __future__ import annotations

import json
from pathlib import Path

from src.analysis.candidates.builder import build_semantic_candidates
from src.analysis.candidates.change_record import CHANGE_THRESHOLD, text_changed


def _heading(xpath: str, text: str, content: str, *, level: int = 1, testid: str = "") -> dict:
  attrs = f' data-testid="{testid}"' if testid else ""
  return {"element_id": f"e_{abs(hash((xpath, text))) % 10**8}", "kind": "heading", "tag": f"h{level}", "level": level,
          "text": text, "accessible_name": text, "visible": True, "xpath": xpath, "selector": f"h{level}",
          "raw_html": f"<h{level}{attrs}>{text}</h{level}>",
          "heading_scope": {"schema_version": "heading_scope_v1", "text_excerpt": content},
          "context": {"nearby_text": content[:60], "parent_text": content[:80], "section_heading": text}}


def _button(xpath: str, name: str, row_text: str, testid: str) -> dict:
  return {"element_id": f"b_{testid}", "kind": "button", "tag": "button", "text": name, "accessible_name": name,
          "visible": True, "xpath": xpath, "selector": "button", "raw_html": f'<button data-testid="{testid}">{name}</button>',
          "context": {"parent_text": row_text, "nearby_text": row_text}}


def _write_run(run_dir: Path, states: dict[str, dict], edges: list[tuple[str, str, dict]]) -> Path:
  for state_id, spec in states.items():
    state_dir = run_dir / "states" / state_id
    state_dir.mkdir(parents=True)
    page = {"url": f"http://127.0.0.1:5173{spec.get('route', '/')}", "title": spec.get("title", "Shop"), "page_lang": "en",
            "body_text_sample": spec.get("body", "")}
    context = {"schema_version": "1", "state_id": state_id, "page": page,
               "state_context": {"depth": spec.get("depth", 0), "parent_state": spec.get("parent"),
                                 "action_from_parent": spec.get("action")},
               "headings": spec.get("headings", []), "buttons": spec.get("buttons", []), "links": [], "landmarks": [],
               "form_controls": [], "visual_cues": []}
    (state_dir / "accessibility_context.json").write_text(json.dumps(context))
    (state_dir / "metadata.json").write_text(json.dumps({"state_id": state_id, "url": page["url"],
                                                         "parent_state": spec.get("parent")}))
  transitions = [{"from": a, "to": b, "action": action} for a, b, action in edges]
  (run_dir / "transitions.json").write_text(json.dumps(transitions))
  (run_dir / "graph.json").write_text(json.dumps({"nodes": [{"state_id": s, "parent_state_id": spec.get("parent")}
                                                            for s, spec in states.items()], "edges": transitions}))
  return run_dir


def _candidates(run_dir: Path) -> list[dict]:
  build_semantic_candidates(run_dir, candidate_types=["heading-not-descriptive"])
  return [json.loads(l) for l in (run_dir / "candidates" / "candidates.jsonl").read_text().splitlines()]


H1 = "/html[1]/body[1]/main[1]/h1[1]"


def test_threshold_is_frozen_and_text_change_rule():
  assert CHANGE_THRESHOLD == 0.15
  assert not text_changed("Your basket", " your  BASKET ")
  assert text_changed("Shipping", "Payment") and text_changed("", "Payment")
  assert not text_changed("Choose a delivery slot for Monday", "Choose a delivery slot for Monday.")


def test_outdated_heading_flagged_updated_heading_not(tmp_path):
  click = {"type": "click", "text": "Continue", "data_testid": "continue"}
  run = _write_run(tmp_path, {
    "state_0000": {"headings": [_heading(H1, "Shipping", "Shipping address street city zip code")], "body": "shipping form"},
    "state_0001": {"parent": "state_0000", "depth": 1, "action": click, "body": "payment form card number expiry",
                   "headings": [_heading(H1, "Shipping", "Payment card number expiry date security code")]},
    "state_0002": {"parent": "state_0000", "depth": 1, "action": click, "body": "payment form card number expiry",
                   "headings": [_heading(H1, "Payment", "Payment card number expiry date security code")]},
  }, [("state_0000", "state_0001", click), ("state_0000", "state_0002", click)])
  by_state = {c["state_id"]: c for c in _candidates(run)}
  stale = by_state["state_0001"]["graph_context"]["incoming_change_record_v1"]
  assert stale["element"]["text_changed"] is False and stale["element"]["content_changed"] is True
  assert [f["kind"] for f in stale["flags"]] == ["heading_text_unchanged_content_changed"]
  updated = by_state["state_0002"]["graph_context"]["incoming_change_record_v1"]
  assert updated["element"]["text_changed"] is True and updated["flags"] == []
  assert by_state["state_0001"]["evidence_scope"] == "incoming" and by_state["state_0000"]["evidence_scope"] == "state"
  assert (run / "candidates" / "change_records.jsonl").exists()


def test_your_basket_is_flagged_but_never_auto_labelled(tmp_path):
  remove = {"type": "click", "text": "Remove Storm Shell", "data_testid": "remove-1"}
  run = _write_run(tmp_path, {
    "state_0000": {"headings": [_heading(H1, "Your basket", "Storm Shell 120 euros Rain Coat 80 euros")]},
    "state_0001": {"parent": "state_0000", "depth": 1, "action": remove,
                   "headings": [_heading(H1, "Your basket", "Rain Coat 80 euros")]},
  }, [("state_0000", "state_0001", remove)])
  candidate = next(c for c in _candidates(run) if c["state_id"] == "state_0001")
  record = candidate["graph_context"]["incoming_change_record_v1"]
  assert record["flags"][0]["kind"] == "heading_text_unchanged_content_changed"
  text = json.dumps(candidate)
  for verdict_key in ('"decision"', '"label"', '"expected_human_judgment"', '"verdict"'):
    assert verdict_key not in text


def test_dialog_from_two_rows_gives_two_backward_candidates_with_their_own_trigger(tmp_path):
  rows = [_button("/html[1]/body[1]/main[1]/ul[1]/li[1]/button[1]", "Remove", "Storm Shell 120 euros", "row-1-remove"),
          _button("/html[1]/body[1]/main[1]/ul[1]/li[2]/button[1]", "Remove", "Rain Coat 80 euros", "row-2-remove")]
  dialog_heading = _heading("/html[1]/body[1]/div[1]/h2[1]", "Remove Storm Shell?", "This cannot be undone", level=2)
  row1 = {"type": "click", "text": "Remove", "data_testid": "row-1-remove"}
  row2 = {"type": "click", "text": "Remove", "data_testid": "row-2-remove"}
  run = _write_run(tmp_path, {
    "state_0000": {"headings": [_heading(H1, "Your basket", "Storm Shell Rain Coat")], "buttons": rows},
    "state_0001": {"parent": "state_0000", "depth": 1, "action": row1, "buttons": rows,
                   "headings": [_heading(H1, "Your basket", "Storm Shell Rain Coat"), dialog_heading]},
  }, [("state_0000", "state_0001", row1), ("state_0000", "state_0001", row2)])
  candidates = [c for c in _candidates(run) if c["state_id"] == "state_0001"]
  dialog = [c for c in candidates if c["element_refs"][0]["element_id"] == dialog_heading["element_id"]]
  assert len(dialog) == 2, [c["candidate_id"] for c in dialog]
  triggers = sorted(c["graph_context"]["incoming_change_record_v1"]["trigger"]["row_text"] for c in dialog)
  assert triggers == ["Rain Coat 80 euros", "Storm Shell 120 euros"]
  added = dialog[0]["graph_context"]["incoming_change_record_v1"]["added_metadata"]
  assert added and added[0]["kind"] == "heading" and added[0]["trigger_name"] == "Remove"
  assert len({c["candidate_id"] for c in dialog}) == 2 and any(c.get("incoming_variant_of") for c in dialog)
