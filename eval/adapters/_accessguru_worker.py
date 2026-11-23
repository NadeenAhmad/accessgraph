"""Runs InterA11y's AccessGuru adapter on one page and returns every finding (run with InterA11y's Python).

  INTERA11Y/.venv/bin/python eval/adapters/_accessguru_worker.py REQUEST_JSON RESULT_JSON   (cwd: INTERA11Y)

InterA11y's `run_accessguru` (adapters/worker.py) is used unchanged; only its last step, which keeps the findings
of one criterion, is replaced so that one call per state serves every case in that state.
"""
import json
import sys
from pathlib import Path

root = Path.cwd()
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "adapters"))
import worker  # noqa: E402  (InterA11y's adapters/worker.py)


def keep_all(entry, rows, *, state="complete", usage=None, timing=None, raw=None):
  return {"rows": rows, "state": state, "usage": usage or {}, "timing": timing or {}}


worker.normalized = keep_all
request = json.loads(Path(sys.argv[1]).read_text())
try:
  result = worker.run_accessguru(request["entry"], request["options"])
except Exception as error:  # reported as an error, never as "nothing found"
  import traceback
  traceback.print_exc()
  result = {"state": "error", "rows": [], "error": f"{type(error).__name__}: {error}"}
Path(sys.argv[2]).write_text(json.dumps(result, default=str))
