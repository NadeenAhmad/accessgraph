Review this AccessGraph semantic accessibility candidate.
It is a candidate payload, not a confirmed finding.

Attached visual evidence is provided as saved evidence.
It may include a target crop, a highlighted state screenshot, or a full state screenshot.
The candidate payload remains the primary structured evidence; attached visual evidence is supplementary.

Type-specific checklist:
{{TYPE_GUIDANCE}}

The checklist guides what evidence to inspect. It is not evidence by itself.

Candidate-type boundary:
Judge only the stated candidate type. Saved evidence may contain signals for other accessibility issues, but do not confirm, reject, or explain the decision primarily as a different violation type. Use overlapping evidence only when it helps decide whether the stated candidate type is supported.

Foreign-language text evidence:
If relevant text evidence is in another language and the stated candidate type is not language-related, do not judge language-tag correctness. Use the meaning of the text only when it can be determined from the saved text/evidence to decide the stated candidate. Choose `uncertain` when the meaning cannot be determined. For language-related candidate types such as `lang-mismatch`, follow the type-specific language guidance.

Decision meanings:
- `violation`: saved evidence and, when useful, attached visual evidence sufficiently support the semantic accessibility problem for this candidate type.
- `no_violation`: saved evidence affirmatively resolves the candidate concern and shows the element or state is acceptable for this candidate type.
- `uncertain`: evidence is missing, indirect, ambiguous, conflicting, too generic, supports more than one plausible interpretation, does not clearly resolve the candidate concern, attached visual evidence is unclear, or the relevant element cannot be identified.

Decision-reason consistency:
- If `decision` is `violation`, the `reason` must explain what conflicts, mismatches, is missing, misleading, or otherwise violates the candidate type.
- If `decision` is `no_violation`, the `reason` must explain why the saved or visual evidence aligns, matches, is sufficient, or does not show the proposed mismatch.
- If `decision` is `uncertain`, the `reason` must explain what saved or visual evidence is missing, ambiguous, conflicting, or insufficient.
- Before finalizing the JSON, ensure the `reason` supports the selected `decision`. If the evidence and reason do not support `violation` or `no_violation`, choose `uncertain`.

Evidence hierarchy:
1. Candidate data and element evidence are primary.
2. State context may clarify the current route, title, page purpose, or visible state.
3. Graph/transition context may clarify SPA navigation, state changes, repeated patterns, or trigger context.
4. Attached visual evidence may clarify visual labels, icons, layout, visible hierarchy, and apparent content.
5. Artifact refs identify saved sources for traceability; do not infer facts from a referenced artifact unless the fact is present in the payload or visible in the attached visual evidence.

Evidence precedence:
Use the affected element's own saved content, accessible name, role, value, text alternative, title, language declaration, landmark label, structural evidence, or clearly identifiable visual evidence as the decision anchor. Use nearby, state, graph, transition, or visual context to clarify purpose or detect stale/mismatched state, but do not let broad context override a direct contradiction in the affected evidence. Context resolves a candidate only when it specifically explains the affected element or state without contradicting the primary evidence.
If the affected element's own saved evidence or clearly identifiable visual evidence already proves a direct contradiction for the stated candidate type, graph, transition, route, form, page, or broad visual context must not lower the decision from `violation` to `uncertain`. Choose `uncertain` only when the contradiction is not proven by saved or visual evidence or when specific saved evidence resolves the contradiction.

Decision priority:
1. Choose `violation` when saved evidence or attached visual evidence shows a direct semantic contradiction for the stated candidate type.
2. Choose `uncertain` when the candidate concern remains plausible but saved evidence does not fully prove or resolve it.
3. Choose `no_violation` only when saved evidence specifically resolves the candidate concern.

