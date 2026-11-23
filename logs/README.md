# Logs

- `run_log.csv`: every evaluation run of the project (started, finished or failed), with its stage, dataset, cost
  and the freeze hash it ran under.
- `cost_ledger.json`, `cost_log.jsonl`: every paid model call (OpenRouter's reported cost), by budget stage; total
  spend of the project about $19.

New runs write to `results/run_log.csv` and `results/cost_ledger.json`.
