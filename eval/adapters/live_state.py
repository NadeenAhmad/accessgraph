"""Live handover of a recorded state to another tool (EVALUATION_SPEC Section 5, "Handing a recorded state to a live
tool", steps 1-2; W4A phase 4).

The app runs locally. A browser opens the state's start URL and AccessGraph's own restore logic replays the recorded
path to the state (the same replay the explorer uses, including the match checks), so the tool gets a working page
in that state: its scripts run, and pressing a control does what it does in the app.

- Rampa: `rampa_check_live()` replays in a Chromium with a debugging port, then Rampa's own Playwright API
  (`checkPage`, dist/playwright.mjs) checks that page over CDP.
- InterA11y: `ReplayService` is a small local HTTP service. With InterA11y's local patch
  (eval/patches/intera11y-8dcf06e-live-replay.patch) every page InterA11y opens, including the fresh pages its tools
  open, calls the service, which replays the path on that very page (found over CDP by a token in window.name).

A failed replay is reported, and the case falls back to the static handover (logged; spec step 3).
"""
from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any

RAMPA = Path.home() / "w4a-external" / "rampa-cli"
ALLOW_HOSTS = ("127.0.0.1", "localhost")


def _rebase(value: Any, old: str, new: str) -> Any:
  if isinstance(value, str):
    return new + value[len(old):] if old and value.startswith(old) else value
  if isinstance(value, dict):
    return {k: _rebase(v, old, new) for k, v in value.items()}
  if isinstance(value, list):
    return [_rebase(v, old, new) for v in value]
  return value


def _graph(run_dir: Path, base_url: str | None = None) -> tuple[SimpleNamespace, str, str]:
  """The recorded states; with `base_url`, the recorded origin is replaced by where the app runs now."""
  from urllib.parse import urlsplit
  data = json.loads((run_dir / "graph.json").read_text(encoding="utf-8"))
  if base_url:
    first = urlsplit(str(data["nodes"][0].get("url") or ""))
    data = _rebase(data, f"{first.scheme}://{first.netloc}", base_url.rstrip("/"))
  nodes = {n["state_id"]: n for n in data["nodes"]}
  start = str(data.get("start_state") or data["nodes"][0]["state_id"])
  return SimpleNamespace(nodes=nodes), start, str(nodes[start].get("url") or "")


async def replay_on_page(page, run_dir: Path, state_id: str, base_url: str | None = None) -> dict[str, Any]:
  """Bring `page` to the recorded state by replaying its path; returns {ok, url, how}."""
  import functools
  from src.crawler.crawl.actions import get_action_candidates
  from src.crawler.crawl.actions.execution import ActionTimeout, perform_action
  from src.crawler.crawl.navigation.restore import StateRestorer, _best_effort_back, _navigate_to_url
  graph, start, start_url = _graph(Path(run_dir), base_url)
  state_url = str(graph.nodes.get(state_id, {}).get("url") or start_url)

  def noop(*_args, **_kwargs):
    return None

  def saved_html(sid: str) -> str | None:
    try:
      return (Path(run_dir) / "states" / sid / "dom.html").read_text(encoding="utf-8", errors="replace")
    except OSError:
      return None

  restorer = StateRestorer(
    page=page, graph=graph, state_html_loader=saved_html, start_url=start_url, back_timeout_ms=10_000,
    replay_candidate_scan_limit=60, in_scope=lambda _url: True, root_state_id_getter=lambda: start,
    increment_coverage=noop, record_replay_attempt_metrics=noop, record_replay_failure=noop,
    get_action_candidates_fn=functools.partial(get_action_candidates, allow_hosts=ALLOW_HOSTS),
    perform_action_fn=perform_action, action_timeout_type=ActionTimeout, navigate_to_url_fn=_navigate_to_url,
    best_effort_back_fn=_best_effort_back)
  try:
    ok = await restorer.restore_state(state_id, state_url, force=True)
  except Exception as error:
    return {"ok": False, "error": f"{type(error).__name__}: {str(error)[:200]}"}
  return {"ok": bool(ok), "url": page.url}


def _free_port() -> int:
  with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    return s.getsockname()[1]


