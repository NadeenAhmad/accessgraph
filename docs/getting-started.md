# Getting Started

This guide takes a fresh clone from installation to a small, local AccessGraph run. It uses the Checkout SPA and the fake judgment provider so the workflow is reproducible without credentials or network-backed model calls.

## Prerequisites

- Git for Windows, including `git` on `PATH`.
- Python 3.12 is recommended. The current development environment uses Python 3.12.3.
- Node.js must satisfy the Vite lockfiles: `^20.19.0 || >=22.12.0`. The current development environment uses Node 24.15.0 and npm 11.12.1.
- A Chromium-compatible browser installed through Playwright.

Clone the repository from Windows PowerShell:

```powershell
git clone https://github.com/NadeenAhmad/accessgraph.git
cd accessgraph
```

Repository access depends on the GitHub repository visibility and your account permissions. Unless a section says otherwise, run all subsequent commands from this repository root.

Create and activate the Python environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
```

Install each maintained SPA from its lockfile:

```powershell
npm.cmd ci --prefix benchmarks/local-spas/checkout-flow
npm.cmd ci --prefix benchmarks/local-spas/booking-scheduler
```

The repository does not currently contain a runnable Task Manager SPA. Task Manager appears in the submitted-thesis history, but there is no local package or startup command to reproduce it from this checkout.

## Start A Local SPA

Run Checkout on port 4173:

```powershell
npm.cmd run dev --prefix benchmarks/local-spas/checkout-flow -- --host 127.0.0.1 --port 4173
```

Booking Scheduler can run separately on port 4174:

```powershell
npm.cmd run dev --prefix benchmarks/local-spas/booking-scheduler -- --host 127.0.0.1 --port 4174
```

Keep the chosen SPA process running while crawling it. Both commands bind to localhost only.

## Create A Local Crawl Configuration

Copying the checked-in external-site example is not recommended for a first run. Create an ignored local file under `runs/` instead:

```powershell
$config = @'
{
  "url": "http://127.0.0.1:4173/",
  "headless": true,
  "runs_dir": "runs/local-checkout",
  "crawl": {
    "max_states": 8,
    "max_depth": 4,
    "max_actions_per_state": 5,
    "scope_policy": "same_origin"
  }
}
'@
[System.IO.Directory]::CreateDirectory((Join-Path $PWD "runs")) | Out-Null
[System.IO.File]::WriteAllText(
  (Join-Path $PWD "runs\crawler_config.local.json"),
  $config,
  [System.Text.UTF8Encoding]::new($false)
)
```

Check the active CLI contract at any time with:

```powershell
python accessgraph.py --help
python accessgraph.py crawl --help
python accessgraph.py candidates --help
python accessgraph.py judge --help
python accessgraph.py report --help
```

## Run The Pipeline

### 1. Crawl

```powershell
python accessgraph.py crawl --config runs/crawler_config.local.json
$run = (Get-ChildItem runs\local-checkout -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
```

The crawl creates a timestamped directory under `runs/local-checkout`; the second command stores the newest directory in `$run`. It contains captured states, screenshots, DOM and accessibility evidence, transitions, and the graph manifest. The exact files depend on the states discovered within the configured bounds.

### 2. Build candidates

```powershell
python accessgraph.py candidates --run $run
```

Candidates are saved under the run directory, including `candidates/candidates.jsonl`. They are evidence-backed hypotheses, not confirmed violations.

### 3. Exercise judgment without a model

```powershell
python accessgraph.py judge --run $run --provider fake --judgment-run-id local-fake
```

The fake provider tests prompt construction, serialization, saved-judgment handling, and reporting. It does not provide a meaningful accessibility assessment.

### 4. Build a report

```powershell
python accessgraph.py report --run $run --judgment-run-id local-fake
```

Judgments are stored under `$run/confirmations/local-fake/`; reporting artifacts are written under `$run/reports/`. Open the generated `report.html` in a browser or read `report.md`. Keep generated run directories out of version control.

## Real Model Providers

Real model use is optional and separate from crawling and candidate generation. It requires explicit provider and model selection.

For OpenAI, provide credentials through the environment and choose a model:

```powershell
$env:OPENAI_API_KEY = "..."
python accessgraph.py judge --run $run --provider openai --model <model-name> --limit 10 --judgment-run-id local-openai
```

For a local Ollama service:

```powershell
$env:ACCESSGRAPH_OLLAMA_BASE_URL = "http://127.0.0.1:11434/api"
python accessgraph.py judge --run $run --provider ollama --model <local-model> --limit 10 --judgment-run-id local-ollama
```

`OLLAMA_BASE_URL` is also recognized. Vision-capable provider names are `openai-vision` and `ollama-vision`. Provider availability, credentials, model access, cost, and saved artifacts must be recorded with any reported model result. Never treat deterministic seeded recovery as an LLM detection result.

## Inspect Controlled Benchmarks

Validate a representative Checkout case without contacting a model:

```powershell
python scripts/benchmarks/checkout/validate_batch.py --profile checkout-co-sem-052
```

List the current benchmark catalogue:

```powershell
python scripts/benchmarks/inspect_case.py --help
python scripts/benchmarks/serve_benchmark_explorer.py --port 8765
```

The Explorer catalogue reports all 166 tracked designs and can launch all 135 implemented cases: 108 Checkout and 27 Booking Scheduler variants. Select a case and choose **Open Variant**; for Booking cases the launcher follows the normal workflow to the route declared by the registry. Choose **Stop** to close the active session, or open another case to stop the current session and switch profiles. Planned, blocked, and rejected cases remain visible but cannot be launched. Two historical pilot configurations, `co-sem-001` and `co-sem-002`, remain executable configuration fixtures outside the tracker catalogue.

See [Implementing benchmark cases](benchmarks/implementing-benchmark-cases.md) before changing a controlled case.

## Tests

Useful non-model checks include:

```powershell
python -m pytest -q tests/test_benchmark_registry_loader.py
python -m pytest -q tests/test_booking_benchmark_scaffolding.py
python -m pytest -q tests/benchmarks/explorer
python -m pytest --collect-only -q
```

Browser-backed tests require Playwright Chromium and installed SPA dependencies. Model-backed confirmation is not required for ordinary unit, registry, crawler, or deterministic recovery tests.

## Troubleshooting

### PowerShell blocks virtual-environment activation

From Command Prompt (`cmd.exe`), activate the environment with:

```cmd
.\.venv\Scripts\activate.bat
```

Alternatively, keep PowerShell open and use the virtual-environment interpreter directly without activation:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

### Playwright cannot find Chromium

```powershell
python -m playwright install chromium
```

### The SPA port is already in use

Choose another localhost port and update `start_url` in the local crawler configuration.

### The crawl reaches no useful states

Confirm the configured `url` is reachable, `crawl.scope_policy` permits the intended local navigation, and the state/depth limits are large enough. Inspect the saved run rather than immediately widening crawler behavior.

### A real judgment provider fails

First rerun with `--provider fake`. For OpenAI, verify `OPENAI_API_KEY`, provider name, and model access. For Ollama, verify the local service, base URL, and installed model. Do not report a failed or partial run as an evaluation result.

### Task Manager cannot be started

This is expected for the current repository: no Task Manager SPA package is present. The historical thesis reference does not imply that its source or artifacts are reproducible here.
