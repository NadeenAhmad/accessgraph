from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable


_SUPPORTED_PROVIDER_NAMES = (
  "fake", "ollama", "ollama-vision", "openai", "openai-vision",
  "anthropic", "anthropic-vision", "openrouter", "openrouter-vision",
)
_EFFORT_LEVELS = ("minimal", "low", "medium", "high", "xhigh", "max")
_CONTEXT_MODES = (
  "graph_context", "isolated_state", "adaptive_context", "minimal_html_screenshot", "history_context", "adaptive_v2",
)
_ESCALATION_POLICIES = ("none", "uncertain_graph_v1", "uncertain_history_v1")


def main(argv: list[str] | None = None) -> int:
  parser = _build_parser()
  args = _with_raw_argv(argv, parser.parse_args(argv))
  return args.handler(args)


def _build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    prog="accessgraph.py",
    description=(
      "AccessGraph staged developer CLI for crawl, candidate generation, "
      "LLM/model judgment, and reporting."
    ),
  )
  subparsers = parser.add_subparsers(dest="command", required=True)

  _add_crawl_parser(subparsers)
  _add_candidates_parser(subparsers)
  _add_judge_parser(subparsers)
  _add_report_parser(subparsers)
  _add_check_page_parser(subparsers)
  return parser


def _add_crawl_parser(subparsers: argparse._SubParsersAction) -> None:
  parser = subparsers.add_parser(
    "crawl",
    help="Run bounded SPA state acquisition and artifact capture.",
    description=(
      "Run only the crawl/state-acquisition stage. This command records "
      "states, transitions, screenshots, DOM snapshots, metadata, and "
      "accessibility context; it does not run candidates, model judgment, or "
      "reporting."
    ),
  )
  parser.add_argument(
    "--config",
    type=Path,
    default=Path("crawler_config.json"),
    help="Path to the crawl-stage config JSON file. Defaults to crawler_config.json.",
  )
  parser.set_defaults(handler=_run_crawl)


def _add_candidates_parser(subparsers: argparse._SubParsersAction) -> None:
  parser = subparsers.add_parser(
    "candidates",
    help="Build semantic review candidates from a completed crawl run.",
    description=(
      "Build taxonomy-guided candidate hypotheses from saved state graph, "
      "state artifacts, and accessibility context."
    ),
  )
  parser.add_argument(
    "--run",
    type=Path,
    required=True,
    help="Path to a completed runs/<run_id> directory.",
  )
  parser.add_argument(
    "--candidate-type",
    action="append",
    default=None,
    help="Optional semantic candidate type to build. May be repeated.",
  )
  parser.set_defaults(handler=_run_candidates)


