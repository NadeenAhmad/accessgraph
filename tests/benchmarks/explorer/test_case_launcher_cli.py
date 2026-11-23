from __future__ import annotations

from scripts.benchmarks import inspect_case
from scripts.benchmarks.case_metadata import resolve_case


def test_cli_launches_implemented_case_with_resolved_profile(monkeypatch):
  calls: list[tuple[str, str | None, bool]] = []

  def fake_launch_case(benchmark_case, *, skip_build):
    calls.append((benchmark_case.case_id, benchmark_case.executable_profile, skip_build))
    return 0

  monkeypatch.setattr(inspect_case, "launch_case", fake_launch_case)

  assert inspect_case.main(["co-sem-052", "--skip-build"]) == 0
  assert calls == [("co-sem-052", "checkout-co-sem-052", True)]


def test_cli_rejects_planned_case_without_launching(
  monkeypatch,
  capsys,
  planned_benchmark_case,
):
  planned_case_id = planned_benchmark_case.case_id

  def fail_launch_case(*args, **kwargs):
    raise AssertionError("planned case should not launch")

  monkeypatch.setattr(
    inspect_case,
    "resolve_case",
    lambda case_id: planned_benchmark_case,
  )
  monkeypatch.setattr(inspect_case, "launch_case", fail_launch_case)

  assert inspect_case.main([planned_case_id]) == 2
  captured = capsys.readouterr()
  assert f"Case {planned_case_id} exists but is not launchable yet." in captured.err
  assert "Status: planned" in captured.err
  assert "No executable benchmark profile is available." in captured.err


def test_cli_rejects_unknown_case(capsys):
  assert inspect_case.main(["co-sem-999"]) == 2

  captured = capsys.readouterr()
  assert "Unknown benchmark case: co-sem-999" in captured.err


def test_case_summary_prints_reviewer_metadata():
  benchmark_case = resolve_case("co-sem-052")

  summary = inspect_case.format_case_summary(
    benchmark_case,
    opening_url="http://127.0.0.1:4173/products",
  )

  assert "Case: co-sem-052" in summary
  assert "Type: landmark-purpose-mismatch" in summary
  assert "Profile: checkout-co-sem-052" in summary
  assert "Baseline:" in summary
  assert "Mutation:" in summary
  assert "Interaction path:" in summary
  assert "Opening:" in summary
