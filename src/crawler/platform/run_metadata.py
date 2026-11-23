from __future__ import annotations

import hashlib
import platform
import subprocess
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from shutil import which
from typing import Any

from ..config.app_config import AppConfig
from .browser import IGNORE_HTTPS_ERRORS


def utc_iso_now() -> str:
  return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_package_version(package_name: str) -> str | None:
  try:
    return package_version(package_name)
  except PackageNotFoundError:
    return None
  except Exception:
    return None


def _run_git_command(repo_root: Path, args: list[str]) -> str | None:
  try:
    proc = subprocess.run(
      ["git", *args],
      cwd=str(repo_root),
      capture_output=True,
      text=True,
      check=False,
      timeout=2,
    )
  except Exception:
    return None

  if proc.returncode != 0:
    return None

  out = proc.stdout.strip()
  return out or None


def _git_metadata(repo_root: Path) -> dict[str, Any]:
  inside = _run_git_command(repo_root, ["rev-parse", "--is-inside-work-tree"])
  if inside != "true":
    return {"available": False}

  dirty_output = _run_git_command(repo_root, ["status", "--porcelain"]) or ""
  return {
    "available": True,
    "commit": _run_git_command(repo_root, ["rev-parse", "HEAD"]),
    "branch": _run_git_command(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"]),
    "is_dirty": bool(dirty_output),
  }


def _config_file_metadata(config_path: Path) -> dict[str, Any]:
  resolved = config_path.resolve()
  metadata: dict[str, Any] = {
    "path": str(config_path),
    "resolved_path": str(resolved),
    "exists": resolved.exists(),
  }

  if not resolved.exists():
    return metadata

  raw = resolved.read_bytes()
  metadata["sha256"] = hashlib.sha256(raw).hexdigest()
  metadata["size_bytes"] = len(raw)
  return metadata


def _cfg_snapshot(cfg_file: AppConfig) -> dict[str, Any]:
  if is_dataclass(cfg_file):
    data = asdict(cfg_file)
    if isinstance(data, dict):
      return data
  return {"url": str(getattr(cfg_file, "url", ""))}


def build_run_metadata(config_path: Path, cfg_file: AppConfig, run_id: str, run_dir: Path) -> dict[str, Any]:
  project_root = Path(__file__).resolve().parents[3]
  return {
    "run_id": run_id,
    "status": "running",
    "started_at_utc": utc_iso_now(),
    "run_dir": str(run_dir),
    "config_file": _config_file_metadata(config_path),
    "config_snapshot": _cfg_snapshot(cfg_file),
    "runtime": {
      "python_version": sys.version,
      "python_implementation": platform.python_implementation(),
      "python_executable": sys.executable,
      "platform": platform.platform(),
      "machine": platform.machine(),
      "processor": platform.processor(),
    },
    "tooling": {
      "playwright_version": _safe_package_version("playwright"),
      "graphviz_dot_available": which("dot") is not None,
    },
    "source_control": _git_metadata(project_root),
    "browser": {
      "engine": "chromium",
      "headless": bool(getattr(cfg_file, "headless", True)),
      "ignore_https_errors": IGNORE_HTTPS_ERRORS,
    },
  }


async def attach_browser_metadata(run_metadata: dict[str, Any], browser_controller: Any) -> None:
  browser_meta = run_metadata.get("browser")
  if not isinstance(browser_meta, dict):
    return

  browser_obj = getattr(browser_controller, "browser", None)
  if browser_obj is not None:
    browser_meta["version"] = getattr(browser_obj, "version", None)

  page_obj = getattr(browser_controller, "page", None)
  if page_obj is None:
    return

  try:
    user_agent = await page_obj.evaluate("() => navigator.userAgent")
    if isinstance(user_agent, str) and user_agent:
      browser_meta["user_agent"] = user_agent
  except Exception:
    return
