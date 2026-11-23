from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path

from src.analysis.candidates.taxonomy import SUPPORTED_CANDIDATE_TYPES

from .hashing import hash_payload
from .models import (
  CONTEXT_MODE_GRAPH,
  CONTEXT_MODE_HISTORY,
  CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT,
  CONTEXT_MODES,
  GUIDED_HTML_SCREENSHOT_PROMPT_VERSION,
  RESOLVED_CONTEXT_MODES,
  PROMPT_VERSION,
  ConfirmationPrompt,
  PromptTemplates,
  ReviewBundle,
)

_PROMPTS_ROOT = Path(__file__).resolve().parent / "prompts"
_ISOLATED_STATE_CONTEXT_EXCLUDED_KEYS = frozenset(
  {
    "parent_state",
    "action_from_parent",
    "depth",
  }
)
# Keys only history_context shows; graph_context keeps the transition path without change records.
_HISTORY_ONLY_GRAPH_CONTEXT_KEYS = frozenset(
  {
    "incoming_change_record_v1",
    "incoming_edge_action",
    "destination_state_context_v2",
  }
)
_FULL_CONTEXT_MODES = frozenset({CONTEXT_MODE_GRAPH, CONTEXT_MODE_HISTORY})
_ISOLATED_SUPPORTING_EXCLUDED_KEYS = frozenset(
  {
    "destination_state_context_v1",
  }
)
_ISOLATED_LINK_DESTINATION_SOURCE_KEYS = (
  "schema_version",
  "raw_href",
  "resolved_url",
  "resolved_path",
  "fragment",
)
_ISOLATED_BUTTON_ACTION_EXCLUDED_KEYS = frozenset(
  {
    "matched_outgoing_transition",
    "result_state_context",
  }
)


def load_prompt_templates(prompt_version: str = PROMPT_VERSION) -> PromptTemplates:
  prompt_dir = _PROMPTS_ROOT / prompt_version
  system_template = _read_template(prompt_dir / "system.md")
  user_template = _read_template(prompt_dir / "user.md")
  type_guidance = _read_type_guidance(prompt_dir / "type_guidance.json")
  prompt_template_hash = hash_prompt_templates(
    system_template=system_template,
    user_template=user_template,
    type_guidance=type_guidance,
  )
  return PromptTemplates(
    prompt_version=prompt_version,
    system_template=system_template,
    user_template=user_template,
    type_guidance=type_guidance,
    prompt_template_hash=prompt_template_hash,
  )


def hash_prompt_templates(
  *,
  system_template: str,
  user_template: str,
  type_guidance: dict[str, str],
) -> str:
  return hash_payload(
    {
      "system.md": system_template,
      "user.md": user_template,
      "type_guidance.json": type_guidance,
    }
  )


def build_confirmation_prompt(
  bundle: ReviewBundle,
  *,
  templates: PromptTemplates | None = None,
  context_mode: str = CONTEXT_MODE_GRAPH,
  requested_context_mode: str | None = None,
  selected_context_mode: str | None = None,
  context_policy_version: str | None = None,
  graph_context_omitted_reason: str | None = None,
) -> ConfirmationPrompt:
  resolved_templates = templates or load_prompt_templates()
  resolved_context_mode = _validate_context_mode(context_mode)
  rendered_context_mode = _validate_requested_context_mode(
    requested_context_mode or resolved_context_mode
  )
  rendered_selected_context_mode = _validate_context_mode(
    selected_context_mode or resolved_context_mode
  )
  if (
    resolved_context_mode == CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT
    or resolved_templates.prompt_version == GUIDED_HTML_SCREENSHOT_PROMPT_VERSION
  ):
    return _build_minimal_html_screenshot_prompt(
      bundle,
      templates=resolved_templates,
      resolved_context_mode=resolved_context_mode,
      rendered_context_mode=rendered_context_mode,
      rendered_selected_context_mode=rendered_selected_context_mode,
      context_policy_version=context_policy_version,
      graph_context_omitted_reason=graph_context_omitted_reason,
    )
  graph_context_included = resolved_context_mode in _FULL_CONTEXT_MODES
  guidance = resolved_templates.type_guidance[bundle.candidate_type]
  candidate_payload = _candidate_prompt_payload(bundle, context_mode=resolved_context_mode)
  user_prompt = (
    resolved_templates.user_template
    .replace("{{TYPE_GUIDANCE}}", guidance)
    .replace("{{CANDIDATE_ID}}", bundle.candidate_id)
    .replace("{{CANDIDATE_TYPE}}", bundle.candidate_type)
    .replace("{{STATE_ID}}", bundle.state_id)
    .replace("{{CANDIDATE_JSON}}", json.dumps(candidate_payload, ensure_ascii=False, indent=2))
  )
  prompt_hash = hash_payload(
    {
      "system": resolved_templates.system_template,
      "user": user_prompt,
      "prompt_version": resolved_templates.prompt_version,
    }
  )
  return ConfirmationPrompt(
    bundle=bundle,
    prompt_version=resolved_templates.prompt_version,
    context_mode=rendered_context_mode,
    requested_context_mode=rendered_context_mode,
    selected_context_mode=rendered_selected_context_mode,
    resolved_context_mode=resolved_context_mode,
    context_policy_version=context_policy_version,
    graph_context_included=graph_context_included,
    graph_context_omitted_reason=graph_context_omitted_reason,
    system_prompt=resolved_templates.system_template,
    user_prompt=user_prompt,
    type_guidance=guidance,
    prompt_template_hash=resolved_templates.prompt_template_hash,
    prompt_hash=prompt_hash,
  )


