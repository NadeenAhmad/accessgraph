from __future__ import annotations

import platform
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .builder import build_report_payload
from .models import (
  GENERATOR_NAME,
  GENERATOR_VERSION,
  SCHEMA_VERSION,
  ConfirmationReportOptions,
  ConfirmationReportResult,
)
from .reader import load_confirmation_run
from .writer import prepare_report_output_dir, report_hash, write_report_outputs


def run_confirmation_report(
  *,
  options: ConfirmationReportOptions,
  generated_at: datetime | None = None,
) -> ConfirmationReportResult:
  generated_at_dt = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
  loaded = load_confirmation_run(options.run_dir, options.confirmation_run_id)
  report_run_id = options.report_run_id or generate_report_run_id(
    confirmation_run_id=options.confirmation_run_id,
    generated_at=generated_at_dt,
  )
  output_dir = (options.output_dir or (loaded.run_dir / "reports" / report_run_id)).resolve()
  _validate_output_dir(output_dir, loaded_run_dir=loaded.run_dir, confirmation_dir=loaded.confirmation_dir)
  prepare_report_output_dir(output_dir, overwrite=options.overwrite)

  report = build_report_payload(
    loaded,
    options=options,
    report_run_id=report_run_id,
    generated_at=generated_at_dt,
  )
  manifest = _build_manifest(
    options=options,
    report=report,
    report_run_id=report_run_id,
    output_dir=output_dir,
    generated_at=generated_at_dt,
  )
  write_report_outputs(
    output_dir=output_dir,
    report=report,
    manifest=manifest,
    include_no_violation=options.include_no_violation,
  )
  return ConfirmationReportResult(
    report_run_id=report_run_id,
    output_dir=output_dir,
    manifest=manifest,
    report=report,
  )


def generate_report_run_id(*, confirmation_run_id: str, generated_at: datetime | None = None) -> str:
  generated = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
  timestamp = generated.strftime("%Y%m%d_%H%M%S")
  sanitized_confirmation = _sanitize_run_id(confirmation_run_id)
  return _sanitize_run_id(f"developer_report_{sanitized_confirmation}_{timestamp}")


def _build_manifest(
  *,
  options: ConfirmationReportOptions,
  report: dict[str, Any],
  report_run_id: str,
  output_dir: Path,
  generated_at: datetime,
) -> dict[str, Any]:
  source = report.get("source") if isinstance(report.get("source"), dict) else {}
  return {
    "schema_version": SCHEMA_VERSION,
    "report_run_id": report_run_id,
    "generated_at": _format_utc(generated_at),
    "run_dir": options.run_dir.resolve().as_posix(),
    "confirmation_run_id": source.get("confirmation_run_id"),
    "confirmation_dir": source.get("confirmation_dir"),
    "output_dir": output_dir.as_posix(),
    "source": source,
    "inputs": {
      "confirmation_manifest": source.get("confirmation_manifest"),
      "confirmations": source.get("confirmations_path"),
    },
    "outputs": {
      "manifest": "manifest.json",
      "report_markdown": "report.md",
      "report_html": "report.html",
      "report_json": "report.json",
    },
    "options": {
      "include_no_violation": options.include_no_violation,
      "load_source_candidates": options.load_source_candidates,
      "verify_artifacts": options.verify_artifacts,
    },
    "summary": report.get("summary"),
    "report_hash": report_hash(report),
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


def _sanitize_run_id(value: str) -> str:
  sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
  sanitized = sanitized.strip("._-")
  return sanitized or "report"


def _validate_output_dir(output_dir: Path, *, loaded_run_dir: Path, confirmation_dir: Path) -> None:
  forbidden = {
    loaded_run_dir.resolve(),
    (loaded_run_dir / "states").resolve(),
    (loaded_run_dir / "candidates").resolve(),
    (loaded_run_dir / "confirmations").resolve(),
    confirmation_dir.resolve(),
  }
  if output_dir in forbidden:
    raise ValueError(f"Refusing to write report output over core run artifact directory: {output_dir}")


def _format_utc(value: datetime) -> str:
  return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
