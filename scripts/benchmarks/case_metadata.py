from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.analysis.evaluation.benchmark_registry import load_benchmark_registry


REPO_ROOT = Path(__file__).resolve().parents[2]
CASE_TRACKER = REPO_ROOT / "benchmarks" / "case-tracker.csv"
BENCHMARK_REGISTRY = (
  REPO_ROOT / "benchmarks" / "registry" / "benchmark-case-registry.json"
)

LAUNCHABLE_STATUSES = frozenset({"implemented", "accepted"})
TRACKER_APP_TO_REGISTRY_APP = {
  "checkout": "checkout-flow",
}

TRACKER_FIELDS = (
  "case_id",
  "violation_type",
  "app",
  "short_description",
  "pattern",
  "tier",
  "baseline",
  "mutation",
  "why_unambiguous",
  "interaction_path",
  "evidence_state",
  "status",
  "notes",
)


class CaseMetadataError(Exception):
  """Base error for expected benchmark metadata issues."""


class UnknownBenchmarkCaseError(CaseMetadataError):
  def __init__(self, case_id: str, available_case_ids: list[str]) -> None:
    self.case_id = case_id
    self.available_case_ids = available_case_ids
    super().__init__(f"Unknown benchmark case: {case_id}")


class CaseConfigurationError(CaseMetadataError):
  """Raised when tracker and registry metadata disagree."""


@dataclass(frozen=True)
class ExecutableConfiguration:
  configuration_id: str
  app: str
  seed_ids: tuple[str, ...]
  status: str


@dataclass(frozen=True)
class BenchmarkCase:
  case_id: str
  violation_type: str
  app: str
  status: str
  short_description: str
  pattern: str
  tier: str
  baseline: str
  mutation: str
  why_unambiguous: str
  interaction_path: str
  evidence_state: str
  notes: str
  executable_configuration: ExecutableConfiguration | None = None
  expected_routes: tuple[str, ...] = ()

  @property
  def executable_profile(self) -> str | None:
    if self.executable_configuration is None:
      return None
    return self.executable_configuration.configuration_id

  @property
  def registry_app(self) -> str | None:
    if self.executable_configuration is None:
      return None
    return self.executable_configuration.app

  @property
  def is_launchable(self) -> bool:
    return (
      self.status in LAUNCHABLE_STATUSES
      and self.executable_configuration is not None
    )


def resolve_case(
  case_id: str,
  *,
  tracker_path: Path = CASE_TRACKER,
  registry_path: Path = BENCHMARK_REGISTRY,
) -> BenchmarkCase:
  tracker_rows = load_tracker_cases(tracker_path)
  row = tracker_rows.get(case_id)
  if row is None:
    raise UnknownBenchmarkCaseError(case_id, sorted(tracker_rows))

  configurations = load_executable_configurations(registry_path)
  expected_routes = load_expected_case_routes(registry_path)
  executable_configuration = configurations.get(case_id)
  if executable_configuration is not None:
    _validate_tracker_registry_consistency(
      case_id=case_id,
      tracker_app=row["app"],
      executable_configuration=executable_configuration,
    )

  return BenchmarkCase(
    case_id=row["case_id"],
    violation_type=row["violation_type"],
    app=row["app"],
    status=row["status"],
    short_description=row["short_description"],
    pattern=row["pattern"],
    tier=row["tier"],
    baseline=row["baseline"],
    mutation=row["mutation"],
    why_unambiguous=row["why_unambiguous"],
    interaction_path=row["interaction_path"],
    evidence_state=row["evidence_state"],
    notes=row["notes"],
    executable_configuration=executable_configuration,
    expected_routes=expected_routes.get(case_id, ()),
  )


