import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.crawler.exceptions import NavigationTimeout

import main as crawler_main


class FakeGraph:
  def __init__(self):
    self.nodes = {"state_0000": {"state_id": "state_0000"}}
    self.edges = [{"from": "state_0000", "to": "state_0001", "action": {"type": "click"}}]
    self.metrics = {
      "status": "success",
      "coverage": {
        "states_total": 1,
        "edges_total": 1,
      },
      "stop": {
        "termination_reason": "frontier_exhausted",
      },
    }

  def save_json(self, path: Path) -> None:
    path.write_text(json.dumps({"nodes": list(self.nodes.values()), "edges": self.edges}), encoding="utf-8")


class FakeBrowserController:
  def __init__(self, headless: bool = True):
    self.headless = headless
    self.page = SimpleNamespace(url="https://example.com/")

  async def start(self) -> None:
    return None

  async def goto(self, _url: str) -> None:
    return None

  async def stop(self) -> None:
    return None


def _has_browser_stop_warning(payload: dict[str, object]) -> bool:
  warnings = payload.get("warnings")
  if not isinstance(warnings, list):
    return False
  return any(
    isinstance(warning, dict)
    and warning.get("phase") == "browser_stop"
    and warning.get("message") == "browser stop failed"
    for warning in warnings
  )


def test_main_writes_run_timing_on_success(monkeypatch, tmp_path):
  runs_dir = tmp_path / "runs"
  cfg = SimpleNamespace(
    url="https://example.com/",
    headless=True,
    runs_dir=str(runs_dir),
    enable_run_timing=True,
    crawl=SimpleNamespace(),
  )

  async def fake_run_crawl(page, start_url, run_dir, cfg):
    assert page.url == "https://example.com/"
    assert start_url == "https://example.com/"
    assert run_dir.parent == runs_dir
    return FakeGraph()

  monkeypatch.setattr(crawler_main, "load_app_config", lambda _path: cfg)
  monkeypatch.setattr(crawler_main, "BrowserController", FakeBrowserController)
  monkeypatch.setattr(crawler_main, "run_crawl", fake_run_crawl)
  monkeypatch.setattr(crawler_main, "export_dot", lambda _graph, dot_path: dot_path.write_text("digraph {}", encoding="utf-8"))
  monkeypatch.setattr(crawler_main, "render_png_from_dot", lambda _dot, _png: False)

  asyncio.run(crawler_main.main(Path("crawler_config.json")))

  run_dirs = [p for p in runs_dir.iterdir() if p.is_dir()]
  assert len(run_dirs) == 1
  crawl_metrics_path = run_dirs[0] / "crawl_metrics.json"
  assert crawl_metrics_path.exists()
  assert (run_dirs[0] / "crawl_config.json").exists()
  transitions_path = run_dirs[0] / "transitions.json"
  assert transitions_path.exists()
  metadata_path = run_dirs[0] / "run_metadata.json"
  assert metadata_path.exists()
  timing_path = run_dirs[0] / "run_timing.json"
  assert timing_path.exists()

  crawl_metrics = json.loads(crawl_metrics_path.read_text(encoding="utf-8"))
  assert crawl_metrics["status"] == "success"
  assert crawl_metrics["coverage"]["states_total"] == 1
  crawl_config = json.loads((run_dirs[0] / "crawl_config.json").read_text(encoding="utf-8"))
  assert crawl_config["strategy"] == "bfs"
  assert crawl_config["state_identity"] == "rendered_dom_identity_hash_plus_canonical_url"
  assert crawl_config["wait_strategy"] == "dom_mutation_or_timeout"
  assert json.loads(transitions_path.read_text(encoding="utf-8")) == [
    {"from": "state_0000", "to": "state_0001", "action": {"type": "click"}}
  ]

  metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
  assert metadata["primary_status"] == "success"
  assert metadata["status"] == "success"
  assert metadata["graph"]["nodes"] == 1
  assert metadata["graph"]["edges"] == 1
  assert "cleanup" not in metadata
  assert "crawl_metrics" in metadata
  assert "runtime" in metadata
  assert "source_control" in metadata
  assert "tooling" in metadata
  assert "started_at_utc" in metadata
  assert "ended_at_utc" in metadata

  timing = json.loads(timing_path.read_text(encoding="utf-8"))
  assert timing["primary_status"] == "success"
  assert timing["status"] == "success"
  assert timing["graph"]["nodes"] == 1
  assert timing["graph"]["edges"] == 1
  assert "cleanup" not in timing
  assert timing["duration_seconds"] >= 0
  assert "started_at_utc" in timing
  assert "ended_at_utc" in timing
  for phase_name in ["browser_start", "initial_navigation", "crawl", "graph_export", "browser_stop"]:
    assert phase_name in timing["phases_seconds"]


