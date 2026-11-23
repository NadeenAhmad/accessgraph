import json

import pytest

from src.crawler.config.app_config import load_app_config


def test_load_app_config_reads_crawl_settings(tmp_path):
  cfg_path = tmp_path / "cfg.json"
  cfg_path.write_text(
    json.dumps(
      {
        "url": "https://example.org",
        "headless": False,
        "runs_dir": "custom_runs",
        "enable_run_timing": False,
        "crawl": {
          "max_states": 42,
          "max_depth": 4,
          "max_actions_per_state": 9,
          "back_timeout_ms": 12345,
          "traversal_strategy": "bfs",
          "scope_policy": "same_origin",
          "prioritize_action_candidates": True,
          "enable_tile_screenshots": False,
          "wait_timeout_ms": 2345,
        },
      }
    ),
    encoding="utf-8",
  )

  cfg = load_app_config(cfg_path)
  assert cfg.url == "https://example.org"
  assert cfg.headless is False
  assert cfg.runs_dir == "custom_runs"
  assert cfg.enable_run_timing is False
  assert cfg.crawl.max_states == 42
  assert cfg.crawl.max_depth == 4
  assert cfg.crawl.max_actions_per_state == 9
  assert cfg.crawl.back_timeout_ms == 12345
  assert cfg.crawl.traversal_strategy == "bfs"
  assert cfg.crawl.scope_policy == "same_origin"
  assert cfg.crawl.prioritize_action_candidates is True
  assert cfg.crawl.enable_tile_screenshots is False
  assert cfg.crawl.wait_timeout_ms == 2345
  assert not hasattr(cfg.crawl, "semantic_handlers")


def test_load_app_config_defaults_to_bfs(tmp_path):
  cfg_path = tmp_path / "cfg.json"
  cfg_path.write_text(json.dumps({}), encoding="utf-8")

  cfg = load_app_config(cfg_path)

  assert cfg.crawl.traversal_strategy == "bfs"
  assert cfg.crawl.scope_policy == "same_origin"
  assert cfg.crawl.max_states == 100
  assert cfg.crawl.max_depth == 5
  assert cfg.crawl.wait_timeout_ms == 2000


def test_load_app_config_accepts_legacy_prioritize_candidates_key(tmp_path):
  cfg_path = tmp_path / "cfg.json"
  cfg_path.write_text(
    json.dumps(
      {
        "crawl": {
          "prioritize_candidates": True,
        }
      }
    ),
    encoding="utf-8",
  )

  cfg = load_app_config(cfg_path)

  assert cfg.crawl.prioritize_action_candidates is True


def test_load_app_config_prefers_prioritize_action_candidates_key(tmp_path):
  cfg_path = tmp_path / "cfg.json"
  cfg_path.write_text(
    json.dumps(
      {
        "crawl": {
          "prioritize_action_candidates": False,
          "prioritize_candidates": True,
        }
      }
    ),
    encoding="utf-8",
  )

  cfg = load_app_config(cfg_path)

  assert cfg.crawl.prioritize_action_candidates is False


def test_load_app_config_rejects_invalid_strategy(tmp_path):
  cfg_path = tmp_path / "cfg.json"
  cfg_path.write_text(
    json.dumps(
      {
        "crawl": {
          "traversal_strategy": "random_walk",
        }
      }
    ),
    encoding="utf-8",
  )

  with pytest.raises(ValueError, match="traversal_strategy"):
    load_app_config(cfg_path)


def test_load_app_config_rejects_invalid_scope_policy(tmp_path):
  cfg_path = tmp_path / "cfg.json"
  cfg_path.write_text(
    json.dumps(
      {
        "crawl": {
          "scope_policy": "offsite_allowed",
        }
      }
    ),
    encoding="utf-8",
  )

  with pytest.raises(ValueError, match="scope_policy"):
    load_app_config(cfg_path)


def test_load_app_config_rejects_invalid_prioritize_action_candidates_flag(tmp_path):
  cfg_path = tmp_path / "cfg.json"
  cfg_path.write_text(
    json.dumps(
      {
        "crawl": {
          "prioritize_action_candidates": "yes",
        }
      }
    ),
    encoding="utf-8",
  )

  with pytest.raises(ValueError, match="prioritize_action_candidates"):
    load_app_config(cfg_path)


