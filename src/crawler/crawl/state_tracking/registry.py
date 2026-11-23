from __future__ import annotations

from dataclasses import dataclass, field

from ..priority import ActionKey


@dataclass
class StateRegistry:
  """Track crawler-local state ids, dedupe keys, and attempted actions."""

  known_key_to_state: dict[str, str] = field(default_factory=dict)
  attempted_actions_by_state_id: dict[str, set[ActionKey]] = field(default_factory=dict)
  next_state_num: int = 0

  def next_state_id(self) -> str:
    state_id = f"state_{self.next_state_num:04d}"
    self.next_state_num += 1
    return state_id

  def remember_state_key(self, key: str, state_id: str) -> None:
    self.known_key_to_state[key] = state_id

  def state_for_key(self, key: str) -> str | None:
    return self.known_key_to_state.get(key)

  def initialize_attempts(self, state_id: str) -> None:
    self.attempted_actions_by_state_id[state_id] = set()

  def attempted_actions_for_state(self, state_id: str) -> set[ActionKey]:
    return self.attempted_actions_by_state_id.setdefault(state_id, set())

  def record_attempted_action(self, state_id: str, action_key: ActionKey) -> bool:
    attempted = self.attempted_actions_for_state(state_id)
    if action_key in attempted:
      return False
    attempted.add(action_key)
    return True
