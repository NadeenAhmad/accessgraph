from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

CONFIRMATION_SCHEMA_VERSION = "1"
GENERATOR_NAME = "offline_semantic_confirmation"
GENERATOR_VERSION = "1"
CALIBRATED_TEXT_PROMPT_VERSION = "confirm_v4_1_text"
CALIBRATED_VISION_PROMPT_VERSION = "confirm_v4_1_vision"
GUIDED_HTML_SCREENSHOT_PROMPT_VERSION = "confirm_guided_html_screenshot"
# v5 (W4A 2027): history and forward rules, per-type WCAG/ACT decision rules, cited key paths.
CONFIRM_V5_TEXT_PROMPT_VERSION = "confirm_v5_text"
CONFIRM_V5_VISION_PROMPT_VERSION = "confirm_v5_vision"
V5_PROMPT_VERSIONS = (CONFIRM_V5_TEXT_PROMPT_VERSION, CONFIRM_V5_VISION_PROMPT_VERSION)
PROMPT_VERSION = CALIBRATED_TEXT_PROMPT_VERSION
VISION_PROMPT_VERSION = CALIBRATED_VISION_PROMPT_VERSION
CONFIDENCE_SEMANTICS = "model_reported_heuristic_not_calibrated"
CONTEXT_MODE_GRAPH = "graph_context"
CONTEXT_MODE_ISOLATED = "isolated_state"
CONTEXT_MODE_ADAPTIVE = "adaptive_context"
CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT = "minimal_html_screenshot"
# history_context = graph context + incoming change record + destination outcomes with change records.
CONTEXT_MODE_HISTORY = "history_context"
# adaptive_v2: transition-capable types get history_context, the rest isolated_state; uncertain isolated
# verdicts are re-judged with history.
CONTEXT_MODE_ADAPTIVE_V2 = "adaptive_v2"
RESOLVED_CONTEXT_MODES = (
  CONTEXT_MODE_GRAPH,
  CONTEXT_MODE_ISOLATED,
  CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT,
  CONTEXT_MODE_HISTORY,
)
CONTEXT_MODES = (
  CONTEXT_MODE_GRAPH,
  CONTEXT_MODE_ISOLATED,
  CONTEXT_MODE_ADAPTIVE,
  CONTEXT_MODE_MINIMAL_HTML_SCREENSHOT,
  CONTEXT_MODE_HISTORY,
  CONTEXT_MODE_ADAPTIVE_V2,
)
ESCALATION_POLICY_NONE = "none"
ESCALATION_POLICY_UNCERTAIN_GRAPH = "uncertain_graph_v1"
ESCALATION_POLICY_UNCERTAIN_HISTORY = "uncertain_history_v1"
ESCALATION_POLICIES = (ESCALATION_POLICY_NONE, ESCALATION_POLICY_UNCERTAIN_GRAPH, ESCALATION_POLICY_UNCERTAIN_HISTORY)

ConfirmationDecision = Literal["violation", "no_violation", "uncertain"]
ConfirmationContextMode = Literal[
  "graph_context", "isolated_state", "adaptive_context", "minimal_html_screenshot", "history_context", "adaptive_v2"
]
ConfirmationEscalationPolicy = Literal["none", "uncertain_graph_v1", "uncertain_history_v1"]
ConfirmationParseStatus = Literal[
  "parsed",
  "malformed_json",
  "schema_error",
  "id_mismatch",
  "client_error",
]