def test_load_app_config_rejects_invalid_legacy_prioritize_candidates_flag(tmp_path):
  cfg_path = tmp_path / "cfg.json"
  cfg_path.write_text(
    json.dumps(
      {
        "crawl": {
          "prioritize_candidates": "yes",
        }
      }
    ),
    encoding="utf-8",
  )

  with pytest.raises(ValueError, match="prioritize_candidates"):
    load_app_config(cfg_path)


def test_load_app_config_rejects_invalid_enable_tile_screenshots_flag(tmp_path):
  cfg_path = tmp_path / "cfg.json"
  cfg_path.write_text(
    json.dumps(
      {
        "crawl": {
          "enable_tile_screenshots": "no",
        }
      }
    ),
    encoding="utf-8",
  )

  with pytest.raises(ValueError, match="enable_tile_screenshots"):
    load_app_config(cfg_path)


def test_load_app_config_rejects_invalid_enable_run_timing_flag(tmp_path):
  cfg_path = tmp_path / "cfg.json"
  cfg_path.write_text(
    json.dumps(
      {
        "enable_run_timing": "sometimes",
      }
    ),
    encoding="utf-8",
  )

  with pytest.raises(ValueError, match="enable_run_timing"):
    load_app_config(cfg_path)


def test_load_app_config_rejects_invalid_url_type(tmp_path):
  cfg_path = tmp_path / "cfg.json"
  cfg_path.write_text(
    json.dumps(
      {
        "url": 123,
      }
    ),
    encoding="utf-8",
  )

  with pytest.raises(ValueError, match="`url` must be a string"):
    load_app_config(cfg_path)


def test_load_app_config_rejects_invalid_headless_type(tmp_path):
  cfg_path = tmp_path / "cfg.json"
  cfg_path.write_text(
    json.dumps(
      {
        "headless": "false",
      }
    ),
    encoding="utf-8",
  )

  with pytest.raises(ValueError, match="`headless` must be a boolean"):
    load_app_config(cfg_path)


def test_load_app_config_rejects_invalid_runs_dir_type(tmp_path):
  cfg_path = tmp_path / "cfg.json"
  cfg_path.write_text(
    json.dumps(
      {
        "runs_dir": ["runs"],
      }
    ),
    encoding="utf-8",
  )

  with pytest.raises(ValueError, match="`runs_dir` must be a string"):
    load_app_config(cfg_path)


def test_load_app_config_rejects_non_string_traversal_strategy(tmp_path):
  cfg_path = tmp_path / "cfg.json"
  cfg_path.write_text(
    json.dumps(
      {
        "crawl": {
          "traversal_strategy": True,
        }
      }
    ),
    encoding="utf-8",
  )

  with pytest.raises(ValueError, match="`crawl.traversal_strategy` must be a string"):
    load_app_config(cfg_path)


def test_load_app_config_rejects_non_string_scope_policy(tmp_path):
  cfg_path = tmp_path / "cfg.json"
  cfg_path.write_text(
    json.dumps(
      {
        "crawl": {
          "scope_policy": 1,
        }
      }
    ),
    encoding="utf-8",
  )

  with pytest.raises(ValueError, match="`crawl.scope_policy` must be a string"):
    load_app_config(cfg_path)


@pytest.mark.parametrize(
  ("key", "value"),
  [
    ("max_depth", -1),
    ("max_states", -1),
    ("max_actions_per_state", -1),
    ("back_timeout_ms", -1),
    ("wait_timeout_ms", -1),
    ("max_depth", "3"),
    ("max_states", False),
    ("max_actions_per_state", False),
  ],
)
def test_load_app_config_rejects_invalid_crawl_numeric_fields(tmp_path, key, value):
  cfg_path = tmp_path / "cfg.json"
  cfg_path.write_text(
    json.dumps(
      {
        "crawl": {
          key: value,
        }
      }
    ),
    encoding="utf-8",
  )

  with pytest.raises(ValueError, match=fr"`crawl\.{key}` must be a non-negative integer"):
    load_app_config(cfg_path)
