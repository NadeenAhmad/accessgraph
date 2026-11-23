from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hashing import candidate_record_hash, sha256_hex, short_hash, stable_json_dumps
from .models import (
  CONFIDENCE_SEMANTICS,
  CONFIRMATION_SCHEMA_VERSION,
  GENERATOR_NAME,
  GENERATOR_VERSION,
  ConfirmationPrompt,
  ConfirmationProviderResponse,
  ParsedConfirmation,
)


@dataclass(frozen=True)
class ConfirmationOutputLayout:
  output_dir: Path
  manifest_path: Path
  confirmations_path: Path
  attempts_path: Path
  by_type_dir: Path
  prompts_dir: Path
  raw_responses_dir: Path


def confirmation_output_layout(output_dir: Path) -> ConfirmationOutputLayout:
  return ConfirmationOutputLayout(
    output_dir=output_dir,
    manifest_path=output_dir / "manifest.json",
    confirmations_path=output_dir / "confirmations.jsonl",
    attempts_path=output_dir / "confirmation_attempts.jsonl",
    by_type_dir=output_dir / "by_type",
    prompts_dir=output_dir / "prompts",
    raw_responses_dir=output_dir / "raw_responses",
  )


def prepare_confirmation_output_dir(
  output_dir: Path,
  *,
  overwrite: bool = False,
  save_prompts: bool = False,
  save_raw_responses: bool = False,
) -> ConfirmationOutputLayout:
  layout = confirmation_output_layout(output_dir)
  if layout.output_dir.exists():
    if not overwrite:
      raise FileExistsError(
        f"Confirmation output directory already exists: {layout.output_dir}. "
        "Use --overwrite to replace it."
      )
    if not layout.output_dir.is_dir():
      raise FileExistsError(f"Confirmation output path exists and is not a directory: {layout.output_dir}")
    shutil.rmtree(layout.output_dir)

  layout.by_type_dir.mkdir(parents=True)
  if save_prompts:
    layout.prompts_dir.mkdir(parents=True)
  if save_raw_responses:
    layout.raw_responses_dir.mkdir(parents=True)
  return layout


def build_confirmation_id(
  *,
  candidate_id: str,
  prompt_version: str,
  provider: str,
  model: str,
  config_hash: str,
) -> str:
  payload = {
    "candidate_id": candidate_id,
    "prompt_version": prompt_version,
    "provider": provider,
    "model": model,
    "config_hash": config_hash,
  }
  return f"confirmation_{short_hash(stable_json_dumps(payload), length=16)}"


