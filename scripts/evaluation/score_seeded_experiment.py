from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(REPO_ROOT))

from src.analysis.evaluation.seeded_scorer import (  # noqa: E402
  DEFAULT_REGISTRY_PATH,
  SeededScorerOptions,
  score_seeded_experiment,
)


def main(argv: list[str] | None = None) -> int:
  parser = _build_parser()
  args = parser.parse_args(argv)
  options = SeededScorerOptions(
    run_dir=args.run_dir,
    config_id=args.config_id,
    registry_path=args.registry,
    candidates_path=args.candidates,
    output_dir=args.output_dir,
    score_run_id=args.score_run_id,
    overwrite=args.overwrite,
    argv=tuple(sys.argv if argv is None else ["scripts/evaluation/score_seeded_experiment.py", *argv]),
    cwd=Path.cwd(),
  )

  try:
    result = score_seeded_experiment(options)
  except Exception as exc:
    print(f"seeded experiment scoring failed: {exc}", file=sys.stderr)
    return 1

  counts = result.summary["counts"]
  rates = result.summary["rates"]
  print(
    "Seeded experiment scoring complete: "
    f"{counts['recovered_seeds']} of {counts['expected_seeds']} expected seeds recovered "
    f"to candidate level in {result.output_dir}"
  )
  print(f"Candidate recovery rate: {rates['candidate_recovery_rate']:.3f}")
  print(f"Score run id: {result.score_run_id}")
  return 0


def _build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description=(
      "Score private seeded benchmark expectations against existing AccessGraph "
      "run artifacts and semantic candidates."
    ),
  )
  parser.add_argument(
    "--run-dir",
    type=Path,
    required=True,
    help="Completed normalized run directory containing states/ and candidates/.",
  )
  parser.add_argument(
    "--config-id",
    required=True,
    help="Seeded configuration id, for example checkout-pilot-001.",
  )
  parser.add_argument(
    "--registry",
    type=Path,
    default=DEFAULT_REGISTRY_PATH,
    help="Private seed expectation registry JSON path.",
  )
  parser.add_argument(
    "--candidates",
    type=Path,
    default=None,
    help="Candidate JSONL path. Defaults to <run-dir>/candidates/candidates.jsonl.",
  )
  parser.add_argument(
    "--output-dir",
    type=Path,
    default=None,
    help=(
      "Optional explicit output directory. Defaults to "
      "<run-dir>/evaluation/seeded_recovery/<score_run_id>."
    ),
  )
  parser.add_argument(
    "--score-run-id",
    default=None,
    help="Explicit score run id. Defaults to a timestamped id.",
  )
  parser.add_argument(
    "--overwrite",
    action="store_true",
    help="Replace an existing scorer output directory.",
  )
  return parser


if __name__ == "__main__":
  raise SystemExit(main())
