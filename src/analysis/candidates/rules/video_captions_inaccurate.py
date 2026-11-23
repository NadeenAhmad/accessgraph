from __future__ import annotations

from typing import Any

from ..evidence_helpers import (
  bounding_box_ref,
  dom_snippet,
  element_ref,
  evidence_items,
  is_visible,
  truncate_text,
)
from ..media_references import find_media_reference
from ..models import RunArtifacts, RunState
from ..payload import build_candidate_payload

CANDIDATE_TYPE = "video-captions-inaccurate"


def build_video_caption_candidates(
  run: RunArtifacts,
  state: RunState,
  graph_context: dict[str, object],
) -> list[dict[str, object]]:
  records: list[dict[str, object]] = []
  seen: set[tuple[str, str]] = set()
  for video in evidence_items(state, "videos"):
    if not is_visible(video):
      continue
    tracks = video.get("tracks") if isinstance(video.get("tracks"), list) else []
    for raw_track in tracks:
      if not isinstance(raw_track, dict) or str(raw_track.get("kind") or "").lower() != "captions":
        continue
      cues = _ordered_cues(raw_track)
      if not cues or not any(cue["text"] for cue in cues):
        continue
      identity = (
        str(video.get("element_id") or ""),
        str(raw_track.get("element_id") or ""),
      )
      if not all(identity) or identity in seen:
        continue
      seen.add(identity)

      reference = find_media_reference(video, raw_track)
      snippet = dom_snippet(video)
      track = _compact_track(raw_track, cues)
      evidence = {
        "primary": {
          "video": _compact_video(video),
          "caption_track": track,
          "caption_text": _aggregate_caption_text(cues),
        },
        "supporting": {
          "context": video.get("context") if isinstance(video.get("context"), dict) else {},
          "structure": video.get("structure") if isinstance(video.get("structure"), dict) else {},
          "reference_evidence": reference or {"available": False},
        },
        "bounding_boxes": [bounding_box_ref(video)],
        "dom_snippets": [snippet] if snippet else [],
      }
      records.append(
        build_candidate_payload(
          run=run,
          state=state,
          candidate_type=CANDIDATE_TYPE,
          element_refs=[
            element_ref("videos", video),
            element_ref("videos.tracks", raw_track),
          ],
          primary_element_ref=element_ref("videos", video),
          selection_reason=["visible_video_with_loaded_caption_track_and_cue_text"],
          required_context=[
            "caption cue text",
            "spoken narration or authoritative transcript evidence",
            "video purpose and local context",
          ],
          evidence=evidence,
          graph_context=graph_context,
        )
      )
  return records


def _compact_video(video: dict[str, Any]) -> dict[str, object]:
  return {
    "element_id": str(video.get("element_id") or ""),
    "tag": str(video.get("tag") or ""),
    "role": video.get("role"),
    "selector": str(video.get("selector") or ""),
    "accessible_name": video.get("accessible_name"),
    "aria_label": video.get("aria_label"),
    "aria_labelledby": video.get("aria_labelledby"),
    "title": video.get("title"),
    "src": str(video.get("src") or ""),
    "current_src": str(video.get("current_src") or ""),
    "source_src": str(video.get("source_src") or ""),
    "sources": video.get("sources") if isinstance(video.get("sources"), list) else [],
    "poster": video.get("poster"),
    "controls": bool(video.get("controls")),
    "preload": str(video.get("preload") or ""),
    "autoplay": bool(video.get("autoplay")),
    "muted": bool(video.get("muted")),
    "loop": bool(video.get("loop")),
    "duration": video.get("duration"),
    "ready_state": video.get("ready_state"),
    "nearby_transcript_text": video.get("nearby_transcript_text"),
  }


def _compact_track(
  track: dict[str, Any],
  cues: list[dict[str, object]],
) -> dict[str, object]:
  return {
    "element_id": str(track.get("element_id") or ""),
    "selector": str(track.get("selector") or ""),
    "xpath": str(track.get("xpath") or ""),
    "kind": str(track.get("kind") or ""),
    "src": str(track.get("src") or ""),
    "current_src": str(track.get("current_src") or ""),
    "srclang": str(track.get("srclang") or ""),
    "label": str(track.get("label") or ""),
    "default": bool(track.get("default")),
    "mode": str(track.get("mode") or ""),
    "ready_state": str(track.get("ready_state") or ""),
    "cue_status": str(track.get("cue_status") or ""),
    "cue_count": int(track.get("cue_count") or len(cues)),
    "cues_truncated": bool(track.get("cues_truncated")),
    "cues": cues,
  }


def _ordered_cues(track: dict[str, Any]) -> list[dict[str, object]]:
  raw_cues = track.get("cues") if isinstance(track.get("cues"), list) else []
  cues: list[dict[str, object]] = []
  for position, raw_cue in enumerate(raw_cues):
    if not isinstance(raw_cue, dict):
      continue
    try:
      start_time = float(raw_cue.get("start_time"))
      end_time = float(raw_cue.get("end_time"))
      index = int(raw_cue.get("index") if raw_cue.get("index") is not None else position)
    except (TypeError, ValueError):
      continue
    cues.append(
      {
        "index": index,
        "start_time": start_time,
        "end_time": end_time,
        "text": truncate_text(raw_cue.get("text")),
      }
    )
  return sorted(cues, key=lambda cue: (float(cue["start_time"]), int(cue["index"])))


def _aggregate_caption_text(cues: list[dict[str, object]]) -> str:
  return " ".join(
    text
    for cue in cues
    if (text := truncate_text(cue.get("text")))
  )
