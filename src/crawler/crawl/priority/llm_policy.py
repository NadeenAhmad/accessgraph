"""LLM-guided exploration (C1): rank a state's actions and propose form values, once per state expansion.

The model only orders actions and proposes form values. It never decides state identity, what is recorded, or
any accessibility verdict. If the call fails, the crawler falls back to discovery order. The provider is built
through the judge's provider registry (no separate HTTP client); providers expose `complete_json`.
"""
from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
  from playwright.async_api import Page
else:
  Page = Any

from ..actions.discovery import ActionCandidate
from ..actions.forms import FormSpec
from .common import CandidatePriorityEvaluation

MAX_HEADINGS = 12
MAX_VISIBLE_TEXT = 600
MAX_ACTIONS_IN_PROMPT = 40
MAX_INVALID_SETS = 2

PAGE_SUMMARY_JS = r"""
(limits) => {
  const visible = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const headings = Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6,[role="heading"]')).filter(visible)
    .slice(0, limits.headings).map((h) => ({ level: Number(h.getAttribute('aria-level') || h.tagName.slice(1)) || 2,
      text: (h.innerText || '').trim().slice(0, 100) }));
  const landmarkSel = 'main,nav,aside,header,footer,form[aria-label],form[aria-labelledby],section[aria-label],section[aria-labelledby],[role="main"],[role="navigation"],[role="complementary"],[role="banner"],[role="contentinfo"],[role="region"],[role="search"],[role="dialog"],dialog[open]';
  const landmarks = Array.from(document.querySelectorAll(landmarkSel)).filter(visible).slice(0, 15).map((el) => ({
    role: el.getAttribute('role') || el.tagName.toLowerCase(),
    name: (el.getAttribute('aria-label') || (el.getAttribute('aria-labelledby') ? (document.getElementById(el.getAttribute('aria-labelledby'))?.innerText || '') : '')).trim().slice(0, 80) }));
  const root = document.querySelector('main,[role="main"]') || document.body;
  return { title: document.title, route: location.pathname + location.search + location.hash, headings, landmarks,
           visible_text: (root.innerText || '').replace(/\s+/g, ' ').trim().slice(0, limits.text) };
}
"""

SYSTEM_PROMPT = """You help a crawler explore a single-page web application within a small action budget.
You see one state of the app and the actions available in it. Rank the action ids so that actions most likely to
reveal new, different app states come first: new pages or steps, dialogs, expanded panels, filtered lists, error
and confirmation messages. Put actions that repeat what was already seen, or only reload the same content, last.
For each form, propose exactly one realistic valid value set (it should pass validation) and up to two invalid value
sets that a real user could plausibly enter (e.g. a required field left empty, a wrong format, an out-of-range
number), so that the app's validation and error states are reached. A "formless" entry is a group of fields
outside any form: filling it does not submit anything, the page reacts to the input (for example a date shows
available times), and the page's own buttons continue. Use only the given field ids and, for select
and radio fields, only the listed options. Use "true"/"false" for checkboxes. Never invent personal data of real
people; use obviously fictional values. Give a one-sentence rationale for the order. Only order actions and
propose values; do not judge the page."""

RESPONSE_SCHEMA: dict[str, Any] = {
  "type": "object",
  "additionalProperties": False,
  "required": ["rationale", "ranking", "forms"],
  "properties": {
    "rationale": {"type": "string"},
    "ranking": {"type": "array", "items": {"type": "string"}},
    "forms": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["form_id", "value_sets"],
        "properties": {
          "form_id": {"type": "string"},
          "value_sets": {
            "type": "array",
            "items": {
              "type": "object",
              "additionalProperties": False,
              "required": ["kind", "values"],
              "properties": {
                "kind": {"type": "string", "enum": ["valid", "invalid"]},
                "values": {
                  "type": "array",
                  "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["field", "value"],
                    "properties": {"field": {"type": "string"}, "value": {"type": "string"}},
                  },
                },
              },
            },
          },
        },
      },
    },
  },
}


@dataclass(frozen=True)
class LLMPolicyConfig:
  provider: str = "fake"
  model: str = ""
  temperature: float = 0.0
  timeout_s: float = 60.0
  effort: str | None = None
  use_screenshot: bool = True


@dataclass
class ExplorationPlan:
  ranking: dict[str, int]                                   # candidate identity -> rank (0 = first)
  value_sets: dict[str, list[tuple[str, dict[str, str]]]]   # form selector -> [(kind, {field selector: value})]
  source: str                                               # llm | fake | fallback
  cost_usd: float = 0.0
  rationale: str = ""

  def evaluator(self) -> Callable[[ActionCandidate], CandidatePriorityEvaluation]:
    """Ranked actions first in the model's order; unranked ones after, in discovery order (ties keep order)."""
    size = len(self.ranking)

    def rank_score(candidate: ActionCandidate) -> CandidatePriorityEvaluation:
      rank = self.ranking.get(plan_key(candidate))
      score = (size - rank) if rank is not None else 0
      flags = (f"llm_rank_{rank}",) if rank is not None else ("llm_unranked",)
      return CandidatePriorityEvaluation(score=score, group="llm", region="", reason_flags=flags)

    return rank_score