def _build_minimal_html_screenshot_prompt(
  bundle: ReviewBundle,
  *,
  templates: PromptTemplates,
  resolved_context_mode: str,
  rendered_context_mode: str,
  rendered_selected_context_mode: str,
  context_policy_version: str | None,
  graph_context_omitted_reason: str | None,
) -> ConfirmationPrompt:
  if resolved_context_mode != CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT:
    raise ValueError(
      f"Prompt version {templates.prompt_version!r} requires "
      f"context_mode={CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT!r}"
    )
  if templates.prompt_version != GUIDED_HTML_SCREENSHOT_PROMPT_VERSION:
    raise ValueError(
      f"context_mode={CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT!r} requires "
      f"{GUIDED_HTML_SCREENSHOT_PROMPT_VERSION!r}"
    )
  candidate_html = _candidate_html_for_minimal_prompt(bundle)
  guidance = templates.type_guidance.get(bundle.candidate_type, "")
  user_prompt = (
    templates.user_template
    .replace("{{TYPE_GUIDANCE}}", guidance)
    .replace("{{CANDIDATE_TYPE}}", bundle.candidate_type)
    .replace("{{CANDIDATE_HTML}}", candidate_html)
  )
  prompt_hash = hash_payload(
    {
      "system": templates.system_template,
      "user": user_prompt,
      "prompt_version": templates.prompt_version,
    }
  )
  return ConfirmationPrompt(
    bundle=bundle,
    prompt_version=templates.prompt_version,
    context_mode=rendered_context_mode,
    requested_context_mode=rendered_context_mode,
    selected_context_mode=rendered_selected_context_mode,
    resolved_context_mode=resolved_context_mode,
    context_policy_version=context_policy_version,
    graph_context_included=False,
    graph_context_omitted_reason=graph_context_omitted_reason,
    system_prompt=templates.system_template,
    user_prompt=user_prompt,
    type_guidance=guidance,
    prompt_template_hash=templates.prompt_template_hash,
    prompt_hash=prompt_hash,
  )


def _read_template(path: Path) -> str:
  if not path.exists() or not path.is_file():
    raise FileNotFoundError(f"Prompt template file does not exist: {path}")
  return path.read_text(encoding="utf-8-sig").strip()


def _read_type_guidance(path: Path) -> dict[str, str]:
  raw = json.loads(path.read_text(encoding="utf-8-sig"))
  if not isinstance(raw, dict):
    raise ValueError(f"Prompt guidance file must be a JSON object: {path}")
  guidance = {str(key): str(value) for key, value in raw.items()}
  missing = sorted(set(SUPPORTED_CANDIDATE_TYPES) - set(guidance))
  extra = sorted(set(guidance) - set(SUPPORTED_CANDIDATE_TYPES))
  if missing:
    raise ValueError(f"Prompt guidance is missing supported candidate types: {', '.join(missing)}")
  if extra:
    raise ValueError(f"Prompt guidance includes unsupported candidate types: {', '.join(extra)}")
  return guidance


def _validate_context_mode(context_mode: str) -> str:
  if context_mode not in RESOLVED_CONTEXT_MODES:
    allowed = ", ".join(RESOLVED_CONTEXT_MODES)
    raise ValueError(f"Unsupported resolved confirmation context_mode: {context_mode}. Allowed values: {allowed}")
  return context_mode


def _validate_requested_context_mode(context_mode: str) -> str:
  if context_mode not in CONTEXT_MODES:
    allowed = ", ".join(CONTEXT_MODES)
    raise ValueError(f"Unsupported requested confirmation context_mode: {context_mode}. Allowed values: {allowed}")
  return context_mode


