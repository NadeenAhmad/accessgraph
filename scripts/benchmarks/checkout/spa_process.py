from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path
from urllib.request import urlopen


REPO_ROOT = Path(__file__).resolve().parents[3]
CHECKOUT_DIR = REPO_ROOT / "benchmarks" / "local-spas" / "checkout-flow"
CHECKOUT_PUBLIC_DIR = CHECKOUT_DIR / "public"

CONTROLLED_SUPPORT_HOST = "127.0.0.1"
CONTROLLED_SUPPORT_PORT = 8771
CONTROLLED_SUPPORT_ORIGIN = (
  f"http://{CONTROLLED_SUPPORT_HOST}:{CONTROLLED_SUPPORT_PORT}"
)
CONTROLLED_SUPPORT_RETURNS_PATH = "/returns-and-refunds.html"
CONTROLLED_SUPPORT_RETURNS_URL = (
  f"{CONTROLLED_SUPPORT_ORIGIN}{CONTROLLED_SUPPORT_RETURNS_PATH}"
)
CONTROLLED_SUPPORT_RESOURCE_PATH = "/resource.html"
CONTROLLED_SUPPORT_RESOURCE_URL = (
  f"{CONTROLLED_SUPPORT_ORIGIN}{CONTROLLED_SUPPORT_RESOURCE_PATH}"
)
CONTROLLED_SUPPORT_DESTINATION_PROFILES = frozenset({
  "checkout-co-sem-027",
  "checkout-co-sem-102",
})


def npm_executable() -> str:
  return "npm.cmd" if os.name == "nt" else "npm"


def run_command(
  cmd: list[str],
  *,
  cwd: Path,
  timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
  return subprocess.run(
    cmd,
    cwd=cwd,
    text=True,
    capture_output=True,
    timeout=timeout_seconds,
    check=False,
  )


def build_checkout_app() -> None:
  result = run_command(
    [npm_executable(), "run", "build"],
    cwd=CHECKOUT_DIR,
    timeout_seconds=120,
  )
  if result.returncode != 0:
    raise RuntimeError(
      "Checkout benchmark build failed.\n"
      f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
    )


def requires_controlled_support_destination(profile: str | None) -> bool:
  return profile in CONTROLLED_SUPPORT_DESTINATION_PROFILES


def find_free_port() -> int:
  with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
    sock.bind(("127.0.0.1", 0))
    return int(sock.getsockname()[1])


def assert_port_available(*, host: str, port: int) -> None:
  with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
    try:
      sock.bind((host, port))
    except OSError as exc:
      raise RuntimeError(
        "Controlled support destination server cannot start because "
        f"{host}:{port} is unavailable. Stop the process using that port "
        "or rerun without controlled support destination inspection."
      ) from exc


def wait_for_url(url: str, *, timeout_seconds: int) -> None:
  deadline = time.perf_counter() + timeout_seconds
  last_error: Exception | None = None
  while time.perf_counter() < deadline:
    try:
      with urlopen(url, timeout=1) as response:
        if response.status == 200:
          return
    except Exception as error:
      last_error = error
      time.sleep(0.25)
  raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def start_vite_preview(*, port: int) -> subprocess.Popen[str]:
  vite_bin = CHECKOUT_DIR / "node_modules" / "vite" / "bin" / "vite.js"
  if not vite_bin.exists():
    raise FileNotFoundError(
      f"Vite executable not found at {vite_bin}. "
      f"Run npm install in {CHECKOUT_DIR} first."
    )
  return subprocess.Popen(
    [
      "node",
      str(vite_bin),
      "preview",
      "--host",
      "127.0.0.1",
      "--port",
      str(port),
    ],
    cwd=CHECKOUT_DIR,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
  )


def start_controlled_support_server() -> subprocess.Popen[str]:
  fixtures = (
    CHECKOUT_PUBLIC_DIR / "returns-and-refunds.html",
    CHECKOUT_PUBLIC_DIR / "resource.html",
  )
  for fixture in fixtures:
    if not fixture.exists():
      raise FileNotFoundError(f"Controlled support fixture not found: {fixture}")
  assert_port_available(
    host=CONTROLLED_SUPPORT_HOST,
    port=CONTROLLED_SUPPORT_PORT,
  )
  return subprocess.Popen(
    [
      sys.executable,
      "-m",
      "http.server",
      str(CONTROLLED_SUPPORT_PORT),
      "--bind",
      CONTROLLED_SUPPORT_HOST,
      "--directory",
      str(CHECKOUT_PUBLIC_DIR),
    ],
    cwd=CHECKOUT_PUBLIC_DIR,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
  )


def stop_process(process: subprocess.Popen[str]) -> None:
  if process.poll() is not None:
    return
  process.terminate()
  try:
    process.wait(timeout=5)
  except subprocess.TimeoutExpired:
    process.kill()