async def _replay_then_rampa(run_dir: Path, state_id: str, out_file: Path, model: str, env: dict,
                            base_url: str | None, init_script: str | None,
                            cache_dir: Path | None = None) -> dict[str, Any]:
  from eval.adapters.recorded import XPATH_JS
  from playwright.async_api import async_playwright
  port = _free_port()
  async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True, args=[f"--remote-debugging-port={port}"])
    try:
      context = await browser.new_context(viewport={"width": 1280, "height": 800})
      if init_script:  # the benchmark app's profile (e.g. its seeded variant), set before every load
        await context.add_init_script(init_script)
      page = await context.new_page()
      token = f"w4a-{port}"
      replay = await replay_on_page(page, run_dir, state_id, base_url)
      if not replay.get("ok"):
        return {"handover": "live-failed", **replay}
      await page.evaluate("(t) => { window.name = t; }", token)
      script = f"""
        import {{ chromium }} from '{(RAMPA / 'node_modules' / 'playwright-core' / 'index.mjs').as_posix()}';
        import {{ checkPage }} from '{(RAMPA / 'dist' / 'playwright.mjs').as_posix()}';
        import {{ writeFileSync }} from 'node:fs';
        const browser = await chromium.connectOverCDP('http://127.0.0.1:{port}');
        let target = null;
        for (const context of browser.contexts()) for (const pg of context.pages())
          if (await pg.evaluate(() => window.name).catch(() => '') === {json.dumps(token)}) target = pg;
        if (!target) throw new Error('replayed page not found');
        const options = {{ model: {json.dumps('openrouter:' + model)} }};
        if ({json.dumps(str(cache_dir.resolve()) if cache_dir else "")}) options.cacheDir = {json.dumps(str(cache_dir.resolve()) if cache_dir else "")};
        const report = await checkPage(target, options);
        // the XPath of each finding's element, read on the replayed page itself (a fresh load would not be in the state)
        const toXPath = {XPATH_JS};
        const xpaths = {{}};
        for (const key of ['findings', 'belowThreshold', 'needsReview'])
          for (const f of report[key] || []) {{
            const ref = f.ref || f.target;
            if (!ref || ref in xpaths) continue;
            try {{ xpaths[ref] = await target.locator(`css=${{ref}}`).first().evaluate(toXPath, null, {{ timeout: 3000 }}); }}
            catch {{ xpaths[ref] = null; }}
          }}
        report.w4aXpaths = xpaths;
        writeFileSync({json.dumps(str(out_file.resolve()))}, JSON.stringify(report));
        process.exit(0);
      """
      done = await asyncio.to_thread(subprocess.run, ["node", "--input-type=module", "-e", script], cwd=RAMPA,
                                     env=env, capture_output=True, text=True, timeout=900)
      if done.returncode or not out_file.exists():
        return {"handover": "live-failed", "error": done.stderr[-600:]}
      return {"handover": "live", "url": replay.get("url")}
    finally:
      await browser.close()


def rampa_check_live(run_dir: Path, state_id: str, out_file: Path, model: str, env: dict,
                     base_url: str | None = None, init_script: str | None = None,
                     cache_dir: Path | None = None) -> dict[str, Any]:
  out_file.parent.mkdir(parents=True, exist_ok=True)
  return asyncio.run(_replay_then_rampa(Path(run_dir), state_id, out_file, model, env, base_url, init_script,
                                        cache_dir))


class ReplayService:
  """Local HTTP service InterA11y's patched session calls for every page it opens: replays the state on it."""

  def __init__(self, run_dir: Path, state_id: str, base_url: str | None = None):
    self.run_dir, self.state_id, self.base_url = Path(run_dir), state_id, base_url
    self.calls: list[dict[str, Any]] = []
    service = self

    class Handler(BaseHTTPRequestHandler):
      def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        result = asyncio.run(service._replay(body.get("ws", ""), body.get("token", "")))
        service.calls.append(result)
        payload = json.dumps(result).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

      def log_message(self, *args):
        pass

    self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=self.server.serve_forever, daemon=True).start()
    self.url = f"http://127.0.0.1:{self.server.server_address[1]}/replay"

  async def _replay(self, ws: str, token: str) -> dict[str, Any]:
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
      try:
        browser = await p.chromium.connect_over_cdp(ws)
      except Exception as error:
        return {"ok": False, "error": f"connect: {type(error).__name__}"}
      try:
        for context in browser.contexts:
          for page in context.pages:
            try:
              name = await page.evaluate("() => window.name")
            except Exception:
              continue
            if name == token:
              return await replay_on_page(page, self.run_dir, self.state_id, self.base_url)
        return {"ok": False, "error": "page with the token not found"}
      finally:
        pass  # leaving the Playwright context disconnects; the browser itself belongs to InterA11y and stays open

  def close(self) -> None:
    self.server.shutdown()