def _candidate_html_for_minimal_prompt(bundle: ReviewBundle) -> str:
  snippets = bundle.evidence.get("dom_snippets")
  supporting = bundle.evidence.get("supporting")
  if not isinstance(snippets, list):
    snippets = supporting.get("dom_snippets") if isinstance(supporting, Mapping) else None
  html_values: list[str] = []
  if isinstance(snippets, list):
    for snippet in snippets:
      if not isinstance(snippet, Mapping):
        continue
      html = snippet.get("html")
      if isinstance(html, str) and html.strip():
        html_values.append(html.strip())
  if not html_values:
    artifact_html = _candidate_html_from_state_dom_artifact(bundle)
    if artifact_html:
      return artifact_html
    raise ValueError(
      "minimal_html_screenshot requires candidate HTML in evidence.dom_snippets "
      "or a readable artifact_refs.dom_html file"
    )
  return "\n".join(html_values)


def _candidate_html_from_state_dom_artifact(bundle: ReviewBundle) -> str | None:
  dom_ref = bundle.artifact_refs.get("dom_html")
  if not isinstance(dom_ref, str) or not dom_ref.strip():
    return None
  dom_path = Path(dom_ref)
  if not dom_path.is_absolute():
    dom_path = bundle.run_dir / dom_path
  resolved_path = dom_path.resolve()
  run_dir = bundle.run_dir.resolve()
  if resolved_path != run_dir and run_dir not in resolved_path.parents:
    raise ValueError("minimal_html_screenshot artifact_refs.dom_html must stay inside the run directory")
  if not resolved_path.exists() or not resolved_path.is_file():
    return None
  html = resolved_path.read_text(encoding="utf-8", errors="replace").strip()
  return html or None


def _candidate_prompt_payload(bundle: ReviewBundle, *, context_mode: str) -> dict[str, object]:
  payload: dict[str, object] = {
    "candidate_is_not_confirmed": True,
    "candidate_id": bundle.candidate_id,
    "candidate_type": bundle.candidate_type,
    "state_id": bundle.state_id,
    "element_refs": list(bundle.element_refs),
    **({"primary_element_ref": bundle.primary_element_ref} if bundle.primary_element_ref else {}),
    "selection_reason": list(bundle.selection_reason),
    "required_context": list(bundle.required_context),
    "evidence": _evidence_for_prompt(bundle.evidence, context_mode=context_mode),
    "state_context": _state_context_for_prompt(bundle.state_context, context_mode=context_mode),
    "artifact_refs": bundle.artifact_refs,
    "generator": bundle.generator,
    "source_candidate_ref": bundle.source_candidate_ref,
  }
  if context_mode == CONTEXT_MODE_HISTORY:
    payload["graph_context"] = bundle.graph_context
  elif context_mode == CONTEXT_MODE_GRAPH:
    payload["graph_context"] = {
      key: value for key, value in bundle.graph_context.items() if key not in _HISTORY_ONLY_GRAPH_CONTEXT_KEYS
    }
  return payload


def _evidence_for_prompt(
  evidence: dict[str, object],
  *,
  context_mode: str,
) -> dict[str, object]:
  projected = deepcopy(evidence)
  if context_mode in _FULL_CONTEXT_MODES:
    return projected

  supporting = projected.get("supporting")
  if not isinstance(supporting, dict):
    return projected

  for key in _ISOLATED_SUPPORTING_EXCLUDED_KEYS:
    supporting.pop(key, None)

  link_destination = supporting.get("link_destination_context_v1")
  if isinstance(link_destination, Mapping):
    supporting["link_destination_context_v1"] = {
      key: link_destination[key]
      for key in _ISOLATED_LINK_DESTINATION_SOURCE_KEYS
      if key in link_destination
    }

  button_action = supporting.get("button_action_context_v1")
  if isinstance(button_action, dict):
    action_evidence = button_action.get("action_evidence")
    if isinstance(action_evidence, dict):
      for key in _ISOLATED_BUTTON_ACTION_EXCLUDED_KEYS:
        action_evidence.pop(key, None)

  return projected


def _state_context_for_prompt(state_context: dict[str, object], *, context_mode: str) -> dict[str, object]:
  if context_mode in _FULL_CONTEXT_MODES:
    return state_context
  return {
    key: value
    for key, value in state_context.items()
    if key not in _ISOLATED_STATE_CONTEXT_EXCLUDED_KEYS
  }
