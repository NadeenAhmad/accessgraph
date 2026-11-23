from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = "1"
GENERATOR_NAME = "local_confirmation_comparison"
GENERATOR_VERSION = "1"


@dataclass(frozen=True)
class ConfirmationComparisonOptions:
  run_dir: Path
  confirmation_run_ids: tuple[str, ...]
  comparison_run_id: str | None = None
  output_dir: Path | None = None
  overwrite: bool = False
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
class ConfirmationComparisonResult:
  comparison_run_id: str
  output_dir: Path
  manifest: dict[str, object]
  comparison: dict[str, object]
