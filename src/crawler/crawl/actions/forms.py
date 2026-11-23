"""Fill-and-submit actions (C1).

A form becomes one `fill_submit` action per value set (one valid set and up to two invalid ones, proposed by the
exploration policy). The action fills every field and then submits the form; it is recorded as a single edge
and can be replayed from its recorded values. Forms are never filled on hosts outside `allow_hosts`, and forms
with password or file inputs are always skipped; every skip is logged by the caller.

Fields outside any <form> (frequent in SPAs) form a "field group" per section-like container: the same action
fills them but does not submit, because such pages react to the input and continue through their own buttons,
which stay ordinary click actions.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:
  from playwright.async_api import Page
else:
  Page = Any

from .discovery import ActionCandidate

MAX_FORMS_PER_STATE = 4
MAX_FIELDS_PER_FORM = 20
FILL_SUBMIT = "fill_submit"

FORM_DISCOVERY_JS = r"""
(maxFields) => {
  const visible = (el) => {
    const s = window.getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return s.visibility !== 'hidden' && s.display !== 'none' && r.width > 0 && r.height > 0;
  };
  const cssPath = (el) => {
    if (el.id) return `#${CSS.escape(el.id)}`;
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && parts.length < 8) {
      let part = node.tagName.toLowerCase();
      if (node.id) { parts.unshift(`#${CSS.escape(node.id)}`); break; }
      const parent = node.parentElement;
      if (parent) {
        const same = Array.from(parent.children).filter((c) => c.tagName === node.tagName);
        if (same.length > 1) part += `:nth-of-type(${same.indexOf(node) + 1})`;
      }
      parts.unshift(part);
      node = parent;
    }
    return parts.join(' > ');
  };
  const labelOf = (el) => {
    const labelled = el.getAttribute('aria-labelledby');
    if (labelled) {
      const text = labelled.split(/\s+/).map((id) => document.getElementById(id)?.innerText || '').join(' ').trim();
      if (text) return text;
    }
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    if (el.labels && el.labels.length) return Array.from(el.labels).map((l) => l.innerText).join(' ').trim();
    return el.getAttribute('placeholder') || el.getAttribute('name') || '';
  };
  const fieldsOf = (controls) => {
    const fields = [];
    const seenRadio = new Set();
    for (const c of controls) {
      const tag = c.tagName.toLowerCase();
      const type = (c.getAttribute('type') || (tag === 'select' ? 'select' : tag === 'textarea' ? 'textarea' : 'text')).toLowerCase();
      if (['submit', 'button', 'reset', 'image', 'hidden'].includes(type) || tag === 'button') continue;
      if (c.disabled || c.readOnly) continue;
      if (type === 'radio') {
        if (!c.name || seenRadio.has(c.name)) continue;
        seenRadio.add(c.name);
        const group = controls.filter((o) => (o.getAttribute('type') || '').toLowerCase() === 'radio' && o.name === c.name);
        fields.push({ selector: `input[type="radio"][name="${CSS.escape(c.name)}"]`, kind: 'radio', label: labelOf(c),
          name: c.name, required: group.some((o) => o.required), options: group.map((o) => o.value) });
        continue;
      }
      if (!visible(c) && type !== 'checkbox') continue;
      fields.push({
        selector: cssPath(c), kind: tag === 'select' ? 'select' : (type === 'checkbox' ? 'checkbox' : 'text'),
        type, label: labelOf(c).slice(0, 120), name: c.getAttribute('name') || '',
        autocomplete: c.getAttribute('autocomplete') || '', required: !!c.required || c.getAttribute('aria-required') === 'true',
        pattern: c.getAttribute('pattern') || '', min: c.getAttribute('min') || '', max: c.getAttribute('max') || '',
        minlength: c.getAttribute('minlength') || '', maxlength: c.getAttribute('maxlength') || '',
        options: tag === 'select' ? Array.from(c.options).map((o) => o.value).slice(0, 30) : [],
      });
      if (fields.length >= maxFields) break;
    }
    return fields;
  };
  const nameOf = (el) => (el.getAttribute('aria-label') || (el.getAttribute('aria-labelledby')
      ? (document.getElementById(el.getAttribute('aria-labelledby'))?.innerText || '') : '')
      || el.querySelector('h1,h2,h3,h4,legend')?.innerText || el.getAttribute('name') || el.id || '').trim().slice(0, 120);
  const forms = [];
  for (const form of Array.from(document.querySelectorAll('form'))) {
    if (!visible(form)) continue;
    const controls = Array.from(form.elements || []).filter((c) => !['fieldset', 'object', 'output'].includes(c.tagName.toLowerCase()));
    const types = controls.map((c) => (c.getAttribute('type') || '').toLowerCase());
    const submit = controls.find((c) => {
      const tag = c.tagName.toLowerCase();
      const type = (c.getAttribute('type') || '').toLowerCase();
      return visible(c) && ((tag === 'button' && (!type || type === 'submit')) || (tag === 'input' && (type === 'submit' || type === 'image')));
    });
    const fields = fieldsOf(controls);
    const name = form.getAttribute('aria-label') || (form.getAttribute('aria-labelledby')
      ? (document.getElementById(form.getAttribute('aria-labelledby'))?.innerText || '') : '')
      || form.querySelector('h1,h2,h3,h4,legend')?.innerText || form.getAttribute('name') || form.id || '';
    forms.push({
      selector: cssPath(form), name: name.trim().slice(0, 120), action: form.getAttribute('action') || '',
      method: (form.getAttribute('method') || 'get').toLowerCase(),
      has_password: types.includes('password'), has_file: types.includes('file'),
      submit_selector: submit ? cssPath(submit) : '', submit_text: submit ? (submit.innerText || submit.value || '').trim().slice(0, 80) : '',
      fields, formless: false,
    });
  }
  // Fields outside any <form> (common in SPAs: the page reacts to input, and a separate button continues).
  // They are grouped by their nearest section-like container; a group is offered only if it has a text-like
  // field, because radios, selects and buttons outside forms are already ordinary click/select actions.
  const textLike = (c) => {
    const tag = c.tagName.toLowerCase();
    const type = (c.getAttribute('type') || 'text').toLowerCase();
    return tag === 'textarea' || (tag === 'input' && !['submit', 'button', 'reset', 'image', 'hidden', 'radio', 'checkbox', 'file', 'password', 'range', 'color'].includes(type));
  };
  const groups = new Map();
  for (const c of Array.from(document.querySelectorAll('input, select, textarea'))) {
    if (c.form || c.closest('form')) continue;
    const container = c.closest('fieldset, section, [role="group"], [role="region"], [role="form"], article, main') || document.body;
    if (!groups.has(container)) groups.set(container, []);
    groups.get(container).push(c);
  }
  for (const [container, controls] of groups) {
    if (!visible(container) || !controls.some((c) => textLike(c) && visible(c) && !c.disabled && !c.readOnly)) continue;
    const types = controls.map((c) => (c.getAttribute('type') || '').toLowerCase());
    forms.push({
      selector: cssPath(container), name: nameOf(container), action: '', method: 'none',
      has_password: types.includes('password'), has_file: types.includes('file'),
      submit_selector: '', submit_text: '', fields: fieldsOf(controls), formless: true,
    });
  }
  return forms;
}
"""


@dataclass(frozen=True)
class FormField:
  selector: str
  kind: str  # text | select | checkbox | radio
  type: str = ""
  label: str = ""
  name: str = ""
  autocomplete: str = ""
  required: bool = False
  pattern: str = ""
  min: str = ""
  max: str = ""
  minlength: str = ""
  maxlength: str = ""
  options: tuple[str, ...] = ()

  def describe(self) -> dict[str, Any]:
    out = {"id": self.selector, "kind": self.kind, "type": self.type, "label": self.label, "name": self.name,
           "required": self.required}
    for key in ("autocomplete", "pattern", "min", "max", "minlength", "maxlength"):
      if getattr(self, key):
        out[key] = getattr(self, key)
    if self.options:
      out["options"] = list(self.options)
    return out


@dataclass(frozen=True)
class FormSpec:
  form_id: str
  selector: str
  name: str
  action: str
  method: str
  submit_selector: str
  submit_text: str
  has_password: bool
  has_file: bool
  fields: tuple[FormField, ...] = field(default_factory=tuple)
  formless: bool = False  # fields outside any <form>: filled, never submitted (the page's own buttons continue)

  def describe(self) -> dict[str, Any]:
    out = {"form_id": self.form_id, "name": self.name, "submit": self.submit_text,
           "fields": [f.describe() for f in self.fields]}
    if self.formless:
      out["formless"] = True
    return out


@dataclass(frozen=True)
class FormSkip:
  form_selector: str
  reason: str


def host_allowed(url: str, allow_hosts: tuple[str, ...] | list[str]) -> bool:
  parsed = urlparse(url)
  if parsed.scheme == "file":  # a page saved on the auditor's machine; allowed only by the explicit entry "file:"
    return "file:" in allow_hosts
  host = (parsed.hostname or "").lower()
  return bool(host) and host in {h.lower() for h in allow_hosts}


async def discover_forms(page: Page, *, allow_hosts: tuple[str, ...]) -> tuple[list[FormSpec], list[FormSkip]]:
  """Fillable forms on the current page, and the forms skipped with a reason."""
  if not host_allowed(page.url, allow_hosts):
    return [], []
  try:
    raw_forms = await page.evaluate(FORM_DISCOVERY_JS, MAX_FIELDS_PER_FORM)
  except Exception:
    return [], []
  forms: list[FormSpec] = []
  skips: list[FormSkip] = []
  for index, raw in enumerate(raw_forms or []):
    selector = str(raw.get("selector") or "")
    if raw.get("has_password"):
      skips.append(FormSkip(selector, "password_input"))
      continue
    if raw.get("has_file"):
      skips.append(FormSkip(selector, "file_input"))
      continue
    fields = tuple(
      FormField(
        selector=str(f.get("selector") or ""), kind=str(f.get("kind") or "text"), type=str(f.get("type") or ""),
        label=str(f.get("label") or ""), name=str(f.get("name") or ""), autocomplete=str(f.get("autocomplete") or ""),
        required=bool(f.get("required")), pattern=str(f.get("pattern") or ""), min=str(f.get("min") or ""),
        max=str(f.get("max") or ""), minlength=str(f.get("minlength") or ""), maxlength=str(f.get("maxlength") or ""),
        options=tuple(str(o) for o in (f.get("options") or [])),
      )
      for f in raw.get("fields") or []
      if f.get("selector")
    )
    if not fields:
      skips.append(FormSkip(selector, "no_fillable_fields"))
      continue
    formless = bool(raw.get("formless"))
    if not formless and not raw.get("submit_selector"):
      skips.append(FormSkip(selector, "no_submit_control"))
      continue
    forms.append(FormSpec(
      form_id=f"{'fields' if formless else 'form'}-{index}", selector=selector, name=str(raw.get("name") or ""),
      action=str(raw.get("action") or ""), method=str(raw.get("method") or "get"),
      submit_selector=str(raw.get("submit_selector") or ""), submit_text=str(raw.get("submit_text") or ""),
      has_password=False, has_file=False, fields=fields, formless=formless,
    ))
    if len(forms) >= MAX_FORMS_PER_STATE:
      break
  return forms, skips


def _values_digest(values: tuple[tuple[str, str], ...]) -> str:
  return hashlib.sha256(json.dumps(values, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def fill_submit_candidate(page: Page, form: FormSpec, kind: str, values: dict[str, str]) -> ActionCandidate | None:
  """One fill_submit candidate for a value set; values for unknown fields are dropped."""
  known = {f.selector for f in form.fields}
  pairs = tuple(sorted((sel, str(val)) for sel, val in values.items() if sel in known))
  if not pairs:
    return None
  label = f"{form.name or form.submit_text or 'form'} [{kind} values{', no submit' if form.formless else ''}]"
  return ActionCandidate(
    locator=page.locator(form.submit_selector or pairs[0][0]).first,
    action_type=FILL_SUBMIT,  # type: ignore[arg-type]
    strategy_name="forms",
    identity=f"fill_submit|{form.selector}|{kind}|{_values_digest(pairs)}",
    text=label[:120],
    tag_name="form",
    selector=form.selector,
    form_values=pairs,
    value_set_kind=kind,
    form_submit_selector=form.submit_selector,
  )


async def perform_fill_submit(page: Page, candidate: ActionCandidate, *, timeout_ms: int) -> bool:
  """Fill every recorded field, then submit with the form's own submit control."""
  form = page.locator(candidate.selector).first
  if await form.count() == 0:
    return False
  for selector, value in candidate.form_values:
    target = page.locator(selector)
    if await target.count() == 0:
      return False
    tag_type = await target.first.evaluate(
      "(el) => [el.tagName.toLowerCase(), (el.getAttribute('type') || '').toLowerCase()]")
    tag, input_type = tag_type
    if tag == "select":
      await target.first.select_option(value=value, timeout=timeout_ms)
    elif input_type == "radio":
      option = page.locator(f"{selector}[value=\"{value}\"]")
      if await option.count() == 0:
        return False
      await option.first.check(timeout=timeout_ms)
    elif input_type == "checkbox":
      wanted = value.strip().lower() in {"true", "1", "yes", "on", "checked"}
      if wanted != await target.first.is_checked():
        await target.first.set_checked(wanted, timeout=timeout_ms)
    else:
      await target.first.fill(value, timeout=timeout_ms)
  if not candidate.form_submit_selector:  # formless field group: the input itself is the action
    last = page.locator(candidate.form_values[-1][0]).first
    await last.evaluate("(el) => { el.dispatchEvent(new Event('change', {bubbles: true})); el.blur(); }")
    return True
  submit = page.locator(candidate.form_submit_selector).first
  if await submit.count() == 0:
    return False
  await submit.click(timeout=timeout_ms)
  return True


def candidate_from_replay_meta(page: Page, replay_action: dict[str, object]) -> ActionCandidate | None:
  """Rebuild a fill_submit action from its recorded edge metadata (for restore by replay)."""
  values = replay_action.get("form_values")
  if replay_action.get("type") != FILL_SUBMIT or not isinstance(values, list):
    return None
  pairs = tuple((str(sel), str(val)) for sel, val in values)
  if not pairs:
    return None
  return ActionCandidate(
    locator=page.locator(str(replay_action.get("form_submit_selector") or "") or pairs[0][0]).first,
    action_type=FILL_SUBMIT,  # type: ignore[arg-type]
    strategy_name="forms",
    identity=str(replay_action.get("identity") or ""),
    text=str(replay_action.get("text") or ""),
    tag_name="form",
    selector=str(replay_action.get("selector") or ""),
    form_values=pairs,
    value_set_kind=str(replay_action.get("value_set_kind") or ""),
    form_submit_selector=str(replay_action.get("form_submit_selector") or ""),
  )
