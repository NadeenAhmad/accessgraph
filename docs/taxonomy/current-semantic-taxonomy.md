# Current Semantic Taxonomy

The canonical taxonomy is `SEMANTIC_VIOLATION_TAXONOMY.json`. It defines the 15 supervisor-approved semantic accessibility problem types currently in scope.

The current candidate pipeline supports all 15 canonical types. The post-thesis controlled Checkout benchmark also represents every type with at least one implemented case. Candidate capability, taxonomy definition, and benchmark-family representation remain separate concepts even though each currently covers all 15 types; this does not imply exhaustive semantic accessibility coverage.

## In-Scope Types

| Type | Current support |
| --- | --- |
| `image-alt-not-descriptive` | Images with a present text alternative and saved visual/context evidence. Missing text alternatives remain syntax scope. |
| `video-captions-inaccurate` | Visible videos with loaded caption tracks; candidates package track metadata, bounded cue text and timing, local context, and optional authoritative narration evidence. Caption accuracy is judged later. |
| `lang-mismatch` | Page-level language declarations compared with saved page text evidence. Missing or invalid language declarations remain syntax scope. |
| `language-of-parts-mismatch` | Locally declared passage/component language compared with saved passage text. Missing local declarations are not candidates. |
| `link-text-mismatch` | Link labels/names compared with href, same-page target, graph, or destination-state evidence when available. |
| `button-label-mismatch` | Button labels/names compared with saved local context, trigger context, and resulting state evidence when available. |
| `form-label-mismatch` | Associated labels/names compared with field purpose evidence. Missing labels remain syntax scope. |
| `widget-label-purpose-mismatch` | Tabs, disclosures, menu items, options, and custom widgets compared with role, controlled content, and state evidence. |
| `heading-not-descriptive` | Headings compared with scoped content, outline context, page context, and transition context when available. |
| `landmark-purpose-mismatch` | Landmark role/name compared with scoped content and surrounding document structure. Structural landmark failures are not candidates. |
| `page-title-not-descriptive` | Present page titles compared with saved page, route, heading, dialog, and graph state context. |
| `autocomplete-purpose-mismatch` | Syntactically valid autocomplete tokens compared with field purpose evidence. Missing or invalid tokens are syntax scope. |
| `aria-state-mismatch` | Present valid ARIA states such as expanded, selected, checked, or pressed compared with rendered state, controlled targets, and peer context. |
| `table-header-association-mismatch` | Resolved table header associations compared with cell content, header text, position, and caption. Broken references remain syntax scope. |
| `error-message-mismatch` | Associated error text for invalid controls compared with the control purpose and validation context. Missing error messages are not candidates. |

## Boundaries

These types cover semantic mismatches in present, syntactically usable accessibility features. Missing or invalid syntax remains outside this semantic scope unless a separate semantic mismatch is grounded by saved evidence.

Examples outside this semantic scope include missing alt text, missing labels, invalid `autocomplete`, missing or invalid language declarations, absent page titles, invalid ARIA syntax, broken table header references, and color contrast.

Candidate-generation mechanics are described in `docs/candidates/semantic-candidate-builder.md`. Benchmark case design and acceptance are described in `docs/benchmarks/controlled-benchmark-guide.md`.
