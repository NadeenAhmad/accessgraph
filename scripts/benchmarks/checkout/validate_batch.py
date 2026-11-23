from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(REPO_ROOT))

from src.analysis.evaluation.benchmark_registry import load_benchmark_registry  # noqa: E402
DEFAULT_RUNS_ROOT = REPO_ROOT / "runs" / "benchmark" / "checkout_flow"
BENCHMARK_REGISTRY = (
  REPO_ROOT
  / "benchmarks"

  / "registry"
  / "benchmark-case-registry.json"
)
STATIC_TEST = REPO_ROOT / "tests" / "test_checkout_benchmark_scaffolding.py"
RUNNER = REPO_ROOT / "scripts" / "benchmarks" / "checkout" / "runner.py"
SCORER = REPO_ROOT / "scripts" / "evaluation" / "score_seeded_experiment.py"
ACCESSGRAPH = REPO_ROOT / "accessgraph.py"
CHECKOUT_APP = "checkout-flow"


class ValidationError(Exception):
  """Expected validation failure with a contributor-facing message."""


class StageError(ValidationError):
  def __init__(
    self,
    stage: str,
    command: list[str],
    completed: subprocess.CompletedProcess[str],
  ) -> None:
    self.stage = stage
    self.command = command
    self.completed = completed
    super().__init__(f"{stage} failed with exit code {completed.returncode}.")


@dataclass(frozen=True)
class BatchSummary:
  profile: str
  python_executable: str
  run_dir: Path
  state_count: int
  transition_count: int
  candidate_count: int
  recovered_seeds: int
  expected_seeds: int


def build_static_validation_command() -> list[str]:
  return [
    sys.executable,
    "-m",
    "pytest",
    str(STATIC_TEST.relative_to(REPO_ROOT)),
    "-q",
  ]


def build_runner_command(
  *,
  profile: str,
  run_dir: Path,
  skip_build: bool,
) -> list[str]:
  command = [
    sys.executable,
    str(RUNNER.relative_to(REPO_ROOT)),
    "--profile",
    profile,
    "--run-dir",
    str(run_dir),
  ]
  if skip_build:
    command.append("--skip-build")
  return command


def build_candidate_command(*, run_dir: Path) -> list[str]:
  return [
    sys.executable,
    str(ACCESSGRAPH.relative_to(REPO_ROOT)),
    "candidates",
    "--run",
    str(run_dir),
  ]


def build_scorer_command(
  *,
  profile: str,
  run_dir: Path,
  score_run_id: str,
) -> list[str]:
  return [
    sys.executable,
    str(SCORER.relative_to(REPO_ROOT)),
    "--run-dir",
    str(run_dir),
    "--config-id",
    profile,
    "--registry",
    str(BENCHMARK_REGISTRY.relative_to(REPO_ROOT)),
    "--score-run-id",
    score_run_id,
  ]


def load_scoreable_profiles(registry_path: Path = BENCHMARK_REGISTRY) -> dict[str, dict[str, Any]]:
  registry = load_benchmark_registry(registry_path)
  configurations = registry.get("seeded_configurations")
  if not isinstance(configurations, list):
    raise ValidationError(f"Registry has no seeded_configurations list: {registry_path}")

  scoreable: dict[str, dict[str, Any]] = {}
  for configuration in configurations:
    if not isinstance(configuration, dict):
      continue
    config_id = str(configuration.get("configuration_id") or "")
    seed_ids = configuration.get("seed_ids")
    app = str(configuration.get("app") or "")
    if config_id and app == CHECKOUT_APP and isinstance(seed_ids, list) and seed_ids:
      scoreable[config_id] = configuration
  return scoreable


def validate_scoreable_profile(
  profile: str,
  registry_path: Path = BENCHMARK_REGISTRY,
) -> dict[str, Any]:
  scoreable = load_scoreable_profiles(registry_path)
  if profile in scoreable:
    return scoreable[profile]

  available = ", ".join(sorted(scoreable)) or "(none)"
  raise ValidationError(
    f"Profile {profile!r} is not a scoreable seeded batch in "
    f"{registry_path.relative_to(REPO_ROOT)}. Available scoreable profiles: {available}."
  )


def make_run_dir(profile: str, *, generated_at: datetime | None = None) -> Path:
  timestamp = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
  run_id = timestamp.strftime("run_%Y%m%dT%H%M%S%fZ")
  return DEFAULT_RUNS_ROOT / _profile_slug(profile) / run_id


def make_score_run_id(*, generated_at: datetime | None = None) -> str:
  timestamp = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
  return timestamp.strftime("validate_batch_%Y%m%dT%H%M%S%fZ")


