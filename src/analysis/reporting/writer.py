from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from src.analysis.confirmation.hashing import stable_json_dumps

from .html import render_html_report
from .markdown import render_markdown_report


def prepare_report_output_dir(output_dir: Path, *, overwrite: bool = False) -> None:
  if output_dir.exists():
    if not overwrite:
      raise FileExistsError(
        f"Report output directory already exists: {output_dir}. Use --overwrite to replace it."
      )
    if not output_dir.is_dir():
      raise FileExistsError(f"Report output path exists and is not a directory: {output_dir}")
    shutil.rmtree(output_dir)
  output_dir.mkdir(parents=True)


def write_report_outputs(
  *,
  output_dir: Path,
  report: dict[str, Any],
  manifest: dict[str, Any],
  include_no_violation: bool,
) -> None:
  markdown = render_markdown_report(
    report,
    report_dir=output_dir,
    include_no_violation=include_no_violation,
  )
  (output_dir / "report.md").write_text(markdown, encoding="utf-8")
  html = render_html_report(
    report,
    report_dir=output_dir,
    include_no_violation=include_no_violation,
  )
  (output_dir / "report.html").write_text(html, encoding="utf-8")
  (output_dir / "report.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
    encoding="utf-8",
  )
  (output_dir / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
    encoding="utf-8",
  )


def report_hash(report: dict[str, Any]) -> str:
  from src.analysis.confirmation.hashing import sha256_hex

  return sha256_hex(stable_json_dumps(report))
