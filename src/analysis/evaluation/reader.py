from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import LoadedConfirmationRun


def load_confirmation_runs(
  run_dir: Path,
  confirmation_run_ids: tuple[str, ...],
) -> tuple[LoadedConfirmationRun, ...]:
  if not confirmation_run_ids:
    raise ValueError("At least one confirmation run id is required.")
  if len(set(confirmation_run_ids)) != len(confirmation_run_ids):
    raise ValueError("Confirmation run ids must be unique.")
  return tuple(_load_confirmation_run(run_dir, confirmation_run_id) for confirmation_run_id in confirmation_run_ids)


def _load_confirmation_run(run_dir: Path, confirmation_run_id: str) -> LoadedConfirmationRun:
  confirmation_dir = run_dir / "confirmations" / confirmation_run_id
  manifest_path = confirmation_dir / "manifest.json"
  confirmations_path = confirmation_dir / "confirmations.jsonl"

  if not confirmation_dir.exists() or not confirmation_dir.is_dir():
    raise FileNotFoundError(f"Confirmation run directory not found: {confirmation_dir}")
  if not manifest_path.exists() or not manifest_path.is_file():
    raise FileNotFoundError(f"Confirmation manifest not found: {manifest_path}")
  if not confirmations_path.exists() or not confirmations_path.is_file():
    raise FileNotFoundError(f"Confirmations JSONL not found: {confirmations_path}")

  manifest = _read_json_object(manifest_path)
  records = tuple(_read_jsonl_objects(confirmations_path))
  return LoadedConfirmationRun(
    run_dir=run_dir.resolve(),
    confirmation_run_id=confirmation_run_id,
    confirmation_dir=confirmation_dir.resolve(),
    manifest_path=manifest_path.resolve(),
    confirmations_path=confirmations_path.resolve(),
    manifest=manifest,
    records=records,
  )


def _read_json_object(path: Path) -> dict[str, object]:
  payload = json.loads(path.read_text(encoding="utf-8"))
  if not isinstance(payload, dict):
    raise ValueError(f"Expected JSON object in {path}")
  return payload


def _read_jsonl_objects(path: Path) -> list[dict[str, Any]]:
  records: list[dict[str, Any]] = []
  with path.open("r", encoding="utf-8") as handle:
    for line_number, line in enumerate(handle, start=1):
      stripped = line.strip()
      if not stripped:
        continue
      payload = json.loads(stripped)
      if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object at {path}:{line_number}")
      records.append(payload)
  return records
