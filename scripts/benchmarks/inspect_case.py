from __future__ import annotations

import argparse
import difflib
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(REPO_ROOT))

from scripts.benchmarks.case_metadata import (
  BenchmarkCase,
  CaseMetadataError,
  UnknownBenchmarkCaseError,
  resolve_case,
)
from scripts.benchmarks.explorer.session import (
  BenchmarkExplorerSession,
  SessionError,
)


def main(argv: list[str] | None = None) -> int:
  args = _parse_args(argv)
  try:
    benchmark_case = resolve_case(args.case_id)
  except UnknownBenchmarkCaseError as exc:
    _print_unknown_case(exc)
    return 2
  except CaseMetadataError as exc:
    print(str(exc), file=sys.stderr)
    return 1

  if not benchmark_case.is_launchable:
    _print_non_launchable_case(benchmark_case)
    return 2

  try:
    return launch_case(benchmark_case, skip_build=args.skip_build)
  except KeyboardInterrupt:
    print("\nStopped.")
    return 0
  except (CaseMetadataError, SessionError) as exc:
    print(str(exc), file=sys.stderr)
    return 1


def launch_case(benchmark_case: BenchmarkCase, *, skip_build: bool) -> int:
  session = BenchmarkExplorerSession(skip_build=skip_build, logger=print)
  try:
    status = session.open_case(benchmark_case)
    print(format_case_summary(benchmark_case, opening_url=status.url or ""))
    if status.support_url:
      print(f"Controlled support destination: {status.support_url}")
    print("Browser opened. Press Ctrl+C to stop.")
    while True:
      time.sleep(3600)
  finally:
    session.shutdown()


def format_case_summary(benchmark_case: BenchmarkCase, *, opening_url: str) -> str:
  profile = benchmark_case.executable_profile or "(none)"
  return "\n".join(
    [
      f"Case: {benchmark_case.case_id}",
      f"Type: {benchmark_case.violation_type}",
      f"Status: {benchmark_case.status}",
      f"Tier: {benchmark_case.tier}",
      f"Evidence state: {benchmark_case.evidence_state}",
      f"Profile: {profile}",
      "",
      "Baseline:",
      benchmark_case.baseline,
      "",
      "Mutation:",
      benchmark_case.mutation,
      "",
      "Why unambiguous:",
      benchmark_case.why_unambiguous,
      "",
      "Interaction path:",
      benchmark_case.interaction_path or "Products page (initial state)",
      "",
      "Opening:",
      opening_url,
    ]
  )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description="Open an implemented benchmark case in a headed local SPA browser."
  )
  parser.add_argument("case_id", help="Benchmark case ID, for example co-sem-052.")
  parser.add_argument(
    "--skip-build",
    action="store_true",
    help="Use the existing Checkout dist output instead of running npm run build.",
  )
  return parser.parse_args(argv)


def _print_unknown_case(exc: UnknownBenchmarkCaseError) -> None:
  print(f"Unknown benchmark case: {exc.case_id}", file=sys.stderr)
  matches = difflib.get_close_matches(exc.case_id, exc.available_case_ids, n=3)
  if matches:
    print(f"Did you mean: {', '.join(matches)}", file=sys.stderr)


def _print_non_launchable_case(benchmark_case: BenchmarkCase) -> None:
  print(
    f"Case {benchmark_case.case_id} exists but is not launchable yet.",
    file=sys.stderr,
  )
  print(f"Status: {benchmark_case.status}", file=sys.stderr)
  if benchmark_case.executable_profile is None:
    print("No executable benchmark profile is available.", file=sys.stderr)
  else:
    print(
      f"Executable profile {benchmark_case.executable_profile!r} exists, "
      "but the tracker status is not implemented/accepted.",
      file=sys.stderr,
    )


if __name__ == "__main__":
  raise SystemExit(main())
