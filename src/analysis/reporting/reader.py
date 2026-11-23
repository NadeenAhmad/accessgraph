from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import LoadedConfirmationRun


def confirmation_run_dir(run_dir: Path, confirmation_run_id: str) -> Path:
  return run_dir / "confirmations" / confirmation_run_id


def load_confirmation_run(run_dir: Path, confirmation_run_id: str) -> LoadedConfirmationRun:
  run_dir = run_dir.resolve()
  confirmation_dir = confirmation_run_dir(run_dir, confirmation_run_id)
  if not confirmation_dir.exists() or not confirmation_dir.is_dir():
    raise FileNotFoundError(f"Confirmation run directory does not exist: {confirmation_dir}")

  manifest_path = confirmation_dir / "manifest.json"
  confirmations_path = confirmation_dir / "confirmations.jsonl"
  if not manifest_path.exists() or not manifest_path.is_file():
    raise FileNotFoundError(f"Confirmation manifest does not exist: {manifest_path}")
  if not confirmations_path.exists() or not confirmations_path.is_file():
    raise FileNotFoundError(f"Confirmations JSONL does not exist: {confirmations_path}")

  manifest = _read_json_object(manifest_path)
  records = tuple(_iter_jsonl_objects(confirmations_path))
  return LoadedConfirmationRun(
    run_dir=run_dir,
    confirmation_run_id=confirmation_run_id,
    confirmation_dir=confirmation_dir,
    manifest_path=manifest_path,
    confirmations_path=confirmations_path,
    manifest=manifest,
    records=records,
  )


def _read_json_object(path: Path) -> dict[str, Any]:
  try:
    payload = json.loads(path.read_text(encoding="utf-8"))
  except json.JSONDecodeError as exc:
    raise ValueError(f"JSON file is invalid: {path}") from exc
  if not isinstance(payload, dict):
    raise ValueError(f"JSON file must contain an object: {path}")
  return payload


def _iter_jsonl_objects(path: Path):
  with path.open("r", encoding="utf-8") as handle:
    for line_number, line in enumerate(handle, start=1):
      if not line.strip():
        continue
      try:
        payload = json.loads(line)
      except json.JSONDecodeError as exc:
        raise ValueError(f"JSONL record at {path}:{line_number} is invalid") from exc
      if not isinstance(payload, dict):
        raise ValueError(f"JSONL record at {path}:{line_number} must be an object")
      yield payload