def build_confirmation_record(
  *,
  confirmation_id: str,
  confirmation_run_id: str,
  prompt: ConfirmationPrompt,
  response: ConfirmationProviderResponse,
  parsed: ParsedConfirmation,
  config_hash: str,
  created_at: str,
  escalation_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
  bundle = prompt.bundle
  provider_metadata = response.provider_metadata if isinstance(response.provider_metadata, dict) else {}
  record = {
    "schema_version": CONFIRMATION_SCHEMA_VERSION,
    "confirmation_id": confirmation_id,
    "confirmation_run_id": confirmation_run_id,
    "candidate_id": parsed.candidate_id,
    "candidate_type": parsed.candidate_type,
    "state_id": parsed.state_id,
    "decision": parsed.decision,
    "confidence": parsed.confidence,
    "confidence_semantics": CONFIDENCE_SEMANTICS,
    "reason": parsed.reason,
    "supporting_evidence": list(parsed.supporting_evidence),
    "provider": response.provider,
    "model": response.model,
    "context_mode": prompt.context_mode,
    "requested_context_mode": prompt.requested_context_mode,
    "selected_context_mode": prompt.selected_context_mode,
    "resolved_context_mode": prompt.resolved_context_mode,
    "context_policy_version": prompt.context_policy_version,
    "graph_context_included": prompt.graph_context_included,
    "graph_context_omitted_reason": prompt.graph_context_omitted_reason,
    "prompt_version": prompt.prompt_version,
    "prompt_template_hash": prompt.prompt_template_hash,
    "prompt_hash": prompt.prompt_hash,
    "response_hash": sha256_hex(response.raw_content),
    "candidate_record_hash": candidate_record_hash(bundle.record),
    "config_hash": config_hash,
    "parse_status": parsed.parse_status,
    "error": parsed.error,
    **({"citation_check": parsed.citation_check} if parsed.citation_check is not None else {}),
    "runtime_ms": response.runtime_ms,
    "token_usage": response.token_usage,
    "estimated_cost_usd": response.estimated_cost_usd,
    "source_candidate_ref": bundle.source_candidate_ref,
    "artifact_refs": bundle.artifact_refs,
    "candidate_summary": bundle.candidate_summary,
    "created_at": created_at,
    "generator": {
      "name": GENERATOR_NAME,
      "version": GENERATOR_VERSION,
    },
  }
  if "input_modalities" in provider_metadata:
    record["input_modalities"] = provider_metadata["input_modalities"]
  if "image_source" in provider_metadata:
    record["image_source"] = provider_metadata["image_source"]
  if "image_input" in provider_metadata:
    record["image_input"] = provider_metadata["image_input"]
  if "image_inputs" in provider_metadata:
    record["image_inputs"] = provider_metadata["image_inputs"]
  if escalation_metadata:
    record.update(escalation_metadata)
  return record


class ConfirmationRunWriter:
  def __init__(
    self,
    output_dir: Path,
    *,
    overwrite: bool = False,
    save_prompts: bool = False,
    save_raw_responses: bool = False,
  ):
    self.layout = prepare_confirmation_output_dir(
      output_dir,
      overwrite=overwrite,
      save_prompts=save_prompts,
      save_raw_responses=save_raw_responses,
    )
    self.save_prompts = save_prompts
    self.save_raw_responses = save_raw_responses

  def write_confirmation(self, record: dict[str, Any]) -> None:
    _append_jsonl(self.layout.confirmations_path, record)
    by_type_path = self.layout.by_type_dir / f"{record['candidate_type']}.jsonl"
    _append_jsonl(by_type_path, record)

  def write_attempt(self, record: dict[str, Any]) -> None:
    _append_jsonl(self.layout.attempts_path, record)

  def write_prompt(self, confirmation_id: str, prompt: ConfirmationPrompt) -> None:
    if not self.save_prompts:
      return
    payload = {
      "confirmation_id": confirmation_id,
      "candidate_id": prompt.bundle.candidate_id,
      "candidate_type": prompt.bundle.candidate_type,
      "state_id": prompt.bundle.state_id,
      "context_mode": prompt.context_mode,
      "requested_context_mode": prompt.requested_context_mode,
      "selected_context_mode": prompt.selected_context_mode,
      "resolved_context_mode": prompt.resolved_context_mode,
      "context_policy_version": prompt.context_policy_version,
      "graph_context_included": prompt.graph_context_included,
      "graph_context_omitted_reason": prompt.graph_context_omitted_reason,
      "prompt_version": prompt.prompt_version,
      "prompt_template_hash": prompt.prompt_template_hash,
      "prompt_hash": prompt.prompt_hash,
      "system_prompt": prompt.system_prompt,
      "user_prompt": prompt.user_prompt,
    }
    _write_json(self.layout.prompts_dir / f"{confirmation_id}.json", payload)

  def write_raw_response(
    self,
    confirmation_id: str,
    response: ConfirmationProviderResponse,
    *,
    error: str | None = None,
  ) -> None:
    if not self.save_raw_responses:
      return
    payload = {
      "confirmation_id": confirmation_id,
      "provider": response.provider,
      "model": response.model,
      "response_hash": sha256_hex(response.raw_content),
      "raw_content": response.raw_content,
      "runtime_ms": response.runtime_ms,
      "token_usage": response.token_usage,
      "estimated_cost_usd": response.estimated_cost_usd,
      "provider_metadata": response.provider_metadata,
      "error": error,
    }
    _write_json(self.layout.raw_responses_dir / f"{confirmation_id}.json", payload)

  def write_manifest(self, manifest: dict[str, Any]) -> None:
    _write_json(self.layout.manifest_path, manifest)


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
  with path.open("a", encoding="utf-8") as handle:
    handle.write(stable_json_dumps(record))
    handle.write("\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
  path.write_text(
    json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
    encoding="utf-8",
  )