def _add_judge_parser(subparsers: argparse._SubParsersAction) -> None:
  parser = subparsers.add_parser(
    "judge",
    help="Run offline LLM/model judgment over semantic candidates.",
    description=(
      "Run explicit offline model judgment over saved semantic review "
      "candidates. Real providers require a model and bounded candidate "
      "selection."
    ),
  )
  parser.add_argument(
    "--run",
    type=Path,
    required=True,
    help="Completed run directory containing candidates/candidates.jsonl.",
  )
  parser.add_argument(
    "--provider",
    choices=_SUPPORTED_PROVIDER_NAMES,
    default="fake",
    help="Model provider. Defaults to fake.",
  )
  parser.add_argument(
    "--model",
    default=None,
    help="Provider model name. Required by real providers.",
  )
  parser.add_argument(
    "--base-url",
    default=None,
    help="Optional Ollama API base URL for Ollama providers.",
  )
  parser.add_argument(
    "--candidate-type",
    action="append",
    default=None,
    help="Candidate type to judge. Repeat to include multiple types.",
  )
  parser.add_argument(
    "--candidate-id",
    action="append",
    default=None,
    help="Candidate id to judge. Repeat to include multiple exact candidates.",
  )
  parser.add_argument(
    "--candidate-id-file",
    type=Path,
    default=None,
    help="Path to a newline-delimited candidate id file.",
  )
  parser.add_argument(
    "--context-mode",
    choices=_CONTEXT_MODES,
    default="graph_context",
    help="Model-judgment context payload mode. Defaults to graph_context.",
  )
  parser.add_argument(
    "--escalation-policy",
    choices=_ESCALATION_POLICIES,
    default="none",
    help=argparse.SUPPRESS,
  )
  parser.add_argument(
    "--limit",
    type=_non_negative_int,
    default=None,
    help="Maximum number of selected candidates to judge.",
  )
  parser.add_argument(
    "--judgment-run-id",
    default=None,
    help="Explicit model-judgment run id for deterministic tests or benchmark runs.",
  )
  parser.add_argument(
    "--prompt-version",
    default=None,
    help="Optional prompt version override for calibration.",
  )
  parser.add_argument(
    "--overwrite",
    action="store_true",
    help="Replace an existing model-judgment run output directory.",
  )
  parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Read candidates and build prompts without calling a provider or writing judgments.",
  )
  parser.add_argument(
    "--save-prompts",
    dest="save_prompts",
    action="store_true",
    default=None,
    help="Save rendered prompt JSON files.",
  )
  parser.add_argument(
    "--no-save-prompts",
    dest="save_prompts",
    action="store_false",
    help="Do not save rendered prompt JSON files.",
  )
  parser.add_argument(
    "--save-raw-responses",
    dest="save_raw_responses",
    action="store_true",
    default=None,
    help="Save raw provider responses.",
  )
  parser.add_argument(
    "--no-save-raw-responses",
    dest="save_raw_responses",
    action="store_false",
    help="Do not save raw provider responses.",
  )
  parser.add_argument(
    "--strict-parse",
    action="store_true",
    help="Fail the run on malformed provider output.",
  )
  parser.add_argument(
    "--fail-fast",
    action="store_true",
    help="Stop on client or parser errors instead of continuing where possible.",
  )
  parser.add_argument(
    "--temperature",
    type=float,
    default=0.0,
    help="Provider temperature stored in decision-affecting config metadata.",
  )
  parser.add_argument(
    "--timeout-seconds",
    type=_positive_float,
    default=120.0,
    help="Provider request timeout in seconds. Defaults to 120.",
  )
  parser.add_argument(
    "--effort",
    choices=_EFFORT_LEVELS,
    default=None,
    help="Reasoning effort for providers that support it (anthropic*, openrouter*). Defaults to the model's own.",
  )
  parser.add_argument(
    "--response-cache",
    type=Path,
    default=None,
    help="Directory for a response cache: identical requests are answered from disk at no cost.",
  )
  parser.set_defaults(handler=_run_judge)


def _add_check_page_parser(subparsers: argparse._SubParsersAction) -> None:
  parser = subparsers.add_parser(
    "check-page",
    help="Judge one page (URL or saved HTML file) without exploring.",
    description="Record one page state, build candidates and judge them in isolated context. "
    "Findings list the element's CSS selector and XPath.",
  )
  parser.add_argument("target", help="URL or path to a saved HTML file.")
  parser.add_argument("--out", type=Path, default=None, help="Run directory (default: runs/check-page-<time>).")
  parser.add_argument("--provider", choices=_SUPPORTED_PROVIDER_NAMES, default="fake")
  parser.add_argument("--model", default=None)
  parser.add_argument("--prompt-version", default=None, help="Default: the provider's v5 prompt.")
  parser.add_argument("--candidate-type", action="append", default=[])
  parser.add_argument("--effort", choices=_EFFORT_LEVELS, default=None)
  parser.add_argument("--timeout-seconds", type=_positive_float, default=120.0)
  parser.add_argument("--response-cache", type=Path, default=None)
  parser.add_argument("--json", type=Path, default=None, help="Also write the findings JSON here.")
  parser.add_argument("--headed", action="store_true", help="Show the browser window.")
  parser.set_defaults(handler=_run_check_page)


