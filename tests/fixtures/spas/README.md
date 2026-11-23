# SPA crawler fixtures

These fixtures are intentionally small single-page apps used by crawler behavior tests.

- `deterministic/` exercises stable UI states, duplicate transitions back to an existing state, and browser-side hash normalization for hidden and animation-only changes.
- `links/` exercises strict same-origin link following while exposing an external link that should be skipped.
- `forms/` exercises conservative form handling: safe pre-filled submission is allowed, while login, empty required, password, file, checkbox, and typing paths are not useful crawler actions.
- Operation fixtures named after the behavior they cover:
  - `button_click/`
  - `role_button_click/`
  - `modal_open_close/`
  - `tab_switch/`
  - `accordion_disclosure/`
  - `same_origin_link/`
  - `dropdown_select/`
  - `prefilled_form_submit/`
  - `async_dom_update/`
  - `hidden_dom_ignored/`
  - `duplicate_state_loop/`
  - `visual_style_state/`
- `semantic_exposure/` contains taxonomy-guided state-reach fixtures. These fixtures verify that the crawler saves useful neutral DOM/evidence artifacts for later analysis without making semantic judgments.
- `smoke_integrated_app/` is a retained static fixture for browser integration tests. It combines crawler-safe SPA interactions with accessibility-context patterns, sensitive-value sentinels, hidden referenced text, arbitrary hidden noise, and inert role-image truncation evidence.

The fixtures are served by `scripts/development/serve_spa_fixtures.py`, which uses Python's standard library HTTP server and disables response caching.