def test_main_writes_run_timing_on_navigation_timeout(monkeypatch, tmp_path):
  runs_dir = tmp_path / "runs"
  cfg = SimpleNamespace(
    url="https://example.com/",
    headless=True,
    runs_dir=str(runs_dir),
    enable_run_timing=True,
    crawl=SimpleNamespace(),
  )

  class TimeoutBrowserController(FakeBrowserController):
    async def goto(self, _url: str) -> None:
      raise NavigationTimeout("Timeout while navigating to https://example.com/")

  async def should_not_crawl(*_args, **_kwargs):
    raise AssertionError("run_crawl should not be called when initial navigation times out")

  monkeypatch.setattr(crawler_main, "load_app_config", lambda _path: cfg)
  monkeypatch.setattr(crawler_main, "BrowserController", TimeoutBrowserController)
  monkeypatch.setattr(crawler_main, "run_crawl", should_not_crawl)
  monkeypatch.setattr(crawler_main, "export_dot", lambda _graph, dot_path: dot_path.write_text("digraph {}", encoding="utf-8"))
  monkeypatch.setattr(crawler_main, "render_png_from_dot", lambda _dot, _png: False)

  asyncio.run(crawler_main.main(Path("crawler_config.json")))

  run_dirs = [p for p in runs_dir.iterdir() if p.is_dir()]
  assert len(run_dirs) == 1
  crawl_metrics_path = run_dirs[0] / "crawl_metrics.json"
  assert not crawl_metrics_path.exists()
  metadata_path = run_dirs[0] / "run_metadata.json"
  assert metadata_path.exists()
  timing_path = run_dirs[0] / "run_timing.json"
  assert timing_path.exists()

  metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
  assert metadata["primary_status"] == "navigation_timeout"
  assert metadata["status"] == "navigation_timeout"
  assert metadata["error"]["type"] == "NavigationTimeout"

  timing = json.loads(timing_path.read_text(encoding="utf-8"))
  assert timing["primary_status"] == "navigation_timeout"
  assert timing["status"] == "navigation_timeout"
  assert timing["error"]["type"] == "NavigationTimeout"
  assert timing["duration_seconds"] >= 0
  assert "browser_start" in timing["phases_seconds"]
  assert "browser_stop" in timing["phases_seconds"]


def test_main_preserves_primary_exception_when_browser_stop_fails(monkeypatch, tmp_path):
  runs_dir = tmp_path / "runs"
  cfg = SimpleNamespace(
    url="https://example.com/",
    headless=True,
    runs_dir=str(runs_dir),
    enable_run_timing=True,
    crawl=SimpleNamespace(),
  )

  class StopFailsBrowserController(FakeBrowserController):
    async def stop(self) -> None:
      raise RuntimeError("browser stop failed")

  async def failing_run_crawl(*_args, **_kwargs):
    raise RuntimeError("crawl failed")

  monkeypatch.setattr(crawler_main, "load_app_config", lambda _path: cfg)
  monkeypatch.setattr(crawler_main, "BrowserController", StopFailsBrowserController)
  monkeypatch.setattr(crawler_main, "run_crawl", failing_run_crawl)
  monkeypatch.setattr(crawler_main, "export_dot", lambda _graph, dot_path: dot_path.write_text("digraph {}", encoding="utf-8"))
  monkeypatch.setattr(crawler_main, "render_png_from_dot", lambda _dot, _png: False)

  with pytest.raises(RuntimeError, match="crawl failed"):
    asyncio.run(crawler_main.main(Path("crawler_config.json")))

  run_dirs = [p for p in runs_dir.iterdir() if p.is_dir()]
  assert len(run_dirs) == 1
  metadata = json.loads((run_dirs[0] / "run_metadata.json").read_text(encoding="utf-8"))
  timing = json.loads((run_dirs[0] / "run_timing.json").read_text(encoding="utf-8"))

  assert metadata["primary_status"] == "error"
  assert metadata["status"] == "error"
  assert metadata["error"]["message"] == "crawl failed"
  assert metadata["cleanup"]["browser_stop"]["status"] == "error"
  assert metadata["cleanup"]["browser_stop"]["error"]["message"] == "browser stop failed"
  assert _has_browser_stop_warning(metadata)
  assert "browser_stop_error" not in metadata
  assert timing["primary_status"] == "error"
  assert timing["status"] == "error"
  assert timing["error"]["message"] == "crawl failed"
  assert timing["cleanup"]["browser_stop"]["status"] == "error"
  assert timing["cleanup"]["browser_stop"]["error"]["message"] == "browser stop failed"
  assert _has_browser_stop_warning(timing)
  assert "browser_stop_error" not in timing


