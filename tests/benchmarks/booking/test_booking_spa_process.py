from __future__ import annotations

import subprocess
from contextlib import contextmanager
from io import StringIO

import pytest

from scripts.benchmarks.booking import spa_process


class FakeProcess:
  def __init__(
    self,
    *,
    exit_code: int | None = None,
    wait_times_out: bool = False,
    with_output: bool = True,
  ):
    self.exit_code = exit_code
    self.wait_times_out = wait_times_out
    self.terminated = False
    self.killed = False
    self.wait_calls: list[int] = []
    if with_output:
      setattr(
        self,
        spa_process._STDOUT_CAPTURE_ATTRIBUTE,
        StringIO("preview stdout"),
      )
      setattr(
        self,
        spa_process._STDERR_CAPTURE_ATTRIBUTE,
        StringIO("preview stderr"),
      )

  def poll(self):
    return self.exit_code

  def terminate(self):
    self.terminated = True

  def kill(self):
    self.killed = True
    self.exit_code = -9

  def wait(self, *, timeout):
    self.wait_calls.append(timeout)
    if self.wait_times_out and not self.killed:
      raise subprocess.TimeoutExpired("vite", timeout)
    self.exit_code = 0 if not self.killed else self.exit_code
    return self.exit_code


@contextmanager
def successful_response(status: int = 200):
  yield type("Response", (), {"status": status})()


def test_build_booking_app_uses_bounded_npm_command(monkeypatch):
  captured = {}

  def fake_run(command, *, cwd, timeout_seconds):
    captured.update(
      command=command,
      cwd=cwd,
      timeout_seconds=timeout_seconds,
    )
    return subprocess.CompletedProcess(command, 0, "built", "")

  monkeypatch.setattr(spa_process, "run_command", fake_run)

  result = spa_process.build_booking_app()

  assert captured == {
    "command": [spa_process.npm_executable(), "run", "build"],
    "cwd": spa_process.BOOKING_DIR,
    "timeout_seconds": 120,
  }
  assert result.stdout == "built"


def test_build_booking_app_surfaces_command_exit_and_output(monkeypatch):
  monkeypatch.setattr(
    spa_process,
    "run_command",
    lambda *args, **kwargs: subprocess.CompletedProcess(
      args[0],
      7,
      "build stdout",
      "build stderr",
    ),
  )

  with pytest.raises(RuntimeError) as error:
    spa_process.build_booking_app()

  message = str(error.value)
  assert "Booking SPA build failed" in message
  assert "exit code: 7" in message
  assert "build stdout" in message
  assert "build stderr" in message


def test_start_vite_preview_uses_local_vite_and_caller_port(monkeypatch):
  captured = {}

  def fake_popen(command, **kwargs):
    captured.update(command=command, kwargs=kwargs)
    return FakeProcess(with_output=False)

  monkeypatch.setattr(spa_process.subprocess, "Popen", fake_popen)

  process = spa_process.start_vite_preview(port=43127)

  assert isinstance(process, FakeProcess)
  assert captured["command"] == [
    "node",
    str(
      spa_process.BOOKING_DIR
      / "node_modules"
      / "vite"
      / "bin"
      / "vite.js"
    ),
    "preview",
    "--host",
    "127.0.0.1",
    "--port",
    "43127",
    "--strictPort",
  ]
  assert captured["kwargs"]["cwd"] == spa_process.BOOKING_DIR
  assert captured["kwargs"]["stdout"] is getattr(
    process,
    spa_process._STDOUT_CAPTURE_ATTRIBUTE,
  )
  assert captured["kwargs"]["stderr"] is getattr(
    process,
    spa_process._STDERR_CAPTURE_ATTRIBUTE,
  )
  assert captured["kwargs"]["stdout"] is not subprocess.PIPE
  assert captured["kwargs"]["stderr"] is not subprocess.PIPE
  spa_process._close_preview_output(process)


def test_wait_for_preview_returns_on_http_readiness(monkeypatch):
  process = FakeProcess()
  monkeypatch.setattr(
    spa_process,
    "urlopen",
    lambda *args, **kwargs: successful_response(),
  )

  spa_process.wait_for_preview(
    process,
    "http://127.0.0.1:43127/services",
    timeout_seconds=1,
  )


def test_wait_for_preview_reports_early_process_exit(monkeypatch):
  process = FakeProcess(exit_code=3)
  monkeypatch.setattr(
    spa_process,
    "urlopen",
    lambda *args, **kwargs: pytest.fail("HTTP should not be polled after exit"),
  )

  with pytest.raises(RuntimeError) as error:
    spa_process.wait_for_preview(
      process,
      "http://127.0.0.1:43127/services",
      timeout_seconds=1,
    )

  message = str(error.value)
  assert "exited before readiness" in message
  assert "Exit code: 3" in message
  assert "preview stdout" in message
  assert "preview stderr" in message


