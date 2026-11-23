# Model Judgment Reference

The `accessgraph.py judge` command runs an explicit post-crawl model-judgment stage over saved semantic candidates. Crawling and candidate generation do not call model providers.

Supported providers are registered in `src/analysis/confirmation/providers/`. The `fake` provider is the default test provider. Real provider use requires explicit model/provider configuration and available credentials or local service configuration.

Prompt templates live under `src/analysis/confirmation/prompts/`. They cover all 15 current executable semantic candidate types. For `video-captions-inaccurate`, text-only judgment can use caption cue text and attached authoritative narration evidence. The current controlled case does not require graph context; vision remains optional, and insufficient reference evidence may warrant an uncertain judgment.

Context modes:

- `isolated_state`: candidate and current-state evidence only
- `graph_context`: includes graph and transition context when available
- `adaptive_context`: chooses isolated or graph context by candidate type and available evidence
- `minimal_html_screenshot`: guided HTML/screenshot baseline for vision providers

Adaptive graph-preferring types are `page-title-not-descriptive`, `heading-not-descriptive`, and `widget-label-purpose-mismatch`.

Saved judgments are written under `<run>/confirmations/<judgment_run_id>/`. Reports and scorers read those saved files later.

## Reproducible Provider Workflow

Start with the fake provider to exercise selection, prompt construction, parsing, and artifact writing without a network or model call:

```powershell
python accessgraph.py judge --run <run> --provider fake --judgment-run-id fake-check --save-prompts
```

Use `--dry-run` to build selected prompts without contacting a provider or writing judgments:

```powershell
python accessgraph.py judge --run <run> --provider openai --model <model> --candidate-type <type> --limit 5 --context-mode isolated_state --dry-run --save-prompts
```

Real providers require a model and bounded selection through `--candidate-type`, `--candidate-id`, `--candidate-id-file`, or `--limit`. For OpenAI:

```powershell
$env:OPENAI_API_KEY = "..."
python accessgraph.py judge --run <run> --provider openai --model <model> --candidate-type <type> --limit 5 --context-mode isolated_state --judgment-run-id openai-check --save-prompts --save-raw-responses
```

For a local Ollama service:

```powershell
$env:ACCESSGRAPH_OLLAMA_BASE_URL = "http://127.0.0.1:11434/api"
python accessgraph.py judge --run <run> --provider ollama --model <local-model> --candidate-type <type> --limit 5 --context-mode isolated_state --judgment-run-id ollama-check --save-prompts --save-raw-responses
```

`OLLAMA_BASE_URL` is also recognized, and `--base-url` overrides the service URL for one command. Use `openai-vision` or `ollama-vision` only when the selected candidates and evaluation design require image evidence.

Preserve the judgment manifest, rendered prompts, parsed judgments, raw responses when enabled, provider/model name, context mode, prompt version, candidate selection, and source run. A report without those artifacts is not independently reproducible. Deterministic benchmark recovery remains a separate offline check and must not be presented as model detection.

## Historical Diagnostic Summaries

The smoke summaries below are historical diagnostic notes, not a reproducible final evaluation. The repository does not retain a complete, immutable artifact bundle and accepted-manifest snapshot for every number reported below. They may guide prompt calibration, but they should not be cited as independently reproduced model-performance results.

### Image-alt judgment smoke

The five implemented image-alt cases (`co-sem-006`-`co-sem-010`) passed acquisition, candidate recovery, vision delivery, and result parsing. With `gpt-5.4-mini`, only `co-sem-006` was judged as a violation; the other four were false negatives. Inspection showed no seed or evidence problem. The current prompt is less explicit than the taxonomy about false subtype, purpose, color, and quantity claims, and the model often accepted a broadly correct object label despite those factual errors. Treat this as a prompt/model-calibration issue, not a reason to change the benchmark cases.

### Language judgment smoke

A vision smoke over `co-sem-011`-`co-sem-019` showed strong model sensitivity. With the same saved candidates and confirmation setup, `gpt-5.4-mini` judged 3/9 cases as violations, while `gpt-5.4` judged all 9/9 as violations. Deterministic recovery, target states, language evidence, screenshots, and parsing were sound, including the distinction between stale page language in `co-sem-015` and stale local language in `co-sem-019`. No benchmark seed changes are indicated by these results.

### Link-text judgment smoke

A GPT-5.4 vision smoke over the pre-review `co-sem-020`-`co-sem-027` link-text set judged all eight then-active cases as violations. The surviving active cases are `co-sem-020`, `co-sem-021`, `co-sem-023`, `co-sem-024`, and `co-sem-027`; all were violations in that smoke. Deterministic candidate recovery, source and destination evidence, state screenshots, and parsing were sound. For `co-sem-027`, saved destination-state evidence for `Returns and refunds` was available directly in the isolated candidate context, so no graph-context escalation or candidate-time network fetch was required. No benchmark seed or evidence changes are indicated by these results.

### Button-label judgment smoke

A GPT-5.4 vision smoke over the pre-review `co-sem-028`-`co-sem-035` button-label set judged all eight then-active cases as violations. The surviving active cases are `co-sem-028`, `co-sem-029`, `co-sem-031`, `co-sem-032`, and `co-sem-035`; all were violations in that smoke. Deterministic candidate recovery, Notebook-set target evidence, visible/accessibility-name relationships, state screenshots, and parsing were sound. The active subset preserves unrelated labels, opposite-action labels, accessible-name-only mismatches, and the wrong-object `Add Cable organizer` case. No benchmark seed or evidence changes are indicated by these results.

### Widget-label judgment smoke

A GPT-5.4 vision smoke over the pre-review `co-sem-036`-`co-sem-039` widget-label set judged all four then-active cases as violations. The surviving active cases are `co-sem-036`, `co-sem-037`, and `co-sem-038`; all were violations in that smoke. Deterministic candidate recovery, tab label/name evidence, controlled tabpanel evidence, state screenshots, and parsing were sound. Adaptive confirmation graph-preferred this taxonomy, but graph context was empty for these cases, so the judgments resolved to isolated state context; the benchmark cases themselves remain state-local. No benchmark seed or evidence changes are indicated by these results.

### Heading judgment smoke

A GPT-5.4 vision smoke over the pre-review `co-sem-040`-`co-sem-047` heading set judged seven of the eight then-active cases as violations. The surviving active cases are `co-sem-041`, `co-sem-042`, `co-sem-044`, `co-sem-045`, and `co-sem-047`; all were violations in that smoke. The only historical `no_violation` judgment was the now-removed partially correct `co-sem-046`. Adaptive confirmation resolved the surviving Products-page heading cases to isolated state context because graph context was empty; `co-sem-047` used the available Products-to-Cart graph context. Deterministic recovery, screenshots, evidence, and parsing were sound. No benchmark seed or evidence changes are indicated by these results.
