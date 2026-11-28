"""D5 review: the name and role screen readers get for each judged element, computed by Chromium's accessibility
engine on the recorded page (the DOM AccessGraph saved for the judged state, loaded without scripts). Free.

  python -m eval.d5_ax_names        # writes results/d5/ax_names.json and prints where it differs from the recording

Pilot review (2026-11-27): the recording's `accessible_name` of a region was its text when the region had no
aria-label, aria-labelledby or title, but screen readers give such a region no name. The review site's facts use the
name computed here, so that "read by screen readers" is what screen readers read.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "results" / "d5" / "export165"
RUNS = ROOT / "runs" / "w4a-d5"
OUT = ROOT / "results" / "d5" / "ax_names.json"
# covered: a dialog is open that does not contain the element, and it is modal (aria-modal, or the app hides
# everything behind it with aria-hidden, as MUI dialogs do)
COVERED = """xp => { const n = document.evaluate(xp, document, null, 9, null).singleNodeValue; if (!n) return false;
  const dialogs = [...document.querySelectorAll('[role=dialog], [role=alertdialog], dialog[open]')].filter(d => !d.contains(n));
  let hidden = false; for (let a = n.parentElement; a; a = a.parentElement) if (a.getAttribute('aria-hidden') === 'true') hidden = true;
  return dialogs.some(d => d.getAttribute('aria-modal') === 'true' || d.tagName === 'DIALOG' || hidden); }"""
UNHIDE = """xp => { let n = document.evaluate(xp, document, null, 9, null).singleNodeValue; const out = [];
  for (let a = n && n.parentElement; a; a = a.parentElement)
    if (a.getAttribute('aria-hidden') === 'true') { out.push(a.tagName.toLowerCase() + (a.id ? '#' + a.id : '')); a.removeAttribute('aria-hidden'); }
  return out; }"""


# an option in a list: the field whose drop-down list it is (the element that controls or owns the list)
OWNER = """xp => { const n = document.evaluate(xp, document, null, 9, null).singleNodeValue; const list = n && n.closest('[role=listbox], [role=menu]');
  if (!list || !list.id) return null;
  const base = list.id.endsWith('-listbox') ? document.getElementById(list.id.slice(0, -8)) : null;
  const ctl = [...document.querySelectorAll(`[aria-controls~="${list.id}"], [aria-owns~="${list.id}"]`)];
  const owner = base || ctl.find(e => e.matches('input, select, textarea, [role=combobox]')) || ctl[0];
  if (!owner) return null;
  owner.setAttribute('data-d5-owner', '1');
  const label = owner.id ? document.querySelector(`label[for="${CSS.escape(owner.id)}"]`) : null;
  return (label ? label.innerText : owner.innerText || owner.value || '').trim().replace(/\\s+/g, ' ').slice(0, 80); }"""


def _ax(cdp, expression: str) -> dict:
  """Chromium's accessibility node (role, name) for the element a JS expression returns."""
  remote = cdp.send("Runtime.evaluate", {"expression": expression})
  if "objectId" not in remote["result"]:
    return {}
  backend = cdp.send("DOM.describeNode", {"objectId": remote["result"]["objectId"]})["node"]["backendNodeId"]
  tree = cdp.send("Accessibility.getPartialAXTree", {"backendNodeId": backend, "fetchRelatives": False})["nodes"]
  node = tree[0] if tree else {}
  return {"role": (node.get("role") or {}).get("value") or "", "name": _norm((node.get("name") or {}).get("value"))}


def _norm(text) -> str:
  return " ".join(str(text or "").split())


def _recorded(ev: dict) -> tuple[str, str]:
  for value in ((ev.get("evidence") or {}).get("primary") or {}).values():
    if isinstance(value, dict) and value.get("element_id"):
      return _norm(value.get("accessible_name")), str(value.get("tag") or "")
  return "", ""


