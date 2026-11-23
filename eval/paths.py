"""Where the evaluation finds the external material it does not redistribute (one place to change).

Default: everything under ~/w4a-external. Override with environment variables:

  ACCESSGRAPH_EXTERNAL   base folder (default ~/w4a-external)
  INTERA11Y_DIR          InterA11y clone at commit 8dcf06e (D2)            default <base>/InterA11y
  RAMPA_DIR              rampa-cli clone at commit df32363 (D3, D6)        default <base>/rampa-cli
  D5_APPS_DIR            the ten D5 apps at the commits in eval/d5_apps.yaml  default <base>/d5-apps
  D5_REVIEW_SITE_DIR     Netlify project of the expert review site (built)  default <base>/d5-review-site
  D5_REVIEW_DATA_DIR     private reviewer links (never in a repository)     default <base>/d5-review-data

The frozen adapter eval/adapters/live_state.py keeps its own default (<home>/w4a-external/rampa-cli), so that the
frozen code stays byte-identical; put the Rampa clone there when you run the live handover.
"""
from __future__ import annotations

import os
from pathlib import Path

EXTERNAL = Path(os.environ.get("ACCESSGRAPH_EXTERNAL", Path.home() / "w4a-external")).expanduser()
INTERA11Y = Path(os.environ.get("INTERA11Y_DIR", EXTERNAL / "InterA11y")).expanduser()
RAMPA = Path(os.environ.get("RAMPA_DIR", EXTERNAL / "rampa-cli")).expanduser()
D5_APPS = Path(os.environ.get("D5_APPS_DIR", EXTERNAL / "d5-apps")).expanduser()
D5_REVIEW_SITE = Path(os.environ.get("D5_REVIEW_SITE_DIR", EXTERNAL / "d5-review-site")).expanduser()
D5_REVIEW_DATA = Path(os.environ.get("D5_REVIEW_DATA_DIR", EXTERNAL / "d5-review-data")).expanduser()