def form_key(form_selector: str, kind: str) -> str:
  return f"form::{form_selector}::{kind}"


def plan_key(candidate: ActionCandidate) -> str:
  if candidate.action_type == "fill_submit":
    return form_key(candidate.selector, candidate.value_set_kind)
  return candidate.identity


def action_label(candidate: ActionCandidate) -> str:
  verb = {"hover": "hover over", "key": f"press {candidate.key or 'a key'} on"}.get(candidate.action_type,
                                                                                     candidate.action_type)
  parts = [verb, candidate.role or candidate.tag_name]
  name = candidate.aria_label or candidate.text or candidate.label_text
  if name:
    parts.append(repr(name.strip()[:80]))
  if candidate.href:
    parts.append(f"href={candidate.href[:80]}")
  if candidate.nearby_heading:
    parts.append(f"near heading {candidate.nearby_heading[:60]!r}")
  return " ".join(p for p in parts if p)


def build_user_prompt(summary: dict[str, Any], actions: list[tuple[str, str]], forms: list[FormSpec],
                      tried: list[str], seen: list[str]) -> str:
  payload = {
    "state": {"title": summary.get("title", ""), "route": summary.get("route", ""),
              "headings": summary.get("headings", []), "landmarks": summary.get("landmarks", []),
              "visible_text": summary.get("visible_text", "")},
    "actions": [{"id": action_id, "action": label} for action_id, label in actions],
    "forms": [form.describe() for form in forms],
    "actions_already_tried_here": tried[:30],
    "routes_and_titles_already_seen": seen[:40],
  }
  return "Plan the exploration of this state.\n" + json.dumps(payload, ensure_ascii=False, indent=1)


def heuristic_value_sets(form: FormSpec) -> list[tuple[str, dict[str, str]]]:
  """Offline value sets (fake provider and fallback): one valid set, one with the first required field empty."""
  valid: dict[str, str] = {}
  for f in form.fields:
    if f.kind in ("select", "radio"):
      options = [o for o in f.options if o]
      if options:
        valid[f.selector] = options[0]
    elif f.kind == "checkbox":
      valid[f.selector] = "true" if f.required else "false"
    else:
      valid[f.selector] = _sample_text(f.type, f.autocomplete, f.min)
  sets = [("valid", valid)]
  required = [f for f in form.fields if f.required and f.kind == "text"]
  if required:
    invalid = dict(valid)
    invalid[required[0].selector] = ""
    sets.append(("invalid", invalid))
  return sets


def _sample_text(input_type: str, autocomplete: str, minimum: str) -> str:
  hint = f"{input_type} {autocomplete}".lower()
  if "email" in hint:
    return "alex.example@example.com"
  if "tel" in hint:
    return "+15550100"
  if "date" in hint:
    return "2027-03-15"
  if "number" in hint or "range" in hint:
    return minimum or "1"
  if "postal" in hint or "zip" in hint:
    return "10115"
  if "url" in hint:
    return "https://example.com"
  if "name" in hint:
    return "Alex Example"
  return "Example text"


