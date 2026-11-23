from __future__ import annotations

ACCESSIBILITY_CONTEXT_SCHEMA_VERSION = "1"
MAX_TEXT_LENGTH = 500

EVIDENCE_CATEGORIES: tuple[str, ...] = (
  "referenced_elements",
  "images",
  "videos",
  "links",
  "buttons",
  "forms",
  "form_controls",
  "headings",
  "landmarks",
  "tables",
  "language_samples",
  "visual_cues",
  "focusables",
  "focus_order",
  "focus_traversal",
  "relationships",
)

# W4A dev round 2 (2026-11-16): element caps raised so large real pages are recorded in full (links 150 -> 600, ...).
EXTRACTION_LIMITS: dict[str, int] = {
  "max_text_length": MAX_TEXT_LENGTH,
  "max_referenced_elements_per_state": 200,
  "max_images_per_state": 400,
  "max_videos_per_state": 50,
  "max_media_cues_per_track": 500,
  "max_media_track_wait_ms": 1500,
  "max_links_per_state": 600,
  "max_buttons_per_state": 400,
  "max_forms_per_state": 50,
  "max_form_controls_per_state": 400,
  "max_headings_per_state": 300,
  "max_landmarks_per_state": 50,
  "max_tables_per_state": 50,
  "max_language_samples_per_state": 120,
  "max_visual_cues_per_state": 120,
  "max_focusables_per_state": 250,
  "max_focus_traversal_steps": 40,
  "max_relationships_per_state": 500,
}

FORBIDDEN_EVIDENCE_KEYS: tuple[str, ...] = (
  "candidate_id",
  "violation_target",
  "violation",
  "candidate",
  "issue",
  "severity",
  "wcag",
  "confidence",
  "classification",
  "semantic_judgment",
  "precheck",
  "llm",
  "report",
)


def empty_category_payload() -> dict[str, list[dict[str, object]]]:
  return {category: [] for category in EVIDENCE_CATEGORIES}
