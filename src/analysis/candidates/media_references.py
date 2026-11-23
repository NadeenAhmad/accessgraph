"""Offline reference material for media candidates.

Reference documents are benchmark fixtures, not crawler evidence. This module
associates them with captured media by normalized source identity and optional
track language without making a semantic comparison.
"""

from __future__ import annotations

import json
import posixpath
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

REPO_ROOT = Path(__file__).resolve().parents[3]
REFERENCE_ROOT = REPO_ROOT / "benchmarks" / "reference"
REFERENCE_CONFIG_NAME = "reference.json"


def find_media_reference(
  video: dict[str, Any],
  track: dict[str, Any],
  *,
  reference_root: Path = REFERENCE_ROOT,
) -> dict[str, object] | None:
  identities = _video_source_identities(video)
  if not identities:
    return None
  track_language = str(track.get("srclang") or "").strip().lower()

  for entry in _reference_catalog(reference_root.resolve()):
    if entry["media_src"] not in identities:
      continue
    reference_language = str(entry.get("language") or "").strip().lower()
    if reference_language and track_language and reference_language != track_language:
      continue
    return dict(entry)
  return None


@lru_cache(maxsize=4)
def _reference_catalog(reference_root: Path) -> tuple[dict[str, object], ...]:
  if not reference_root.exists():
    return ()
  entries = [
    _load_reference_config(path)
    for path in sorted(reference_root.rglob(REFERENCE_CONFIG_NAME))
  ]
  return tuple(entry for entry in entries if entry is not None)


def _load_reference_config(path: Path) -> dict[str, object] | None:
  raw = json.loads(path.read_text(encoding="utf-8-sig"))
  if not isinstance(raw, dict):
    raise ValueError(f"Media reference config must be a JSON object: {path}")
  media = raw.get("media") if isinstance(raw.get("media"), dict) else {}
  reference = raw.get("reference") if isinstance(raw.get("reference"), dict) else {}
  media_src = _normalize_media_src(media.get("src"))
  reference_kind = str(reference.get("kind") or "").strip()
  reference_text = _normalize_text(reference.get("text"))
  if not media_src or not reference_kind or not reference_text:
    raise ValueError(
      "Media reference config requires media.src, reference.kind, and "
      f"reference.text: {path}"
    )

  transcript_path = _reference_path(path, reference.get("transcript_path"))
  provenance_path = _reference_path(path, reference.get("provenance_path"))
  return {
    "available": True,
    "media_src": media_src,
    "reference_kind": reference_kind,
    "language": str(reference.get("language") or "").strip(),
    "source": str(reference.get("source") or "").strip(),
    "exactness_claim": str(reference.get("exactness_claim") or "").strip(),
    "reference_transcript": reference_text,
    "transcript_path": _repo_relative(transcript_path),
    "provenance_path": _repo_relative(provenance_path),
    "configuration_path": _repo_relative(path.resolve()),
  }


def _video_source_identities(video: dict[str, Any]) -> set[str]:
  values: list[object] = [
    video.get("src"),
    video.get("current_src"),
    video.get("source_src"),
  ]
  sources = video.get("sources") if isinstance(video.get("sources"), list) else []
  for source in sources:
    if not isinstance(source, dict):
      continue
    values.extend((source.get("src"), source.get("current_src")))
  return {
    normalized
    for value in values
    if (normalized := _normalize_media_src(value))
  }


def _normalize_media_src(value: object) -> str:
  raw = str(value or "").strip().replace("\\", "/")
  if not raw:
    return ""
  parsed = urlsplit(raw)
  path = unquote(parsed.path or raw)
  normalized = posixpath.normpath(path)
  if normalized in {"", "."}:
    return ""
  return normalized if normalized.startswith("/") else f"/{normalized}"


def _reference_path(config_path: Path, value: object) -> Path | None:
  raw = str(value or "").strip()
  if not raw:
    return None
  resolved = (config_path.parent / raw).resolve()
  root = config_path.parent.resolve()
  if resolved != root and root not in resolved.parents:
    raise ValueError(f"Media reference path must stay beside its config: {config_path}")
  if not resolved.is_file():
    raise FileNotFoundError(f"Media reference file does not exist: {resolved}")
  return resolved


def _repo_relative(path: Path | None) -> str:
  if path is None:
    return ""
  try:
    return path.relative_to(REPO_ROOT).as_posix()
  except ValueError:
    return path.as_posix()


def _normalize_text(value: object) -> str:
  return " ".join(str(value or "").split())
