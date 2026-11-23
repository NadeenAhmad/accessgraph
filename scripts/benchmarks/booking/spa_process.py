from __future__ import annotations

import os
import socket
import subprocess
import tempfile
import time
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
from urllib.request import urlopen


REPO_ROOT = Path(__file__).resolve().parents[3]
BOOKING_DIR = REPO_ROOT / "benchmarks" / "local-spas" / "booking-scheduler"
BOOKING_HOST = "127.0.0.1"
BUILD_TIMEOUT_SECONDS = 120
READINESS_TIMEOUT_SECONDS = 20
SHUTDOWN_TIMEOUT_SECONDS = 5
_STDOUT_CAPTURE_ATTRIBUTE = "_booking_preview_stdout"
_STDERR_CAPTURE_ATTRIBUTE = "_booking_preview_stderr"


@dataclass(frozen=True)
class BookingSpaProcess:
  process: subprocess.Popen[str]
  base_url: str
  port: int


def npm_executable() -> str:
  return "npm.cmd" if os.name == "nt" else "npm"


def run_command(
  command: list[str],
  *,
  cwd: Path,
  timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
  return subprocess.run(
    command,
    cwd=cwd,
    text=True,
    capture_output=True,
    timeout=timeout_seconds,
    check=False,
  )


def build_booking_app() -> subprocess.CompletedProcess[str]:
  command = [npm_executable(), "run", "build"]
  try:
    result = run_command(
      command,
      cwd=BOOKING_DIR,
      timeout_seconds=BUILD_TIMEOUT_SECONDS,
    )
  except subprocess.TimeoutExpired as exc:
    raise RuntimeError(
      "Booking SPA build timed out after "
      f"{BUILD_TIMEOUT_SECONDS} seconds. Command: {command!r}\n"
      f"STDOUT:\n{exc.stdout or ''}\n\nSTDERR:\n{exc.stderr or ''}"
    ) from exc

  if result.returncode != 0:
    raise RuntimeError(
      "Booking SPA build failed. "
      f"Command: {command!r}; exit code: {result.returncode}\n"
      f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
    )
  return result


def find_free_port() -> int:
  with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
    sock.bind((BOOKING_HOST, 0))
    return int(sock.getsockname()[1])


def start_vite_preview(*, port: int) -> subprocess.Popen[str]:
  vite_bin = BOOKING_DIR / "node_modules" / "vite" / "bin" / "vite.js"
  if not vite_bin.exists():
    raise FileNotFoundError(
      f"Booking SPA Vite executable not found at {vite_bin}. "
      f"Install the existing Booking dependencies in {BOOKING_DIR} first."
    )

  stdout_capture = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
  stderr_capture = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
  try:
    process = subprocess.Popen(
      [
        "node",
        str(vite_bin),
        "preview",
        "--host",
        BOOKING_HOST,
        "--port",
        str(port),
        "--strictPort",
      ],
      cwd=BOOKING_DIR,
      text=True,
      stdout=stdout_capture,
      stderr=stderr_capture,
    )
  except BaseException:
    stdout_capture.close()
    stderr_capture.close()
    raise

  setattr(process, _STDOUT_CAPTURE_ATTRIBUTE, stdout_capture)
  setattr(process, _STDERR_CAPTURE_ATTRIBUTE, stderr_capture)
  return process


def _read_preview_output(process: subprocess.Popen[str]) -> tuple[str, str]:
  output: list[str] = []
  for attribute in (_STDOUT_CAPTURE_ATTRIBUTE, _STDERR_CAPTURE_ATTRIBUTE):
    capture = getattr(process, attribute, None)
    if capture is None or capture.closed:
      output.append("")
      continue
    capture.flush()
    capture.seek(0)
    output.append(capture.read())
  return output[0], output[1]


def _close_preview_output(process: subprocess.Popen[str]) -> None:
  close_error: Exception | None = None
  for attribute in (_STDOUT_CAPTURE_ATTRIBUTE, _STDERR_CAPTURE_ATTRIBUTE):
    capture = getattr(process, attribute, None)
    if capture is None or capture.closed:
      continue
    try:
      capture.close()
    except Exception as exc:
      if close_error is None:
        close_error = exc
      else:
        close_error.add_note(f"Additional preview-output cleanup failure: {exc}")
  if close_error is not None:
    raise close_error


def _add_cleanup_note(primary_error: BaseException, message: str, error: Exception) -> None:
  primary_error.add_note(f"{message}: {error}")


def _collect_preview_output(
  process: subprocess.Popen[str],
  primary_error: BaseException,
) -> tuple[str, str]:
  stdout = ""
  stderr = ""
  try:
    stdout, stderr = _read_preview_output(process)
  except Exception as exc:
    _add_cleanup_note(primary_error, "Could not read Booking preview output", exc)
  try:
    _close_preview_output(process)
  except Exception as exc:
    _add_cleanup_note(primary_error, "Could not close Booking preview output", exc)
  return stdout, stderr


def _append_preview_output(
  error: RuntimeError,
  *,
  stdout: str,
  stderr: str,
) -> None:
  error.args = (
    f"{error}\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}",
  )


def wait_for_preview(
  process: subprocess.Popen[str],
  url: str,
  *,
  timeout_seconds: int = READINESS_TIMEOUT_SECONDS,
) -> None:
  deadline = time.perf_counter() + timeout_seconds
  last_error: Exception | None = None

  while time.perf_counter() < deadline:
    exit_code = process.poll()
    if exit_code is not None:
      error = RuntimeError(
        "Booking SPA preview exited before readiness. "
        f"Exit code: {exit_code}; URL: {url}"
      )
      stdout, stderr = _collect_preview_output(process, error)
      _append_preview_output(error, stdout=stdout, stderr=stderr)
      raise error

    try:
      with urlopen(url, timeout=1) as response:
        if response.status == 200:
          return
    except Exception as error:
      last_error = error
      time.sleep(0.25)

  error = RuntimeError(
    "Timed out waiting for Booking SPA preview at "
    f"{url} after {timeout_seconds} seconds: {last_error}"
  )
  try:
    stop_process(process)
  except Exception as exc:
    _add_cleanup_note(error, "Booking preview shutdown also failed", exc)

  if process.poll() is None:
    error.add_note(
      "Booking preview output could not be read because the process remained active."
    )
    try:
      _close_preview_output(process)
    except Exception as exc:
      _add_cleanup_note(error, "Could not close Booking preview output", exc)
  else:
    stdout, stderr = _collect_preview_output(process, error)
    _append_preview_output(error, stdout=stdout, stderr=stderr)
  raise error


def stop_process(process: subprocess.Popen[str]) -> None:
  if process.poll() is not None:
    return

  process.terminate()
  try:
    process.wait(timeout=SHUTDOWN_TIMEOUT_SECONDS)
  except subprocess.TimeoutExpired:
    process.kill()
    process.wait(timeout=SHUTDOWN_TIMEOUT_SECONDS)


@contextmanager
def open_booking_spa(
  *,
  port: int | None = None,
  build: bool = True,
) -> Iterator[BookingSpaProcess]:
  if build:
    build_booking_app()

  selected_port = port if port is not None else find_free_port()
  process = start_vite_preview(port=selected_port)
  base_url = f"http://{BOOKING_HOST}:{selected_port}"
  primary_error: BaseException | None = None

  try:
    wait_for_preview(process, f"{base_url}/services")
    yield BookingSpaProcess(
      process=process,
      base_url=base_url,
      port=selected_port,
    )
  except BaseException as exc:
    primary_error = exc
    raise
  finally:
    cleanup_error: Exception | None = None
    try:
      stop_process(process)
    except Exception as exc:
      cleanup_error = exc
    try:
      _close_preview_output(process)
    except Exception as exc:
      if cleanup_error is None:
        cleanup_error = exc
      else:
        cleanup_error.add_note(f"Preview-output cleanup also failed: {exc}")

    if cleanup_error is not None:
      if primary_error is None:
        raise cleanup_error
      _add_cleanup_note(
        primary_error,
        "Booking preview cleanup also failed",
        cleanup_error,
      )
