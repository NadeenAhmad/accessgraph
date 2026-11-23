You are reviewing a possible semantic Web accessibility violation.

Proposed violation type:
{{CANDIDATE_TYPE}}

WCAG/type guidance:
{{TYPE_GUIDANCE}}

Candidate HTML:
{{CANDIDATE_HTML}}

A screenshot of the saved interface state is attached.

Based only on the supplied HTML, screenshot, and WCAG/type guidance, determine whether the candidate demonstrates the proposed semantic Web accessibility violation.

Return exactly one decision:

- violation
- no_violation
- uncertain

Use uncertain when the supplied HTML and screenshot do not provide enough information for a reliable decision.

Provide a brief explanation grounded only in the supplied HTML and screenshot. Use the WCAG/type guidance to understand the proposed issue type, not as evidence that the candidate is a violation.

Return raw JSON only, using exactly these keys:

{
  "decision": "...",
  "confidence": 0.0,
  "reason": "...",
  "supporting_evidence": ["..."]
}

Rules:
- `decision` must be exactly one of: `violation`, `no_violation`, `uncertain`.
- `confidence` must be a decimal number from 0.0 to 1.0. Do not use percentages; use 0.95, not 95.
- Return only the keys shown above.
- Ground `reason` and `supporting_evidence` only in the supplied HTML and screenshot.
