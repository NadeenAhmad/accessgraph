from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.benchmarks.checkout import validate_batch


def test_scoreable_profiles_come_from_benchmark_registry():
  profiles = validate_batch.load_scoreable_profiles()

  removed_profiles = {22, 25, 26, 30, 33, 34, 39, 40, 43, 46}
  expected_profiles = {
    "checkout-pilot-001",
    *(
      f"checkout-co-sem-{case_number:03d}"
      for case_number in range(6, 48)
      if case_number not in removed_profiles
    ),
    "checkout-co-sem-052",
    "checkout-co-sem-053",
    "checkout-co-sem-054",
    "checkout-co-sem-055",
    "checkout-co-sem-056",
    "checkout-co-sem-058",
    "checkout-co-sem-059",
    "checkout-co-sem-060",
    "checkout-co-sem-061",
    "checkout-co-sem-062",
    "checkout-co-sem-063",
    "checkout-co-sem-064",
    "checkout-co-sem-065",
    "checkout-co-sem-066",
    "checkout-co-sem-067",
    "checkout-co-sem-068",
    "checkout-co-sem-069",
    "checkout-co-sem-070",
    "checkout-co-sem-071",
    "checkout-co-sem-072",
    "checkout-co-sem-073",
    "checkout-co-sem-074",
    "checkout-co-sem-075",
    "checkout-co-sem-076",
    "checkout-co-sem-077",
    "checkout-co-sem-078",
    "checkout-co-sem-079",
    "checkout-co-sem-080",
    "checkout-co-sem-081",
    "checkout-co-sem-086",
    "checkout-co-sem-087",
    "checkout-co-sem-088",
    "checkout-co-sem-089",
    "checkout-co-sem-090",
    "checkout-co-sem-091",
    "checkout-co-sem-092",
    "checkout-co-sem-093",
    "checkout-co-sem-094",
    "checkout-co-sem-095",
    "checkout-co-sem-097",
    "checkout-co-sem-100",
    "checkout-co-sem-101",
    "checkout-co-sem-102",
    "checkout-co-sem-103",
    "checkout-co-sem-104",
    "checkout-co-sem-107",
    "checkout-co-sem-108",
    "checkout-co-sem-109",
    "checkout-co-sem-110",
    "checkout-co-sem-111",
    "checkout-co-sem-112",
    "checkout-co-sem-113",
    "checkout-co-sem-114",
    "checkout-co-sem-116",
    "checkout-co-sem-117",
    "checkout-co-sem-118",
    "checkout-co-sem-119",
    "checkout-co-sem-120",
    "checkout-co-sem-121",
    "checkout-co-sem-122",
    "checkout-co-sem-123",
    "checkout-co-sem-124",
    "checkout-co-sem-125",
    "checkout-co-sem-126",
    "checkout-co-sem-127",
    "checkout-co-sem-128",
    "checkout-co-sem-129",
    "checkout-co-sem-130",
    "checkout-co-sem-131",
    "checkout-co-sem-132",
    "checkout-co-sem-134",
    "checkout-co-sem-135",
    "checkout-co-sem-136",
    "checkout-co-sem-137",
    "checkout-co-sem-138",
    "checkout-co-sem-139",
  }
  assert set(profiles) == expected_profiles
  assert "checkout-clean-v1" not in profiles


def test_clean_and_unknown_profiles_are_rejected():
  for profile in ("checkout-clean-v1", "checkout-unknown-profile"):
    with pytest.raises(validate_batch.ValidationError, match="not a scoreable seeded batch"):
      validate_batch.validate_scoreable_profile(profile)


def test_child_python_commands_use_current_interpreter():
  run_dir = Path("runs/example")
  commands = [
    validate_batch.build_static_validation_command(),
    validate_batch.build_runner_command(
      profile="checkout-pilot-001",
      run_dir=run_dir,
      skip_build=True,
    ),
    validate_batch.build_candidate_command(run_dir=run_dir),
    validate_batch.build_scorer_command(
      profile="checkout-pilot-001",
      run_dir=run_dir,
      score_run_id="score-example",
    ),
  ]

  for command in commands:
    assert command[0] == sys.executable
    assert command[0] != "python"


def test_runner_command_targets_exact_run_directory():
  run_dir = Path("runs/benchmark/checkout_flow/example/run_1")
  command = validate_batch.build_runner_command(
    profile="checkout-pilot-001",
    run_dir=run_dir,
    skip_build=True,
  )

  assert command[:2] == [
    sys.executable,
    str(validate_batch.RUNNER.relative_to(validate_batch.REPO_ROOT)),
  ]
  assert "--profile" in command
  assert command[command.index("--profile") + 1] == "checkout-pilot-001"
  assert "--run-dir" in command
  assert command[command.index("--run-dir") + 1] == str(run_dir)
  assert "--skip-build" in command


def test_run_dir_and_score_id_are_timestamped_and_profile_scoped():
  generated_at = datetime(2026, 8, 20, 18, 50, 30, 123456, tzinfo=timezone.utc)

  run_dir = validate_batch.make_run_dir(
    "checkout-pilot-001",
    generated_at=generated_at,
  )
  score_run_id = validate_batch.make_score_run_id(generated_at=generated_at)

  assert run_dir.as_posix().endswith(
    "checkout_pilot_001/run_20260820T185030123456Z"
  )
  assert score_run_id == "validate_batch_20260820T185030123456Z"