def _run_check_page(args: argparse.Namespace) -> int:
  from datetime import datetime, timezone

  from src.check_page import CheckPageOptions, check_page

  out = args.out or Path("runs") / ("check-page-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
  try:
    report = check_page(CheckPageOptions(
      target=args.target, out_dir=out, provider=args.provider, model=args.model or "",
      prompt_version=args.prompt_version, candidate_types=tuple(args.candidate_type), effort=args.effort,
      timeout_seconds=args.timeout_seconds, response_cache=args.response_cache, headless=not args.headed))
  except Exception as exc:
    print(f"check-page failed: {exc}", file=sys.stderr)
    return 1
  if args.json:
    args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
  print(f"Candidates: {report['candidates']}  Findings: {len(report['findings'])}  Cost: ${report['estimated_cost_usd']:.4f}")
  for finding in report["findings"]:
    print(f"  [{finding['decision']}] {finding['candidate_type']}  {finding['css_selector'] or finding['xpath']}")
  print("Report:", Path(report["run_dir"]) / "check_page_findings.json")
  return 0


def _add_report_parser(subparsers: argparse._SubParsersAction) -> None:
  parser = subparsers.add_parser(
    "report",
    help="Generate a developer report from a model-judgment run.",
    description="Generate a Markdown-first developer report from one saved model-judgment run.",
  )
  parser.add_argument(
    "--run",
    type=Path,
    required=True,
    help="Completed run directory containing saved model-judgment artifacts.",
  )
  parser.add_argument(
    "--judgment-run-id",
    required=True,
    help="Model-judgment run id to report on.",
  )
  parser.add_argument(
    "--report-run-id",
    default=None,
    help="Explicit report run id.",
  )
  parser.add_argument(
    "--output-dir",
    type=Path,
    default=None,
    help="Optional explicit output directory.",
  )
  parser.add_argument(
    "--include-no-violation",
    action="store_true",
    help="Include detailed no_violation records in the Markdown appendix.",
  )
  parser.add_argument(
    "--overwrite",
    action="store_true",
    help="Replace an existing report output directory.",
  )
  parser.add_argument(
    "--no-load-source-candidates",
    dest="load_source_candidates",
    action="store_false",
    default=True,
    help="Do not load compact source candidate excerpts.",
  )
  parser.add_argument(
    "--no-verify-artifacts",
    dest="verify_artifacts",
    action="store_false",
    default=True,
    help="Do not check whether artifact_refs paths exist.",
  )
  parser.set_defaults(handler=_run_report)


def _run_crawl(args: argparse.Namespace) -> int:
  crawl_main = _load_crawl_main()
  asyncio.run(crawl_main(args.config))
  return 0


def _run_candidates(args: argparse.Namespace) -> int:
  build_semantic_candidates = _load_candidate_builder()
  summary = build_semantic_candidates(args.run, candidate_types=args.candidate_type)
  print("Semantic candidate builder finished.")
  print("Run dir:", summary.run_dir.resolve())
  print("Output dir:", summary.output_dir.resolve())
  counts = summary.manifest.get("counts", {})
  print(json.dumps(counts, ensure_ascii=False, indent=2))
  return 0


def _run_judge(args: argparse.Namespace) -> int:
  components = _load_judgment_components()
  parser = _build_parser()
  provider_spec = components.get_confirmation_provider_spec(args.provider)
  if provider_spec.model_required and not args.model:
    parser.error(f"--model is required when --provider {args.provider}")
  if args.model:
    try:
      provider_spec.validate_model(args.model)
    except ValueError as exc:
      parser.error(str(exc))
  prompt_version = args.prompt_version or provider_spec.default_prompt_version
  if args.prompt_version and args.prompt_version not in provider_spec.compatible_prompt_versions:
    parser.error(provider_spec.incompatible_prompt_version_message(args.prompt_version))

  candidate_ids = tuple(args.candidate_id or ())
  if args.candidate_id_file:
    try:
      candidate_ids = (*candidate_ids, *_read_candidate_id_file(args.candidate_id_file))
    except ValueError as exc:
      parser.error(str(exc))

  model = args.model or components.DEFAULT_FAKE_MODEL
  config = components.ConfirmationConfig(
    provider=args.provider,
    model=model,
    prompt_version=prompt_version,
    temperature=args.temperature,
    strict_parse=args.strict_parse,
    base_url=args.base_url if provider_spec.uses_ollama_api else None,
    timeout_seconds=args.timeout_seconds,
    context_mode=args.context_mode,
    escalation_policy=args.escalation_policy,
    effort=args.effort,
  )
  options = components.ConfirmationRunOptions(
    run_dir=args.run,
    confirmation_run_id=args.judgment_run_id,
    candidate_types=tuple(args.candidate_type or ()),
    candidate_ids=candidate_ids,
    candidate_id_file=args.candidate_id_file,
    limit=args.limit,
    overwrite=args.overwrite,
    dry_run=args.dry_run,
    save_prompts=args.save_prompts,
    save_raw_responses=args.save_raw_responses,
    fail_fast=args.fail_fast,
    argv=tuple(sys.argv if args._raw_argv is None else ["accessgraph.py", *args._raw_argv]),
    cwd=Path.cwd(),
  )

  client = None
  if args.response_cache is not None and not args.dry_run:
    from src.analysis.confirmation.providers.caching import CachingConfirmationClient
    from src.analysis.confirmation.providers.registry import build_confirmation_client, resolve_confirmation_config

    try:
      client = CachingConfirmationClient(
        build_confirmation_client(resolve_confirmation_config(config)),
        args.response_cache,
        parameters={"effort": args.effort, "timeout_seconds": args.timeout_seconds},
      )
    except ValueError as exc:
      parser.error(str(exc))
  try:
    extra = {"client": client} if client is not None else {}
    result = components.run_confirmation(config=config, options=options, **extra)
  except Exception as exc:
    print(f"model judgment failed: {exc}", file=sys.stderr)
    return 1

  counts = result.manifest["counts"]
  if result.dry_run:
    print(
      "Dry run: "
      f"selected {counts['candidates_selected']} of {counts['candidates_available']} candidates; "
      "no model judgments were written."
    )
    print(f"Planned model-judgment run id: {result.confirmation_run_id}")
    print(f"Planned output directory: {result.output_dir}")
    return 0

  print(
    "Model judgment run complete: "
    f"{counts['confirmations_written']} judgments written to {result.output_dir}"
  )
  print(f"Judgment run id: {result.confirmation_run_id}")
  return 0


def _run_report(args: argparse.Namespace) -> int:
  components = _load_report_components()
  options = components.ConfirmationReportOptions(
    run_dir=args.run,
    confirmation_run_id=args.judgment_run_id,
    report_run_id=args.report_run_id,
    output_dir=args.output_dir,
    include_no_violation=args.include_no_violation,
    overwrite=args.overwrite,
    load_source_candidates=args.load_source_candidates,
    verify_artifacts=args.verify_artifacts,
    argv=tuple(sys.argv if args._raw_argv is None else ["accessgraph.py", *args._raw_argv]),
    cwd=Path.cwd(),
  )

  try:
    result = components.run_confirmation_report(options=options)
  except Exception as exc:
    print(f"report generation failed: {exc}", file=sys.stderr)
    return 1

  summary = result.report["summary"]
  print(
    "Developer report complete: "
    f"{summary['total_records']} model-judgment records summarized in {result.output_dir}"
  )
  print(f"Report run id: {result.report_run_id}")
  return 0


def _load_crawl_main() -> Callable[[Path], Any]:
  import main as crawler_main

  return crawler_main.main


def _load_candidate_builder() -> Callable[..., Any]:
  from src.analysis.candidates import build_semantic_candidates

  return build_semantic_candidates


def _load_judgment_components() -> SimpleNamespace:
  from src.analysis.confirmation.models import ConfirmationConfig
  from src.analysis.confirmation.providers.fake import DEFAULT_FAKE_MODEL
  from src.analysis.confirmation.providers.registry import get_confirmation_provider_spec
  from src.analysis.confirmation.runner import ConfirmationRunOptions, run_confirmation

  return SimpleNamespace(
    ConfirmationConfig=ConfirmationConfig,
    ConfirmationRunOptions=ConfirmationRunOptions,
    DEFAULT_FAKE_MODEL=DEFAULT_FAKE_MODEL,
    get_confirmation_provider_spec=get_confirmation_provider_spec,
    run_confirmation=run_confirmation,
  )


def _load_report_components() -> SimpleNamespace:
  from src.analysis.reporting.models import ConfirmationReportOptions
  from src.analysis.reporting.runner import run_confirmation_report

  return SimpleNamespace(
    ConfirmationReportOptions=ConfirmationReportOptions,
    run_confirmation_report=run_confirmation_report,
  )


def _non_negative_int(value: str) -> int:
  parsed = int(value)
  if parsed < 0:
    raise argparse.ArgumentTypeError("must be zero or greater")
  return parsed


def _positive_float(value: str) -> float:
  parsed = float(value)
  if parsed <= 0:
    raise argparse.ArgumentTypeError("must be greater than zero")
  return parsed


def _read_candidate_id_file(path: Path) -> tuple[str, ...]:
  if not path.exists() or not path.is_file():
    raise ValueError(f"--candidate-id-file does not exist or is not a file: {path}")
  candidate_ids: list[str] = []
  with path.open("r", encoding="utf-8") as handle:
    for line in handle:
      candidate_id = line.strip()
      if not candidate_id or candidate_id.startswith("#"):
        continue
      candidate_ids.append(candidate_id)
  if not candidate_ids:
    raise ValueError(f"--candidate-id-file did not contain any candidate ids: {path}")
  return tuple(candidate_ids)


def _with_raw_argv(argv: list[str] | None, parsed: argparse.Namespace) -> argparse.Namespace:
  parsed._raw_argv = argv
  return parsed


if __name__ == "__main__":
  parser = _build_parser()
  parsed_args = _with_raw_argv(sys.argv[1:], parser.parse_args())
  raise SystemExit(parsed_args.handler(parsed_args))
