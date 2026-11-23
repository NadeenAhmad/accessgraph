from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .markdown import render_comparison_markdown


def prepare_comparison_output_dir(output_dir: Path, *, overwrite: bool = False) -> None:
  if output_dir.exists():
    if not overwrite:
      raise FileExistsError(
        f"Comparison output directory already exists: {output_dir}. Use --overwrite to replace it."
      )
    if not output_dir.is_dir():
      raise FileExistsError(f"Comparison output path exists and is not a directory: {output_dir}")
    shutil.rmtree(output_dir)
  output_dir.mkdir(parents=True)


def write_comparison_outputs(
  *,
  output_dir: Path,
  comparison: dict[str, Any],
  manifest: dict[str, Any],
) -> None:
  (output_dir / "comparison.md").write_text(render_comparison_markdown(comparison), encoding="utf-8")
  (output_dir / "comparison.json").write_text(
    json.dumps(comparison, ensure_ascii=False, indent=2, sort_keys=True),
    encoding="utf-8",
  )
  (output_dir / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
    encoding="utf-8",
  )
