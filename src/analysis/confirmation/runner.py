from __future__ import annotations

import platform
import sys
import time
from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .hashing import config_hash, hash_payload
from .image_inputs import (
  combined_image_source,
  image_input_metadata,
  load_provider_image_inputs,
)
from .context_policy import (
  context_policy_version_for_context_mode,
  resolve_confirmation_context_mode,
)
from .escalation_policy import (
  escalation_policy_version_for_policy,
  is_graph_escalation_eligible,
  resolve_escalation_decision,
)
from .models import (
  CONFIRMATION_SCHEMA_VERSION,
  CONTEXT_MODE_ADAPTIVE,
  CONTEXT_MODE_ADAPTIVE_V2,
  CONTEXT_MODE_GRAPH,
  CONTEXT_MODE_HISTORY,
  CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT,
  GENERATOR_NAME,
  GENERATOR_VERSION,
  ESCALATION_POLICY_NONE,
  ESCALATION_POLICY_UNCERTAIN_GRAPH,
  ESCALATION_POLICY_UNCERTAIN_HISTORY,
  ConfirmationConfig,
  ConfirmationParseStatus,
  ConfirmationPrompt,
  ConfirmationProviderResponse,
  ParsedConfirmation,
  RESOLVED_CONTEXT_MODES,
  ReviewBundle,
)
from .citation_check import check_citations
from .parser import ConfirmationParseError, parse_confirmation_response
from .providers.base import ConfirmationClient
from .providers.registry import (
  ConfirmationProviderSpec,
  build_confirmation_client,
  get_confirmation_provider_spec,
  resolve_confirmation_config,
)
from .providers.base import ProviderOutOfCredits
from .prompt_builder import build_confirmation_prompt, load_prompt_templates
from .reader import candidate_bundle_path, load_review_bundles
from .run_id import generate_confirmation_run_id
from .visual_context import prepare_candidate_visual_context
from .writer import (
  ConfirmationRunWriter,
  build_confirmation_id,
  build_confirmation_record,
  confirmation_output_layout,
)


@dataclass(frozen=True)
class ConfirmationRunOptions:
  run_dir: Path
  confirmation_run_id: str | None = None
  candidate_types: tuple[str, ...] = ()
  candidate_ids: tuple[str, ...] = ()
  candidate_id_file: Path | None = None
  limit: int | None = None
  overwrite: bool = False
  dry_run: bool = False
  save_prompts: bool | None = None
  save_raw_responses: bool | None = None
  fail_fast: bool = False
  argv: tuple[str, ...] = ()
  cwd: Path | None = None


@dataclass(frozen=True)
class ConfirmationRunResult:
  confirmation_run_id: str
  output_dir: Path
  dry_run: bool
  manifest: dict[str, object]


@dataclass(frozen=True)
class _ConfirmationAttempt:
  attempt_index: int
  attempt_role: str
  prompt: ConfirmationPrompt
  response: ConfirmationProviderResponse
  parsed: ParsedConfirmation


def _normalize_context_escalation_config(config: ConfirmationConfig) -> ConfirmationConfig:
  effective_policy = {
    CONTEXT_MODE_ADAPTIVE: ESCALATION_POLICY_UNCERTAIN_GRAPH,
    CONTEXT_MODE_ADAPTIVE_V2: ESCALATION_POLICY_UNCERTAIN_HISTORY,
  }.get(config.context_mode, ESCALATION_POLICY_NONE)
  if config.escalation_policy == effective_policy:
    return config
  return replace(config, escalation_policy=effective_policy)


