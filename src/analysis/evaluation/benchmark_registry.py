from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


DEFAULT_REGISTRY_PATH = Path("benchmarks/registry/benchmark-case-registry.json")
FAMILY_FILES_KEY = "family_files"
SEEDED_CONFIGURATIONS_KEY = "seeded_configurations"
EXPLICIT_SEEDED_CONFIGURATIONS_KEY = "explicit_seeded_configurations"
CASE_ID_PATTERN = re.compile(r"^(?P<prefix>[a-z]+-[a-z]+)-(?P<number>\d+)$")


def load_benchmark_registry(path: Path | str = DEFAULT_REGISTRY_PATH) -> dict[str, Any]:
  """Load the benchmark registry, assembling family-file storage when present."""
  registry_path = Path(path)
  payload = _read_json_object(registry_path)
  family_files = payload.get(FAMILY_FILES_KEY)
  if family_files is None:
    variant_ids = _validate_variants_if_present(payload, registry_path)
    _validate_seeded_configurations(payload, registry_path, variant_ids=variant_ids)
    return payload

  variants = _load_family_variants(
    registry_path=registry_path,
    family_files=_validate_family_files(family_files, registry_path),
  )
  variant_ids = {str(variant["variant_id"]) for variant in variants}
  if EXPLICIT_SEEDED_CONFIGURATIONS_KEY not in payload:
    _validate_seeded_configurations(payload, registry_path, variant_ids=variant_ids)
    return _compatibility_registry(
      payload,
      variants,
      seeded_configurations=payload.get(SEEDED_CONFIGURATIONS_KEY),
    )

  explicit_configurations = _validate_explicit_seeded_configurations(
    payload,
    registry_path,
    variant_ids=variant_ids,
  )
  seeded_configurations = _assemble_seeded_configurations(variants, explicit_configurations)
  return _compatibility_registry(payload, variants, seeded_configurations=seeded_configurations)


def _read_json_object(path: Path) -> dict[str, Any]:
  if not path.exists() or not path.is_file():
    raise FileNotFoundError(f"Benchmark registry not found: {path}")
  data = json.loads(path.read_text(encoding="utf-8"))
  if not isinstance(data, dict):
    raise ValueError(f"Benchmark registry root must be a JSON object: {path}")
  return data


def _validate_family_files(value: object, registry_path: Path) -> tuple[str, ...]:
  if not isinstance(value, list):
    raise ValueError(f"Registry family_files must be a list: {registry_path}")
  family_files: list[str] = []
  for index, item in enumerate(value):
    if not isinstance(item, str) or not item:
      raise ValueError(
        f"Registry family_files[{index}] must be a non-empty string: {registry_path}"
      )
    family_files.append(item)
  if not family_files:
    raise ValueError(f"Registry family_files must not be empty: {registry_path}")
  return tuple(family_files)


def _load_family_variants(*, registry_path: Path, family_files: tuple[str, ...]) -> list[dict[str, Any]]:
  variants: list[dict[str, Any]] = []
  seen_variant_ids: set[str] = set()
  for family_file in family_files:
    family_path = registry_path.parent / family_file
    family = _read_json_object(family_path)
    candidate_type = family.get("candidate_type")
    if not isinstance(candidate_type, str) or not candidate_type:
      raise ValueError(f"Registry family is missing candidate_type: {family_path}")
    raw_variants = family.get("variants")
    if not isinstance(raw_variants, list):
      raise ValueError(f"Registry family variants must be a list: {family_path}")
    for index, variant in enumerate(raw_variants):
      if not isinstance(variant, dict):
        raise ValueError(f"Registry family variant must be an object: {family_path}:{index}")
      variant_id = variant.get("variant_id")
      if not isinstance(variant_id, str) or not variant_id:
        raise ValueError(f"Registry family variant is missing variant_id: {family_path}:{index}")
      variant_candidate_type = variant.get("candidate_type")
      if variant_candidate_type != candidate_type:
        raise ValueError(
          "Registry family candidate_type mismatch for "
          f"{variant_id}: {family_path} declares {candidate_type!r}, "
          f"variant uses {variant_candidate_type!r}"
        )
      if variant_id in seen_variant_ids:
        raise ValueError(f"Duplicate registry variant_id {variant_id!r}: {family_path}")
      seen_variant_ids.add(variant_id)
      variants.append(variant)
  return sorted(variants, key=_variant_order_key)


def _variant_order_key(variant: dict[str, Any]) -> tuple[str, int, str]:
  variant_id = str(variant.get("variant_id") or "")
  match = CASE_ID_PATTERN.match(variant_id)
  if match is None:
    return (variant_id, -1, variant_id)
  return (match.group("prefix"), int(match.group("number")), variant_id)


def _validate_variants_if_present(payload: dict[str, Any], path: Path) -> set[str] | None:
  raw_variants = payload.get("variants")
  if raw_variants is None:
    return None
  if not isinstance(raw_variants, list):
    raise ValueError(f"Registry variants must be a list: {path}")
  variant_ids: set[str] = set()
  for index, variant in enumerate(raw_variants):
    if not isinstance(variant, dict):
      raise ValueError(f"Registry variant must be an object: {path}:{index}")
    variant_id = variant.get("variant_id")
    if not isinstance(variant_id, str) or not variant_id:
      raise ValueError(f"Registry variant is missing variant_id: {path}:{index}")
    if variant_id in variant_ids:
      raise ValueError(f"Duplicate registry variant_id {variant_id!r}: {path}")
    variant_ids.add(variant_id)
  return variant_ids