class LLMExplorationPolicy:
  """One model call per state expansion (cached for that expansion); logs every decision."""

  def __init__(self, cfg: LLMPolicyConfig, *, client: Any | None = None, log_path: Path | None = None,
               client_factory: Callable[[LLMPolicyConfig], Any] | None = None):
    self.cfg = cfg
    self._client = client
    self._client_factory = client_factory or _build_client
    self.log_path = log_path
    self._plans: dict[str, ExplorationPlan] = {}
    self.counters = {"llm_calls": 0, "llm_fallbacks": 0, "plans_cached": 0, "form_value_sets": 0,
                     "cost_usd": 0.0}

  @property
  def client(self) -> Any:
    if self._client is None and self.cfg.provider != "fake":
      self._client = self._client_factory(self.cfg)
    return self._client

  def cached_plan(self, state_id: str) -> ExplorationPlan | None:
    plan = self._plans.get(state_id)
    if plan is not None:
      self.counters["plans_cached"] += 1
    return plan

  async def plan(self, page: Page, *, state_id: str, candidates: list[ActionCandidate], forms: list[FormSpec],
                 tried: list[str], seen: list[str]) -> ExplorationPlan:
    if state_id in self._plans:
      return self._plans[state_id]
    started = time.perf_counter()
    if self.cfg.provider == "fake":
      plan = ExplorationPlan(ranking={}, value_sets={f.selector: heuristic_value_sets(f) for f in forms}, source="fake")
      error = None
    else:
      try:
        plan = await self._llm_plan(page, candidates, forms, tried, seen)
        error = None
      except Exception as exc:  # any failure -> discovery order, never a crash
        self.counters["llm_fallbacks"] += 1
        plan = ExplorationPlan(ranking={}, value_sets={f.selector: heuristic_value_sets(f) for f in forms},
                               source="fallback")
        error = f"{type(exc).__name__}: {str(exc)[:200]}"
    self.counters["form_value_sets"] += sum(len(v) for v in plan.value_sets.values())
    self.counters["cost_usd"] += plan.cost_usd
    self._plans[state_id] = plan
    self._log({"event": "plan", "state_id": state_id, "source": plan.source, "error": error,
               "candidates": len(candidates), "ranked": len(plan.ranking), "forms": len(forms),
               "value_sets": {k: [kind for kind, _ in v] for k, v in plan.value_sets.items()},
               "rationale": plan.rationale, "cost_usd": plan.cost_usd,
               "seconds": round(time.perf_counter() - started, 3)})
    return plan

  async def _llm_plan(self, page: Page, candidates: list[ActionCandidate], forms: list[FormSpec],
                      tried: list[str], seen: list[str]) -> ExplorationPlan:
    summary = await page.evaluate(PAGE_SUMMARY_JS, {"headings": MAX_HEADINGS, "text": MAX_VISIBLE_TEXT})
    listed = [c for c in candidates if c.identity][:MAX_ACTIONS_IN_PROMPT]
    ids = {f"a{i + 1}": c.identity for i, c in enumerate(listed)}
    actions = [(f"a{i + 1}", action_label(c)) for i, c in enumerate(listed)]
    for i, form in enumerate(forms):
      name = form.name or form.submit_text or form.form_id
      for kind, text in (("valid", "valid values"), ("invalid-1", "invalid values (set 1)"),
                         ("invalid-2", "invalid values (set 2)")):
        action_id = f"f{i + 1}-{kind}"
        ids[action_id] = form_key(form.selector, kind)
        verb = "fill (no submit) the fields of" if form.formless else "fill and submit form"
        actions.append((action_id, f"{verb} {name!r} ({form.form_id}) with {text}"))
    images = []
    if self.cfg.use_screenshot and "vision" in self.cfg.provider:
      shot = await page.screenshot(type="png")
      images.append("data:image/png;base64," + base64.b64encode(shot).decode("ascii"))
    response = self.client.complete_json(system=SYSTEM_PROMPT, user=build_user_prompt(summary, actions, forms, tried, seen),
                                         schema=RESPONSE_SCHEMA, schema_name="accessgraph_exploration_plan",
                                         image_data_urls=images)
    self.counters["llm_calls"] += 1
    data = json.loads(response.raw_content)
    ranking: dict[str, int] = {}
    for action_id in data.get("ranking", []):
      identity = ids.get(str(action_id))
      if identity and identity not in ranking:
        ranking[identity] = len(ranking)
    by_id = {f.form_id: f for f in forms}
    value_sets: dict[str, list[tuple[str, dict[str, str]]]] = {}
    for entry in data.get("forms", []):
      form = by_id.get(str(entry.get("form_id")))
      if form is None:
        continue
      known = {f.selector for f in form.fields}
      sets: list[tuple[str, dict[str, str]]] = []
      valid_seen = invalid_seen = 0
      for value_set in entry.get("value_sets", []):
        kind = value_set.get("kind")
        values = {str(v.get("field")): str(v.get("value")) for v in value_set.get("values", [])
                  if str(v.get("field")) in known}
        if not values:
          continue
        if kind == "valid" and valid_seen == 0:
          valid_seen += 1
          sets.append(("valid", values))
        elif kind == "invalid" and invalid_seen < MAX_INVALID_SETS:
          invalid_seen += 1
          sets.append((f"invalid-{invalid_seen}", values))
      value_sets[form.selector] = sets or heuristic_value_sets(form)
    for form in forms:
      value_sets.setdefault(form.selector, heuristic_value_sets(form))
    return ExplorationPlan(ranking=ranking, value_sets=value_sets, source="llm",
                           cost_usd=float(response.estimated_cost_usd or 0.0),
                           rationale=str(data.get("rationale") or "")[:300])

  def log_event(self, record: dict[str, Any]) -> None:
    self._log(record)

  def _log(self, record: dict[str, Any]) -> None:
    if self.log_path is None:
      return
    self.log_path.parent.mkdir(parents=True, exist_ok=True)
    with self.log_path.open("a", encoding="utf-8") as handle:
      handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _build_client(cfg: LLMPolicyConfig) -> Any:
  from src.analysis.confirmation.models import ConfirmationConfig
  from src.analysis.confirmation.providers.registry import build_confirmation_client, resolve_confirmation_config

  client = build_confirmation_client(resolve_confirmation_config(ConfirmationConfig(
    provider=cfg.provider, model=cfg.model, temperature=cfg.temperature, timeout_seconds=cfg.timeout_s,
    effort=cfg.effort)))
  if not hasattr(client, "complete_json"):
    raise ValueError(f"provider {cfg.provider!r} does not support LLM exploration (no complete_json)")
  return client
