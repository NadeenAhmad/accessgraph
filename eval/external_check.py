"""Check that the local InterA11y and Rampa clones carry exactly the frozen patches (FREEZE.json v2).

  python -m eval.external_check

Each patch is regenerated from the clone with the command that wrote it and compared with the frozen file. Runs of
InterA11y, InterA11y+, AccessGuru and Rampa call `verify()` first and refuse to start on any difference.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from eval.paths import EXTERNAL  # noqa: E402
NEW_INTERA11Y = ["runtime/intera11y/src/criteria/2.4.2.js", "runtime/intera11y/src/criteria/2.4.6.js",
                 "runtime/intera11y/src/criteria/descriptive-common.js", "runtime/intera11y/rubrics/2.4.2.js",
                 "runtime/intera11y/rubrics/2.4.6.js"]
PATCHES = {
  "eval/patches/intera11y-8dcf06e-omit-temperature.patch": ("InterA11y", [], ["runtime/intera11y/src/judge/openrouter.js"]),
  "eval/patches/intera11y-8dcf06e-accessgraph-system.patch": ("InterA11y", [], ["adapters", "intera11y_benchmark"]),
  "eval/patches/intera11y-8dcf06e-w4a-rubrics.patch": ("InterA11y", NEW_INTERA11Y,
                                                         ["runtime/intera11y/src/criteria", "runtime/intera11y/rubrics"]),
  "eval/patches/intera11y-8dcf06e-live-replay.patch": ("InterA11y", [], ["runtime/intera11y/src/core/session.js"]),
  "eval/patches/rampa-df32363-accessgraph-row.patch": ("rampa-cli", ["bench/tools/accessgraph.mjs"],
                                                       ["bench/lib/tools.mjs", "bench/tools/accessgraph.mjs"]),
}
COMMITS = {"InterA11y": "8dcf06e", "rampa-cli": "df32363"}


class ExternalCloneChanged(RuntimeError):
  pass


def _diff(repo: Path, new_files: list[str], paths: list[str]) -> str:
  git = ["git", "-C", str(repo)]
  if new_files:
    subprocess.run(git + ["add", "-N", *new_files], check=True)
  try:
    return subprocess.run(git + ["diff", "--", *paths], check=True, capture_output=True, text=True).stdout
  finally:
    if new_files:
      subprocess.run(git + ["reset", "-q", *new_files], check=True)


def verify() -> None:
  problems = []
  for name, commit in COMMITS.items():
    head = subprocess.run(["git", "-C", str(EXTERNAL / name), "rev-parse", "--short=7", "HEAD"], capture_output=True,
                          text=True).stdout.strip()
    if head != commit:
      problems.append(f"{name} is at {head}, not {commit}")
  for patch, (name, new_files, paths) in PATCHES.items():
    if _diff(EXTERNAL / name, new_files, paths) != (ROOT / patch).read_text(encoding="utf-8"):
      problems.append(f"{name} differs from {patch}")
  if problems:
    raise ExternalCloneChanged("; ".join(problems))


if __name__ == "__main__":
  verify()
  print("external clones match the frozen patches")
