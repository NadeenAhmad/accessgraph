from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.benchmarks.checkout import spa_process


def test_build_checkout_app_runs_checkout_build(monkeypatch):
  calls = []

  def fake_run_command(cmd, *, cwd, timeout_seconds):
    calls.append((cmd, cwd, timeout_seconds))
    return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

  monkeypatch.setattr(spa_process, "run_command", fake_run_command)

  spa_process.build_checkout_app()

  assert len(calls) == 1
  cmd, cwd, timeout_seconds = calls[0]
  assert cmd[1:] == ["run", "build"]
  assert cmd[0] in {"npm", "npm.cmd"}
  assert cwd == spa_process.CHECKOUT_DIR
  assert timeout_seconds == 120


def test_build_checkout_app_reports_failed_build(monkeypatch):
  def fake_run_command(cmd, *, cwd, timeout_seconds):
    return subprocess.CompletedProcess(cmd, 1, stdout="build out", stderr="build err")

  monkeypatch.setattr(spa_process, "run_command", fake_run_command)

  with pytest.raises(RuntimeError, match="Checkout benchmark build failed"):
    spa_process.build_checkout_app()


def test_start_vite_preview_uses_local_vite_binary(tmp_path, monkeypatch):
  checkout_dir = tmp_path / "checkout-flow"
  vite_bin = checkout_dir / "node_modules" / "vite" / "bin" / "vite.js"
  vite_bin.parent.mkdir(parents=True)
  vite_bin.write_text("", encoding="utf-8")
  popen_calls = []

  class FakeProcess:
    pass

  def fake_popen(cmd, **kwargs):
    popen_calls.append((cmd, kwargs))
    return FakeProcess()

  monkeypatch.setattr(spa_process, "CHECKOUT_DIR", checkout_dir)
  monkeypatch.setattr(spa_process.subprocess, "Popen", fake_popen)

  process = spa_process.start_vite_preview(port=49231)

  assert isinstance(process, FakeProcess)
  assert len(popen_calls) == 1
  cmd, kwargs = popen_calls[0]
  assert cmd == [
    "node",
    str(vite_bin),
    "preview",
    "--host",
    "127.0.0.1",
    "--port",
    "49231",
  ]
  assert kwargs["cwd"] == checkout_dir
  assert kwargs["text"] is True
  assert kwargs["stdout"] == subprocess.PIPE
  assert kwargs["stderr"] == subprocess.PIPE


def test_stop_process_terminates_running_process():
  class FakeProcess:
    def __init__(self):
      self.terminated = False
      self.killed = False
      self.waited = False

    def poll(self):
      return None

    def terminate(self):
      self.terminated = True

    def wait(self, *, timeout):
      self.waited = True

    def kill(self):
      self.killed = True

  process = FakeProcess()

  spa_process.stop_process(process)

  assert process.terminated
  assert process.waited
  assert not process.killed


def test_controlled_support_destination_profile_membership_is_narrow():
  assert spa_process.requires_controlled_support_destination("checkout-co-sem-027")
  assert spa_process.requires_controlled_support_destination("checkout-co-sem-102")
  assert not spa_process.requires_controlled_support_destination("checkout-co-sem-052")
  assert not spa_process.requires_controlled_support_destination(None)