Contradiction precedence:
Direct contradictions between visible text, accessible name, alt text, field purpose, autocomplete value, link destination, page title, heading purpose, landmark label, contained content, or attached visual evidence are strong evidence for `violation` when they match the stated candidate type. Do not choose `no_violation` merely because broader page, form, route, surrounding context, or general visual context is understandable. It is better to surface a saved semantic contradiction as `violation` for developer review than to hide it as `no_violation`.
Do not choose `uncertain` merely because graph context is broad, long, noisy, incomplete, or introduces additional plausible context when the affected saved or visual evidence itself shows the semantic contradiction.

State/transition precedence:
For state-dependent candidate types, saved state and graph/transition evidence is evidence about the current semantic purpose, not optional background. When route, selected value, active filter, current step, trigger action, or transition path contradicts element text, page title, heading text, control label/action, link purpose, landmark label, contained content, or attached visual evidence, treat that as a direct semantic contradiction for the stated candidate type. Do not choose `no_violation` merely because the local element text is descriptive in isolation when saved state or transition evidence shows it is stale or describes a previous state.
Before choosing `uncertain` or `no_violation` for a state-dependent candidate, inspect saved fields such as `action_from_parent`, `incoming_action`, `transition_path`, `state_context`, and `graph_context` when they are present. If those fields identify the current state or recent change and the affected semantic text identifies a different state, choose `violation`.

Return raw JSON only, using exactly these keys:

{
  "candidate_id": "{{CANDIDATE_ID}}",
  "candidate_type": "{{CANDIDATE_TYPE}}",
  "state_id": "{{STATE_ID}}",
  "decision": "...",
  "confidence": 0.0,
  "reason": "...",
  "supporting_evidence": ["..."]
}

Required output identifiers:
- `candidate_id`: `{{CANDIDATE_ID}}`
- `candidate_type`: `{{CANDIDATE_TYPE}}`
- `state_id`: `{{STATE_ID}}`
Use these exact values in the JSON output.
Do not copy seed ids, element ids, rule ids, violation names, selection reasons, state ids, or related candidate ids into these fields.

Rules:
- `decision` must be exactly one of: `violation`, `no_violation`, `uncertain`.
- `confidence` must be a number from 0.0 to 1.0.
- Copy `candidate_id`, `candidate_type`, and `state_id` exactly from the candidate payload.
- Use `candidate_type`, not `violation_id`.
- Return only the keys shown above.
- Do not include `fix_suggestion`, `violation_id`, remediation instructions, or any extra keys.
- Ground `reason` in concrete saved evidence fields and/or attached visual evidence.
- Treat attached visual evidence as supplementary evidence, not a replacement for the candidate payload.
- Use `violation` only when the evidence supports the specific semantic problem, not merely because a candidate was generated.
- Absence of enough evidence for `violation` is not evidence for `no_violation`.
- Use `no_violation` only when saved evidence affirmatively resolves the candidate concern for this candidate type.
- If the candidate concern remains plausible but not fully proven, use `uncertain`.
- Do not use broad surrounding context to excuse a clear contradiction between visible text, accessible name, role/type, destination, field purpose, page purpose, landmark label, contained content, or attached visual evidence.
- For state-dependent candidates, give saved state or transition contradictions the same weight as local element contradictions.
- Do not ignore `action_from_parent`, `incoming_action`, or `transition_path` when they identify the current state for a heading, title, link, control, or landmark candidate.
- Use `uncertain` when the evidence is too thin, missing key context, conflicting, or would require guessing.
- Use `uncertain` if attached visual evidence is too broad, unclear, unrelated to the candidate, or the relevant element is not visible or identifiable.
- Confidence is model-reported or heuristic, not a calibrated probability.
- Use high confidence only when concrete saved evidence supports the decision; otherwise use lower confidence or `uncertain`.
- `supporting_evidence` must be a short list of concrete fields or facts visible in the candidate payload or attached visual evidence.
- Do not invent DOM, screenshot, visual, browser, assistive-technology, or live-page details not included below or visible in the attached visual evidence.

Candidate payload:
{{CANDIDATE_JSON}}
