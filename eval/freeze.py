"""Freeze before test (evaluation protocol: docs/evaluation.md).

FREEZE.json lists every file and parameter that affects AccessGraph's output, with hashes. Test runs are
refused while any frozen file differs from its recorded hash.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DEFAULT_FREEZE = Path("eval/FREEZE.json")


class FrozenFileChanged(RuntimeError):
  pass


def file_sha256(path: Path) -> str:
  return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def expand(paths: Iterable[str], root: Path) -> list[str]:
  out: set[str] = set()
  for pattern in paths:
    matched = [p for p in root.glob(pattern) if p.is_file() and "__pycache__" not in p.parts]
    if not matched:
      raise FileNotFoundError(f"freeze pattern matched nothing: {pattern}")
    out.update(p.relative_to(root).as_posix() for p in matched)
  return sorted(out)


def freeze_hash(files: dict[str, str], params: dict[str, Any]) -> str:
  payload = json.dumps({"files": files, "params": params}, sort_keys=True, separators=(",", ":"))
  return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_freeze(patterns: Iterable[str], params: dict[str, Any], *, root: Path = Path("."),
                 path: Path = DEFAULT_FREEZE) -> dict[str, Any]:
  files = {rel: file_sha256(root / rel) for rel in expand(patterns, root)}
  record = {
    "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "patterns": list(patterns),
    "params": params,
    "files": files,
    "freeze_hash": freeze_hash(files, params),
  }
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
  return record


def verify_freeze(*, root: Path = Path("."), path: Path = DEFAULT_FREEZE) -> str:
  """Return the freeze hash, or raise FrozenFileChanged listing every changed, missing or added file."""
  if not path.exists():
    raise FrozenFileChanged(f"{path} does not exist: freeze before any test run")
  record = json.loads(path.read_text(encoding="utf-8"))
  problems = []
  for rel, digest in record["files"].items():
    target = root / rel
    if not target.exists():
      problems.append(f"missing: {rel}")
    elif file_sha256(target) != digest:
      problems.append(f"changed: {rel}")
  current = set(expand(record["patterns"], root))
  problems += [f"added: {rel}" for rel in sorted(current - set(record["files"]))]
  if problems:
    raise FrozenFileChanged("frozen files differ from FREEZE.json:\n  " + "\n  ".join(problems))
  return record["freeze_hash"]


# Everything that affects AccessGraph's output (evaluation protocol: docs/evaluation.md): candidate rules and evidence, change
# records, judge prompts and type guidance, context and escalation policies, the judge core, explorer prompts and
# parameters, the safety lists, the crawl config, and the type -> criterion mapping. Model ids and run parameters
# go into `params`.
FREEZE_PATTERNS = (
  "src/analysis/candidates/**/*.py",
  "src/analysis/confirmation/*.py",
  "src/analysis/confirmation/providers/*.py",
  "src/analysis/confirmation/prompts/**/*",
  "src/crawler/**/*.py",
  "src/crawler/**/*.js",
  "src/check_page.py",
  "eval/mappings/taxonomy_sc_rules.yaml",
  # v2 (2026-11-16, after the PI's review): baseline material that decides what is compared, not AccessGraph's output
  "eval/mappings/external_act_rampa.yaml",
  "eval/patches/intera11y-8dcf06e-*.patch",
  "eval/patches/rampa-df32363-*.patch",
  # v6: single-page mode settings and the follow-up wiring live in the adapter; the baselines' live handover
  "eval/adapters/ag_single.py",
  "eval/adapters/live_state.py",
)


def main(argv: list[str] | None = None) -> int:
  import argparse
  parser = argparse.ArgumentParser(description="Write or verify eval/FREEZE.json")
  parser.add_argument("--write", type=Path, metavar="PARAMS_JSON", help="freeze with these parameters (JSON file)")
  parser.add_argument("--verify", action="store_true")
  args = parser.parse_args(argv)
  if args.write:
    record = write_freeze(FREEZE_PATTERNS, json.loads(args.write.read_text(encoding="utf-8")))
    print(f"frozen {len(record['files'])} files, freeze_hash {record['freeze_hash']}")
  if args.verify:
    print(f"freeze OK: {verify_freeze()}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
