import argparse
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from src.crawler.config.app_config import load_app_config
from src.crawler.crawl.entrypoint import run_crawl
from src.crawler.exceptions import NavigationTimeout
from src.crawler.graph.graph_render import export_dot, render_png_from_dot
from src.crawler.platform.browser import BrowserController
from src.crawler.platform.run_metadata import (
  attach_browser_metadata,
  build_run_metadata,
  utc_iso_now,
)

LEGACY_CONFIRM_RUN_DISABLED_MESSAGE = (
  "The legacy main.py --confirm-run path is disabled and is not the current "
  "AccessGraph model-judgment pipeline. Use "
  "`python accessgraph.py judge --run <run_id>` instead."
)
LEGACY_REPORT_RUN_DISABLED_MESSAGE = (
  "The legacy main.py --report-run path is disabled and is not the current "
  "AccessGraph developer report pipeline. Use "
  "`python accessgraph.py report --run <run_id> "
  "--judgment-run-id <judgment_run_id>` instead."
)


def _seconds_elapsed(start_time: float) -> float:
  return round(time.perf_counter() - start_time, 3)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
  path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_timing_payload(*, run_id: str, config_path: Path, url: str) -> dict[str, Any]:
  return {
    "run_id": run_id,
    "config_path": str(config_path),
    "url": url,
    "status": "running",
    "started_at_utc": utc_iso_now(),
    "phases_seconds": {},
  }


def _record_phase_duration(timing: dict[str, Any] | None, phase_name: str, phase_started: float) -> None:
  if timing is None:
    return
  timing["phases_seconds"][phase_name] = _seconds_elapsed(phase_started)


def _error_payload(error: Exception) -> dict[str, str]:
  return {"type": type(error).__name__, "message": str(error)}


def _record_error(
  *,
  status: str,
  error: Exception,
  run_metadata: dict[str, Any],
  timing: dict[str, Any] | None,
) -> None:
  error_payload = _error_payload(error)
  run_metadata["primary_status"] = status
  run_metadata["status"] = status
  run_metadata["error"] = error_payload
  if timing is not None:
    timing["primary_status"] = status
    timing["status"] = status
    timing["error"] = error_payload


def _append_warning(payload: dict[str, Any], *, phase: str, error: Exception) -> None:
  warnings = payload.get("warnings")
  if not isinstance(warnings, list):
    warnings = []
    payload["warnings"] = warnings
  warnings.append({"phase": phase, **_error_payload(error)})


def _record_cleanup_error(payload: dict[str, Any], *, phase: str, error: Exception) -> None:
  cleanup = payload.get("cleanup")
  if not isinstance(cleanup, dict):
    cleanup = {}
    payload["cleanup"] = cleanup
  cleanup[phase] = {
    "status": "error",
    "error": _error_payload(error),
  }
  _append_warning(payload, phase=phase, error=error)
  if payload.get("primary_status") == "success":
    payload["status"] = "success_with_warnings"


def _record_browser_stop_error(
  *,
  error: Exception,
  run_metadata: dict[str, Any],
  timing: dict[str, Any] | None,
) -> None:
  _record_cleanup_error(run_metadata, phase="browser_stop", error=error)
  if timing is not None:
    _record_cleanup_error(timing, phase="browser_stop", error=error)


def _record_success(
  *,
  graph: Any,
  run_metadata: dict[str, Any],
  timing: dict[str, Any] | None,
) -> None:
  graph_counts = {
    "nodes": len(graph.nodes),
    "edges": len(graph.edges),
  }
  run_metadata["graph"] = graph_counts
  run_metadata["primary_status"] = "success"
  run_metadata["status"] = "success"
  if timing is not None:
    timing["graph"] = graph_counts
    timing["primary_status"] = "success"
    timing["status"] = "success"


def _persist_crawl_metrics(graph: Any, run_dir: Path, run_metadata: dict[str, Any]) -> None:
  crawl_metrics = getattr(graph, "metrics", None)
  if not isinstance(crawl_metrics, dict) or not crawl_metrics:
    return
  crawl_metrics_path = run_dir / "crawl_metrics.json"
  _write_json(crawl_metrics_path, crawl_metrics)
  run_metadata["crawl_metrics"] = crawl_metrics
  print("Crawl metrics:", crawl_metrics_path.resolve())