def _validate_seeded_configurations(
  payload: dict[str, Any],
  path: Path,
  *,
  variant_ids: set[str] | None,
) -> list[dict[str, Any]]:
  raw_configurations = payload.get(SEEDED_CONFIGURATIONS_KEY)
  if raw_configurations is None:
    return []
  if not isinstance(raw_configurations, list):
    raise ValueError(f"Registry seeded_configurations must be a list: {path}")
  return _validate_configuration_list(raw_configurations, path, variant_ids=variant_ids)


def _validate_explicit_seeded_configurations(
  payload: dict[str, Any],
  path: Path,
  *,
  variant_ids: set[str],
) -> list[dict[str, Any]]:
  if SEEDED_CONFIGURATIONS_KEY in payload:
    raise ValueError(
      "Registry with explicit seeded configurations must not also define "
      f"{SEEDED_CONFIGURATIONS_KEY!r}: {path}"
    )
  raw_configurations = payload.get(EXPLICIT_SEEDED_CONFIGURATIONS_KEY)
  if not isinstance(raw_configurations, list):
    raise ValueError(f"Registry explicit_seeded_configurations must be a list: {path}")
  return _validate_configuration_list(raw_configurations, path, variant_ids=variant_ids)


def _validate_configuration_list(
  raw_configurations: list[object],
  path: Path,
  *,
  variant_ids: set[str] | None,
) -> list[dict[str, Any]]:
  configuration_ids: set[str] = set()
  claimed_seed_ids: set[str] = set()
  configurations: list[dict[str, Any]] = []
  for index, configuration in enumerate(raw_configurations):
    if not isinstance(configuration, dict):
      raise ValueError(f"Registry seeded configuration must be an object: {path}:{index}")
    configuration_id = configuration.get("configuration_id")
    if not isinstance(configuration_id, str) or not configuration_id:
      raise ValueError(f"Registry seeded configuration is missing configuration_id: {path}:{index}")
    if configuration_id in configuration_ids:
      raise ValueError(f"Duplicate registry configuration_id {configuration_id!r}: {path}")
    configuration_ids.add(configuration_id)
    seed_ids = configuration.get("seed_ids")
    if not isinstance(seed_ids, list) or not seed_ids:
      raise ValueError(f"Registry seeded configuration has no seed_ids: {configuration_id}")
    if variant_ids is not None:
      missing = [str(seed_id) for seed_id in seed_ids if str(seed_id) not in variant_ids]
      if missing:
        raise ValueError(
          f"Registry seeded configuration {configuration_id!r} references unknown seed ids: "
          f"{', '.join(missing)}"
        )
    overlapping = [str(seed_id) for seed_id in seed_ids if str(seed_id) in claimed_seed_ids]
    if overlapping:
      raise ValueError(
        f"Registry seeded configuration {configuration_id!r} claims already-owned seed ids: "
        f"{', '.join(overlapping)}"
      )
    claimed_seed_ids.update(str(seed_id) for seed_id in seed_ids)
    configurations.append(configuration)
  return configurations


def _assemble_seeded_configurations(
  variants: list[dict[str, Any]],
  explicit_configurations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
  explicit_by_seed_id: dict[str, dict[str, Any]] = {}
  for configuration in explicit_configurations:
    for seed_id in configuration["seed_ids"]:
      explicit_by_seed_id[str(seed_id)] = configuration

  explicit_configuration_ids = {
    str(configuration["configuration_id"])
    for configuration in explicit_configurations
  }
  seeded_configurations: list[dict[str, Any]] = []
  emitted_explicit_ids: set[str] = set()

  for variant in variants:
    variant_id = str(variant["variant_id"])
    explicit_configuration = explicit_by_seed_id.get(variant_id)
    if explicit_configuration is not None:
      configuration_id = str(explicit_configuration["configuration_id"])
      if configuration_id not in emitted_explicit_ids:
        seeded_configurations.append(explicit_configuration)
        emitted_explicit_ids.add(configuration_id)
      continue

    configuration = _build_normal_seeded_configuration(variant)
    configuration_id = str(configuration["configuration_id"])
    if configuration_id in explicit_configuration_ids:
      raise ValueError(f"Synthesized registry configuration_id collides with explicit config: {configuration_id}")
    seeded_configurations.append(configuration)

  return seeded_configurations


def _build_normal_seeded_configuration(variant: dict[str, Any]) -> dict[str, Any]:
  variant_id = str(variant["variant_id"])
  return {
    "desired_activation": "benchmark_runner_profile",
    "current_activation_status": "focused_runner_runtime_profile_injection_supported",
    "description": f"Single-case profile for implemented dataset case {variant_id}.",
    "configuration_id": variant["profile"],
    "baseline_configuration": "clean",
    "individual_seed_activation_role": "debugging_and_focused_validation",
    "seed_ids": [
      variant_id,
    ],
    "intended_use": "implemented_dataset_case_not_accepted",
    "preserves_workflow_routes": True,
    "app": variant["app"],
    "status": "implemented",
    "planned_seed_count": 1,
  }


def _compatibility_registry(
  manifest: dict[str, Any],
  variants: list[dict[str, Any]],
  *,
  seeded_configurations: list[dict[str, Any]] | None,
) -> dict[str, Any]:
  registry: dict[str, Any] = {"variants": variants}
  for key in ("description", "schema_version", "benchmark_generation"):
    if key in manifest:
      registry[key] = manifest[key]
  if seeded_configurations is not None:
    registry[SEEDED_CONFIGURATIONS_KEY] = seeded_configurations
  if "notes" in manifest:
    registry["notes"] = manifest["notes"]
  return registry