def main() -> int:
  from playwright.sync_api import sync_playwright
  key = sorted(csv.DictReader((SRC / "key_do_not_share.csv").open(encoding="utf-8")), key=lambda r: int(r["order"]))
  result, differs = {}, []
  with sync_playwright() as pw:
    browser = pw.chromium.launch()
    ctx = browser.new_context(java_script_enabled=False, viewport={"width": 1280, "height": 800})
    page = ctx.new_page()
    cdp = ctx.new_cdp_session(page)
    cdp.send("Accessibility.enable")
    for r in key:
      ev = json.loads((SRC / "items" / r["item_id"] / "evidence.json").read_text(encoding="utf-8"))
      xpath = ((ev.get("element_refs") or [{}])[0]).get("xpath") or ""
      dom = RUNS / r["app"] / "explore" / "states" / ev["state_id"] / "dom.html"
      if not xpath or not dom.exists():
        continue
      page.set_content(dom.read_text(encoding="utf-8", errors="ignore"), wait_until="domcontentloaded")
      # an open menu or dialog makes some apps hide everything behind it (aria-hidden on the app root); the question is
      # about the element itself, so its name is computed as it is once the overlay is closed
      covered = page.evaluate(COVERED, xpath)  # an open modal dialog that does not contain the element covers it
      hidden_by = page.evaluate(UNHIDE, xpath)
      handle = page.evaluate_handle("xp => document.evaluate(xp, document, null, 9, null).singleNodeValue", xpath)
      element = handle.as_element()
      if element is None:
        result[r["item_id"]] = {"found": False}
        continue
      remote = cdp.send("Runtime.evaluate", {"expression": f"document.evaluate({json.dumps(xpath)}, document, null, 9, null).singleNodeValue"})
      backend = cdp.send("DOM.describeNode", {"objectId": remote["result"]["objectId"]})["node"]["backendNodeId"]
      tree = cdp.send("Accessibility.getPartialAXTree", {"backendNodeId": backend, "fetchRelatives": False})["nodes"]
      ax = tree[0] if tree else {}
      name = _norm((ax.get("name") or {}).get("value"))
      role = (ax.get("role") or {}).get("value") or ""
      recorded, tag = _recorded(ev)
      result[r["item_id"]] = {"found": True, "role": role, "name": name, "ignored": bool(ax.get("ignored")),
                              "hidden_by_open_overlay": hidden_by, "covered_by_modal_dialog": covered, "recorded_name": recorded}
      if role in ("option", "menuitem"):  # PI's check: "option in a list" did not say which list
        shown = page.evaluate(OWNER, xpath)
        if shown is not None:
          result[r["item_id"]]["owner"] = {**_ax(cdp, "document.querySelector('[data-d5-owner]')"), "visible": shown}
      # path steps whose element has no text in the recording ("clicks a button without a visible name"): the name
      # screen readers read and the visible label, from the page the step starts on
      replay = json.loads((SRC / "items" / r["item_id"] / "replay.json").read_text(encoding="utf-8"))
      steps = {}
      for k, step in enumerate(replay["steps"]):
        action = step["action"] or {}
        if (action.get("text") or action.get("accessible_name")) or not (action.get("selector") or action.get("dom_path")):
          continue
        # React-made ids (":r3p:") change between renders: an id selector matches the right element on the page saved
        # right after the action (where the id was taken), a structural path on the page the step starts on
        by_id = "#" in str(action.get("selector") or "")
        for state, sel in ((step["to"], action.get("selector")), (step["from"], action.get("dom_path")), (step["from"], action.get("selector")))[0 if by_id else 1:]:
          sdom = RUNS / r["app"] / "explore" / "states" / state / "dom.html"
          if not sel or not sdom.exists():
            continue
          page.set_content(sdom.read_text(encoding="utf-8", errors="ignore"), wait_until="domcontentloaded")
          try:
            found = page.evaluate("s => !!document.querySelector(s)", sel)
          except Exception:
            found = False
          if found:
            node = _ax(cdp, f"document.querySelector({json.dumps(sel)})")
            node["visible_text"] = _norm(page.evaluate("s => document.querySelector(s).innerText || ''", sel))
            steps[str(k)] = node
            break
      if steps:
        result[r["item_id"]]["steps"] = steps
      if recorded != name:
        differs.append((r["order"], r["item_id"], r["type"], tag, role + (" ignored" if ax.get("ignored") else ""), recorded[:60], name[:60]))
    browser.close()
  OUT.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
  print(f"{len(result)} items; name differs from the recording for {len(differs)}:")
  for d in differs:
    print(f"  #{d[0]} {d[1]} {d[2]} <{d[3]}> role={d[4]}: recorded {d[5]!r} -> computed {d[6]!r}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