def _crawl_config_payload(crawl_cfg: Any) -> dict[str, Any]:
  return {
    "strategy": getattr(crawl_cfg, "traversal_strategy", "bfs"),
    "max_states": getattr(crawl_cfg, "max_states", 100),
    "max_depth": getattr(crawl_cfg, "max_depth", 5),
    "max_actions_per_state": getattr(crawl_cfg, "max_actions_per_state", 5),
    "state_identity": "rendered_dom_identity_hash_plus_canonical_url",
    "same_origin_links_only": getattr(crawl_cfg, "scope_policy", "same_origin") == "same_origin",
    "screenshot": "full_page_after_new_state_confirmed",
    "wait_strategy": "dom_mutation_or_timeout",
    "wait_timeout_ms": getattr(crawl_cfg, "wait_timeout_ms", 2_000),
  }


def _persist_effective_crawl_config(crawl_cfg: Any, run_dir: Path) -> Path:
  path = run_dir / "crawl_config.json"
  _write_json(path, _crawl_config_payload(crawl_cfg))
  return path


def _persist_graph_artifacts(graph: Any, run_dir: Path) -> tuple[Path, Path, Path, Path, bool]:
  graph_json = run_dir / "graph.json"
  transitions_json = run_dir / "transitions.json"
  dot_path = run_dir / "graph.dot"
  png_path = run_dir / "graph.png"

  graph.save_json(graph_json)
  if hasattr(graph, "save_transitions_json"):
    graph.save_transitions_json(transitions_json)
  else:
    transitions_json.write_text(
      json.dumps(getattr(graph, "edges", []), ensure_ascii=False, indent=2),
      encoding="utf-8",
    )
  export_dot(graph, dot_path)
  made_png = render_png_from_dot(dot_path, png_path)
  return graph_json, transitions_json, dot_path, png_path, made_png


def _print_graph_artifacts(
  *,
  run_dir: Path,
  graph_json: Path,
  transitions_json: Path,
  dot_path: Path,
  png_path: Path,
  made_png: bool,
) -> None:
  print("\n Crawl finished.")
  print("Run dir:", run_dir.resolve())
  print("Graph:", graph_json.resolve())
  print("Transitions:", transitions_json.resolve())
  print("DOT:", dot_path.resolve())
  if made_png:
    print("PNG:", png_path.resolve())
  else:
    print("(PNG not rendered: Graphviz 'dot' not found)")


def _print_next_offline_steps(run_dir: Path) -> None:
  run_arg = str(run_dir)
  print("\nNext offline stages (not run by main.py):")
  print(f"  python accessgraph.py candidates --run {run_arg}")
  print(f"  python accessgraph.py judge --run {run_arg} --provider fake --limit 5")
  print(
    "  python accessgraph.py report "
    f"--run {run_arg} --judgment-run-id <judgment_run_id>"
  )


def _finalize_timing_artifact(
  *,
  timing: dict[str, Any] | None,
  run_started: float | None,
  phase_started: float,
  run_dir: Path,
) -> None:
  if timing is None or run_started is None:
    return

  _record_phase_duration(timing, "browser_stop", phase_started)
  timing["ended_at_utc"] = utc_iso_now()
  timing["duration_seconds"] = _seconds_elapsed(run_started)

  timing_path = run_dir / "run_timing.json"
  _write_json(timing_path, timing)
  print("Timing:", timing_path.resolve())


def _persist_run_metadata(run_metadata: dict[str, Any], run_dir: Path) -> None:
  run_metadata["ended_at_utc"] = utc_iso_now()
  metadata_path = run_dir / "run_metadata.json"
  _write_json(metadata_path, run_metadata)
  print("Metadata:", metadata_path.resolve())


