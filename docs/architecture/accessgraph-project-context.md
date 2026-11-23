# AccessGraph Project Context

AccessGraph separates acquisition from semantic judgment.

The crawler discovers bounded SPA states, records transitions, stores raw artifacts, and extracts neutral accessibility evidence. Taxonomy scope may guide which evidence categories are preserved, but crawl output remains observable facts, not findings.

In short: acquisition and neutral evidence -> semantic candidates -> model or researcher judgment -> reporting and evaluation.

Candidate generation is the first taxonomy-aware analysis stage. It reads saved crawl artifacts and packages hypotheses for later review. The current semantic scope is defined in `docs/taxonomy/current-semantic-taxonomy.md`.

Model judgment consumes saved candidates and artifacts after crawling. Reporting and scoring operate later over saved candidates, model judgments, and benchmark metadata.
