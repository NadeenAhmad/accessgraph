from __future__ import annotations

from typing import Any

from ..evidence_helpers import bounding_box_ref, dom_snippet, element_ref, evidence_items, is_visible, truncate_text
from ..models import RunArtifacts, RunState
from ..payload import build_candidate_payload
from .structure_common import compact_page

CANDIDATE_TYPE = "table-header-association-mismatch"
TABLE_HEADER_CONTEXT_SCHEMA_VERSION = "table_header_association_context_v1"


def build_table_header_association_mismatch_candidates(
  run: RunArtifacts,
  state: RunState,
  graph_context: dict[str, object],
) -> list[dict[str, object]]:
  records: list[dict[str, object]] = []
  for table in evidence_items(state, "tables"):
    if not is_visible(table):
      continue
    associated_cells = _associated_data_cells(table)
    if not associated_cells:
      continue
    snippet = dom_snippet(table)
    primary_ref = element_ref("tables", table)
    records.append(
      build_candidate_payload(
        run=run,
        state=state,
        candidate_type=CANDIDATE_TYPE,
        primary_element_ref=primary_ref,
        element_refs=[primary_ref],
        selection_reason=["table_with_structural_header_associations"],
        required_context=[
          "table header text",
          "data-cell content",
          "row and column relationship meaning",
        ],
        evidence={
          "primary": {"table": _compact_table(table, associated_cells)},
          "supporting": {
            "page": compact_page(state),
            "table_header_association_context_v1": _build_table_context(table, associated_cells),
            "context": table.get("context") if isinstance(table.get("context"), dict) else {},
            "structure": table.get("structure") if isinstance(table.get("structure"), dict) else {},
          },
          "bounding_boxes": [bounding_box_ref(table)],
          "dom_snippets": [snippet] if snippet else [],
        },
        graph_context=graph_context,
      )
    )
  return records


def _associated_data_cells(table: dict[str, Any]) -> list[dict[str, Any]]:
  cells = table.get("data_cells") if isinstance(table.get("data_cells"), list) else []
  associated = []
  for cell in cells:
    if not isinstance(cell, dict):
      continue
    header_ids = cell.get("header_ids") if isinstance(cell.get("header_ids"), list) else []
    if header_ids and cell.get("headers_all_resolved") is True:
      associated.append(cell)
  return associated


def _compact_table(table: dict[str, Any], associated_cells: list[dict[str, Any]]) -> dict[str, object]:
  return {
    "element_id": str(table.get("element_id") or ""),
    "tag": str(table.get("tag") or ""),
    "role": table.get("role"),
    "selector": str(table.get("selector") or ""),
    "accessible_name": truncate_text(table.get("accessible_name")),
    "caption": truncate_text(table.get("caption")),
    "header_count": _as_int(table.get("header_count")),
    "data_cell_count": _as_int(table.get("data_cell_count")),
    "associated_data_cell_count": len(associated_cells),
  }


def _build_table_context(table: dict[str, Any], associated_cells: list[dict[str, Any]]) -> dict[str, object]:
  headers = table.get("headers") if isinstance(table.get("headers"), list) else []
  return {
    "schema_version": TABLE_HEADER_CONTEXT_SCHEMA_VERSION,
    "table": _compact_table(table, associated_cells),
    "headers": [_compact_header(header) for header in headers[:12] if isinstance(header, dict)],
    "associated_data_cells": [
      _compact_cell(cell)
      for cell in associated_cells[:16]
    ],
    "relationship_summary": {
      "uses_headers_attribute": True,
      "all_included_associations_resolved": True,
      "syntax_notes": "Invalid or unresolved header references are excluded from this semantic candidate rule.",
    },
  }


def _compact_header(header: dict[str, Any]) -> dict[str, object]:
  return {
    "id": truncate_text(header.get("id"), max_length=120),
    "text": truncate_text(header.get("text"), max_length=160),
    "scope": truncate_text(header.get("scope"), max_length=80),
    "row_index": _as_int(header.get("row_index")),
    "column_index": _as_int(header.get("column_index")),
    "selector": truncate_text(header.get("selector"), max_length=240),
  }


def _compact_cell(cell: dict[str, Any]) -> dict[str, object]:
  return {
    "text": truncate_text(cell.get("text"), max_length=160),
    "header_ids": [truncate_text(item, max_length=120) for item in cell.get("header_ids", [])],
    "associated_headers": [
      _compact_header(header)
      for header in cell.get("associated_headers", [])
      if isinstance(header, dict)
    ],
    "row_index": _as_int(cell.get("row_index")),
    "column_index": _as_int(cell.get("column_index")),
    "selector": truncate_text(cell.get("selector"), max_length=240),
  }


def _as_int(value: object) -> int | None:
  try:
    return int(str(value))
  except (TypeError, ValueError):
    return None