async def main(config_path: Path):
  cfg_file = load_app_config(config_path)
  url = cfg_file.url
  enable_run_timing = bool(getattr(cfg_file, "enable_run_timing", True))
  run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
  run_dir = Path(cfg_file.runs_dir) / run_id
  run_dir.mkdir(parents=True, exist_ok=True)
  _persist_effective_crawl_config(cfg_file.crawl, run_dir)
  run_metadata = build_run_metadata(config_path, cfg_file, run_id, run_dir)

  timing: dict[str, Any] | None = None
  run_started: float | None = None
  if enable_run_timing:
    timing = _build_timing_payload(run_id=run_id, config_path=config_path, url=url)
    run_started = time.perf_counter()

  bc = BrowserController(headless=cfg_file.headless)
  primary_error: Exception | None = None
  try:
    phase_started = time.perf_counter()
    await bc.start()
    await attach_browser_metadata(run_metadata, bc)
    _record_phase_duration(timing, "browser_start", phase_started)

    phase_started = time.perf_counter()
    await bc.goto(url)
    _record_phase_duration(timing, "initial_navigation", phase_started)
    assert bc.page is not None

    phase_started = time.perf_counter()
    graph = await run_crawl(
      page=bc.page,
      start_url=url,
      run_dir=run_dir,
      cfg=cfg_file.crawl,
    )
    _record_phase_duration(timing, "crawl", phase_started)

    # Save graph artifacts
    phase_started = time.perf_counter()
    graph_json, transitions_json, dot_path, png_path, made_png = _persist_graph_artifacts(graph, run_dir)
    _record_phase_duration(timing, "graph_export", phase_started)
    _record_success(graph=graph, run_metadata=run_metadata, timing=timing)
    _persist_crawl_metrics(graph, run_dir, run_metadata)
    _print_graph_artifacts(
      run_dir=run_dir,
      graph_json=graph_json,
      transitions_json=transitions_json,
      dot_path=dot_path,
      png_path=png_path,
      made_png=made_png,
    )
    _print_next_offline_steps(run_dir)

  except NavigationTimeout as e:
    primary_error = e
    _record_error(
      status="navigation_timeout",
      error=e,
      run_metadata=run_metadata,
      timing=timing,
    )
    print(f"[WARN] {e}")
  except Exception as e:
    primary_error = e
    _record_error(
      status="error",
      error=e,
      run_metadata=run_metadata,
      timing=timing,
    )
    raise
  finally:
    phase_started = time.perf_counter()
    stop_error = None
    try:
      await bc.stop()
    except Exception as e:
      stop_error = e
      _record_browser_stop_error(
        error=e,
        run_metadata=run_metadata,
        timing=timing,
      )
    _finalize_timing_artifact(
      timing=timing,
      run_started=run_started,
      phase_started=phase_started,
      run_dir=run_dir,
    )
    _persist_run_metadata(run_metadata, run_dir)

    if stop_error is not None and primary_error is None and run_metadata.get("primary_status") != "success":
      raise stop_error


def _build_arg_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description=(
      "AccessGraph crawl/state-acquisition CLI. This command runs only the SPA "
      "state crawl and state-graph/artifact/accessibility-context capture stage. "
      "Current offline analysis stages use accessgraph.py candidates, "
      "accessgraph.py judge, and accessgraph.py report."
    )
  )
  parser.add_argument(
    "--config",
    type=Path,
    default=Path("crawler_config.json"),
    help="Path to crawl-stage config JSON file",
  )
  parser.add_argument(
    "--confirm-run",
    type=Path,
    default=None,
    help=(
      "Disabled legacy model-judgment path. Use accessgraph.py judge instead."
    ),
  )
  parser.add_argument(
    "--report-run",
    type=Path,
    default=None,
    help=(
      "Disabled legacy report path. Use accessgraph.py report instead."
    ),
  )
  parser.add_argument(
    "--report-output-dir",
    type=Path,
    default=None,
    help=argparse.SUPPRESS,
  )
  parser.add_argument(
    "--confirm-violation",
    action="append",
    default=None,
    help=argparse.SUPPRESS,
  )
  parser.add_argument(
    "--confirm-max-candidates-per-violation",
    type=int,
    default=50,
    help=argparse.SUPPRESS,
  )
  parser.add_argument(
    "--confirm-client",
    choices=("fake", "ollama"),
    default="fake",
    help=argparse.SUPPRESS,
  )
  parser.add_argument(
    "--confirm-model",
    default="qwen2.5:7b",
    help=argparse.SUPPRESS,
  )
  parser.add_argument(
    "--confirm-base-url",
    default="http://localhost:11434",
    help=argparse.SUPPRESS,
  )
  parser.add_argument(
    "--confirm-timeout-seconds",
    type=float,
    default=120.0,
    help=argparse.SUPPRESS,
  )
  parser.add_argument(
    "--confirm-temperature",
    type=float,
    default=0.0,
    help=argparse.SUPPRESS,
  )
  return parser


def _run_cli(args: argparse.Namespace) -> None:
  if args.report_run is not None:
    raise SystemExit(LEGACY_REPORT_RUN_DISABLED_MESSAGE)
  if args.confirm_run is not None:
    raise SystemExit(LEGACY_CONFIRM_RUN_DISABLED_MESSAGE)
  asyncio.run(main(args.config))


if __name__ == "__main__":
  args = _build_arg_parser().parse_args()
  _run_cli(args)