def run_confirmation(
  *,
  config: ConfirmationConfig,
  options: ConfirmationRunOptions,
  client: ConfirmationClient | None = None,
  created_at: datetime | None = None,
) -> ConfirmationRunResult:
  if options.limit is not None and options.limit < 0:
    raise ValueError("Confirmation limit must be zero or greater")
  config = resolve_confirmation_config(config)
  config = _normalize_context_escalation_config(config)
  _validate_real_provider_selection(config=config, options=options)

  started = time.perf_counter()
  run_dir = options.run_dir.resolve()
  cfg_hash = config_hash(config)
  started_at_dt = (created_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
  started_at = _format_utc(started_at_dt)
  confirmation_run_id = options.confirmation_run_id or generate_confirmation_run_id(
    config=config,
    config_hash=cfg_hash,
    created_at=started_at_dt,
  )
  output_dir = run_dir / "confirmations" / confirmation_run_id
  save_prompts = _resolve_raw_saving(config.provider, options.save_prompts)
  save_raw_responses = _resolve_raw_saving(config.provider, options.save_raw_responses)

  templates = load_prompt_templates(config.prompt_version)
  available_bundles = load_review_bundles(
    run_dir,
    candidate_types=options.candidate_types or None,
    candidate_ids=options.candidate_ids or None,
  )
  selected_bundles = _limit_bundles(available_bundles, options.limit)

  if options.dry_run:
    resolved_context_mode_counts: Counter[str] = Counter()
    selected_context_mode_counts: Counter[str] = Counter()
    graph_context_omitted_reason_counts: Counter[str] = Counter()
    escalation_eligible_count = 0
    for bundle in selected_bundles:
      context_resolution = resolve_confirmation_context_mode(
        bundle.candidate_type,
        config.context_mode,
        candidate_record=bundle.record,
      )
      selected_context_mode_counts[context_resolution.selected_context_mode] += 1
      resolved_context_mode_counts[context_resolution.resolved_context_mode] += 1
      if context_resolution.graph_context_omitted_reason:
        graph_context_omitted_reason_counts[
          context_resolution.graph_context_omitted_reason
        ] += 1
      if is_graph_escalation_eligible(
        bundle.candidate_type,
        config.escalation_policy,
        requested_context_mode=context_resolution.requested_context_mode,
        selected_context_mode=context_resolution.selected_context_mode,
        initial_context_mode=context_resolution.resolved_context_mode,
      ):
        escalation_eligible_count += 1
      build_confirmation_prompt(
        bundle,
        templates=templates,
        context_mode=context_resolution.resolved_context_mode,
        requested_context_mode=context_resolution.requested_context_mode,
        selected_context_mode=context_resolution.selected_context_mode,
        context_policy_version=context_resolution.context_policy_version,
        graph_context_omitted_reason=context_resolution.graph_context_omitted_reason,
      )
    manifest = _build_manifest(
      config=config,
      config_hash=cfg_hash,
      confirmation_run_id=confirmation_run_id,
      run_dir=run_dir,
      output_dir=output_dir,
      prompt_template_hash=templates.prompt_template_hash,
      context_mode=config.context_mode,
      selected_context_mode_counts=selected_context_mode_counts,
      resolved_context_mode_counts=resolved_context_mode_counts,
      graph_context_omitted_reason_counts=graph_context_omitted_reason_counts,
      started_at=started_at,
      completed_at=_format_utc(datetime.now(timezone.utc)),
      duration_ms=_elapsed_ms(started),
      candidate_types=options.candidate_types,
      candidate_ids=options.candidate_ids,
      candidate_id_file=options.candidate_id_file,
      selected_candidate_ids=tuple(bundle.candidate_id for bundle in selected_bundles),
      limit=options.limit,
      available_count=len(available_bundles),
      selected_count=len(selected_bundles),
      confirmations_written=0,
      by_decision=Counter(),
      by_candidate_type=Counter(bundle.candidate_type for bundle in selected_bundles),
      parse_status_counts=Counter(),
      attempt_count_total=0,
      attempt_resolved_context_mode_counts=Counter(),
      escalation_eligible_count=escalation_eligible_count,
      escalation_triggered_count=0,
      retry_parse_status_counts=Counter(),
      retry_error_count=0,
      final_decision_source_counts=Counter(),
      save_prompts=save_prompts,
      save_raw_responses=save_raw_responses,
      dry_run=True,
      invocation=_invocation_metadata(options),
    )
    return ConfirmationRunResult(
      confirmation_run_id=confirmation_run_id,
      output_dir=output_dir,
      dry_run=True,
      manifest=manifest,
    )

  resolved_client = client or build_confirmation_client(config)
  writer = ConfirmationRunWriter(
    output_dir,
    overwrite=options.overwrite,
    save_prompts=save_prompts,
    save_raw_responses=save_raw_responses,
  )
  by_decision: Counter[str] = Counter()
  by_candidate_type: Counter[str] = Counter()
  parse_status_counts: Counter[str] = Counter()
  selected_context_mode_counts: Counter[str] = Counter()
  resolved_context_mode_counts: Counter[str] = Counter()
  attempt_resolved_context_mode_counts: Counter[str] = Counter()
  graph_context_omitted_reason_counts: Counter[str] = Counter()
  retry_parse_status_counts: Counter[str] = Counter()
  final_decision_source_counts: Counter[str] = Counter()
  escalation_eligible_count = 0
  escalation_triggered_count = 0
  retry_error_count = 0
  attempt_count_total = 0
  confirmations_written = 0

  for selected_bundle in selected_bundles:
    if config.context_mode == CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT:
      bundle = selected_bundle
    else:
      bundle = prepare_candidate_visual_context(
        selected_bundle,
        output_dir=writer.layout.output_dir,
      )
    confirmation_id = build_confirmation_id(
      candidate_id=bundle.candidate_id,
      prompt_version=config.prompt_version,
      provider=config.provider,
      model=config.model,
      config_hash=cfg_hash,
    )
    attempts = _confirm_with_optional_escalation(
      bundle=bundle,
      config=config,
      client=resolved_client,
      templates=templates,
      fail_fast=options.fail_fast,
    )
    final_attempt = _final_attempt(attempts)
    final_parsed = final_attempt.parsed
    final_prompt = final_attempt.prompt
    final_response = final_attempt.response
    escalation_metadata = _build_escalation_metadata(
      config=config,
      attempts=attempts,
      final_attempt=final_attempt,
    )
    _write_attempt_outputs(
      writer=writer,
      confirmation_id=confirmation_id,
      confirmation_run_id=confirmation_run_id,
      attempts=attempts,
      final_attempt=final_attempt,
      config_hash=cfg_hash,
      created_at=started_at,
      save_prompts=save_prompts,
      save_raw_responses=save_raw_responses,
      escalation_metadata=escalation_metadata,
    )
    record = build_confirmation_record(
      confirmation_id=confirmation_id,
      confirmation_run_id=confirmation_run_id,
      prompt=final_prompt,
      response=final_response,
      parsed=final_parsed,
      config_hash=cfg_hash,
      created_at=started_at,
      escalation_metadata=escalation_metadata,
    )
    writer.write_confirmation(record)
    confirmations_written += 1
    by_decision[final_parsed.decision] += 1
    by_candidate_type[final_parsed.candidate_type] += 1
    parse_status_counts[final_parsed.parse_status] += 1
    selected_context_mode_counts[final_prompt.selected_context_mode] += 1
    resolved_context_mode_counts[final_prompt.resolved_context_mode] += 1
    if final_prompt.graph_context_omitted_reason:
      graph_context_omitted_reason_counts[final_prompt.graph_context_omitted_reason] += 1
    for attempt in attempts:
      attempt_resolved_context_mode_counts[attempt.prompt.resolved_context_mode] += 1
    attempt_count_total += len(attempts)
    if escalation_metadata["escalation_eligible"]:
      escalation_eligible_count += 1
    if escalation_metadata["escalation_triggered"]:
      escalation_triggered_count += 1
    if len(attempts) > 1:
      retry_attempt = attempts[1]
      retry_parse_status_counts[retry_attempt.parsed.parse_status] += 1
      if retry_attempt.parsed.parse_status != "parsed" or retry_attempt.parsed.error:
        retry_error_count += 1
    final_decision_source_counts[str(escalation_metadata["final_decision_source"])] += 1

  manifest = _build_manifest(
    config=config,
    config_hash=cfg_hash,
    confirmation_run_id=confirmation_run_id,
    run_dir=run_dir,
    output_dir=output_dir,
    prompt_template_hash=templates.prompt_template_hash,
    context_mode=config.context_mode,
    selected_context_mode_counts=selected_context_mode_counts,
    resolved_context_mode_counts=resolved_context_mode_counts,
    graph_context_omitted_reason_counts=graph_context_omitted_reason_counts,
    started_at=started_at,
    completed_at=_format_utc(datetime.now(timezone.utc)),
    duration_ms=_elapsed_ms(started),
    candidate_types=options.candidate_types,
    candidate_ids=options.candidate_ids,
    candidate_id_file=options.candidate_id_file,
    selected_candidate_ids=tuple(bundle.candidate_id for bundle in selected_bundles),
    limit=options.limit,
    available_count=len(available_bundles),
    selected_count=len(selected_bundles),
    confirmations_written=confirmations_written,
    by_decision=by_decision,
    by_candidate_type=by_candidate_type,
    parse_status_counts=parse_status_counts,
    attempt_count_total=attempt_count_total,
    attempt_resolved_context_mode_counts=attempt_resolved_context_mode_counts,
    escalation_eligible_count=escalation_eligible_count,
    escalation_triggered_count=escalation_triggered_count,
    retry_parse_status_counts=retry_parse_status_counts,
    retry_error_count=retry_error_count,
    final_decision_source_counts=final_decision_source_counts,
    save_prompts=save_prompts,
    save_raw_responses=save_raw_responses,
    dry_run=False,
    invocation=_invocation_metadata(options),
  )
  writer.write_manifest(manifest)
  return ConfirmationRunResult(
    confirmation_run_id=confirmation_run_id,
    output_dir=output_dir,
    dry_run=False,
    manifest=manifest,
  )


def _confirm_with_optional_escalation(
  *,
  bundle: ReviewBundle,
  config: ConfirmationConfig,
  client: ConfirmationClient,
  templates,
  fail_fast: bool,
) -> tuple[_ConfirmationAttempt, ...]:
  initial_context_resolution = resolve_confirmation_context_mode(
    bundle.candidate_type,
    config.context_mode,
    candidate_record=bundle.record,
  )
  try:
    initial_prompt = build_confirmation_prompt(
      bundle,
      templates=templates,
      context_mode=initial_context_resolution.resolved_context_mode,
      requested_context_mode=initial_context_resolution.requested_context_mode,
      selected_context_mode=initial_context_resolution.selected_context_mode,
      context_policy_version=initial_context_resolution.context_policy_version,
      graph_context_omitted_reason=initial_context_resolution.graph_context_omitted_reason,
    )
  except Exception as exc:
    if fail_fast or config.context_mode != CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT:
      raise
    return (
      _input_error_attempt(
        bundle=bundle,
        config=config,
        templates=templates,
        context_resolution=initial_context_resolution,
        error=str(exc),
      ),
    )
  initial_response, initial_parsed = _confirm_one(
    bundle=bundle,
    prompt=initial_prompt,
    config=config,
    client=client,
    fail_fast=fail_fast,
  )
  initial_attempt = _ConfirmationAttempt(
    attempt_index=1,
    attempt_role="initial_attempt",
    prompt=initial_prompt,
    response=initial_response,
    parsed=initial_parsed,
  )
  escalation = resolve_escalation_decision(
    candidate_type=bundle.candidate_type,
    initial_decision=initial_parsed.decision,
    initial_parse_status=initial_parsed.parse_status,
    escalation_policy=config.escalation_policy,
    requested_context_mode=initial_prompt.requested_context_mode,
    selected_context_mode=initial_prompt.selected_context_mode,
    initial_context_mode=initial_prompt.resolved_context_mode,
  )
  if not escalation.triggered or escalation.retry_context_mode is None:
    return (initial_attempt,)

  retry_context_resolution = resolve_confirmation_context_mode(
    bundle.candidate_type,
    escalation.retry_context_mode,
    candidate_record=bundle.record,
  )
  if retry_context_resolution.resolved_context_mode == initial_prompt.resolved_context_mode:
    return (initial_attempt,)

  retry_prompt = build_confirmation_prompt(
    bundle,
    templates=templates,
    context_mode=retry_context_resolution.resolved_context_mode,
    requested_context_mode=config.context_mode,
    selected_context_mode=retry_context_resolution.selected_context_mode,
    context_policy_version=retry_context_resolution.context_policy_version,
    graph_context_omitted_reason=retry_context_resolution.graph_context_omitted_reason,
  )
  retry_response, retry_parsed = _confirm_one(
    bundle=bundle,
    prompt=retry_prompt,
    config=config,
    client=client,
    fail_fast=fail_fast,
  )
  retry_attempt = _ConfirmationAttempt(
    attempt_index=2,
    attempt_role="history_retry" if escalation.retry_context_mode == CONTEXT_MODE_HISTORY else "graph_retry",
    prompt=retry_prompt,
    response=retry_response,
    parsed=retry_parsed,
  )
  return (initial_attempt, retry_attempt)


def _input_error_attempt(
  *,
  bundle: ReviewBundle,
  config: ConfirmationConfig,
  templates,
  context_resolution,
  error: str,
) -> _ConfirmationAttempt:
  prompt = ConfirmationPrompt(
    bundle=bundle,
    prompt_version=templates.prompt_version,
    context_mode=context_resolution.requested_context_mode,
    requested_context_mode=context_resolution.requested_context_mode,
    selected_context_mode=context_resolution.selected_context_mode,
    resolved_context_mode=context_resolution.resolved_context_mode,
    context_policy_version=context_resolution.context_policy_version,
    graph_context_included=False,
    graph_context_omitted_reason=context_resolution.graph_context_omitted_reason,
    system_prompt="",
    user_prompt="",
    type_guidance="",
    prompt_template_hash=templates.prompt_template_hash,
    prompt_hash=hash_payload(
      {
        "prompt_version": templates.prompt_version,
        "context_mode": context_resolution.resolved_context_mode,
        "input_error": error,
      }
    ),
  )
  response = ConfirmationProviderResponse(
    provider=config.provider,
    model=config.model,
    raw_content="",
    runtime_ms=None,
    token_usage=None,
    estimated_cost_usd=None,
    provider_metadata=_client_error_metadata(config, prompt),
  )
  parsed = _uncertain_from_error(
    bundle,
    parse_status="client_error",
    error=f"Input error: {error}",
  )
  return _ConfirmationAttempt(
    attempt_index=1,
    attempt_role="input_error",
    prompt=prompt,
    response=response,
    parsed=parsed,
  )


def _final_attempt(attempts: tuple[_ConfirmationAttempt, ...]) -> _ConfirmationAttempt:
  if len(attempts) == 1:
    return attempts[0]
  retry_attempt = attempts[1]
  if retry_attempt.parsed.parse_status == "parsed":
    return retry_attempt
  return attempts[0]


def _validate_real_provider_selection(
  *,
  config: ConfirmationConfig,
  options: ConfirmationRunOptions,
) -> None:
  provider_spec = get_confirmation_provider_spec(config.provider)
  if config.context_mode == CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT and not provider_spec.screenshot_required:
    raise ValueError("minimal_html_screenshot confirmation requires a vision provider with screenshot support")
  if (
    provider_spec.requires_candidate_selection
    and not options.candidate_types
    and not options.candidate_ids
    and options.limit is None
  ):
    raise ValueError("Real confirmation provider requires --candidate-type, --candidate-id, --candidate-id-file, or --limit")


def _confirm_one(
  *,
  bundle: ReviewBundle,
  prompt,
  config: ConfirmationConfig,
  client: ConfirmationClient,
  fail_fast: bool,
) -> tuple[ConfirmationProviderResponse, ParsedConfirmation]:
  try:
    response = client.confirm(prompt)
  except ProviderOutOfCredits:
    raise
  except Exception as exc:
    if fail_fast:
      raise
    response = ConfirmationProviderResponse(
      provider=config.provider,
      model=config.model,
      raw_content="",
      runtime_ms=None,
      token_usage=None,
      estimated_cost_usd=None,
      provider_metadata=_client_error_metadata(config, prompt),
    )
    return response, _uncertain_from_error(bundle, parse_status="client_error", error=str(exc))

  parsed = parse_confirmation_response(
    response.raw_content,
    bundle=bundle,
    prompt_version=prompt.prompt_version,
    strict=config.strict_parse,
  )
  parsed = check_citations(parsed, prompt_version=prompt.prompt_version, user_prompt=prompt.user_prompt,
                           vision="vision" in config.provider)
  if parsed.parse_status != "parsed" and fail_fast:
    raise ConfirmationParseError(
      parsed.error or f"Confirmation response parse status: {parsed.parse_status}",
      parse_status=parsed.parse_status,
    )
  return response, parsed


def _build_escalation_metadata(
  *,
  config: ConfirmationConfig,
  attempts: tuple[_ConfirmationAttempt, ...],
  final_attempt: _ConfirmationAttempt,
) -> dict[str, object]:
  initial_attempt = attempts[0]
  retry_attempt = attempts[1] if len(attempts) > 1 else None
  policy_version = escalation_policy_version_for_policy(config.escalation_policy)
  eligible = is_graph_escalation_eligible(
    initial_attempt.parsed.candidate_type,
    config.escalation_policy,
    requested_context_mode=initial_attempt.prompt.requested_context_mode,
    selected_context_mode=initial_attempt.prompt.selected_context_mode,
    initial_context_mode=initial_attempt.prompt.resolved_context_mode,
  )
  return {
    "escalation_policy": config.escalation_policy,
    "escalation_policy_version": policy_version,
    "escalation_eligible": eligible,
    "attempt_count": len(attempts),
    "escalation_triggered": retry_attempt is not None,
    "final_decision_source": final_attempt.attempt_role,
    "final_attempt_index": final_attempt.attempt_index,
    "initial_context_mode": initial_attempt.prompt.resolved_context_mode,
    "initial_decision": initial_attempt.parsed.decision,
    "initial_parse_status": initial_attempt.parsed.parse_status,
    "retry_context_mode": retry_attempt.prompt.resolved_context_mode if retry_attempt else None,
    "retry_decision": retry_attempt.parsed.decision if retry_attempt else None,
    "retry_parse_status": retry_attempt.parsed.parse_status if retry_attempt else None,
    "retry_error": retry_attempt.parsed.error if retry_attempt else None,
    "escalation_reason": "initial_uncertain" if retry_attempt else None,
  }


def _write_attempt_outputs(
  *,
  writer: ConfirmationRunWriter,
  confirmation_id: str,
  confirmation_run_id: str,
  attempts: tuple[_ConfirmationAttempt, ...],
  final_attempt: _ConfirmationAttempt,
  config_hash: str,
  created_at: str,
  save_prompts: bool,
  save_raw_responses: bool,
  escalation_metadata: dict[str, object],
) -> None:
  use_attempt_specific_artifacts = len(attempts) > 1
  for attempt in attempts:
    attempt_confirmation_id = _attempt_confirmation_id(
      confirmation_id,
      attempt.attempt_index,
      use_attempt_specific_artifacts=use_attempt_specific_artifacts,
    )
    writer.write_prompt(attempt_confirmation_id, attempt.prompt)
    writer.write_raw_response(attempt_confirmation_id, attempt.response, error=attempt.parsed.error)
    writer.write_attempt(
      _build_attempt_record(
        confirmation_id=confirmation_id,
        attempt_confirmation_id=attempt_confirmation_id,
        confirmation_run_id=confirmation_run_id,
        attempt=attempt,
        config_hash=config_hash,
        created_at=created_at,
        prompt_ref=f"prompts/{attempt_confirmation_id}.json" if save_prompts else None,
        raw_response_ref=f"raw_responses/{attempt_confirmation_id}.json" if save_raw_responses else None,
        escalation_metadata=escalation_metadata,
      )
    )
  if use_attempt_specific_artifacts:
    writer.write_prompt(confirmation_id, final_attempt.prompt)
    writer.write_raw_response(confirmation_id, final_attempt.response, error=final_attempt.parsed.error)


def _attempt_confirmation_id(
  confirmation_id: str,
  attempt_index: int,
  *,
  use_attempt_specific_artifacts: bool,
) -> str:
  if not use_attempt_specific_artifacts:
    return confirmation_id
  return f"{confirmation_id}_attempt_{attempt_index}"


def _build_attempt_record(
  *,
  confirmation_id: str,
  attempt_confirmation_id: str,
  confirmation_run_id: str,
  attempt: _ConfirmationAttempt,
  config_hash: str,
  created_at: str,
  prompt_ref: str | None,
  raw_response_ref: str | None,
  escalation_metadata: dict[str, object],
) -> dict[str, object]:
  prompt = attempt.prompt
  parsed = attempt.parsed
  response = attempt.response
  return {
    "schema_version": CONFIRMATION_SCHEMA_VERSION,
    "confirmation_id": confirmation_id,
    "attempt_confirmation_id": attempt_confirmation_id,
    "confirmation_run_id": confirmation_run_id,
    "candidate_id": parsed.candidate_id,
    "candidate_type": parsed.candidate_type,
    "state_id": parsed.state_id,
    "attempt_index": attempt.attempt_index,
    "attempt_role": attempt.attempt_role,
    "context_mode": prompt.context_mode,
    "requested_context_mode": prompt.requested_context_mode,
    "selected_context_mode": prompt.selected_context_mode,
    "resolved_context_mode": prompt.resolved_context_mode,
    "context_policy_version": prompt.context_policy_version,
    "graph_context_included": prompt.graph_context_included,
    "graph_context_omitted_reason": prompt.graph_context_omitted_reason,
    "escalation_policy": escalation_metadata["escalation_policy"],
    "escalation_policy_version": escalation_metadata["escalation_policy_version"],
    "decision": parsed.decision,
    "parse_status": parsed.parse_status,
    "confidence": parsed.confidence,
    "error": parsed.error,
    "prompt_version": prompt.prompt_version,
    "prompt_hash": prompt.prompt_hash,
    "prompt_ref": prompt_ref,
    "response_ref": raw_response_ref,
    "provider": response.provider,
    "model": response.model,
    "runtime_ms": response.runtime_ms,
    "token_usage": response.token_usage,
    "estimated_cost_usd": response.estimated_cost_usd,
    "config_hash": config_hash,
    "created_at": created_at,
  }


def _uncertain_from_error(
  bundle: ReviewBundle,
  *,
  parse_status: ConfirmationParseStatus,
  error: str,
) -> ParsedConfirmation:
  return ParsedConfirmation(
    candidate_id=bundle.candidate_id,
    candidate_type=bundle.candidate_type,
    state_id=bundle.state_id,
    decision="uncertain",
    confidence=0.0,
    reason=f"Confirmation provider failed: {error}",
    supporting_evidence=(),
    parse_status=parse_status,
    error=error,
  )


def _limit_bundles(bundles: list[ReviewBundle], limit: int | None) -> list[ReviewBundle]:
  if limit is None:
    return bundles
  return bundles[:limit]


def _resolve_raw_saving(provider: str, requested: bool | None) -> bool:
  if requested is not None:
    return requested
  return provider == "fake"


def _build_manifest(
  *,
  config: ConfirmationConfig,
  config_hash: str,
  confirmation_run_id: str,
  run_dir: Path,
  output_dir: Path,
  prompt_template_hash: str,
  context_mode: str,
  selected_context_mode_counts: Counter[str],
  resolved_context_mode_counts: Counter[str],
  graph_context_omitted_reason_counts: Counter[str],
  started_at: str,
  completed_at: str,
  duration_ms: int,
  candidate_types: Iterable[str],
  candidate_ids: Iterable[str],
  candidate_id_file: Path | None,
  selected_candidate_ids: Iterable[str],
  limit: int | None,
  available_count: int,
  selected_count: int,
  confirmations_written: int,
  by_decision: Counter[str],
  by_candidate_type: Counter[str],
  parse_status_counts: Counter[str],
  attempt_count_total: int,
  attempt_resolved_context_mode_counts: Counter[str],
  escalation_eligible_count: int,
  escalation_triggered_count: int,
  retry_parse_status_counts: Counter[str],
  retry_error_count: int,
  final_decision_source_counts: Counter[str],
  save_prompts: bool,
  save_raw_responses: bool,
  dry_run: bool,
  invocation: dict[str, object],
) -> dict[str, object]:
  layout = confirmation_output_layout(output_dir)
  provider_spec = get_confirmation_provider_spec(config.provider)
  context_policy_version = context_policy_version_for_context_mode(context_mode)
  escalation_policy_version = escalation_policy_version_for_policy(config.escalation_policy)
  selected_counts = dict(sorted(selected_context_mode_counts.items()))
  resolved_counts = dict(sorted(resolved_context_mode_counts.items()))
  attempt_resolved_counts = dict(sorted(attempt_resolved_context_mode_counts.items()))
  graph_omitted_counts = dict(sorted(graph_context_omitted_reason_counts.items()))
  resolved_context_mode = _single_resolved_context_mode(
    context_mode,
    resolved_context_mode_counts,
  )
  return {
    "schema_version": CONFIRMATION_SCHEMA_VERSION,
    "confirmation_run_id": confirmation_run_id,
    "generated_at": completed_at,
    "run_dir": run_dir.as_posix(),
    "output_dir": output_dir.as_posix(),
    "provider": config.provider,
    "model": config.model,
    "context_mode": context_mode,
    "requested_context_mode": context_mode,
    "resolved_context_mode": resolved_context_mode,
    "context_policy_version": context_policy_version,
    "selected_context_mode_counts": selected_counts,
    "resolved_context_mode_counts": resolved_counts,
    "graph_context_omitted_reason_counts": graph_omitted_counts,
    "graph_context_included": _graph_context_included(
      context_mode,
      resolved_context_mode_counts,
      attempt_resolved_context_mode_counts,
    ),
    "escalation_policy": config.escalation_policy,
    "escalation_policy_version": escalation_policy_version,
    "initial_context_mode": context_mode,
    "retry_context_mode": CONTEXT_MODE_GRAPH if escalation_policy_version else None,
    "input_mode": provider_spec.input_mode,
    "input_modalities": list(provider_spec.input_modalities),
    "image_source": provider_spec.image_source,
    "config": config.decision_affecting_payload(),
    "config_hash": config_hash,
    "prompt_version": config.prompt_version,
    "prompt_template_hash": prompt_template_hash,
    "inputs": {
      "candidate_path": candidate_bundle_path(run_dir).relative_to(run_dir).as_posix(),
      "candidate_types": list(candidate_types),
      "candidate_ids": list(candidate_ids),
      "candidate_id_file": _path_for_manifest(candidate_id_file, run_dir) if candidate_id_file else None,
      "selected_candidate_ids": list(selected_candidate_ids),
      "limit": limit,
    },
    "outputs": {
      "manifest": layout.manifest_path.relative_to(output_dir).as_posix(),
      "confirmations": layout.confirmations_path.relative_to(output_dir).as_posix(),
      "confirmation_attempts": layout.attempts_path.relative_to(output_dir).as_posix(),
      "by_type_dir": layout.by_type_dir.relative_to(output_dir).as_posix(),
      "prompts_dir": layout.prompts_dir.relative_to(output_dir).as_posix() if save_prompts else None,
      "raw_responses_dir": layout.raw_responses_dir.relative_to(output_dir).as_posix()
      if save_raw_responses
      else None,
    },
    "counts": {
      "candidates_available": available_count,
      "candidates_selected": selected_count,
      "confirmations_written": confirmations_written,
      "attempt_count_total": attempt_count_total,
      "escalation_eligible_count": escalation_eligible_count,
      "escalation_triggered_count": escalation_triggered_count,
      "retry_error_count": retry_error_count,
    },
    "by_decision": dict(sorted(by_decision.items())),
    "final_by_decision": dict(sorted(by_decision.items())),
    "by_candidate_type": dict(sorted(by_candidate_type.items())),
    "parse_status_counts": dict(sorted(parse_status_counts.items())),
    "attempt_resolved_context_mode_counts": attempt_resolved_counts,
    "retry_parse_status_counts": dict(sorted(retry_parse_status_counts.items())),
    "final_decision_source_counts": dict(sorted(final_decision_source_counts.items())),
    "raw_logging": _raw_logging_metadata(
      provider=config.provider,
      save_prompts=save_prompts,
      save_raw_responses=save_raw_responses,
    ),
    "dry_run": dry_run,
    "started_at": started_at,
    "completed_at": completed_at,
    "duration_ms": duration_ms,
    "generator": {
      "name": GENERATOR_NAME,
      "version": GENERATOR_VERSION,
    },
    "invocation": invocation,
  }


def _invocation_metadata(options: ConfirmationRunOptions) -> dict[str, object]:
  return {
    "argv": list(options.argv),
    "cwd": str(options.cwd or Path.cwd()),
    "python_version": sys.version,
    "platform": platform.platform(),
  }


def _single_resolved_context_mode(
  requested_context_mode: str,
  resolved_context_mode_counts: Counter[str],
) -> str | None:
  nonzero_modes = [
    context_mode
    for context_mode, count in resolved_context_mode_counts.items()
    if count > 0
  ]
  if len(nonzero_modes) == 1:
    return nonzero_modes[0]
  if not nonzero_modes and requested_context_mode in RESOLVED_CONTEXT_MODES:
    return requested_context_mode
  return None


def _graph_context_included(
  requested_context_mode: str,
  resolved_context_mode_counts: Counter[str],
  attempt_resolved_context_mode_counts: Counter[str],
) -> bool:
  if attempt_resolved_context_mode_counts:
    return attempt_resolved_context_mode_counts[CONTEXT_MODE_GRAPH] > 0
  if resolved_context_mode_counts:
    return resolved_context_mode_counts[CONTEXT_MODE_GRAPH] > 0
  return requested_context_mode == CONTEXT_MODE_GRAPH


def _path_for_manifest(path: Path, run_dir: Path) -> str:
  resolved = path.resolve()
  try:
    return resolved.relative_to(run_dir).as_posix()
  except ValueError:
    return resolved.as_posix()


def _client_error_metadata(
  config: ConfirmationConfig,
  prompt: ConfirmationPrompt,
) -> dict[str, object] | None:
  provider_spec = get_confirmation_provider_spec(config.provider)
  if config.provider == "fake":
    return None
  metadata = _provider_metadata(provider_spec)
  if provider_spec.screenshot_required:
    try:
      image_inputs = load_provider_image_inputs(
        prompt.bundle,
        provider=config.provider,
        context_mode=prompt.resolved_context_mode,
      )
    except Exception:
      return metadata
    metadata.update(
      {
        "image_source": combined_image_source(image_inputs),
        "image_input": image_input_metadata(image_inputs[0]),
        "image_inputs": [image_input_metadata(image_input) for image_input in image_inputs],
        "request": {
          "image_count": len(image_inputs),
        },
      }
    )
  return metadata


def _raw_logging_metadata(
  *,
  provider: str,
  save_prompts: bool,
  save_raw_responses: bool,
) -> dict[str, object]:
  metadata: dict[str, object] = {
    "save_prompts": save_prompts,
    "save_raw_responses": save_raw_responses,
  }
  provider_spec = get_confirmation_provider_spec(provider)
  if provider_spec.screenshot_required:
    metadata["save_raw_images"] = False
  return metadata


def _provider_metadata(provider_spec: ConfirmationProviderSpec) -> dict[str, object]:
  return {
    "input_modalities": list(provider_spec.input_modalities),
    "image_source": provider_spec.image_source,
  }


def _format_utc(value: datetime) -> str:
  return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _elapsed_ms(started: float) -> int:
  return int((time.perf_counter() - started) * 1000)