def test_main_records_browser_stop_error_after_success(monkeypatch, tmp_path):
  runs_dir = tmp_path / "runs"
  cfg = SimpleNamespace(
    url="https://example.com/",
    headless=True,
    runs_dir=str(runs_dir),
    enable_run_timing=True,
    crawl=SimpleNamespace(),
  )

  class StopFailsBrowserController(FakeBrowserController):
    async def stop(self) -> None:
      raise RuntimeError("browser stop failed")

  async def fake_run_crawl(page, start_url, run_dir, cfg):
    assert page.url == "https://example.com/"
    assert start_url == "https://example.com/"
    assert run_dir.parent == runs_dir
    return FakeGraph()

  monkeypatch.setattr(crawler_main, "load_app_config", lambda _path: cfg)
  monkeypatch.setattr(crawler_main, "BrowserController", StopFailsBrowserController)
  monkeypatch.setattr(crawler_main, "run_crawl", fake_run_crawl)
  monkeypatch.setattr(crawler_main, "export_dot", lambda _graph, dot_path: dot_path.write_text("digraph {}", encoding="utf-8"))
  monkeypatch.setattr(crawler_main, "render_png_from_dot", lambda _dot, _png: False)

  asyncio.run(crawler_main.main(Path("crawler_config.json")))

  run_dirs = [p for p in runs_dir.iterdir() if p.is_dir()]
  assert len(run_dirs) == 1
  metadata = json.loads((run_dirs[0] / "run_metadata.json").read_text(encoding="utf-8"))
  timing = json.loads((run_dirs[0] / "run_timing.json").read_text(encoding="utf-8"))

  assert metadata["primary_status"] == "success"
  assert metadata["status"] == "success_with_warnings"
  assert metadata["graph"]["nodes"] == 1
  assert metadata["cleanup"]["browser_stop"]["status"] == "error"
  assert metadata["cleanup"]["browser_stop"]["error"]["message"] == "browser stop failed"
  assert _has_browser_stop_warning(metadata)
  assert "browser_stop_error" not in metadata
  assert timing["primary_status"] == "success"
  assert timing["status"] == "success_with_warnings"
  assert timing["graph"]["edges"] == 1
  assert timing["cleanup"]["browser_stop"]["status"] == "error"
  assert timing["cleanup"]["browser_stop"]["error"]["message"] == "browser stop failed"
  assert _has_browser_stop_warning(timing)
  assert "browser_stop_error" not in timing


def test_main_records_browser_stop_error_after_navigation_timeout(monkeypatch, tmp_path):
  runs_dir = tmp_path / "runs"
  cfg = SimpleNamespace(
    url="https://example.com/",
    headless=True,
    runs_dir=str(runs_dir),
    enable_run_timing=True,
    crawl=SimpleNamespace(),
  )

  class TimeoutAndStopFailsBrowserController(FakeBrowserController):
    async def goto(self, _url: str) -> None:
      raise NavigationTimeout("Timeout while navigating to https://example.com/")

    async def stop(self) -> None:
      raise RuntimeError("browser stop failed")

  async def should_not_crawl(*_args, **_kwargs):
    raise AssertionError("run_crawl should not be called when initial navigation times out")

  monkeypatch.setattr(crawler_main, "load_app_config", lambda _path: cfg)
  monkeypatch.setattr(crawler_main, "BrowserController", TimeoutAndStopFailsBrowserController)
  monkeypatch.setattr(crawler_main, "run_crawl", should_not_crawl)
  monkeypatch.setattr(crawler_main, "export_dot", lambda _graph, dot_path: dot_path.write_text("digraph {}", encoding="utf-8"))
  monkeypatch.setattr(crawler_main, "render_png_from_dot", lambda _dot, _png: False)

  asyncio.run(crawler_main.main(Path("crawler_config.json")))

  run_dirs = [p for p in runs_dir.iterdir() if p.is_dir()]
  assert len(run_dirs) == 1
  metadata = json.loads((run_dirs[0] / "run_metadata.json").read_text(encoding="utf-8"))
  timing = json.loads((run_dirs[0] / "run_timing.json").read_text(encoding="utf-8"))

  assert metadata["primary_status"] == "navigation_timeout"
  assert metadata["status"] == "navigation_timeout"
  assert metadata["error"]["type"] == "NavigationTimeout"
  assert metadata["cleanup"]["browser_stop"]["status"] == "error"
  assert metadata["cleanup"]["browser_stop"]["error"]["message"] == "browser stop failed"
  assert _has_browser_stop_warning(metadata)
  assert "browser_stop_error" not in metadata
  assert timing["primary_status"] == "navigation_timeout"
  assert timing["status"] == "navigation_timeout"
  assert timing["error"]["type"] == "NavigationTimeout"
  assert timing["cleanup"]["browser_stop"]["status"] == "error"
  assert timing["cleanup"]["browser_stop"]["error"]["message"] == "browser stop failed"
  assert _has_browser_stop_warning(timing)
  assert "browser_stop_error" not in timing


