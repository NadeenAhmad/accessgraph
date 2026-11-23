from __future__ import annotations

import platform
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import (
  GENERATOR_NAME,
  GENERATOR_VERSION,
  SCHEMA_VERSION,
  ConfirmationComparisonOptions,
  ConfirmationComparisonResult,
)
from .reader import load_confirmation_runs
from .summarizer import build_comparison_payload
from .writer import prepare_comparison_output_dir, write_comparison_outputs


def run_confirmation_comparison(
  *,
  options: ConfirmationComparisonOptions,
  generated_at: datetime | None = None,
) -> ConfirmationComparisonResult:
  generated_at_dt = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
  loaded_runs = load_confirmation_runs(options.run_dir, options.confirmation_run_ids)
  comparison_run_id = options.comparison_run_id or generate_comparison_run_id(generated_at=generated_at_dt)
  output_dir = (options.output_dir or (options.run_dir / "comparisons" / comparison_run_id)).resolve()
  _validate_output_dir(output_dir, run_dir=options.run_dir)
  prepare_comparison_output_dir(output_dir, overwrite=options.overwrite)

  comparison = build_comparison_payload(
    loaded_runs,
    options=options,
    comparison_run_id=comparison_run_id,
    generated_at=generated_at_dt,
  )
  manifest = _build_manifest(
    options=options,
    comparison=comparison,
    comparison_run_id=comparison_run_id,
    output_dir=output_dir,
    generated_at=generated_at_dt,
  )
  write_comparison_outputs(output_dir=output_dir, comparison=comparison, manifest=manifest)
  return ConfirmationComparisonResult(
    comparison_run_id=comparison_run_id,
    output_dir=output_dir,
    manifest=manifest,
    comparison=comparison,
  )


def generate_comparison_run_id(*, generated_at: datetime | None = None) -> str:
  generated = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
  return _sanitize_run_id(f"confirmation_comparison_{generated.strftime('%Y%m%d_%H%M%S')}")


def _build_manifest(
  *,
  options: ConfirmationComparisonOptions,
  comparison: dict[str, Any],
  comparison_run_id: str,
  output_dir: Path,
  generated_at: datetime,
) -> dict[str, Any]:
  summary = comparison.get("summary") if isinstance(comparison.get("summary"), dict) else {}
  return {
    "schema_version": SCHEMA_VERSION,
    "comparison_run_id": comparison_run_id,
    "generated_at": _format_utc(generated_at),
    "run_dir": options.run_dir.resolve().as_posix(),
    "output_dir": output_dir.as_posix(),
    "input_confirmation_run_ids": list(options.confirmation_run_ids),
    "inputs": {
      "confirmation_runs": [
        {
          "confirmation_run_id": run.get("confirmation_run_id"),
          "manifest": run.get("manifest_path"),
          "confirmations": run.get("confirmations_path"),
        }
        for run in comparison.get("included_confirmation_runs", [])
        if isinstance(run, dict)
      ],
    },
    "outputs": {
      "manifest": "manifest.json",
      "comparison_markdown": "comparison.md",
      "comparison_json": "comparison.json",
    },
    "counts": {
      "confirmation_run_count": summary.get("confirmation_run_count", 0),
      "total_records": summary.get("total_records", 0),
      "unique_candidate_count": summary.get("unique_candidate_count", 0),
      "overlapping_candidate_count": summary.get("overlapping_candidate_count", 0),
    },
    "warnings_count": summary.get("warnings_count", 0),
    "generator": {
      "name": GENERATOR_NAME,
      "version": GENERATOR_VERSION,
    },
    "invocation": {
      "argv": list(options.argv),
      "cwd": str(options.cwd or Path.cwd()),
      "python_version": sys.version,
      "platform": platform.platform(),
    },
  }


def _validate_output_dir(output_dir: Path, *, run_dir: Path) -> None:
  forbidden = {
    run_dir.resolve(),
    (run_dir / "states").resolve(),
    (run_dir / "candidates").resolve(),
    (run_dir / "confirmations").resolve(),
    (run_dir / "reports").resolve(),
  }
  if output_dir in forbidden:
    raise ValueError(f"Refusing to write comparison output over core run artifact directory: {output_dir}")


def _sanitize_run_id(value: str) -> str:
  sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
  sanitized = sanitized.strip("._-")
  return sanitized or "comparison"


def _format_utc(value: datetime) -> str:
  return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
