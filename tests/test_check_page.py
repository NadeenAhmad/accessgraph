"""C4: single-page mode (fake provider, no paid calls)."""
from __future__ import annotations

import json

from src.check_page import CheckPageOptions, check_page, target_url, xpath_to_css

PAGE = """<!doctype html><html lang="en"><head><title>Order history</title></head><body>
<a href="#main">Skip to main content</a>
<main id="main"><h1>Order history</h1><p>Your last orders.</p><a href="/terms">Read more</a>
<button>Download invoice</button></main></body></html>"""


def test_xpath_to_css_and_targets(tmp_path):
  assert xpath_to_css("/html[1]/body[1]/div[2]/a[1]") == "html > body > div:nth-of-type(2) > a:nth-of-type(1)"
  assert xpath_to_css("/html[1]/head[1]/title[1]") == "html > head > title:nth-of-type(1)"
  assert xpath_to_css("not an xpath ()") == ""
  page = tmp_path / "p.html"
  page.write_text("x")
  assert target_url(str(page)).startswith("file://") and target_url("https://example.com/") == "https://example.com/"


def test_check_page_judges_one_state_in_isolation(tmp_path):
  page = tmp_path / "page.html"
  page.write_text(PAGE)
  report = check_page(CheckPageOptions(target=str(page), out_dir=tmp_path / "run"))
  assert report["context_mode"] == "isolated_state" and report["prompt_version"] == "confirm_v5_text"
  assert report["candidates"] >= 5 and len(list((tmp_path / "run" / "states").iterdir())) == 1
  by_type = {f["candidate_type"]: f for f in report["findings"]}
  assert by_type["heading-not-descriptive"]["css_selector"].endswith("h1:nth-of-type(1)")
  assert by_type["page-title-not-descriptive"]["xpath"] == "/html[1]/head[1]/title[1]"
  saved = json.loads((tmp_path / "run" / "check_page_findings.json").read_text())
  assert saved["findings"] == report["findings"]