def test_main_skips_run_timing_when_disabled(monkeypatch, tmp_path):
  runs_dir = tmp_path / "runs"
  cfg = SimpleNamespace(
    url="https://example.com/",
    headless=True,
    runs_dir=str(runs_dir),
    enable_run_timing=False,
    crawl=SimpleNamespace(),
  )

  async def fake_run_crawl(page, start_url, run_dir, cfg):
    assert page.url == "https://example.com/"
    assert start_url == "https://example.com/"
    assert run_dir.parent == runs_dir
    return FakeGraph()

  monkeypatch.setattr(crawler_main, "load_app_config", lambda _path: cfg)
  monkeypatch.setattr(crawler_main, "BrowserController", FakeBrowserController)
  monkeypatch.setattr(crawler_main, "run_crawl", fake_run_crawl)
  monkeypatch.setattr(crawler_main, "export_dot", lambda _graph, dot_path: dot_path.write_text("digraph {}", encoding="utf-8"))
  monkeypatch.setattr(crawler_main, "render_png_from_dot", lambda _dot, _png: False)

  asyncio.run(crawler_main.main(Path("crawler_config.json")))

  run_dirs = [p for p in runs_dir.iterdir() if p.is_dir()]
  assert len(run_dirs) == 1
  crawl_metrics_path = run_dirs[0] / "crawl_metrics.json"
  assert crawl_metrics_path.exists()
  metadata_path = run_dirs[0] / "run_metadata.json"
  assert metadata_path.exists()

  crawl_metrics = json.loads(crawl_metrics_path.read_text(encoding="utf-8"))
  assert crawl_metrics["status"] == "success"

  metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
  assert metadata["status"] == "success"
  assert metadata["graph"]["nodes"] == 1
  assert metadata["graph"]["edges"] == 1

  assert not (run_dirs[0] / "run_timing.json").exists()


def test_main_help_describes_crawl_only_cli():
  parser = crawler_main._build_arg_parser()

  assert "crawl/state-acquisition CLI" in parser.description
  assert "offline analysis stages" in parser.description


def test_main_prints_next_offline_steps(capsys):
  run_dir = Path("runs") / "20260322_224141"
  crawler_main._print_next_offline_steps(run_dir)

  out = capsys.readouterr().out
  assert "Next offline stages (not run by main.py)" in out
  assert f"accessgraph.py candidates --run {run_dir}" in out
  assert f"accessgraph.py judge --run {run_dir}" in out
  assert f"accessgraph.py report --run {run_dir}" in out


def test_confirm_run_flag_is_legacy_disabled():
  args = crawler_main._build_arg_parser().parse_args(
    [
      "--confirm-run",
      "runs/20260322_000000",
      "--confirm-client",
      "ollama",
      "--confirm-model",
      "qwen2.5:7b",
    ]
  )

  with pytest.raises(SystemExit) as exc_info:
    crawler_main._run_cli(args)

  message = str(exc_info.value)
  assert "legacy main.py --confirm-run path is disabled" in message
  assert "accessgraph.py judge" in message


def test_report_run_flag_is_legacy_disabled():
  args = crawler_main._build_arg_parser().parse_args(
    [
      "--report-run",
      "runs/20260322_000000/confirmations/old",
      "--report-output-dir",
      "runs/20260322_000000/old_report",
    ]
  )

  with pytest.raises(SystemExit) as exc_info:
    crawler_main._run_cli(args)

  message = str(exc_info.value)
  assert "legacy main.py --report-run path is disabled" in message
  assert "accessgraph.py report" in message
