from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(REPO_ROOT))

from src.analysis.evaluation.models import ConfirmationComparisonOptions
from src.analysis.evaluation.runner import run_confirmation_comparison


def main(argv: list[str] | None = None) -> int:
  parser = _build_parser()
  args = parser.parse_args(argv)
  options = ConfirmationComparisonOptions(
    run_dir=args.run_dir,
    confirmation_run_ids=tuple(args.confirmation_run_ids),
    comparison_run_id=args.comparison_run_id,
    output_dir=args.output_dir,
    overwrite=args.overwrite,
    argv=tuple(sys.argv if argv is None else ["scripts/evaluation/compare_confirmation_runs.py", *argv]),
    cwd=Path.cwd(),
  )

  try:
    result = run_confirmation_comparison(options=options)
  except Exception as exc:
    print(f"confirmation comparison failed: {exc}", file=sys.stderr)
    return 1

  summary = result.comparison["summary"]
  print(
    "Confirmation comparison complete: "
    f"{summary['confirmation_run_count']} runs and {summary['total_records']} records summarized in {result.output_dir}"
  )
  print(f"Comparison run id: {result.comparison_run_id}")
  return 0


def _build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description="Compare existing local confirmation runs descriptively without labels or accuracy metrics.",
  )
  parser.add_argument(
    "--run-dir",
    type=Path,
    required=True,
    help="Completed run directory containing confirmations/<confirmation_run_id> folders.",
  )
  parser.add_argument(
    "--confirmation-run-id",
    action="append",
    dest="confirmation_run_ids",
    required=True,
    help="Confirmation run id to include. Repeat for multiple runs.",
  )
  parser.add_argument(
    "--comparison-run-id",
    default=None,
    help="Explicit comparison run id. Defaults to a timestamped id.",
  )
  parser.add_argument(
    "--output-dir",
    type=Path,
    default=None,
    help="Optional explicit output directory. Defaults to runs/<run_id>/comparisons/<comparison_run_id>.",
  )
  parser.add_argument(
    "--overwrite",
    action="store_true",
    help="Replace an existing comparison output directory.",
  )
  return parser


if __name__ == "__main__":
  raise SystemExit(main())
