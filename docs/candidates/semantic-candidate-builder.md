# Semantic Candidate Builder

The candidate builder reads completed crawl runs and writes semantic candidate records under `<run>/candidates/`.

Crawler artifacts remain neutral. Candidate records are hypotheses for later model or researcher judgment; they are not accessibility findings.

## Scope

The builder supports all 15 semantic candidate types defined by `SEMANTIC_VIOLATION_TAXONOMY.json`. Candidate support means the pipeline can package relevant neutral evidence for later judgment; it does not mean every candidate is a violation or that the taxonomy exhausts semantic accessibility problems. See `docs/taxonomy/current-semantic-taxonomy.md` for the canonical type list and scope.

## Inputs And Outputs

The input is a completed run directory containing saved graph, transition, state, screenshot, DOM, metadata, and accessibility-context artifacts. The output is a set of candidate records and supporting candidate output files under `<run>/candidates/`.

## Evidence Shape

Candidate rules use only saved state artifacts and neutral accessibility context. Evidence packages can include bounded facts for images, videos, caption tracks and cues, links, buttons, forms, form controls, headings, landmarks, tables, language samples, visual cues, focusables, focus traversal, referenced elements, and relationships.

Rules that need interaction meaning can use saved graph context. Candidate records may include transition or destination-state context when the run already contains it.

## Video-Caption Candidates

A `video-captions-inaccurate` candidate unit is one visible video plus one loaded captions track with non-empty cue text. Evidence may include video identity and local context, track metadata, bounded cue text and timing, aggregate caption text, and an optional authoritative narration reference.

The browser evidence extractor captures neutral video, track, and cue facts. Offline reference enrichment may attach an authoritative narration reference by media identity and language. The candidate packages the captured and reference evidence without comparing them; confirmation or researcher review performs semantic judgment later. Accurate captions may therefore generate a candidate.

Cue loading and extraction are bounded. Timing is retained as evidence, but the current controlled video benchmark targets semantic caption-content accuracy rather than synchronization. The Brightlane reference is an exact supervisor-provided narration transcript without supervisor-provided timestamps.

## Boundary

The builder must not read private benchmark expected labels, perform model judgment, or mark a candidate as a confirmed violation. Missing syntactic requirements are intentionally outside the semantic candidate set unless a separate semantic mismatch is grounded by saved evidence.
