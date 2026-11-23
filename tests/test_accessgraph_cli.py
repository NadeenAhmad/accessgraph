from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import accessgraph


class _ProviderSpec:
  model_required = False
  uses_ollama_api = False
  compatible_prompt_versions = ("prompt_v1",)
  default_prompt_version = "prompt_v1"

  def validate_model(self, model: str) -> str:
    return model

  def incompatible_prompt_version_message(self, prompt_version: str) -> str:
    return f"incompatible prompt version: {prompt_version}"


class _Options:
  def __init__(self, **kwargs):
    self.__dict__.update(kwargs)


class _Config:
  def __init__(self, **kwargs):
    self.__dict__.update(kwargs)


def test_top_level_help_lists_stage_commands():
  help_text = accessgraph._build_parser().format_help()

  assert "crawl" in help_text
  assert "candidates" in help_text
  assert "judge" in help_text
  assert "report" in help_text


def test_judge_help_uses_model_judgment_wording(capsys):
  parser = accessgraph._build_parser()

  with pytest.raises(SystemExit) as exc_info:
    parser.parse_args(["judge", "--help"])

  assert exc_info.value.code == 0
  help_text = capsys.readouterr().out
  assert "model judgment" in help_text.lower()
  assert "confirmation" not in help_text.lower()


def test_crawl_delegates_to_current_crawl_entry(monkeypatch, tmp_path):
  calls: list[Path] = []

  async def fake_crawl_main(config_path: Path) -> None:
    calls.append(config_path)

  def fail_if_loaded():
    raise AssertionError("crawl must not load candidate generation")

  monkeypatch.setattr(accessgraph, "_load_crawl_main", lambda: fake_crawl_main)
  monkeypatch.setattr(accessgraph, "_load_candidate_builder", fail_if_loaded)
  monkeypatch.setattr(accessgraph, "_load_judgment_components", fail_if_loaded)
  monkeypatch.setattr(accessgraph, "_load_report_components", fail_if_loaded)

  config_path = tmp_path / "crawler_config.json"
  exit_code = accessgraph.main(["crawl", "--config", str(config_path)])

  assert exit_code == 0
  assert calls == [config_path]


def test_candidates_delegates_to_candidate_builder(monkeypatch, tmp_path, capsys):
  calls: list[tuple[Path, list[str] | None]] = []

  def fake_builder(run_dir: Path, *, candidate_types: list[str] | None = None):
    calls.append((run_dir, candidate_types))
    return SimpleNamespace(
      run_dir=run_dir,
      output_dir=run_dir / "candidates",
      manifest={"counts": {"candidates_total": 2}},
    )

  monkeypatch.setattr(accessgraph, "_load_candidate_builder", lambda: fake_builder)

  exit_code = accessgraph.main(
    [
      "candidates",
      "--run",
      str(tmp_path),
      "--candidate-type",
      "button-label-mismatch",
    ]
  )

  assert exit_code == 0
  assert calls == [(tmp_path, ["button-label-mismatch"])]
  assert "Semantic candidate builder finished" in capsys.readouterr().out


def test_judge_maps_judgment_run_id_to_internal_option(monkeypatch, tmp_path, capsys):
  captured: dict[str, object] = {}

  def fake_run_confirmation(*, config, options):
    captured["config"] = config
    captured["options"] = options
    return SimpleNamespace(
      confirmation_run_id=options.confirmation_run_id,
      output_dir=tmp_path / "confirmations" / options.confirmation_run_id,
      dry_run=False,
      manifest={"counts": {"confirmations_written": 3}},
    )

  monkeypatch.setattr(
    accessgraph,
    "_load_judgment_components",
    lambda: SimpleNamespace(
      ConfirmationConfig=_Config,
      ConfirmationRunOptions=_Options,
      DEFAULT_FAKE_MODEL="fake-model",
      get_confirmation_provider_spec=lambda _provider: _ProviderSpec(),
      run_confirmation=fake_run_confirmation,
    ),
  )

  exit_code = accessgraph.main(
    [
      "judge",
      "--run",
      str(tmp_path),
      "--provider",
      "fake",
      "--judgment-run-id",
      "judgment-test",
      "--limit",
      "5",
      "--dry-run",
    ]
  )

  options = captured["options"]
  config = captured["config"]
  assert exit_code == 0
  assert options.run_dir == tmp_path
  assert options.confirmation_run_id == "judgment-test"
  assert options.limit == 5
  assert options.dry_run is True
  assert config.provider == "fake"
  assert config.model == "fake-model"
  out = capsys.readouterr().out
  assert "Model judgment run complete" in out
  assert "Judgment run id: judgment-test" in out


def test_report_maps_judgment_run_id_to_report_options(monkeypatch, tmp_path, capsys):
  captured: dict[str, object] = {}

  def fake_run_report(*, options):
    captured["options"] = options
    return SimpleNamespace(
      report_run_id="report-test",
      output_dir=tmp_path / "reports" / "report-test",
      report={"summary": {"total_records": 4}},
    )

  monkeypatch.setattr(
    accessgraph,
    "_load_report_components",
    lambda: SimpleNamespace(
      ConfirmationReportOptions=_Options,
      run_confirmation_report=fake_run_report,
    ),
  )

  exit_code = accessgraph.main(
    [
      "report",
      "--run",
      str(tmp_path),
      "--judgment-run-id",
      "judgment-test",
      "--report-run-id",
      "report-test",
      "--include-no-violation",
      "--no-load-source-candidates",
      "--no-verify-artifacts",
    ]
  )

  options = captured["options"]
  assert exit_code == 0
  assert options.run_dir == tmp_path
  assert options.confirmation_run_id == "judgment-test"
  assert options.report_run_id == "report-test"
  assert options.include_no_violation is True
  assert options.load_source_candidates is False
  assert options.verify_artifacts is False
  assert "model-judgment records" in capsys.readouterr().out
