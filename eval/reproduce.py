"""Rebuild every number of the paper from the saved results and check it against the published numbers. Free: no
model calls, no apps, a few minutes.

  python -m eval.reproduce

Needs the two baselines' public repositories at their pinned commits, for the labels and the baselines' released
results: InterA11y at 8dcf06e and rampa-cli at df32363 (`bash scripts/setup_external.sh`, or set INTERA11Y_DIR and
RAMPA_DIR; see eval/paths.py).

Steps: check the two clones; put AccessGraph's saved predictions (results/d2/predictions, results/d3d6) where the
scoring scripts read them (tag `final`); score D2 with axe-core and compute its statistics (cluster bootstrap,
permutation tests, Holm), D3/D6 statistics, and all paper numbers; compare them with results/PAPER_NUMBERS.md and
print every difference. Exit code 0 when everything matches.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAG = "final"
PINNED = {"INTERA11Y_DIR (InterA11y)": "8dcf06e", "RAMPA_DIR (rampa-cli)": "df32363"}


def _commit(path: Path) -> str:
  done = subprocess.run(["git", "-C", str(path), "rev-parse", "--short=7", "HEAD"], capture_output=True, text=True)
  return done.stdout.strip() if done.returncode == 0 else ""


def _run(*module_args: str) -> None:
  print("  python -m", " ".join(module_args), flush=True)
  done = subprocess.run([sys.executable, "-m", *module_args], cwd=ROOT, capture_output=True, text=True)
  if done.returncode != 0:
    raise SystemExit(f"FAILED: python -m {' '.join(module_args)}\n{(done.stderr or done.stdout)[-1500:]}")


def _table(path: Path) -> dict[str, str]:
  rows = {}
  for line in path.read_text(encoding="utf-8").splitlines():
    parts = [p.strip() for p in line.strip().strip("|").split("|")]
    if len(parts) == 2 and parts[0] not in ("KEY", "---"):
      rows[parts[0]] = parts[1]
  return rows


def main() -> int:
  from eval.paths import INTERA11Y, RAMPA
  print("1. External repositories", flush=True)
  for (name, commit), path in zip(PINNED.items(), (INTERA11Y, RAMPA)):
    found = _commit(path)
    if not found:
      raise SystemExit(f"  missing: {name} at {path}; run `bash scripts/setup_external.sh` or set the variable")
    print(f"  {name}: {path} at {found}" + ("" if found == commit else f"  (expected {commit})"), flush=True)

  print("2. Saved AccessGraph results -> scoring layout (tag 'final')", flush=True)
  for csv_path in sorted((ROOT / "results" / "d2" / "predictions").glob("*-run-*.csv")):
    dataset, run = csv_path.stem.rsplit("-run-", 1)
    target = ROOT / "runs" / "w4a-d2" / "runs" / f"{dataset}-{TAG}-run-{run}"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy(csv_path, target / "predictions.csv")
  d3d6 = ROOT / "results" / f"d3d6-{TAG}"
  if d3d6.exists():
    shutil.rmtree(d3d6)
  shutil.copytree(ROOT / "results" / "d3d6", d3d6)

  print("3. Scoring and statistics", flush=True)
  _run("eval.d2_combined", "--tag", TAG)
  _run("eval.d2_stats", "--tag", TAG, "--full", "--with-axe")
  _run("eval.d2_stats", "--tag", TAG, "--full")
  _run("eval.d2_stats", "--tag", TAG)
  _run("eval.d3d6_stats", "--tag", TAG)
  _run("eval.paper_values", "--tag", TAG)

  print("4. Comparison with results/PAPER_NUMBERS.md", flush=True)
  expected = _table(ROOT / "results" / "PAPER_NUMBERS.md")
  got = _table(ROOT / "results" / f"PAPER_VALUES-{TAG}.md")
  diffs = [(k, expected.get(k), got.get(k)) for k in sorted(set(expected) | set(got)) if expected.get(k) != got.get(k)]
  for key, want, have in diffs:
    print(f"  DIFF {key}: published {want!r}, rebuilt {have!r}")
  print(f"  {len(expected) - len(diffs)} of {len(expected)} numbers match" + ("" if diffs else ": everything reproduces"))
  return 1 if diffs else 0


if __name__ == "__main__":
  raise SystemExit(main())
