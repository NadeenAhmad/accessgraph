from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = "1"
GENERATOR_NAME = "developer_confirmation_report"
GENERATOR_VERSION = "1"


@dataclass(frozen=True)
class ConfirmationReportOptions:
  run_dir: Path
  confirmation_run_id: str
  report_run_id: str | None = None
  output_dir: Path | None = None
  include_no_violation: bool = False
  overwrite: bool = False
  load_source_candidates: bool = True
  verify_artifacts: bool = True
  argv: tuple[str, ...] = ()
  cwd: Path | None = None


@dataclass(frozen=True)
class LoadedConfirmationRun:
  run_dir: Path
  confirmation_run_id: str
  confirmation_dir: Path
  manifest_path: Path
  confirmations_path: Path
  manifest: dict[str, object]
  records: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class ConfirmationReportResult:
  report_run_id: str
  output_dir: Path
  manifest: dict[str, object]
  report: dict[str, object]