def load_tracker_cases(path: Path = CASE_TRACKER) -> dict[str, dict[str, str]]:
  with path.open("r", encoding="utf-8", newline="") as handle:
    reader = csv.DictReader(handle)
    fieldnames = set(reader.fieldnames or [])
    missing = [field for field in TRACKER_FIELDS if field not in fieldnames]
    if missing:
      raise CaseMetadataError(
        f"Tracker is missing required columns in {path}: {', '.join(missing)}"
      )

    rows: dict[str, dict[str, str]] = {}
    for row in reader:
      case_id = (row.get("case_id") or "").strip()
      if not case_id:
        raise CaseMetadataError(f"Tracker row without case_id in {path}")
      if case_id in rows:
        raise CaseMetadataError(f"Duplicate benchmark case ID in tracker: {case_id}")
      rows[case_id] = {
        field: (row.get(field) or "").strip()
        for field in TRACKER_FIELDS
      }
  return rows


def load_executable_configurations(
  path: Path = BENCHMARK_REGISTRY,
) -> dict[str, ExecutableConfiguration]:
  registry = _read_registry(path)
  configurations = registry.get("seeded_configurations")
  if not isinstance(configurations, list):
    raise CaseMetadataError(f"Registry has no seeded_configurations list: {path}")

  by_case_id: dict[str, ExecutableConfiguration] = {}
  for raw_configuration in configurations:
    if not isinstance(raw_configuration, dict):
      continue
    configuration = _parse_configuration(raw_configuration)
    for seed_id in configuration.seed_ids:
      existing = by_case_id.get(seed_id)
      if existing is not None:
        raise CaseConfigurationError(
          "Multiple registry seeded configurations include "
          f"{seed_id}: {existing.configuration_id}, "
          f"{configuration.configuration_id}"
        )
      by_case_id[seed_id] = configuration
  return by_case_id


def load_expected_case_routes(
  path: Path = BENCHMARK_REGISTRY,
) -> dict[str, tuple[str, ...]]:
  registry = _read_registry(path)
  variants = registry.get("variants")
  if not isinstance(variants, list):
    return {}

  routes_by_case_id: dict[str, tuple[str, ...]] = {}
  for raw_variant in variants:
    if not isinstance(raw_variant, dict):
      continue
    case_id = raw_variant.get("variant_id")
    expected_state = raw_variant.get("expected_state")
    if not isinstance(case_id, str) or not isinstance(expected_state, dict):
      continue
    raw_routes = expected_state.get("routes")
    if not isinstance(raw_routes, list):
      continue
    routes = tuple(
      route for route in raw_routes
      if isinstance(route, str) and route.startswith("/")
    )
    if routes:
      routes_by_case_id[case_id] = routes
  return routes_by_case_id


def _parse_configuration(data: dict[str, Any]) -> ExecutableConfiguration:
  configuration_id = data.get("configuration_id")
  app = data.get("app")
  seed_ids = data.get("seed_ids")
  status = data.get("status")
  if (
    not isinstance(configuration_id, str)
    or not configuration_id
    or not isinstance(app, str)
    or not app
    or not isinstance(seed_ids, list)
  ):
    raise CaseConfigurationError(
      "Registry seeded configuration is missing configuration_id, app, or seed_ids."
    )
  parsed_seed_ids = tuple(str(seed_id) for seed_id in seed_ids if str(seed_id))
  if not parsed_seed_ids:
    raise CaseConfigurationError(
      f"Registry seeded configuration {configuration_id!r} has no seed_ids."
    )
  return ExecutableConfiguration(
    configuration_id=configuration_id,
    app=app,
    seed_ids=parsed_seed_ids,
    status=str(status or ""),
  )


def _read_registry(path: Path) -> dict[str, Any]:
  try:
    return load_benchmark_registry(path)
  except (OSError, ValueError) as exc:
    raise CaseMetadataError(f"Registry could not be loaded: {path}") from exc


def _validate_tracker_registry_consistency(
  *,
  case_id: str,
  tracker_app: str,
  executable_configuration: ExecutableConfiguration,
) -> None:
  expected_registry_app = TRACKER_APP_TO_REGISTRY_APP.get(tracker_app, tracker_app)
  if executable_configuration.app != expected_registry_app:
    raise CaseConfigurationError(
      f"Case {case_id} tracker app {tracker_app!r} maps to "
      f"{expected_registry_app!r}, but registry configuration "
      f"{executable_configuration.configuration_id!r} uses "
      f"{executable_configuration.app!r}."
    )
