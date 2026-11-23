"""Recorded states (regime R2) handed to tools that judge a live page: Rampa, InterA11y+, AccessGuru, VLM baselines.

One item per case: the run, the state, and the XPath(s) of the case's element. The state is handed over with the
spec's fallback (EVALUATION_SPEC Section 5, "Handing a recorded state to a live tool", step 3): `serve_state` serves
its saved DOM, with the app's scripts disabled, at the state's own route (so the URL a tool sees is the page's real
path and says nothing about the case), and the app's built assets around it. Every tool sees the recorded state and
nothing else. Each item records `handover = "static"`, and forward cases judged this way are reported apart.

Findings are linked to a case by element: a finding counts for the case when it names one of the case's success
criteria and its element is the case's element, inside it, or contains it; for page-level types (page title,
page language) any finding on the criterion counts.
"""
from __future__ import annotations

import functools
import json
import re
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from eval.adapters.ag_single import type_to_criteria, within  # noqa: E402
from eval.intera11y_dev import APP_DIST, _candidates, _states, _xpaths, serve, stage_page  # noqa: E402
from eval.predictions import read_gold  # noqa: E402

DEV = ROOT / "results" / "dev"
PAGE_LEVEL = {"page-title-not-descriptive", "lang-mismatch"}

# Absolute XPath with an index on every step, the format of AccessGraph's recorded element XPaths.
XPATH_JS = """(el) => {
  const steps = [];
  for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
    let index = 1;
    for (let sib = node.previousElementSibling; sib; sib = sib.previousElementSibling)
      if (sib.localName === node.localName) index++;
    steps.unshift(`${node.localName}[${index}]`);
  }
  return '/' + steps.join('/');
}"""


def items(gold_csv: Path = DEV / "gold.csv", links_jsonl: Path = DEV / "links.jsonl",
          types: set[str] | None = None) -> list[dict]:
  """One item per gold row (optionally only some types): where the tool is pointed and what links a finding."""
  criteria = type_to_criteria()
  links = {l["case_id"]: l for l in (json.loads(x) for x in links_jsonl.read_text().splitlines() if x.strip())}
  out = []
  for case in read_gold(gold_csv):
    if types and case.candidate_type not in types:
      continue
    link = links[case.case_id]
    run_dir = ROOT / link["run_dir"]
    source, state_id = None, None
    if link["candidate_ids"]:
      source = _candidates(run_dir)[link["candidate_ids"][0]]
      state_id = source["state_id"]
    elif case.case_kind == "clean_twin":  # no candidate on the clean element: the seeded element's place
      seeded = links[case.case_id.split("~")[0]]
      if seeded["candidate_ids"]:
        seeded_dir = ROOT / seeded["run_dir"]
        source = _candidates(seeded_dir)[seeded["candidate_ids"][0]]
        want = _states(seeded_dir)[source["state_id"]]
        state_id = next((sid for sid, s in _states(run_dir).items()
                         if s.get("benchmark_state_id") == want.get("benchmark_state_id")
                         and s.get("focused_state_name") == want.get("focused_state_name")), None)
    out.append({"case_id": case.case_id, "app": case.app, "candidate_type": case.candidate_type,
                "criteria": criteria.get(case.candidate_type, []), "run_dir": link["run_dir"],
                "state_id": state_id, "xpaths": _xpaths(source, case.candidate_type) if source else [],
                "page_level": case.candidate_type in PAGE_LEVEL, "handover": "static"})
  return out


def serve_state(item: dict) -> tuple[ThreadingHTTPServer, str]:
  """Serve one recorded state at its own route on a fresh port; return the server and the page URL."""
  run_dir = ROOT / item["run_dir"]
  route = (_states(run_dir)[item["state_id"]].get("route") or "/").split("?")[0].split("#")[0] or "/"
  dom = (run_dir / "states" / item["state_id"] / "dom.html").read_text(encoding="utf-8")
  # the first `type` attribute wins in HTML, so this disables every script without moving any element
  body = re.sub(r"<script\b", '<script type="text/plain" data-w4a-disabled=""', dom, flags=re.IGNORECASE).encode()

  class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
      if urlsplit(self.path).path.rstrip("/") == route.rstrip("/"):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
      else:
        super().do_GET()

    def log_message(self, *args):
      pass

  server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Handler, directory=str(APP_DIST[item["app"]])))
  threading.Thread(target=server.serve_forever, daemon=True).start()
  return server, f"http://127.0.0.1:{server.server_address[1]}{route}"


def finding_matches(item: dict, criterion: str, xpath: str | None) -> bool:
  if criterion not in item["criteria"]:
    return False
  if item["page_level"]:
    return True
  return any(within(xpath, x) or within(x, xpath) for x in item["xpaths"]) if xpath else False


__all__ = ["items", "finding_matches", "serve_state", "serve", "stage_page", "XPATH_JS"]