@dataclass(frozen=True)
class ConfirmationConfig:
  provider: str = "fake"
  model: str = "fake-confirmation-model"
  prompt_version: str = PROMPT_VERSION
  temperature: float = 0.0
  strict_parse: bool = False
  base_url: str | None = None
  timeout_seconds: float = 120.0
  fake_mode: str = "default"
  context_mode: ConfirmationContextMode = CONTEXT_MODE_GRAPH
  escalation_policy: ConfirmationEscalationPolicy = ESCALATION_POLICY_NONE
  effort: str | None = None  # reasoning effort for providers that support it; None = provider default

  def __post_init__(self) -> None:
    if self.context_mode not in CONTEXT_MODES:
      raise ValueError(f"Unsupported confirmation context_mode: {self.context_mode}")
    if self.escalation_policy not in ESCALATION_POLICIES:
      raise ValueError(f"Unsupported confirmation escalation_policy: {self.escalation_policy}")

  def decision_affecting_payload(self) -> dict[str, object]:
    payload: dict[str, object] = {
      "provider": self.provider,
      "model": self.model,
      "prompt_version": self.prompt_version,
      "temperature": self.temperature,
      "strict_parse": self.strict_parse,
      "base_url": self.base_url,
      "timeout_seconds": self.timeout_seconds,
      "fake_mode": self.fake_mode,
      "context_mode": self.context_mode,
      "escalation_policy": self.escalation_policy,
    }
    if self.effort is not None:
      payload["effort"] = self.effort
    if self.context_mode in {CONTEXT_MODE_ADAPTIVE, CONTEXT_MODE_GRAPH}:
      from .context_policy import ADAPTIVE_CONTEXT_POLICY_VERSION

      payload["context_policy_version"] = ADAPTIVE_CONTEXT_POLICY_VERSION
    elif self.context_mode in {CONTEXT_MODE_ADAPTIVE_V2, CONTEXT_MODE_HISTORY}:
      from .context_policy import ADAPTIVE_V2_CONTEXT_POLICY_VERSION

      payload["context_policy_version"] = ADAPTIVE_V2_CONTEXT_POLICY_VERSION
    if self.escalation_policy != ESCALATION_POLICY_NONE:
      from .escalation_policy import escalation_policy_version_for_policy

      payload["escalation_policy_version"] = escalation_policy_version_for_policy(
        self.escalation_policy
      )
    return payload


@dataclass(frozen=True)
class ReviewBundle:
  run_dir: Path
  source_path: Path
  source_line_number: int
  record: dict[str, Any]
  candidate_id: str
  candidate_type: str
  state_id: str
  element_refs: tuple[dict[str, Any], ...]
  selection_reason: tuple[str, ...]
  required_context: tuple[str, ...]
  evidence: dict[str, Any]
  state_context: dict[str, Any]
  graph_context: dict[str, Any]
  artifact_refs: dict[str, Any]
  generator: dict[str, Any]
  primary_element_ref: dict[str, Any] | None = None

  @property
  def source_candidate_ref(self) -> dict[str, object]:
    return {
      "path": self._source_path_for_manifest(),
      "line_number": self.source_line_number,
    }

  @property
  def candidate_summary(self) -> dict[str, object]:
    return {
      "selection_reason": list(self.selection_reason),
      "required_context": list(self.required_context),
      "element_ref_count": len(self.element_refs),
      "has_graph_context": bool(self.graph_context),
      "has_artifact_refs": bool(self.artifact_refs),
    }

  def _source_path_for_manifest(self) -> str:
    try:
      return self.source_path.relative_to(self.run_dir).as_posix()
    except ValueError:
      return self.source_path.as_posix()


@dataclass(frozen=True)
class PromptTemplates:
  prompt_version: str
  system_template: str
  user_template: str
  type_guidance: dict[str, str]
  prompt_template_hash: str


@dataclass(frozen=True)
class ConfirmationPrompt:
  bundle: ReviewBundle
  prompt_version: str
  context_mode: str
  requested_context_mode: str
  selected_context_mode: str
  resolved_context_mode: str
  context_policy_version: str | None
  graph_context_included: bool
  graph_context_omitted_reason: str | None
  system_prompt: str
  user_prompt: str
  type_guidance: str
  prompt_template_hash: str
  prompt_hash: str


@dataclass(frozen=True)
class ConfirmationProviderResponse:
  provider: str
  model: str
  raw_content: str
  runtime_ms: int | None = None
  token_usage: dict[str, Any] | None = None
  estimated_cost_usd: float | None = None
  provider_metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ParsedConfirmation:
  candidate_id: str
  candidate_type: str
  state_id: str
  decision: ConfirmationDecision
  confidence: float
  reason: str
  supporting_evidence: tuple[str, ...]
  parse_status: ConfirmationParseStatus
  error: str | None = None
  citation_check: dict[str, Any] | None = None

  def __post_init__(self) -> None:
    if self.decision not in {"violation", "no_violation", "uncertain"}:
      raise ValueError(f"Unsupported confirmation decision: {self.decision}")
    if not 0.0 <= self.confidence <= 1.0:
      raise ValueError("`confidence` must be between 0.0 and 1.0")
    if not self.candidate_id:
      raise ValueError("`candidate_id` must not be empty")
    if not self.candidate_type:
      raise ValueError("`candidate_type` must not be empty")
    if not self.state_id:
      raise ValueError("`state_id` must not be empty")