def test_wait_for_preview_timeout_stops_process_and_reports_output():
  process = FakeProcess()

  with pytest.raises(RuntimeError) as error:
    spa_process.wait_for_preview(
      process,
      "http://127.0.0.1:43127/services",
      timeout_seconds=0,
    )

  message = str(error.value)
  assert "Timed out waiting for Booking SPA preview" in message
  assert "preview stdout" in message
  assert "preview stderr" in message
  assert process.terminated is True


def test_readiness_timeout_remains_primary_when_shutdown_also_fails(monkeypatch):
  process = FakeProcess()
  monkeypatch.setattr(
    spa_process,
    "stop_process",
    lambda process: (_ for _ in ()).throw(RuntimeError("shutdown failed")),
  )

  with pytest.raises(RuntimeError) as error:
    spa_process.wait_for_preview(
      process,
      "http://127.0.0.1:43127/services",
      timeout_seconds=0,
    )

  assert "Timed out waiting for Booking SPA preview" in str(error.value)
  assert any(
    "shutdown also failed: shutdown failed" in note
    for note in getattr(error.value, "__notes__", [])
  )


def test_stop_process_terminates_cleanly():
  process = FakeProcess()

  spa_process.stop_process(process)

  assert process.terminated is True
  assert process.killed is False
  assert process.wait_calls == [5]


def test_stop_process_kills_after_bounded_wait():
  process = FakeProcess(wait_times_out=True)

  spa_process.stop_process(process)

  assert process.terminated is True
  assert process.killed is True
  assert process.wait_calls == [5, 5]


@pytest.mark.parametrize("requested_port", [None, 43127])
def test_open_booking_spa_uses_selected_port_and_always_stops(
  monkeypatch,
  requested_port,
):
  processes: list[FakeProcess] = []
  stopped: list[FakeProcess] = []
  readiness_urls: list[str] = []
  build_calls: list[bool] = []

  monkeypatch.setattr(
    spa_process,
    "build_booking_app",
    lambda: build_calls.append(True),
  )
  monkeypatch.setattr(spa_process, "find_free_port", lambda: 45119)

  def fake_start(*, port):
    process = FakeProcess()
    processes.append(process)
    return process

  monkeypatch.setattr(spa_process, "start_vite_preview", fake_start)
  monkeypatch.setattr(
    spa_process,
    "wait_for_preview",
    lambda process, url: readiness_urls.append(url),
  )
  monkeypatch.setattr(
    spa_process,
    "stop_process",
    lambda process: stopped.append(process),
  )

  with spa_process.open_booking_spa(port=requested_port) as server:
    expected_port = requested_port if requested_port is not None else 45119
    assert server.port == expected_port
    assert server.base_url == f"http://127.0.0.1:{expected_port}"

  assert build_calls == [True]
  assert readiness_urls == [f"{server.base_url}/services"]
  assert stopped == processes


def test_open_booking_spa_preserves_body_error_when_cleanup_fails(monkeypatch):
  process = FakeProcess()
  monkeypatch.setattr(spa_process, "build_booking_app", lambda: None)
  monkeypatch.setattr(spa_process, "start_vite_preview", lambda **kwargs: process)
  monkeypatch.setattr(spa_process, "wait_for_preview", lambda *args, **kwargs: None)
  monkeypatch.setattr(
    spa_process,
    "stop_process",
    lambda process: (_ for _ in ()).throw(RuntimeError("cleanup failed")),
  )
  primary_error = ValueError("caller failed")

  with pytest.raises(ValueError) as error:
    with spa_process.open_booking_spa(port=43127):
      raise primary_error

  assert error.value is primary_error
  assert any(
    "preview cleanup also failed: cleanup failed" in note
    for note in getattr(error.value, "__notes__", [])
  )


def test_open_booking_spa_surfaces_cleanup_only_failure(monkeypatch):
  process = FakeProcess()
  monkeypatch.setattr(spa_process, "build_booking_app", lambda: None)
  monkeypatch.setattr(spa_process, "start_vite_preview", lambda **kwargs: process)
  monkeypatch.setattr(spa_process, "wait_for_preview", lambda *args, **kwargs: None)
  monkeypatch.setattr(
    spa_process,
    "stop_process",
    lambda process: (_ for _ in ()).throw(RuntimeError("cleanup failed")),
  )

  with pytest.raises(RuntimeError, match="cleanup failed"):
    with spa_process.open_booking_spa(port=43127):
      pass
