from __future__ import annotations

from src.crawler.crawl.state_tracking.registry import StateRegistry


def test_state_registry_generates_stable_incrementing_state_ids():
  registry = StateRegistry()

  assert registry.next_state_id() == "state_0000"
  assert registry.next_state_id() == "state_0001"
  assert registry.next_state_num == 2


def test_state_registry_tracks_dedupe_keys_and_attempted_actions():
  registry = StateRegistry()
  action_key = ("identity", "button-open")

  registry.remember_state_key("key-one", "state_0001")
  registry.initialize_attempts("state_0001")

  assert registry.state_for_key("key-one") == "state_0001"
  assert registry.state_for_key("missing") is None
  assert registry.record_attempted_action("state_0001", action_key) is True
  assert registry.record_attempted_action("state_0001", action_key) is False
  assert registry.attempted_actions_for_state("state_0001") == {action_key}