def validate_batch(profile: str, *, skip_build: bool) -> BatchSummary:
  validate_scoreable_profile(profile)
  run_dir = make_run_dir(profile)
  score_run_id = make_score_run_id()

  print("Checkout benchmark batch validation")
  print(f"Profile: {profile}")
  print(f"Python: {sys.executable}")

  print("Static validation: RUN")
  _run_stage("Static validation", build_static_validation_command())
  print("Static validation: PASS")

  print("Acquisition: RUN")
  _run_stage(
    "Acquisition",
    build_runner_command(profile=profile, run_dir=run_dir, skip_build=skip_build),
  )
  run_metadata = _read_json(run_dir / "run_metadata.json")
  print("Acquisition: PASS")

  print("Candidate generation: RUN")
  _run_stage("Candidate generation", build_candidate_command(run_dir=run_dir))
  candidate_manifest = _read_json(run_dir / "candidates" / "manifest.json")
  print("Candidate generation: PASS")

  print("Seeded scoring: RUN")
  _run_stage(
    "Seeded scoring",
    build_scorer_command(
      profile=profile,
      run_dir=run_dir,
      score_run_id=score_run_id,
    ),
  )
  score_summary = _read_json(
    run_dir
    / "evaluation"
    / "seeded_recovery"
    / score_run_id
    / "seeded_recovery_summary.json"
  )
  print("Seeded scoring: PASS")

  counts = score_summary.get("counts") if isinstance(score_summary.get("counts"), dict) else {}
  recovered = _required_int(counts, "recovered_seeds")
  expected = _required_int(counts, "expected_seeds")
  if recovered != expected:
    raise ValidationError(
      f"Seeded scoring recovered {recovered}/{expected}; expected full recovery."
    )

  candidate_counts = (
    candidate_manifest.get("counts")
    if isinstance(candidate_manifest.get("counts"), dict)
    else {}
  )
  return BatchSummary(
    profile=profile,
    python_executable=sys.executable,
    run_dir=Path(str(run_metadata.get("run_dir") or run_dir)),
    state_count=_required_int(run_metadata, "state_count"),
    transition_count=_required_int(run_metadata, "transition_count"),
    candidate_count=_required_int(candidate_counts, "total_candidates"),
    recovered_seeds=recovered,
    expected_seeds=expected,
  )


def main(argv: list[str] | None = None) -> int:
  args = _parse_args(argv)
  try:
    summary = validate_batch(args.profile, skip_build=args.skip_build)
  except StageError as exc:
    print(f"{exc.stage}: FAIL", file=sys.stderr)
    _print_subprocess_output(exc.completed)
    print("Result: FAIL", file=sys.stderr)
    return 1
  except ValidationError as exc:
    print(str(exc), file=sys.stderr)
    print("Result: FAIL", file=sys.stderr)
    return 1

  print(f"Run: {summary.run_dir}")
  print(f"States/transitions: {summary.state_count} / {summary.transition_count}")
  print(f"Candidates: {summary.candidate_count}")
  print(f"Recovery: {summary.recovered_seeds}/{summary.expected_seeds}")
  print("Result: PASS")
  return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description=(
      "Validate a Checkout benchmark seeded batch by running static checks, "
      "focused acquisition, candidate generation, and seeded recovery scoring."
    ),
  )
  parser.add_argument(
    "--profile",
    required=True,
    help="Scoreable Checkout benchmark seeded batch profile/configuration id.",
  )
  parser.add_argument(
    "--skip-build",
    action="store_true",
    help="Pass --skip-build through to the Checkout benchmark runner.",
  )
  return parser.parse_args(argv)


def _run_stage(stage: str, command: list[str]) -> subprocess.CompletedProcess[str]:
  completed = subprocess.run(
    command,
    cwd=REPO_ROOT,
    text=True,
    capture_output=True,
    check=False,
  )
  if completed.returncode != 0:
    raise StageError(stage, command, completed)
  return completed


def _read_json(path: Path) -> dict[str, Any]:
  try:
    with path.open("r", encoding="utf-8") as handle:
      data = json.load(handle)
  except OSError as exc:
    raise ValidationError(f"Required output was not found or readable: {path}") from exc
  except json.JSONDecodeError as exc:
    raise ValidationError(f"Required output is not valid JSON: {path}") from exc
  if not isinstance(data, dict):
    raise ValidationError(f"Required output is not a JSON object: {path}")
  return data


def _required_int(data: dict[str, Any], key: str) -> int:
  value = data.get(key)
  if not isinstance(value, int):
    raise ValidationError(f"Required integer field {key!r} is missing from output.")
  return value


def _print_subprocess_output(completed: subprocess.CompletedProcess[str]) -> None:
  if completed.stdout:
    print("STDOUT:", file=sys.stderr)
    print(completed.stdout, file=sys.stderr)
  if completed.stderr:
    print("STDERR:", file=sys.stderr)
    print(completed.stderr, file=sys.stderr)


def _profile_slug(profile: str) -> str:
  return "".join(character if character.isalnum() else "_" for character in profile).strip("_")


if __name__ == "__main__":
  raise SystemExit(main())
