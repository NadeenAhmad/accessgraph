from __future__ import annotations

import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from scripts.benchmarks.booking.runner import (
  BOOKING_CLEAN_PROFILE,
  BOOKING_PROFILE_GLOBAL,
  open_booking_run,
)
from scripts.benchmarks.booking.spa_process import open_booking_spa
from src.analysis.candidates import build_semantic_candidates
from src.analysis.candidates.run_reader import load_run_artifacts
from src.analysis.evaluation.seeded_scorer import (
  SeededScorerOptions,
  score_seeded_experiment,
)
from src.crawler.crawl.entrypoint import CrawlConfig, run_crawl
from src.crawler.evidence.accessibility_context_schema import (
  FORBIDDEN_EVIDENCE_KEYS,
)
from src.crawler.state.focused_run import (
  FocusedRunRecorder,
  FocusedStateSpec,
  capture_focused_transition_trigger,
)


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = REPO_ROOT / "benchmarks" / "registry" / "benchmark-case-registry.json"
SEMANTIC_JUDGMENT_KEYS = {
  *(key.casefold() for key in FORBIDDEN_EVIDENCE_KEYS),
  "candidate_type",
  "confirmation",
  "expected_violation",
  "expectedviolation",
  "llm_result",
  "taxonomy",
  "violations",
}
SEMANTIC_OUTPUT_NAMES = {
  "candidates",
  "confirmations",
  "evaluation",
  "reports",
}


@pytest.fixture(scope="module")
def booking_spa():
  with open_booking_spa() as server:
    yield server


@pytest.fixture(scope="module")
def booking_browser():
  playwright = pytest.importorskip("playwright.async_api")
  loop = asyncio.new_event_loop()
  manager = None
  browser = None
  try:
    manager = loop.run_until_complete(playwright.async_playwright().start())
    browser = loop.run_until_complete(manager.chromium.launch(headless=True))
  except Exception as exc:
    if manager is not None:
      loop.run_until_complete(manager.stop())
    loop.close()
    pytest.skip(f"Playwright Chromium is unavailable: {exc}")

  try:
    yield loop, browser
  finally:
    loop.run_until_complete(browser.close())
    loop.run_until_complete(manager.stop())
    loop.close()


def _run_async(booking_browser, coroutine):
  loop, _ = booking_browser
  return loop.run_until_complete(coroutine)


def _read_json(path: Path):
  return json.loads(path.read_text(encoding="utf-8"))


def _build_booking_candidates(run_dir: Path, candidate_type: str) -> list[dict]:
  build = build_semantic_candidates(
    run_dir,
    candidate_types=[candidate_type],
  )
  return [
    json.loads(line)
    for line in (
      build.output_dir / "candidates.jsonl"
    ).read_text(encoding="utf-8").splitlines()
    if line
  ]


def _score_booking_recovery(
  run_dir: Path,
  *,
  config_id: str,
  score_run_id: str,
  expected_recovered: int,
  expected_matched_entries: int,
):
  score = score_seeded_experiment(
    SeededScorerOptions(
      run_dir=run_dir,
      config_id=config_id,
      registry_path=REGISTRY,
      score_run_id=score_run_id,
    )
  )
  assert score.summary["counts"]["expected_seeds"] == 1
  assert score.summary["counts"]["recovered_seeds"] == expected_recovered
  assert score.summary["counts"]["matched_candidates"] == (
    expected_matched_entries
  )
  matched_candidates = score.summary["results"][0].get(
    "matched_candidates",
    [],
  )
  assert len(matched_candidates) == expected_matched_entries
  return score, matched_candidates


def _json_keys(value) -> set[str]:
  if isinstance(value, dict):
    keys = {str(key).casefold() for key in value}
    for child in value.values():
      keys.update(_json_keys(child))
    return keys
  if isinstance(value, list):
    keys: set[str] = set()
    for child in value:
      keys.update(_json_keys(child))
    return keys
  return set()


def _assert_neutral_state_artifacts(
  run_dir: Path,
  state_id: str,
  *,
  dom_marker: str | None = None,
) -> tuple[dict, dict]:
  state_dir = run_dir / "states" / state_id
  dom_path = state_dir / "dom.html"
  screenshot_path = state_dir / "screenshot.png"
  metadata_path = state_dir / "metadata.json"
  context_path = state_dir / "accessibility_context.json"

  dom = dom_path.read_text(encoding="utf-8")
  assert dom.strip()
  if dom_marker is not None:
    assert dom_marker in dom

  assert screenshot_path.stat().st_size > len(PNG_SIGNATURE)
  assert screenshot_path.read_bytes()[: len(PNG_SIGNATURE)] == PNG_SIGNATURE

  metadata = _read_json(metadata_path)
  assert metadata["state_id"] == state_id
  assert metadata["html_hash"]
  assert metadata["dom_identity_hash"]

  context = _read_json(context_path)
  assert context["schema_version"] == "1"
  assert SEMANTIC_JUDGMENT_KEYS.isdisjoint(_json_keys(context))

  aria_path = state_dir / "aria_snapshot.json"
  if aria_path.exists():
    assert isinstance(_read_json(aria_path), dict)
  else:
    assert metadata["aria_snapshot"]["status"] == "error"

  assert not (state_dir / "semantic_elements.json").exists()
  return metadata, context


def _assert_no_semantic_outputs(run_dir: Path) -> None:
  assert SEMANTIC_OUTPUT_NAMES.isdisjoint(
    path.name for path in run_dir.iterdir()
  )


def test_prepared_review_supports_neutral_focused_acquisition(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    run_dir = tmp_path / "focused"

    async with open_booking_run(
      browser,
      base_url=booking_spa.base_url,
      profile=BOOKING_CLEAN_PROFILE,
      target_state="review",
    ) as run:
      assert urlsplit(run.page.url).path == "/review"
      assert await run.page.get_by_role(
        "heading",
        name="Review appointment",
        level=1,
        exact=True,
      ).is_visible()
      assert await run.page.evaluate(
        f"window[{json.dumps(BOOKING_PROFILE_GLOBAL)}]"
      ) == BOOKING_CLEAN_PROFILE

      recorder = FocusedRunRecorder(
        run_dir=run_dir,
        app_name="booking-scheduler",
        benchmark_name="booking-clean-integration",
        source_script="tests/test_booking_accessgraph_integration.py",
      )
      record = await recorder.capture_page_state(
        run.page,
        FocusedStateSpec(
          benchmark_state_id="booking-review",
          focused_state_name="review",
          action_path=["prepare Review with the Booking functional-state runner"],
          key_validated_selectors=[
            '[data-testid="route-review"]',
            '[data-testid="review-only-note"]',
          ],
        ),
      )
      manifest = recorder.write_run_artifacts()

    persisted_manifest = _read_json(run_dir / "run_metadata.json")
    expected_stable_manifest = {
      "acquisition_method": "focused_scripted",
      "app_name": "booking-scheduler",
      "benchmark_name": "booking-clean-integration",
      "source_script": "tests/test_booking_accessgraph_integration.py",
      "ordinary_crawler_policy_changed": False,
      "semantic_judgments_included": False,
      "state_count": 1,
      "transition_count": 0,
    }
    assert {
      key: persisted_manifest[key]
      for key in expected_stable_manifest
    } == expected_stable_manifest
    assert {
      key: manifest[key]
      for key in expected_stable_manifest
    } == expected_stable_manifest

    assert record.state_id == "state_0000"
    assert record.route == "/review"
    assert manifest["acquisition_method"] == "focused_scripted"
    assert manifest["state_count"] == 1
    assert manifest["transition_count"] == 0
    assert manifest["semantic_judgments_included"] is False

    graph = _read_json(run_dir / "graph.json")
    transitions = _read_json(run_dir / "transitions.json")
    assert graph["start_state"] == "state_0000"
    assert graph["states"] == ["state_0000"]
    assert graph["edges"] == []
    assert transitions == []

    metadata, _ = _assert_neutral_state_artifacts(
      run_dir,
      "state_0000",
      dom_marker="Review appointment",
    )
    assert metadata["route"] == "/review"
    assert metadata["parent_state"] is None
    assert metadata["focused_acquisition"]["method"] == "focused_scripted"
    assert metadata["focused_acquisition"]["focused_state_name"] == "review"

    loaded = load_run_artifacts(run_dir)
    assert [state.state_id for state in loaded.states] == ["state_0000"]
    assert loaded.states[0].metadata["route"] == "/review"
    _assert_no_semantic_outputs(run_dir)

  _run_async(booking_browser, verify())


def test_bs_sem_159_help_page_declares_wrong_document_language(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    snapshots = {}
    cases = (
      ("clean", BOOKING_CLEAN_PROFILE, "en", 0),
      ("seeded", "booking-bs-sem-159", "de", 1),
    )

    for label, profile, expected_lang, expected_recovered in cases:
      run_dir = tmp_path / label
      async with open_booking_run(
        browser,
        base_url=booking_spa.base_url,
        profile=profile,
        target_state="help",
      ) as run:
        route = run.page.locator('[data-testid="route-help"]')
        help_content = run.page.locator('[data-testid="help-content"]')
        local_language_targets = (
          '[data-testid="cancellation-policy-text"], '
          '[data-testid="preparation-instructions-text"], '
          '[data-testid="arrival-instructions-text"]'
        )

        assert urlsplit(run.page.url).path == "/help"
        assert await run.page.title() == (
          "Help & policies | Booking Scheduler Benchmark"
        )
        assert await route.locator("h1").inner_text() == "Help & policies"
        assert await run.page.locator("html").get_attribute("lang") == expected_lang
        assert await help_content.locator("h2").all_inner_texts() == [
          "Clinic information",
          "Cancellation policy",
          "Rescheduling",
          "Preparing for your appointment",
          "Contact",
          "Directions",
        ]
        assert "Contact the clinic at least 24 hours" in await help_content.inner_text()
        assert "Arrive 10 minutes early" in await help_content.inner_text()
        assert "Use the Cedar Lane entrance" in await help_content.inner_text()
        assert await run.page.locator(local_language_targets).count() == 3
        for index in range(3):
          assert (
            await run.page.locator(local_language_targets).nth(index).get_attribute("lang")
            is None
          )

        snapshots[label] = {
          "html": await run.page.content(),
          "aria": await route.aria_snapshot(),
          "text": await help_content.inner_text(),
          "links": await route.locator("a").evaluate_all(
            "elements => elements.map(element => ({text: element.textContent, href: element.getAttribute('href')}))"
          ),
        }

        recorder = FocusedRunRecorder(
          run_dir=run_dir,
          app_name="booking-scheduler",
          benchmark_name=f"booking-bs-sem-159-{label}",
          source_script="tests/test_booking_accessgraph_integration.py",
        )
        record = await recorder.capture_page_state(
          run.page,
          FocusedStateSpec(
            benchmark_state_id="",
            focused_state_name="help-document-language",
            action_path=["open Help and policies"],
            key_validated_selectors=[
              '[data-testid="route-help"]',
              '[data-testid="help-content"]',
              "section#cancellation > h2",
              '[data-testid="cancellation-policy-text"]',
              "section#preparation > h2",
              '[data-testid="preparation-instructions-text"]',
              "section#directions > h2",
              '[data-testid="arrival-instructions-text"]',
            ],
          ),
        )
        recorder.write_run_artifacts()

        assert record.state_id == "state_0000"
        assert record.benchmark_state_id == ""
        assert record.route == "/help"

      _, context = _assert_neutral_state_artifacts(
        run_dir,
        "state_0000",
        dom_marker='data-testid="route-help"',
      )
      page_evidence = context["page"]
      assert page_evidence["html_lang"] == expected_lang
      assert page_evidence["document_lang"] == expected_lang
      assert page_evidence["title"] == (
        "Help & policies | Booking Scheduler Benchmark"
      )
      assert "Help & policies" in page_evidence["body_text_sample"]
      assert "Cancellation policy" in page_evidence["body_text_sample"]

      candidates = _build_booking_candidates(
        run_dir,
        "lang-mismatch",
      )
      assert len(candidates) == 1
      candidate = candidates[0]
      page = candidate["evidence"]["primary"]["page"]
      context_evidence = candidate["evidence"]["supporting"][
        "lang_mismatch_context_v1"
      ]
      assert candidate["state_id"] == "state_0000"
      assert candidate["state_context"]["url"].endswith("/help")
      assert page["html_lang"] == expected_lang
      assert page["document_lang"] == expected_lang
      assert page["title"] == "Help & policies | Booking Scheduler Benchmark"
      assert "Help & policies" in page["body_text_sample"]
      assert context_evidence["declared_page_language"]["route"] == "/help"
      assert context_evidence["declared_page_language"]["html_lang"] == expected_lang
      assert context_evidence["page_text_evidence"][
        "strongest_marker_language_hint"
      ] == "en"
      assert "seed" not in json.dumps(candidate).casefold()
      assert "profile" not in json.dumps(candidate).casefold()

      _score_booking_recovery(
        run_dir,
        config_id="booking-bs-sem-159",
        score_run_id=f"bs-sem-159-{label}",
        expected_recovered=expected_recovered,
        expected_matched_entries=expected_recovered,
      )

    assert snapshots["clean"]["aria"] == snapshots["seeded"]["aria"]
    assert snapshots["clean"]["text"] == snapshots["seeded"]["text"]
    assert snapshots["clean"]["links"] == snapshots["seeded"]["links"]
    assert snapshots["seeded"]["html"].replace(
      '<html lang="de">',
      '<html lang="en">',
    ) == snapshots["clean"]["html"]

    async with open_booking_run(
      browser,
      base_url=booking_spa.base_url,
      profile="booking-bs-sem-159",
      target_state="services",
    ) as run:
      assert await run.page.locator("html").get_attribute("lang") == "en"
      await run.page.get_by_role("link", name="Help & policies").click()
      await run.page.wait_for_url("**/help")
      assert await run.page.locator("html").get_attribute("lang") == "de"
      await run.page.go_back()
      await run.page.wait_for_url("**/services")
      assert await run.page.locator("html").get_attribute("lang") == "en"

  _run_async(booking_browser, verify())


def test_services_root_supports_bounded_autonomous_crawl(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    run_dir = tmp_path / "autonomous"
    start_url = f"{booking_spa.base_url}/services"
    cfg = CrawlConfig(
      max_states=4,
      max_depth=1,
      max_actions_per_state=3,
      back_timeout_ms=3_000,
      traversal_strategy="bfs",
      scope_policy="same_origin",
      prioritize_action_candidates=True,
      enable_tile_screenshots=False,
      wait_timeout_ms=300,
    )

    async with open_booking_run(
      browser,
      base_url=booking_spa.base_url,
      profile=BOOKING_CLEAN_PROFILE,
      target_state="services",
    ) as run:
      assert urlsplit(run.page.url).path == "/services"
      assert await run.page.get_by_role(
        "heading",
        name="Select service",
        level=1,
        exact=True,
      ).is_visible()
      assert await run.page.evaluate(
        f"window[{json.dumps(BOOKING_PROFILE_GLOBAL)}]"
      ) == BOOKING_CLEAN_PROFILE

      graph = await run_crawl(run.page, start_url, run_dir, cfg)
      assert await run.page.evaluate(
        f"window[{json.dumps(BOOKING_PROFILE_GLOBAL)}]"
      ) == BOOKING_CLEAN_PROFILE

    graph.save_json(run_dir / "graph.json")
    graph.save_transitions_json(run_dir / "transitions.json")

    graph_payload = _read_json(run_dir / "graph.json")
    transitions = _read_json(run_dir / "transitions.json")
    state_ids = set(graph_payload["states"])

    assert graph_payload["start_state"] == "state_0000"
    assert len(state_ids) >= 2
    assert transitions
    assert graph_payload["edges"] == transitions
    assert {node["state_id"] for node in graph_payload["nodes"]} == state_ids
    assert all(edge["from"] in state_ids for edge in transitions)
    assert all(edge["to"] in state_ids for edge in transitions)
    assert all(isinstance(edge["action"], dict) for edge in transitions)

    root = next(
      node
      for node in graph_payload["nodes"]
      if node["state_id"] == graph_payload["start_state"]
    )
    assert root["route"] == "/services"
    root_metadata, _ = _assert_neutral_state_artifacts(
      run_dir,
      "state_0000",
      dom_marker="Select service",
    )
    assert root_metadata["route"] == "/services"

    child_state_id = next(
      edge["to"]
      for edge in transitions
      if edge["to"] != graph_payload["start_state"]
    )
    child_metadata, _ = _assert_neutral_state_artifacts(
      run_dir,
      child_state_id,
    )
    assert child_metadata["parent_state"] in state_ids
    assert child_metadata["action_from_parent"]
    _assert_no_semantic_outputs(run_dir)

  _run_async(booking_browser, verify())


def test_bs_sem_112_clean_and_seeded_schedule_recovery(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    cases = (
      (
        "clean",
        BOOKING_CLEAN_PROFILE,
        "09:00 Available",
        None,
        '- button "09:00 Available"',
        '- button "09:00 Selected" [pressed]',
        0,
      ),
      (
        "seeded",
        "booking-bs-sem-112",
        "13:00 Available",
        "13:00 Available",
        '- button "13:00 Available": 09:00 Available',
        '- button "13:00 Available" [pressed]: 09:00 Selected',
        1,
      ),
    )

    for (
      label,
      profile,
      expected_accessible_name,
      expected_aria_label,
      expected_initial_snapshot,
      expected_selected_snapshot,
      expected_recovered,
    ) in cases:
      run_dir = tmp_path / label
      async with open_booking_run(
        browser,
        base_url=booking_spa.base_url,
        profile=profile,
        target_state="schedule",
      ) as run:
        await run.page.locator('[data-testid="schedule-date-input"]').fill(
          "2026-06-16"
        )
        slot = run.page.locator('[data-testid="slot-button-0900"]')
        sibling = run.page.locator('[data-testid="slot-button-1300"]')

        assert await run.page.locator("#slot-list-heading").inner_text() == (
          "Available times for June 16, 2026"
        )
        assert await slot.inner_text() == "09:00\nAvailable"
        assert await slot.get_attribute("type") == "button"
        assert await slot.get_attribute("aria-label") == expected_aria_label
        assert await slot.get_attribute("aria-pressed") is None
        assert await slot.aria_snapshot() == expected_initial_snapshot
        assert await sibling.inner_text() == "13:00\nAvailable"
        assert await sibling.get_attribute("aria-label") is None
        assert await sibling.get_attribute("aria-pressed") is None
        assert await sibling.aria_snapshot() == '- button "13:00 Available"'

        recorder = FocusedRunRecorder(
          run_dir=run_dir,
          app_name="booking-scheduler",
          benchmark_name=f"booking-bs-sem-112-{label}",
          source_script="tests/test_booking_accessgraph_integration.py",
        )
        record = await recorder.capture_page_state(
          run.page,
          FocusedStateSpec(
            benchmark_state_id="BS-S002",
            focused_state_name="schedule-june-16",
            action_path=[
              "select Consultation",
              "continue to Schedule",
              "select June 16",
            ],
            key_validated_selectors=[
              '[data-testid="route-schedule"]',
              '[data-testid="slot-button-0900"]',
              '[data-testid="slot-button-1300"]',
            ],
          ),
        )
        recorder.write_run_artifacts()

        assert record.state_id == "state_0000"
        assert record.route == "/schedule"
        await slot.click()
        assert await slot.inner_text() == "09:00\nSelected"
        assert await slot.get_attribute("aria-pressed") == "true"
        assert await slot.aria_snapshot() == expected_selected_snapshot
        assert await run.page.locator(
          '[data-testid="summary-slot"]'
        ).inner_text() == "09:00"
        assert await run.page.locator(
          '[data-testid="status-region"]'
        ).inner_text() == "09:00 selected for Consultation."
        assert await sibling.inner_text() == "13:00\nAvailable"
        assert await sibling.get_attribute("aria-pressed") is None
        assert await sibling.aria_snapshot() == '- button "13:00 Available"'

      build = build_semantic_candidates(
        run_dir,
        candidate_types=["button-label-mismatch"],
      )
      candidates = [
        json.loads(line)
        for line in (
          build.output_dir / "candidates.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if line
      ]
      assert len(candidates) == 3

      candidates_by_testid = {
        candidate["evidence"]["supporting"]["button_action_context_v1"][
          "action_evidence"
        ]["data_testid"]: candidate
        for candidate in candidates
      }
      assert set(candidates_by_testid) == {
        "slot-button-0900",
        "slot-button-1300",
        "slot-button-1530",
      }
      candidate = candidates_by_testid["slot-button-0900"]
      button = candidate["evidence"]["primary"]["button"]
      action_context = candidate["evidence"]["supporting"][
        "button_action_context_v1"
      ]
      sibling_button = candidates_by_testid["slot-button-1300"]["evidence"][
        "primary"
      ]["button"]

      assert button["text"] == "09:00 Available"
      assert button["accessible_name"] == expected_accessible_name
      assert button["aria_label"] == expected_aria_label
      assert action_context["local_context"]["section_heading"] == (
        "Available times for June 16, 2026"
      )
      assert sibling_button["text"] == "13:00 Available"
      assert sibling_button["accessible_name"] == "13:00 Available"
      assert sibling_button["aria_label"] is None

      score = score_seeded_experiment(
        SeededScorerOptions(
          run_dir=run_dir,
          config_id="booking-bs-sem-112",
          registry_path=REGISTRY,
          score_run_id=f"bs-sem-112-{label}",
        )
      )
      assert score.summary["counts"]["expected_seeds"] == 1
      assert score.summary["counts"]["recovered_seeds"] == expected_recovered
      matched_candidates = score.summary["results"][0].get(
        "matched_candidates",
        [],
      )
      assert len(matched_candidates) == expected_recovered
      if expected_recovered:
        assert matched_candidates[0]["candidate_id"] == candidate["candidate_id"]

  _run_async(booking_browser, verify())


def test_bs_sem_113_clean_and_seeded_schedule_recovery(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    cases = (
      (
        "clean",
        BOOKING_CLEAN_PROFILE,
        "14:00 Available",
        None,
        '- button "14:00 Available"',
        '- button "14:00 Selected" [pressed]',
        0,
      ),
      (
        "seeded",
        "booking-bs-sem-113",
        "14:00 Available on June 16, 2026",
        "14:00 Available on June 16, 2026",
        '- button "14:00 Available on June 16, 2026": 14:00 Available',
        '- button "14:00 Available on June 16, 2026" [pressed]: 14:00 Selected',
        1,
      ),
    )

    for (
      label,
      profile,
      expected_accessible_name,
      expected_aria_label,
      expected_initial_snapshot,
      expected_selected_snapshot,
      expected_recovered,
    ) in cases:
      run_dir = tmp_path / label
      async with open_booking_run(
        browser,
        base_url=booking_spa.base_url,
        profile=profile,
        target_state="schedule",
      ) as run:
        await run.page.locator('[data-testid="schedule-date-input"]').fill(
          "2026-06-18"
        )
        slot = run.page.locator('[data-testid="slot-button-1400"]')
        early_slot = run.page.locator('[data-testid="slot-button-0830"]')
        late_slot = run.page.locator('[data-testid="slot-button-1600"]')
        unavailable_slot = run.page.locator(
          '[data-testid="slot-unavailable-1100"]'
        )

        assert await run.page.locator("#slot-list-heading").inner_text() == (
          "Available times for June 18, 2026"
        )
        assert await run.page.locator(
          '[data-testid="summary-date"]'
        ).inner_text() == "June 18, 2026"
        assert await slot.inner_text() == "14:00\nAvailable"
        assert await slot.get_attribute("type") == "button"
        assert await slot.get_attribute("aria-label") == expected_aria_label
        assert await slot.get_attribute("aria-pressed") is None
        assert await slot.aria_snapshot() == expected_initial_snapshot
        assert await early_slot.aria_snapshot() == '- button "08:30 Available"'
        assert await late_slot.aria_snapshot() == '- button "16:00 Available"'
        assert await unavailable_slot.inner_text() == "11:00\nUnavailable"

        recorder = FocusedRunRecorder(
          run_dir=run_dir,
          app_name="booking-scheduler",
          benchmark_name=f"booking-bs-sem-113-{label}",
          source_script="tests/test_booking_accessgraph_integration.py",
        )
        record = await recorder.capture_page_state(
          run.page,
          FocusedStateSpec(
            benchmark_state_id="BS-S002",
            focused_state_name="schedule-june-18",
            action_path=[
              "select Consultation",
              "continue to Schedule",
              "select June 18",
            ],
            key_validated_selectors=[
              '[data-testid="route-schedule"]',
              '[data-testid="slot-button-0830"]',
              '[data-testid="slot-button-1400"]',
              '[data-testid="slot-button-1600"]',
            ],
          ),
        )
        recorder.write_run_artifacts()

        assert record.state_id == "state_0000"
        assert record.route == "/schedule"
        await slot.click()
        assert await slot.inner_text() == "14:00\nSelected"
        assert await slot.get_attribute("aria-pressed") == "true"
        assert await slot.aria_snapshot() == expected_selected_snapshot
        assert await run.page.locator(
          '[data-testid="summary-date"]'
        ).inner_text() == "June 18, 2026"
        assert await run.page.locator(
          '[data-testid="summary-slot"]'
        ).inner_text() == "14:00"
        assert await run.page.locator(
          '[data-testid="status-region"]'
        ).inner_text() == "14:00 selected for Consultation."
        assert await early_slot.aria_snapshot() == '- button "08:30 Available"'
        assert await late_slot.aria_snapshot() == '- button "16:00 Available"'
        assert await unavailable_slot.inner_text() == "11:00\nUnavailable"

      build = build_semantic_candidates(
        run_dir,
        candidate_types=["button-label-mismatch"],
      )
      candidates = [
        json.loads(line)
        for line in (
          build.output_dir / "candidates.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if line
      ]
      assert len(candidates) == 3

      candidates_by_testid = {
        candidate["evidence"]["supporting"]["button_action_context_v1"][
          "action_evidence"
        ]["data_testid"]: candidate
        for candidate in candidates
      }
      assert set(candidates_by_testid) == {
        "slot-button-0830",
        "slot-button-1400",
        "slot-button-1600",
      }
      candidate = candidates_by_testid["slot-button-1400"]
      button = candidate["evidence"]["primary"]["button"]
      action_context = candidate["evidence"]["supporting"][
        "button_action_context_v1"
      ]

      assert button["text"] == "14:00 Available"
      assert button["accessible_name"] == expected_accessible_name
      assert button["aria_label"] == expected_aria_label
      assert action_context["local_context"]["section_heading"] == (
        "Available times for June 18, 2026"
      )
      assert candidates_by_testid["slot-button-0830"]["evidence"]["primary"][
        "button"
      ]["accessible_name"] == "08:30 Available"
      assert candidates_by_testid["slot-button-1600"]["evidence"]["primary"][
        "button"
      ]["accessible_name"] == "16:00 Available"

      score = score_seeded_experiment(
        SeededScorerOptions(
          run_dir=run_dir,
          config_id="booking-bs-sem-113",
          registry_path=REGISTRY,
          score_run_id=f"bs-sem-113-{label}",
        )
      )
      assert score.summary["counts"]["expected_seeds"] == 1
      assert score.summary["counts"]["recovered_seeds"] == expected_recovered
      matched_candidates = score.summary["results"][0].get(
        "matched_candidates",
        [],
      )
      assert len(matched_candidates) == expected_recovered
      if expected_recovered:
        assert matched_candidates[0]["candidate_id"] == candidate["candidate_id"]

    june_16_dir = tmp_path / "june-16-control"
    async with open_booking_run(
      browser,
      base_url=booking_spa.base_url,
      profile=BOOKING_CLEAN_PROFILE,
      target_state="schedule",
    ) as run:
      await run.page.locator('[data-testid="schedule-date-input"]').fill(
        "2026-06-16"
      )
      assert await run.page.locator("#slot-list-heading").inner_text() == (
        "Available times for June 16, 2026"
      )
      assert await run.page.locator(
        '[data-testid="slot-button-1400"]'
      ).count() == 0

      recorder = FocusedRunRecorder(
        run_dir=june_16_dir,
        app_name="booking-scheduler",
        benchmark_name="booking-bs-sem-113-june-16-control",
        source_script="tests/test_booking_accessgraph_integration.py",
      )
      await recorder.capture_page_state(
        run.page,
        FocusedStateSpec(
          benchmark_state_id="BS-S002",
          focused_state_name="schedule-june-16-control",
          action_path=[
            "select Consultation",
            "continue to Schedule",
            "select June 16",
          ],
          key_validated_selectors=[
            '[data-testid="route-schedule"]',
            '[data-testid="slot-button-0900"]',
            '[data-testid="slot-button-1300"]',
          ],
        ),
      )
      recorder.write_run_artifacts()

    build = build_semantic_candidates(
      june_16_dir,
      candidate_types=["button-label-mismatch"],
    )
    candidates = [
      json.loads(line)
      for line in (
        build.output_dir / "candidates.jsonl"
      ).read_text(encoding="utf-8").splitlines()
      if line
    ]
    assert len(candidates) == 3
    score = score_seeded_experiment(
      SeededScorerOptions(
        run_dir=june_16_dir,
        config_id="booking-bs-sem-113",
        registry_path=REGISTRY,
        score_run_id="bs-sem-113-june-16-control",
      )
    )
    assert score.summary["counts"]["expected_seeds"] == 1
    assert score.summary["counts"]["recovered_seeds"] == 0
    assert score.summary["results"][0].get("matched_candidates", []) == []

  _run_async(booking_browser, verify())


def test_bs_sem_114_clean_and_seeded_review_link_recovery(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    cases = (
      ("clean", BOOKING_CLEAN_PROFILE, "Change service", 0),
      ("seeded", "booking-bs-sem-114", "Change appointment", 1),
    )

    for label, profile, expected_target_name, expected_recovered in cases:
      run_dir = tmp_path / label
      async with open_booking_run(
        browser,
        base_url=booking_spa.base_url,
        profile=profile,
        target_state="review",
      ) as run:
        target = run.page.locator('[data-testid="change-service"]')
        sibling = run.page.locator('[data-testid="change-appointment"]')
        edit_details = run.page.locator('[data-testid="edit-details"]')
        service_panel = run.page.locator(
          '[data-testid="review-service-summary"]'
        )

        assert urlsplit(run.page.url).path == "/review"
        assert await run.page.get_by_role(
          "heading",
          name="Review appointment",
          level=1,
          exact=True,
        ).is_visible()
        assert await service_panel.locator("h3").inner_text() == "Service"
        assert await service_panel.locator(
          '[data-testid="review-service-name"]'
        ).inner_text() == "Consultation"
        assert await service_panel.locator(
          '[data-testid="review-service-duration"]'
        ).inner_text() == "30 minutes"

        assert await target.inner_text() == expected_target_name
        assert await target.get_attribute("href") == "/services"
        assert await target.aria_snapshot() == (
          f'- link "{expected_target_name}":\n  - /url: /services'
        )
        assert await sibling.inner_text() == "Change appointment"
        assert await sibling.get_attribute("href") == "/schedule"
        assert await sibling.aria_snapshot() == (
          '- link "Change appointment":\n  - /url: /schedule'
        )
        assert await edit_details.inner_text() == "Edit details"
        assert await edit_details.get_attribute("href") == "/details"
        assert await edit_details.aria_snapshot() == (
          '- link "Edit details":\n  - /url: /details'
        )

        recorder = FocusedRunRecorder(
          run_dir=run_dir,
          app_name="booking-scheduler",
          benchmark_name=f"booking-bs-sem-114-{label}",
          source_script="tests/test_booking_accessgraph_integration.py",
        )
        record = await recorder.capture_page_state(
          run.page,
          FocusedStateSpec(
            benchmark_state_id="BS-S004",
            focused_state_name="review",
            action_path=[
              "select Consultation",
              "select June 16 at 09:00",
              "enter valid customer details",
              "continue to Review",
            ],
            key_validated_selectors=[
              '[data-testid="route-review"]',
              '[data-testid="review-service-summary"]',
              '[data-testid="change-service"]',
              '[data-testid="change-appointment"]',
            ],
          ),
        )
        recorder.write_run_artifacts()

        assert record.state_id == "state_0000"
        assert record.route == "/review"

        await sibling.click()
        await run.page.wait_for_url("**/schedule")
        assert urlsplit(run.page.url).path == "/schedule"
        assert await run.page.locator("h1").inner_text() == (
          "Schedule appointment"
        )
        await run.page.go_back()
        await run.page.wait_for_url("**/review")

        await edit_details.click()
        await run.page.wait_for_url("**/details")
        assert urlsplit(run.page.url).path == "/details"
        assert await run.page.locator("h1").inner_text() == "Booking details"
        await run.page.go_back()
        await run.page.wait_for_url("**/review")

        await target.click()
        await run.page.wait_for_url("**/services")
        assert urlsplit(run.page.url).path == "/services"
        assert await run.page.locator("h1").inner_text() == "Select service"

      build = build_semantic_candidates(
        run_dir,
        candidate_types=["link-text-mismatch"],
      )
      candidates = [
        json.loads(line)
        for line in (
          build.output_dir / "candidates.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if line
      ]
      assert len(candidates) == 9

      target_candidates = [
        candidate
        for candidate in candidates
        if candidate["evidence"]["primary"]["link"]["href"] == "/services"
        and candidate["evidence"]["supporting"]["context"].get(
          "section_heading"
        ) == "Service"
      ]
      assert len(target_candidates) == 1
      target_candidate = target_candidates[0]
      target_link = target_candidate["evidence"]["primary"]["link"]
      target_context = target_candidate["evidence"]["supporting"]

      assert target_link["text"] == expected_target_name
      assert target_link["accessible_name"] == expected_target_name
      assert target_link["href"] == "/services"
      assert target_context["context"]["nearby_text"] == (
        "NameConsultationDuration30 minutes"
      )
      nearest_heading = target_context["structure"]["nearest_heading"]
      assert {
        key: nearest_heading[key]
        for key in ("selector", "tag", "text")
      } == {
        "selector": "h3#review-service-heading",
        "tag": "h3",
        "text": "Service",
      }
      assert target_context["link_destination_context_v1"]["raw_href"] == (
        "/services"
      )
      assert target_context["link_destination_context_v1"][
        "resolved_path"
      ] == "/services"

      sibling_candidates = [
        candidate
        for candidate in candidates
        if candidate["evidence"]["primary"]["link"]["href"] == "/schedule"
        and candidate["evidence"]["supporting"]["context"].get(
          "section_heading"
        ) == "Date and time"
      ]
      assert len(sibling_candidates) == 1
      sibling_link = sibling_candidates[0]["evidence"]["primary"]["link"]
      assert sibling_link["text"] == "Change appointment"
      assert sibling_link["accessible_name"] == "Change appointment"

      score = score_seeded_experiment(
        SeededScorerOptions(
          run_dir=run_dir,
          config_id="booking-bs-sem-114",
          registry_path=REGISTRY,
          score_run_id=f"bs-sem-114-{label}",
        )
      )
      assert score.summary["counts"]["expected_seeds"] == 1
      assert score.summary["counts"]["recovered_seeds"] == expected_recovered
      matched_candidates = score.summary["results"][0].get(
        "matched_candidates",
        [],
      )
      assert len(matched_candidates) == expected_recovered
      if expected_recovered:
        assert matched_candidates[0]["candidate_id"] == (
          target_candidate["candidate_id"]
        )

  _run_async(booking_browser, verify())


def test_bs_sem_115_review_link_requires_observed_wrong_destination(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    cases = (
      ("source-only", "booking-bs-sem-115", None, None, None, 0),
      (
        "clean",
        BOOKING_CLEAN_PROFILE,
        "/schedule",
        "Schedule appointment",
        "BS-S002",
        0,
      ),
      (
        "seeded",
        "booking-bs-sem-115",
        "/services",
        "Select service",
        "BS-S001",
        1,
      ),
    )

    for (
      label,
      profile,
      expected_destination,
      expected_heading,
      expected_destination_state,
      expected_recovered,
    ) in cases:
      run_dir = tmp_path / label
      async with open_booking_run(
        browser,
        base_url=booking_spa.base_url,
        profile=profile,
        target_state="review",
      ) as run:
        target = run.page.locator('[data-testid="change-appointment"]')
        change_service = run.page.locator('[data-testid="change-service"]')
        edit_details = run.page.locator('[data-testid="edit-details"]')
        schedule_panel = run.page.locator(
          '[data-testid="review-schedule-summary"]'
        )

        assert urlsplit(run.page.url).path == "/review"
        assert await run.page.get_by_role(
          "heading",
          name="Review appointment",
          level=1,
          exact=True,
        ).is_visible()
        assert await schedule_panel.locator("h3").inner_text() == (
          "Date and time"
        )
        assert await schedule_panel.locator(
          '[data-testid="review-date"]'
        ).inner_text() == "June 16, 2026"
        assert await schedule_panel.locator(
          '[data-testid="review-slot"]'
        ).inner_text() == "09:00"

        assert await target.inner_text() == "Change appointment"
        assert await target.get_attribute("href") == "/schedule"
        assert await target.aria_snapshot() == (
          '- link "Change appointment":\n  - /url: /schedule'
        )
        assert await change_service.inner_text() == "Change service"
        assert await change_service.get_attribute("href") == "/services"
        assert await edit_details.inner_text() == "Edit details"
        assert await edit_details.get_attribute("href") == "/details"

        recorder = FocusedRunRecorder(
          run_dir=run_dir,
          app_name="booking-scheduler",
          benchmark_name=f"booking-bs-sem-115-{label}",
          source_script="tests/test_booking_accessgraph_integration.py",
        )
        source_record = await recorder.capture_page_state(
          run.page,
          FocusedStateSpec(
            benchmark_state_id="BS-S004",
            focused_state_name="review",
            action_path=[
              "select Consultation",
              "select June 16 at 09:00",
              "enter valid customer details",
              "continue to Review",
            ],
            key_validated_selectors=[
              '[data-testid="route-review"]',
              '[data-testid="review-schedule-summary"]',
              '[data-testid="change-appointment"]',
            ],
          ),
        )

        destination_record = None
        if expected_destination is not None:
          trigger = await capture_focused_transition_trigger(
            target,
            action_type="click",
            selector='[data-testid="change-appointment"]',
          )
          await target.click()
          await run.page.wait_for_url(f"**{expected_destination}")
          assert urlsplit(run.page.url).path == expected_destination
          assert await run.page.locator("h1").inner_text() == expected_heading

          destination_record = await recorder.capture_page_state(
            run.page,
            FocusedStateSpec(
              benchmark_state_id=expected_destination_state,
              focused_state_name=f"{label}-destination",
              action_path=["activate Change appointment"],
              key_validated_selectors=[
                (
                  '[data-testid="route-services"]'
                  if expected_destination == "/services"
                  else '[data-testid="route-schedule"]'
                )
              ],
              parent_focused_state_name="review",
              transition_text="activate Change appointment",
              transition_trigger=trigger,
            ),
          )

        manifest = recorder.write_run_artifacts()

      assert source_record.state_id == "state_0000"
      assert source_record.route == "/review"
      assert manifest["state_count"] == (2 if destination_record else 1)
      assert manifest["transition_count"] == (1 if destination_record else 0)

      build = build_semantic_candidates(
        run_dir,
        candidate_types=["link-text-mismatch"],
      )
      candidates = [
        json.loads(line)
        for line in (
          build.output_dir / "candidates.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if line
      ]
      target_candidates = [
        candidate
        for candidate in candidates
        if candidate["state_id"] == source_record.state_id
        and candidate["evidence"]["primary"]["link"]["href"] == "/schedule"
        and candidate["evidence"]["supporting"]["context"].get(
          "section_heading"
        )
        == "Date and time"
      ]
      assert len(target_candidates) == 1
      target_candidate = target_candidates[0]
      target_link = target_candidate["evidence"]["primary"]["link"]
      target_supporting = target_candidate["evidence"]["supporting"]

      assert target_link["text"] == "Change appointment"
      assert target_link["accessible_name"] == "Change appointment"
      assert target_link["href"] == "/schedule"
      assert target_supporting["link_destination_context_v1"][
        "resolved_path"
      ] == "/schedule"

      if destination_record is None:
        assert "destination_state_context_v1" not in target_supporting
      else:
        destination_context = target_supporting[
          "destination_state_context_v1"
        ]
        assert destination_context["source_state_id"] == source_record.state_id
        assert destination_context["match_basis"] == ["data_testid"]
        assert destination_context["match_count"] == 1
        captured_destination = destination_context["destinations"][0]
        assert captured_destination["target_state_id"] == (
          destination_record.state_id
        )
        assert captured_destination["target_route"] == expected_destination
        assert captured_destination["target_title"] == (
          f"{expected_heading} | Booking Scheduler Benchmark"
        )
        assert captured_destination["target_primary_headings"][0]["text"] == (
          expected_heading
        )
        assert captured_destination["trigger"]["data_testid"] == (
          "change-appointment"
        )
        assert captured_destination["trigger"]["href"] == "/schedule"
        assert captured_destination["trigger"]["text"] == (
          "Change appointment"
        )
        assert captured_destination["trigger"]["accessible_name"] == (
          "Change appointment"
        )

      score = score_seeded_experiment(
        SeededScorerOptions(
          run_dir=run_dir,
          config_id="booking-bs-sem-115",
          registry_path=REGISTRY,
          score_run_id=f"bs-sem-115-{label}",
        )
      )
      assert score.summary["counts"]["expected_seeds"] == 1
      assert score.summary["counts"]["recovered_seeds"] == expected_recovered
      assert score.summary["counts"]["matched_candidates"] == expected_recovered
      matched_candidates = score.summary["results"][0].get(
        "matched_candidates",
        [],
      )
      assert len(matched_candidates) == expected_recovered
      if expected_recovered:
        assert matched_candidates[0]["candidate_id"] == (
          target_candidate["candidate_id"]
        )

  _run_async(booking_browser, verify())


def test_bs_sem_116_clean_and_seeded_services_recovery(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    cases = (
      ("clean", BOOKING_CLEAN_PROFILE, "Consultation", 0),
      ("seeded", "booking-bs-sem-116", "Repair assessment", 1),
    )

    for label, profile, expected_name, expected_recovered in cases:
      run_dir = tmp_path / label
      async with open_booking_run(
        browser,
        base_url=booking_spa.base_url,
        profile=profile,
        target_state="services",
      ) as run:
        consultation = run.page.locator(
          '[data-testid="service-option-svc-consultation"]'
        )
        radio = consultation.locator('input[type="radio"]')
        native_label = consultation.locator("label")

        assert await radio.get_attribute("id") == "service-svc-consultation"
        assert await radio.get_attribute("name") == "service"
        assert await radio.get_attribute("value") == "svc-consultation"
        assert await native_label.get_attribute("for") == (
          "service-svc-consultation"
        )
        assert await consultation.locator(".service-name").inner_text() == (
          expected_name
        )
        assert await consultation.locator(".service-duration").inner_text() == (
          "30 minutes"
        )
        assert await consultation.locator(".service-description").inner_text() == (
          "Initial planning appointment for the benchmark fixture."
        )
        assert await run.page.locator(
          '[data-testid="service-option-svc-repair-assessment"] .service-name'
        ).inner_text() == "Repair assessment"
        assert await run.page.locator(
          '[data-testid="service-option-svc-follow-up-call"] .service-name'
        ).inner_text() == "Follow-up call"
        assert await run.page.get_by_role(
          "group",
          name="Available services",
          exact=True,
        ).count() == 1

        accessible_name = (
          f"{expected_name} 30 minutes "
          "Initial planning appointment for the benchmark fixture."
        )
        compact_accessible_name = (
          f"{expected_name}30 minutes"
          "Initial planning appointment for the benchmark fixture."
        )
        assert await radio.aria_snapshot() == f'- radio "{accessible_name}"'

        recorder = FocusedRunRecorder(
          run_dir=run_dir,
          app_name="booking-scheduler",
          benchmark_name=f"booking-bs-sem-116-{label}",
          source_script="tests/test_booking_accessgraph_integration.py",
        )
        record = await recorder.capture_page_state(
          run.page,
          FocusedStateSpec(
            benchmark_state_id="BS-S001",
            focused_state_name="services",
            action_path=["open initial Services state"],
            key_validated_selectors=[
              '[data-testid="route-services"]',
              '[data-testid="service-radio-svc-consultation"]',
            ],
          ),
        )
        recorder.write_run_artifacts()

        assert record.state_id == "state_0000"
        assert record.route == "/services"
        assert not await radio.is_checked()
        await radio.check()
        assert await radio.is_checked()
        assert not await run.page.locator(
          '[data-testid="continue-to-schedule"]'
        ).is_disabled()

      build = build_semantic_candidates(
        run_dir,
        candidate_types=["form-label-mismatch"],
      )
      candidates = [
        json.loads(line)
        for line in (
          build.output_dir / "candidates.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if line
      ]
      assert len(candidates) == 3

      consultation_candidates = [
        candidate
        for candidate in candidates
        if candidate["evidence"]["primary"]["form_control"].get("id")
        == "service-svc-consultation"
      ]
      assert len(consultation_candidates) == 1
      candidate = consultation_candidates[0]
      form_control = candidate["evidence"]["primary"]["form_control"]
      label_source = candidate["evidence"]["supporting"][
        "form_label_context_v1"
      ]["labeling"]["label_sources"][0]

      assert form_control["type"] == "radio"
      assert form_control["name"] == "service"
      assert form_control["accessible_name"] == compact_accessible_name
      assert label_source["relationship_type"] == "labels"
      assert label_source["method"] == "for"
      assert label_source["text_segments"] == [
        expected_name,
        "30 minutes",
        "Initial planning appointment for the benchmark fixture.",
      ]

      score = score_seeded_experiment(
        SeededScorerOptions(
          run_dir=run_dir,
          config_id="booking-bs-sem-116",
          registry_path=REGISTRY,
          score_run_id=f"bs-sem-116-{label}",
        )
      )
      assert score.summary["counts"]["expected_seeds"] == 1
      assert score.summary["counts"]["recovered_seeds"] == expected_recovered
      matched_candidates = score.summary["results"][0].get(
        "matched_candidates",
        [],
      )
      assert len(matched_candidates) == expected_recovered
      if expected_recovered:
        assert matched_candidates[0]["candidate_id"] == candidate["candidate_id"]

  _run_async(booking_browser, verify())


def test_bs_sem_117_selected_slot_exposes_only_seeded_false_state(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    cases = (
      (
        "clean",
        BOOKING_CLEAN_PROFILE,
        "true",
        '- button "09:00 Selected" [pressed]',
        0,
      ),
      (
        "seeded",
        "booking-bs-sem-117",
        "false",
        '- button "09:00 Selected"',
        1,
      ),
    )

    for (
      label,
      profile,
      expected_aria_pressed,
      expected_snapshot,
      expected_recovered,
    ) in cases:
      run_dir = tmp_path / label
      async with open_booking_run(
        browser,
        base_url=booking_spa.base_url,
        profile=profile,
        target_state="schedule",
      ) as run:
        date_input = run.page.locator('[data-testid="schedule-date-input"]')
        slot = run.page.locator('[data-testid="slot-button-0900"]')
        sibling = run.page.locator('[data-testid="slot-button-1300"]')

        await date_input.fill("2026-06-16")
        await slot.click()

        assert urlsplit(run.page.url).path == "/schedule"
        assert await date_input.input_value() == "2026-06-16"
        assert await slot.inner_text() == "09:00\nSelected"
        assert await slot.get_attribute("aria-label") is None
        assert await slot.get_attribute("aria-pressed") == (
          expected_aria_pressed
        )
        assert await slot.get_attribute("class") == "slot-button is-selected"
        assert await slot.aria_snapshot() == expected_snapshot
        assert await run.page.get_by_role(
          "button",
          name="09:00 Selected",
          exact=True,
        ).count() == 1
        assert await run.page.locator(
          '[data-testid="summary-slot"]'
        ).inner_text() == "09:00"
        assert await run.page.locator(
          '[data-testid="status-region"]'
        ).inner_text() == "09:00 selected for Consultation."
        continuation = run.page.locator(
          '[data-testid="continue-to-details"]'
        )
        assert await continuation.is_visible()
        assert not await continuation.is_disabled()
        assert await sibling.inner_text() == "13:00\nAvailable"
        assert await sibling.get_attribute("class") == "slot-button"
        assert await sibling.get_attribute("aria-label") is None
        assert await sibling.get_attribute("aria-pressed") is None
        assert await sibling.aria_snapshot() == '- button "13:00 Available"'

        recorder = FocusedRunRecorder(
          run_dir=run_dir,
          app_name="booking-scheduler",
          benchmark_name=f"booking-bs-sem-117-{label}",
          source_script="tests/test_booking_accessgraph_integration.py",
        )
        record = await recorder.capture_page_state(
          run.page,
          FocusedStateSpec(
            benchmark_state_id="BS-S002",
            focused_state_name="schedule-june-16-0900-selected",
            action_path=[
              "select Consultation",
              "continue to Schedule",
              "select June 16",
              "select 09:00",
            ],
            key_validated_selectors=[
              '[data-testid="route-schedule"]',
              '[data-testid="slot-button-0900"]',
              '[data-testid="summary-slot"]',
              '[data-testid="continue-to-details"]',
            ],
          ),
        )
        recorder.write_run_artifacts()

        assert record.state_id == "state_0000"
        assert record.route == "/schedule"

        await continuation.click()
        assert urlsplit(run.page.url).path == "/details"
        assert await run.page.locator(
          '[data-testid="summary-slot"]'
        ).inner_text() == "09:00"

      build = build_semantic_candidates(
        run_dir,
        candidate_types=["aria-state-mismatch"],
      )
      candidates = [
        json.loads(line)
        for line in (
          build.output_dir / "candidates.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if line
      ]
      assert len(candidates) == 2
      target_candidates = [
        candidate
        for candidate in candidates
        if candidate["evidence"]["primary"]["aria_state"]["text"]
        == "09:00 Selected"
      ]
      assert len(target_candidates) == 1
      assert all(
        candidate["evidence"]["primary"]["aria_state"]["text"]
        not in {"13:00 Available", "15:30 Available"}
        for candidate in candidates
      )

      candidate = target_candidates[0]
      aria_state = candidate["evidence"]["primary"]["aria_state"]
      state_context = candidate["evidence"]["supporting"][
        "aria_state_context_v1"
      ]

      assert aria_state["bucket"] == "buttons"
      assert aria_state["text"] == "09:00 Selected"
      assert aria_state["accessible_name"] == "09:00 Selected"
      assert aria_state["state_attributes"] == {
        "aria_pressed": expected_aria_pressed,
      }
      assert state_context["declared_state"] == {
        "aria_pressed": expected_aria_pressed,
      }
      assert state_context["labeling"]["visible_text"] == "09:00 Selected"
      assert state_context["labeling"]["computed_accessible_name"] == (
        "09:00 Selected"
      )
      assert state_context["rendered_state_observations"]["is_visible"] is True
      assert state_context["rendered_state_observations"]["disabled"] is False
      assert 'data-testid="slot-button-0900"' in candidate["evidence"][
        "dom_snippets"
      ][0]["html"]

      score = score_seeded_experiment(
        SeededScorerOptions(
          run_dir=run_dir,
          config_id="booking-bs-sem-117",
          registry_path=REGISTRY,
          score_run_id=f"bs-sem-117-{label}",
        )
      )
      assert score.summary["counts"]["expected_seeds"] == 1
      assert score.summary["counts"]["recovered_seeds"] == expected_recovered
      assert score.summary["counts"]["matched_candidates"] == (
        expected_recovered
      )
      matched_candidates = score.summary["results"][0].get(
        "matched_candidates",
        [],
      )
      assert len(matched_candidates) == expected_recovered
      if expected_recovered:
        assert matched_candidates[0]["candidate_id"] == candidate["candidate_id"]

  _run_async(booking_browser, verify())


def test_bs_sem_135_unselected_slot_exposes_only_seeded_true_state(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    cases = (
      (
        "clean",
        BOOKING_CLEAN_PROFILE,
        None,
        '- button "13:00 Available"',
        0,
      ),
      (
        "seeded",
        "booking-bs-sem-135",
        "true",
        '- button "13:00 Available" [pressed]',
        1,
      ),
    )

    for (
      label,
      profile,
      expected_aria_pressed,
      expected_snapshot,
      expected_recovered,
    ) in cases:
      run_dir = tmp_path / label
      async with open_booking_run(
        browser,
        base_url=booking_spa.base_url,
        profile=profile,
        target_state="schedule",
      ) as run:
        date_input = run.page.locator('[data-testid="schedule-date-input"]')
        selected_slot = run.page.locator('[data-testid="slot-button-0900"]')
        target_slot = run.page.locator('[data-testid="slot-button-1300"]')

        await date_input.fill("2026-06-16")
        await selected_slot.click()

        assert urlsplit(run.page.url).path == "/schedule"
        assert await date_input.input_value() == "2026-06-16"
        assert await selected_slot.inner_text() == "09:00\nSelected"
        assert await selected_slot.get_attribute("aria-pressed") == "true"
        assert await selected_slot.get_attribute("class") == (
          "slot-button is-selected"
        )
        assert await target_slot.inner_text() == "13:00\nAvailable"
        assert await target_slot.get_attribute("aria-label") is None
        assert await target_slot.get_attribute("aria-pressed") == (
          expected_aria_pressed
        )
        assert await target_slot.get_attribute("class") == "slot-button"
        assert await target_slot.aria_snapshot() == expected_snapshot
        assert await run.page.locator(
          '[data-testid="summary-slot"]'
        ).inner_text() == "09:00"
        assert await run.page.locator(
          '[data-testid="status-region"]'
        ).inner_text() == "09:00 selected for Consultation."
        continuation = run.page.locator(
          '[data-testid="continue-to-details"]'
        )
        assert await continuation.is_visible()
        assert not await continuation.is_disabled()

        recorder = FocusedRunRecorder(
          run_dir=run_dir,
          app_name="booking-scheduler",
          benchmark_name=f"booking-bs-sem-135-{label}",
          source_script="tests/test_booking_accessgraph_integration.py",
        )
        record = await recorder.capture_page_state(
          run.page,
          FocusedStateSpec(
            benchmark_state_id="BS-S002",
            focused_state_name="schedule-june-16-0900-selected",
            action_path=[
              "select Consultation",
              "continue to Schedule",
              "select June 16",
              "select 09:00",
            ],
            key_validated_selectors=[
              '[data-testid="route-schedule"]',
              '[data-testid="slot-button-0900"]',
              '[data-testid="slot-button-1300"]',
              '[data-testid="summary-slot"]',
              '[data-testid="continue-to-details"]',
            ],
          ),
        )
        recorder.write_run_artifacts()

        assert record.state_id == "state_0000"
        assert record.route == "/schedule"

        await target_slot.click()
        assert await target_slot.inner_text() == "13:00\nSelected"
        assert await target_slot.get_attribute("class") == (
          "slot-button is-selected"
        )
        assert await selected_slot.inner_text() == "09:00\nAvailable"
        assert await selected_slot.get_attribute("class") == "slot-button"
        assert await selected_slot.get_attribute("aria-pressed") is None
        assert await run.page.locator(
          '[data-testid="summary-slot"]'
        ).inner_text() == "13:00"
        assert await run.page.locator(
          '[data-testid="status-region"]'
        ).inner_text() == "13:00 selected for Consultation."
        await continuation.click()
        assert urlsplit(run.page.url).path == "/details"
        assert await run.page.locator(
          '[data-testid="summary-slot"]'
        ).inner_text() == "13:00"

      candidates = _build_booking_candidates(
        run_dir,
        "aria-state-mismatch",
      )
      target_candidates = [
        candidate
        for candidate in candidates
        if candidate["evidence"]["primary"]["aria_state"]["text"]
        == "13:00 Available"
      ]
      assert len(target_candidates) == expected_recovered

      if target_candidates:
        candidate = target_candidates[0]
        aria_state = candidate["evidence"]["primary"]["aria_state"]
        state_context = candidate["evidence"]["supporting"][
          "aria_state_context_v1"
        ]

        assert aria_state["bucket"] == "buttons"
        assert aria_state["text"] == "13:00 Available"
        assert aria_state["accessible_name"] == "13:00 Available"
        assert aria_state["state_attributes"] == {
          "aria_pressed": "true",
        }
        assert state_context["declared_state"] == {
          "aria_pressed": "true",
        }
        assert state_context["labeling"]["visible_text"] == (
          "13:00 Available"
        )
        assert state_context["labeling"]["computed_accessible_name"] == (
          "13:00 Available"
        )
        assert state_context["rendered_state_observations"][
          "is_visible"
        ] is True
        assert state_context["rendered_state_observations"][
          "disabled"
        ] is False
        assert 'data-testid="slot-button-1300"' in candidate["evidence"][
          "dom_snippets"
        ][0]["html"]

      _, matched_candidates = _score_booking_recovery(
        run_dir,
        config_id="booking-bs-sem-135",
        score_run_id=f"bs-sem-135-{label}",
        expected_recovered=expected_recovered,
        expected_matched_entries=expected_recovered,
      )
      if expected_recovered:
        assert matched_candidates[0]["candidate_id"] == (
          target_candidates[0]["candidate_id"]
        )

  _run_async(booking_browser, verify())


def test_bs_sem_118_review_service_heading_uses_service_scoped_content(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    cases = (
      ("clean", BOOKING_CLEAN_PROFILE, "Service", 1, 0),
      ("seeded", "booking-bs-sem-118", "Date and time", 2, 1),
    )

    for (
      label,
      profile,
      expected_target_name,
      expected_duplicate_count,
      expected_recovered,
    ) in cases:
      run_dir = tmp_path / label
      async with open_booking_run(
        browser,
        base_url=booking_spa.base_url,
        profile=profile,
        target_state="review",
      ) as run:
        service_panel = run.page.locator(
          '[data-testid="review-service-summary"]'
        )
        target_heading = run.page.locator("h3#review-service-heading")
        schedule_panel = run.page.locator(
          '[data-testid="review-schedule-summary"]'
        )
        sibling_heading = run.page.locator("h3#review-schedule-heading")

        assert urlsplit(run.page.url).path == "/review"
        assert await target_heading.evaluate(
          "element => element.tagName"
        ) == "H3"
        assert await target_heading.inner_text() == expected_target_name
        assert await target_heading.aria_snapshot() == (
          f'- heading "{expected_target_name}" [level=3]'
        )
        assert await service_panel.locator(
          '[data-testid="review-service-name"]'
        ).inner_text() == "Consultation"
        assert await service_panel.locator(
          '[data-testid="review-service-duration"]'
        ).inner_text() == "30 minutes"
        change_service = service_panel.locator(
          '[data-testid="change-service"]'
        )
        assert await change_service.inner_text() == "Change service"
        assert await change_service.get_attribute("href") == "/services"

        assert await sibling_heading.evaluate(
          "element => element.tagName"
        ) == "H3"
        assert await sibling_heading.inner_text() == "Date and time"
        assert await sibling_heading.aria_snapshot() == (
          '- heading "Date and time" [level=3]'
        )
        assert await schedule_panel.locator(
          '[data-testid="review-date"]'
        ).inner_text() == "June 16, 2026"
        assert await schedule_panel.locator(
          '[data-testid="review-slot"]'
        ).inner_text() == "09:00"
        change_appointment = schedule_panel.locator(
          '[data-testid="change-appointment"]'
        )
        assert await change_appointment.inner_text() == "Change appointment"
        assert await change_appointment.get_attribute("href") == "/schedule"

        assert await run.page.get_by_role(
          "heading",
          name="Date and time",
          level=3,
          exact=True,
        ).count() == expected_duplicate_count

        recorder = FocusedRunRecorder(
          run_dir=run_dir,
          app_name="booking-scheduler",
          benchmark_name=f"booking-bs-sem-118-{label}",
          source_script="tests/test_booking_accessgraph_integration.py",
        )
        record = await recorder.capture_page_state(
          run.page,
          FocusedStateSpec(
            benchmark_state_id="BS-S004",
            focused_state_name="review",
            action_path=[
              "select Consultation",
              "select June 16 at 09:00",
              "enter valid customer details",
              "continue to Review",
            ],
            key_validated_selectors=[
              '[data-testid="route-review"]',
              '[data-testid="review-service-summary"]',
              "h3#review-service-heading",
              '[data-testid="review-schedule-summary"]',
              "h3#review-schedule-heading",
            ],
          ),
        )
        recorder.write_run_artifacts()

        assert record.state_id == "state_0000"
        assert record.route == "/review"

      build = build_semantic_candidates(
        run_dir,
        candidate_types=["heading-not-descriptive"],
      )
      candidates = [
        json.loads(line)
        for line in (
          build.output_dir / "candidates.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if line
      ]
      assert len(candidates) == 8

      candidates_by_selector = {
        candidate["evidence"]["primary"]["heading"]["selector"]: candidate
        for candidate in candidates
      }
      target_candidate = candidates_by_selector["h3#review-service-heading"]
      sibling_candidate = candidates_by_selector[
        "h3#review-schedule-heading"
      ]
      target_heading_evidence = target_candidate["evidence"]["primary"][
        "heading"
      ]
      target_supporting = target_candidate["evidence"]["supporting"]
      sibling_heading_evidence = sibling_candidate["evidence"]["primary"][
        "heading"
      ]
      sibling_supporting = sibling_candidate["evidence"]["supporting"]

      assert target_heading_evidence == {
        "element_id": target_heading_evidence["element_id"],
        "tag": "h3",
        "role": None,
        "selector": "h3#review-service-heading",
        "text": expected_target_name,
        "level": 3,
        "accessible_name": expected_target_name,
      }
      assert target_supporting["context"] == {
        "nearby_text": "NameConsultationDuration30 minutes",
        "parent_text": (
          f"{expected_target_name}NameConsultationDuration30 minutes"
          "Change service"
        ),
        "section_heading": expected_target_name,
      }
      assert target_supporting["heading_scoped_content"] == {
        "schema_version": "heading_scoped_content_v1",
        "source": "labelledby_landmark_text_sample",
        "source_element_ref": {
          "bucket": "landmarks",
          "element_id": target_supporting["heading_scoped_content"][
            "source_element_ref"
          ]["element_id"],
          "selector": "section:nth-of-type(1)",
          "tag": "section",
        },
        "text_excerpt": (
          f"{expected_target_name} Name Consultation Duration 30 minutes "
          "Change service"
        ),
        "truncated": False,
      }

      assert sibling_heading_evidence["text"] == "Date and time"
      assert sibling_heading_evidence["accessible_name"] == "Date and time"
      assert sibling_supporting["context"] == {
        "nearby_text": "DateJune 16, 2026Time09:00",
        "parent_text": (
          "Date and timeDateJune 16, 2026Time09:00Change appointment"
        ),
        "section_heading": "Date and time",
      }
      assert sibling_supporting["heading_scoped_content"]["text_excerpt"] == (
        "Date and time Date June 16, 2026 Time 09:00 Change appointment"
      )

      score = score_seeded_experiment(
        SeededScorerOptions(
          run_dir=run_dir,
          config_id="booking-bs-sem-118",
          registry_path=REGISTRY,
          score_run_id=f"bs-sem-118-{label}",
        )
      )
      assert score.summary["counts"]["expected_seeds"] == 1
      assert score.summary["counts"]["recovered_seeds"] == expected_recovered
      assert score.summary["counts"]["matched_candidates"] == (
        expected_recovered
      )
      matched_candidates = score.summary["results"][0].get(
        "matched_candidates",
        [],
      )
      assert len(matched_candidates) == expected_recovered
      if expected_recovered:
        assert matched_candidates[0]["candidate_id"] == (
          target_candidate["candidate_id"]
        )
        assert matched_candidates[0]["candidate_id"] != (
          sibling_candidate["candidate_id"]
        )

  _run_async(booking_browser, verify())


def test_bs_sem_119_phone_required_error_uses_associated_message_evidence(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    seeded_message = (
      "Choose a date and available time before entering booking details."
    )
    cases = (
      ("clean", BOOKING_CLEAN_PROFILE, "Phone is required.", 0),
      ("seeded", "booking-bs-sem-119", seeded_message, 1),
    )

    for label, profile, expected_message, expected_recovered in cases:
      run_dir = tmp_path / label
      async with open_booking_run(
        browser,
        base_url=booking_spa.base_url,
        profile=profile,
        target_state="details",
      ) as run:
        full_name = run.page.locator('[data-testid="details-full-name"]')
        email = run.page.locator('[data-testid="details-email"]')
        phone = run.page.locator('[data-testid="details-phone"]')
        phone_error = run.page.locator('[data-testid="details-phone-error"]')
        submit = run.page.locator('[data-testid="details-submit"]')

        assert urlsplit(run.page.url).path == "/details"
        assert await run.page.title() == (
          "Booking details | Booking Scheduler Benchmark"
        )
        await full_name.fill("Jordan Lee")
        await email.fill("jordan.lee@example.test")

        assert await phone.input_value() == ""
        assert await phone.get_attribute("id") == "details-phone"
        assert await phone.get_attribute("name") == "phone"
        assert await phone.get_attribute("type") == "tel"
        assert await phone.get_attribute("autocomplete") == "tel"
        assert await phone.evaluate("element => element.required") is True
        assert await phone.evaluate(
          "element => ({"
          " valid: element.validity.valid,"
          " valueMissing: element.validity.valueMissing"
          "})"
        ) == {"valid": False, "valueMissing": True}

        await submit.click()

        assert urlsplit(run.page.url).path == "/details"
        await run.page.wait_for_function(
          "document.activeElement?.id === 'details-phone'"
        )
        assert await phone.evaluate(
          "element => document.activeElement === element"
        ) is True
        assert await phone.get_attribute("aria-invalid") == "true"
        assert await phone.get_attribute("aria-describedby") == (
          "details-phone-error"
        )
        assert await phone_error.get_attribute("id") == "details-phone-error"
        assert await phone_error.inner_text() == expected_message
        assert await full_name.input_value() == "Jordan Lee"
        assert await email.input_value() == "jordan.lee@example.test"
        assert await full_name.get_attribute("aria-invalid") is None
        assert await email.get_attribute("aria-invalid") is None
        assert await run.page.locator(
          '[data-testid="details-full-name-error"]'
        ).count() == 0
        assert await run.page.locator(
          '[data-testid="details-email-error"]'
        ).count() == 0
        assert await run.page.locator(".field-error").count() == 1

        recorder = FocusedRunRecorder(
          run_dir=run_dir,
          app_name="booking-scheduler",
          benchmark_name=f"booking-bs-sem-119-{label}",
          source_script="tests/test_booking_accessgraph_integration.py",
        )
        record = await recorder.capture_page_state(
          run.page,
          FocusedStateSpec(
            benchmark_state_id="BS-S003",
            focused_state_name="details-phone-required-error",
            action_path=[
              "select Consultation",
              "select June 16 at 09:00",
              "enter valid Full name and Email",
              "leave Phone empty",
              "submit Booking details",
            ],
            key_validated_selectors=[
              '[data-testid="route-details"]',
              '[data-testid="details-form"]',
              "input#details-phone",
              "p#details-phone-error",
            ],
          ),
        )
        recorder.write_run_artifacts()

        assert record.state_id == "state_0000"
        assert record.route == "/details"

        await phone.fill("555-0134")
        assert await phone.get_attribute("aria-invalid") is None
        assert await phone.get_attribute("aria-describedby") is None
        assert await phone_error.count() == 0
        assert await run.page.locator(
          '[data-testid="details-validation-status"]'
        ).count() == 0

        await submit.click()
        await run.page.wait_for_url("**/review")
        assert urlsplit(run.page.url).path == "/review"
        assert await run.page.locator(
          '[data-testid="review-customer-full-name"]'
        ).inner_text() == "Jordan Lee"
        assert await run.page.locator(
          '[data-testid="review-customer-email"]'
        ).inner_text() == "jordan.lee@example.test"
        assert await run.page.locator(
          '[data-testid="review-customer-phone"]'
        ).inner_text() == "555-0134"

      build = build_semantic_candidates(
        run_dir,
        candidate_types=["error-message-mismatch"],
      )
      candidates = [
        json.loads(line)
        for line in (
          build.output_dir / "candidates.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        if line and "invalid_form_control_with_associated_message_evidence" in json.loads(line)["selection_reason"]  # W4A round 3: the field's own-message candidate
      ]
      assert len(candidates) == 1

      candidate = candidates[0]
      primary = candidate["evidence"]["primary"]
      supporting = candidate["evidence"]["supporting"]
      control = primary["form_control"]
      error_message = primary["error_message"]
      error_context = supporting["error_message_context_v1"]

      assert candidate["candidate_type"] == "error-message-mismatch"
      assert candidate["state_id"] == "state_0000"
      assert candidate["state_context"]["url"].endswith("/details")
      assert control["selector"] == "input#details-phone"
      assert control["id"] == "details-phone"
      assert control["name"] == "phone"
      assert control["type"] == "tel"
      assert control["autocomplete"] == "tel"
      assert control["required"] is True
      assert control["has_value"] is False
      assert control["invalid"] is True
      assert control["aria_invalid"] == "true"
      assert control["aria_describedby"] == "details-phone-error"
      assert "Phone" in control["label"]
      assert "Phone" in control["accessible_name"]
      assert control["native_validity"]["valid"] is False
      assert control["native_validity"]["value_missing"] is True
      assert error_message == {
        "element_id": error_message["element_id"],
        "selector": "p#details-phone-error",
        "text": expected_message,
        "relationship_type": "describes",
        "method": "aria-describedby",
      }
      assert error_context["control"]["selector"] == "input#details-phone"
      assert error_context["control"]["value_state"] == "empty"
      assert error_context["associated_error_messages"] == [error_message]
      assert supporting["parent_form"]["selector"] == "form:nth-of-type(1)"

      score = score_seeded_experiment(
        SeededScorerOptions(
          run_dir=run_dir,
          config_id="booking-bs-sem-119",
          registry_path=REGISTRY,
          score_run_id=f"bs-sem-119-{label}",
        )
      )
      assert score.summary["counts"]["expected_seeds"] == 1
      assert score.summary["counts"]["recovered_seeds"] == expected_recovered
      assert score.summary["counts"]["matched_candidates"] == (
        2 if expected_recovered else 0
      )
      matched_candidates = score.summary["results"][0].get(
        "matched_candidates",
        [],
      )
      matched_candidate_ids = {
        match["candidate_id"]
        for match in matched_candidates
      }
      assert len(matched_candidate_ids) == expected_recovered
      if expected_recovered:
        assert matched_candidate_ids == {candidate["candidate_id"]}

  _run_async(booking_browser, verify())


def test_bs_sem_138_full_name_required_error_uses_associated_message_evidence(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    cases = (
      ("clean", BOOKING_CLEAN_PROFILE, "Full name is required.", 0),
      ("seeded", "booking-bs-sem-138", "Email is required.", 1),
    )

    for label, profile, expected_message, expected_recovered in cases:
      run_dir = tmp_path / label
      async with open_booking_run(
        browser,
        base_url=booking_spa.base_url,
        profile=profile,
        target_state="details",
      ) as run:
        full_name = run.page.locator('[data-testid="details-full-name"]')
        email = run.page.locator('[data-testid="details-email"]')
        phone = run.page.locator('[data-testid="details-phone"]')
        full_name_error = run.page.locator(
          '[data-testid="details-full-name-error"]'
        )
        submit = run.page.locator('[data-testid="details-submit"]')

        assert urlsplit(run.page.url).path == "/details"
        assert await run.page.title() == (
          "Booking details | Booking Scheduler Benchmark"
        )
        await email.fill("jordan.lee@example.test")
        await phone.fill("555-0134")

        assert await full_name.input_value() == ""
        assert await full_name.get_attribute("id") == "details-fullName"
        assert await full_name.get_attribute("name") == "fullName"
        assert await full_name.get_attribute("type") == "text"
        assert await full_name.get_attribute("autocomplete") == "name"
        assert await full_name.evaluate("element => element.required") is True
        assert await full_name.evaluate(
          "element => ({"
          " valid: element.validity.valid,"
          " valueMissing: element.validity.valueMissing"
          "})"
        ) == {"valid": False, "valueMissing": True}
        assert await email.input_value() == "jordan.lee@example.test"
        assert await email.evaluate(
          "element => ({"
          " valid: element.validity.valid,"
          " valueMissing: element.validity.valueMissing,"
          " typeMismatch: element.validity.typeMismatch"
          "})"
        ) == {
          "valid": True,
          "valueMissing": False,
          "typeMismatch": False,
        }
        assert await phone.input_value() == "555-0134"
        assert await phone.evaluate(
          "element => element.validity.valid"
        ) is True

        await submit.click()

        assert urlsplit(run.page.url).path == "/details"
        await run.page.wait_for_function(
          "document.activeElement?.id === 'details-fullName'"
        )
        assert await full_name.evaluate(
          "element => document.activeElement === element"
        ) is True
        assert await full_name.get_attribute("aria-invalid") == "true"
        assert await full_name.get_attribute("aria-describedby") == (
          "details-fullName-error"
        )
        assert await full_name_error.get_attribute("id") == (
          "details-fullName-error"
        )
        assert await full_name_error.inner_text() == expected_message
        assert await email.input_value() == "jordan.lee@example.test"
        assert await phone.input_value() == "555-0134"
        assert await email.get_attribute("aria-invalid") is None
        assert await phone.get_attribute("aria-invalid") is None
        assert await run.page.locator(
          '[data-testid="details-email-error"]'
        ).count() == 0
        assert await run.page.locator(
          '[data-testid="details-phone-error"]'
        ).count() == 0
        assert await run.page.locator(".field-error").count() == 1

        recorder = FocusedRunRecorder(
          run_dir=run_dir,
          app_name="booking-scheduler",
          benchmark_name=f"booking-bs-sem-138-{label}",
          source_script="tests/test_booking_accessgraph_integration.py",
        )
        record = await recorder.capture_page_state(
          run.page,
          FocusedStateSpec(
            benchmark_state_id="BS-S003",
            focused_state_name="details-full-name-required-error",
            action_path=[
              "select Consultation",
              "select June 16 at 09:00",
              "enter valid Email and Phone",
              "leave Full name empty",
              "submit Booking details",
            ],
            key_validated_selectors=[
              '[data-testid="route-details"]',
              '[data-testid="details-form"]',
              "input#details-fullName",
              "p#details-fullName-error",
            ],
          ),
        )
        recorder.write_run_artifacts()

        assert record.state_id == "state_0000"
        assert record.route == "/details"

        await full_name.fill("Jordan Lee")
        assert await full_name.get_attribute("aria-invalid") is None
        assert await full_name.get_attribute("aria-describedby") is None
        assert await full_name_error.count() == 0
        assert await run.page.locator(
          '[data-testid="details-validation-status"]'
        ).count() == 0

        await submit.click()
        await run.page.wait_for_url("**/review")
        assert urlsplit(run.page.url).path == "/review"
        assert await run.page.locator(
          '[data-testid="review-customer-full-name"]'
        ).inner_text() == "Jordan Lee"
        assert await run.page.locator(
          '[data-testid="review-customer-email"]'
        ).inner_text() == "jordan.lee@example.test"
        assert await run.page.locator(
          '[data-testid="review-customer-phone"]'
        ).inner_text() == "555-0134"

      candidates = [  # W4A round 3: the field's own-message candidate (summaries and icon-only errors are separate)
        c for c in _build_booking_candidates(run_dir, "error-message-mismatch")
        if "invalid_form_control_with_associated_message_evidence" in c["selection_reason"]
      ]
      assert len(candidates) == 1

      candidate = candidates[0]
      primary = candidate["evidence"]["primary"]
      supporting = candidate["evidence"]["supporting"]
      control = primary["form_control"]
      error_message = primary["error_message"]
      error_context = supporting["error_message_context_v1"]

      assert candidate["candidate_type"] == "error-message-mismatch"
      assert candidate["state_id"] == "state_0000"
      assert candidate["state_context"]["url"].endswith("/details")
      assert control["selector"] == "input#details-fullName"
      assert control["id"] == "details-fullName"
      assert control["name"] == "fullName"
      assert control["type"] == "text"
      assert control["autocomplete"] == "name"
      assert control["required"] is True
      assert control["has_value"] is False
      assert control["invalid"] is True
      assert control["aria_invalid"] == "true"
      assert control["aria_describedby"] == "details-fullName-error"
      assert "Full name" in control["label"]
      assert "Full name" in control["accessible_name"]
      assert control["native_validity"]["valid"] is False
      assert control["native_validity"]["value_missing"] is True
      assert error_message == {
        "element_id": error_message["element_id"],
        "selector": "p#details-fullName-error",
        "text": expected_message,
        "relationship_type": "describes",
        "method": "aria-describedby",
      }
      assert error_context["control"]["selector"] == (
        "input#details-fullName"
      )
      assert error_context["control"]["value_state"] == "empty"
      assert error_context["associated_error_messages"] == [error_message]
      assert supporting["parent_form"]["selector"] == "form:nth-of-type(1)"

      _, matched_candidates = _score_booking_recovery(
        run_dir,
        config_id="booking-bs-sem-138",
        score_run_id=f"bs-sem-138-{label}",
        expected_recovered=expected_recovered,
        expected_matched_entries=(2 if expected_recovered else 0),
      )
      matched_candidate_ids = {
        match["candidate_id"]
        for match in matched_candidates
      }
      assert len(matched_candidate_ids) == expected_recovered
      if expected_recovered:
        assert matched_candidate_ids == {candidate["candidate_id"]}

  _run_async(booking_browser, verify())


def test_bs_sem_139_empty_email_required_error_uses_associated_format_message_evidence(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    cases = (
      ("clean", BOOKING_CLEAN_PROFILE, "Email is required.", 0),
      ("seeded", "booking-bs-sem-139", "Email format is invalid.", 1),
    )

    for label, profile, expected_message, expected_recovered in cases:
      run_dir = tmp_path / label
      async with open_booking_run(
        browser,
        base_url=booking_spa.base_url,
        profile=profile,
        target_state="details",
      ) as run:
        full_name = run.page.locator('[data-testid="details-full-name"]')
        email = run.page.locator('[data-testid="details-email"]')
        phone = run.page.locator('[data-testid="details-phone"]')
        email_error = run.page.locator('[data-testid="details-email-error"]')
        submit = run.page.locator('[data-testid="details-submit"]')

        assert urlsplit(run.page.url).path == "/details"
        assert await run.page.title() == (
          "Booking details | Booking Scheduler Benchmark"
        )
        await full_name.fill("Jordan Lee")
        await phone.fill("555-0134")

        assert await email.input_value() == ""
        assert await email.get_attribute("id") == "details-email"
        assert await email.get_attribute("name") == "email"
        assert await email.get_attribute("type") == "email"
        assert await email.get_attribute("autocomplete") == "email"
        assert await email.evaluate("element => element.required") is True
        assert await email.evaluate(
          "element => ({"
          " valid: element.validity.valid,"
          " valueMissing: element.validity.valueMissing,"
          " typeMismatch: element.validity.typeMismatch"
          "})"
        ) == {
          "valid": False,
          "valueMissing": True,
          "typeMismatch": False,
        }
        assert await full_name.input_value() == "Jordan Lee"
        assert await full_name.evaluate(
          "element => element.validity.valid"
        ) is True
        assert await phone.input_value() == "555-0134"
        assert await phone.evaluate(
          "element => element.validity.valid"
        ) is True

        await submit.click()

        assert urlsplit(run.page.url).path == "/details"
        await run.page.wait_for_function(
          "document.activeElement?.id === 'details-email'"
        )
        assert await email.evaluate(
          "element => document.activeElement === element"
        ) is True
        assert await email.get_attribute("aria-invalid") == "true"
        assert await email.get_attribute("aria-describedby") == (
          "details-email-error"
        )
        assert await email_error.get_attribute("id") == "details-email-error"
        assert await email_error.inner_text() == expected_message
        assert await full_name.input_value() == "Jordan Lee"
        assert await phone.input_value() == "555-0134"
        assert await full_name.get_attribute("aria-invalid") is None
        assert await phone.get_attribute("aria-invalid") is None
        assert await run.page.locator(
          '[data-testid="details-full-name-error"]'
        ).count() == 0
        assert await run.page.locator(
          '[data-testid="details-phone-error"]'
        ).count() == 0
        assert await run.page.locator(".field-error").count() == 1

        recorder = FocusedRunRecorder(
          run_dir=run_dir,
          app_name="booking-scheduler",
          benchmark_name=f"booking-bs-sem-139-{label}",
          source_script="tests/test_booking_accessgraph_integration.py",
        )
        record = await recorder.capture_page_state(
          run.page,
          FocusedStateSpec(
            benchmark_state_id="BS-S003",
            focused_state_name="details-email-required-error",
            action_path=[
              "select Consultation",
              "select June 16 at 09:00",
              "enter valid Full name and Phone",
              "leave Email empty",
              "submit Booking details",
            ],
            key_validated_selectors=[
              '[data-testid="route-details"]',
              '[data-testid="details-form"]',
              "input#details-email",
              "p#details-email-error",
            ],
          ),
        )
        recorder.write_run_artifacts()

        assert record.state_id == "state_0000"
        assert record.route == "/details"

        await email.fill("jordan.lee@example.test")
        assert await email.get_attribute("aria-invalid") is None
        assert await email.get_attribute("aria-describedby") is None
        assert await email_error.count() == 0
        assert await run.page.locator(
          '[data-testid="details-validation-status"]'
        ).count() == 0

        await submit.click()
        await run.page.wait_for_url("**/review")
        assert urlsplit(run.page.url).path == "/review"
        assert await run.page.locator(
          '[data-testid="review-customer-full-name"]'
        ).inner_text() == "Jordan Lee"
        assert await run.page.locator(
          '[data-testid="review-customer-email"]'
        ).inner_text() == "jordan.lee@example.test"
        assert await run.page.locator(
          '[data-testid="review-customer-phone"]'
        ).inner_text() == "555-0134"

      candidates = [  # W4A round 3: the field's own-message candidate (summaries and icon-only errors are separate)
        c for c in _build_booking_candidates(run_dir, "error-message-mismatch")
        if "invalid_form_control_with_associated_message_evidence" in c["selection_reason"]
      ]
      assert len(candidates) == 1

      candidate = candidates[0]
      primary = candidate["evidence"]["primary"]
      supporting = candidate["evidence"]["supporting"]
      control = primary["form_control"]
      error_message = primary["error_message"]
      error_context = supporting["error_message_context_v1"]

      assert candidate["candidate_type"] == "error-message-mismatch"
      assert candidate["state_id"] == "state_0000"
      assert candidate["state_context"]["url"].endswith("/details")
      assert control["selector"] == "input#details-email"
      assert control["id"] == "details-email"
      assert control["name"] == "email"
      assert control["type"] == "email"
      assert control["autocomplete"] == "email"
      assert control["required"] is True
      assert control["has_value"] is False
      assert control["invalid"] is True
      assert control["aria_invalid"] == "true"
      assert control["aria_describedby"] == "details-email-error"
      assert "Email" in control["label"]
      assert "Email" in control["accessible_name"]
      assert control["native_validity"]["valid"] is False
      assert control["native_validity"]["value_missing"] is True
      assert control["native_validity"]["type_mismatch"] is False
      assert error_message == {
        "element_id": error_message["element_id"],
        "selector": "p#details-email-error",
        "text": expected_message,
        "relationship_type": "describes",
        "method": "aria-describedby",
      }
      assert error_context["control"]["selector"] == "input#details-email"
      assert error_context["control"]["value_state"] == "empty"
      assert error_context["control"]["native_validity"]["valid"] is False
      assert error_context["control"]["native_validity"][
        "value_missing"
      ] is True
      assert error_context["control"]["native_validity"][
        "type_mismatch"
      ] is False
      assert error_context["associated_error_messages"] == [error_message]
      assert supporting["parent_form"]["selector"] == "form:nth-of-type(1)"

      _, matched_candidates = _score_booking_recovery(
        run_dir,
        config_id="booking-bs-sem-139",
        score_run_id=f"bs-sem-139-{label}",
        expected_recovered=expected_recovered,
        expected_matched_entries=(2 if expected_recovered else 0),
      )
      matched_candidate_ids = {
        match["candidate_id"]
        for match in matched_candidates
      }
      assert len(matched_candidate_ids) == expected_recovered
      if expected_recovered:
        assert matched_candidate_ids == {candidate["candidate_id"]}

  _run_async(booking_browser, verify())


def test_bs_sem_140_empty_phone_required_error_uses_associated_optional_message_evidence(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    cases = (
      ("clean", BOOKING_CLEAN_PROFILE, "Phone is required.", 0),
      ("seeded", "booking-bs-sem-140", "Phone is optional.", 1),
    )

    for label, profile, expected_message, expected_recovered in cases:
      run_dir = tmp_path / label
      async with open_booking_run(
        browser,
        base_url=booking_spa.base_url,
        profile=profile,
        target_state="details",
      ) as run:
        full_name = run.page.locator('[data-testid="details-full-name"]')
        email = run.page.locator('[data-testid="details-email"]')
        phone = run.page.locator('[data-testid="details-phone"]')
        phone_error = run.page.locator('[data-testid="details-phone-error"]')
        submit = run.page.locator('[data-testid="details-submit"]')

        assert urlsplit(run.page.url).path == "/details"
        assert await run.page.title() == (
          "Booking details | Booking Scheduler Benchmark"
        )
        await full_name.fill("Jordan Lee")
        await email.fill("jordan.lee@example.test")

        assert await phone.input_value() == ""
        assert await phone.get_attribute("id") == "details-phone"
        assert await phone.get_attribute("name") == "phone"
        assert await phone.get_attribute("type") == "tel"
        assert await phone.get_attribute("autocomplete") == "tel"
        assert await phone.evaluate("element => element.required") is True
        assert await phone.evaluate(
          "element => ({"
          " valid: element.validity.valid,"
          " valueMissing: element.validity.valueMissing,"
          " typeMismatch: element.validity.typeMismatch"
          "})"
        ) == {
          "valid": False,
          "valueMissing": True,
          "typeMismatch": False,
        }
        assert await full_name.input_value() == "Jordan Lee"
        assert await full_name.evaluate(
          "element => element.validity.valid"
        ) is True
        assert await email.input_value() == "jordan.lee@example.test"
        assert await email.evaluate(
          "element => ({"
          " valid: element.validity.valid,"
          " valueMissing: element.validity.valueMissing,"
          " typeMismatch: element.validity.typeMismatch"
          "})"
        ) == {
          "valid": True,
          "valueMissing": False,
          "typeMismatch": False,
        }

        await submit.click()

        assert urlsplit(run.page.url).path == "/details"
        await run.page.wait_for_function(
          "document.activeElement?.id === 'details-phone'"
        )
        assert await phone.evaluate(
          "element => document.activeElement === element"
        ) is True
        assert await phone.get_attribute("aria-invalid") == "true"
        assert await phone.get_attribute("aria-describedby") == (
          "details-phone-error"
        )
        assert await phone_error.get_attribute("id") == "details-phone-error"
        assert await phone_error.inner_text() == expected_message
        assert await full_name.input_value() == "Jordan Lee"
        assert await email.input_value() == "jordan.lee@example.test"
        assert await full_name.get_attribute("aria-invalid") is None
        assert await email.get_attribute("aria-invalid") is None
        assert await run.page.locator(
          '[data-testid="details-full-name-error"]'
        ).count() == 0
        assert await run.page.locator(
          '[data-testid="details-email-error"]'
        ).count() == 0
        assert await run.page.locator(".field-error").count() == 1

        recorder = FocusedRunRecorder(
          run_dir=run_dir,
          app_name="booking-scheduler",
          benchmark_name=f"booking-bs-sem-140-{label}",
          source_script="tests/test_booking_accessgraph_integration.py",
        )
        record = await recorder.capture_page_state(
          run.page,
          FocusedStateSpec(
            benchmark_state_id="BS-S003",
            focused_state_name="details-phone-required-error",
            action_path=[
              "select Consultation",
              "select June 16 at 09:00",
              "enter valid Full name and Email",
              "leave Phone empty",
              "submit Booking details",
            ],
            key_validated_selectors=[
              '[data-testid="route-details"]',
              '[data-testid="details-form"]',
              "input#details-phone",
              "p#details-phone-error",
            ],
          ),
        )
        recorder.write_run_artifacts()

        assert record.state_id == "state_0000"
        assert record.route == "/details"

        await phone.fill("555-0134")
        assert await phone.get_attribute("aria-invalid") is None
        assert await phone.get_attribute("aria-describedby") is None
        assert await phone_error.count() == 0
        assert await run.page.locator(
          '[data-testid="details-validation-status"]'
        ).count() == 0

        await submit.click()
        await run.page.wait_for_url("**/review")
        assert urlsplit(run.page.url).path == "/review"
        assert await run.page.locator(
          '[data-testid="review-customer-full-name"]'
        ).inner_text() == "Jordan Lee"
        assert await run.page.locator(
          '[data-testid="review-customer-email"]'
        ).inner_text() == "jordan.lee@example.test"
        assert await run.page.locator(
          '[data-testid="review-customer-phone"]'
        ).inner_text() == "555-0134"

      candidates = [  # W4A round 3: the field's own-message candidate (summaries and icon-only errors are separate)
        c for c in _build_booking_candidates(run_dir, "error-message-mismatch")
        if "invalid_form_control_with_associated_message_evidence" in c["selection_reason"]
      ]
      assert len(candidates) == 1

      candidate = candidates[0]
      primary = candidate["evidence"]["primary"]
      supporting = candidate["evidence"]["supporting"]
      control = primary["form_control"]
      error_message = primary["error_message"]
      error_context = supporting["error_message_context_v1"]

      assert candidate["candidate_type"] == "error-message-mismatch"
      assert candidate["state_id"] == "state_0000"
      assert candidate["state_context"]["url"].endswith("/details")
      assert control["selector"] == "input#details-phone"
      assert control["id"] == "details-phone"
      assert control["name"] == "phone"
      assert control["type"] == "tel"
      assert control["autocomplete"] == "tel"
      assert control["required"] is True
      assert control["has_value"] is False
      assert control["invalid"] is True
      assert control["aria_invalid"] == "true"
      assert control["aria_describedby"] == "details-phone-error"
      assert "Phone" in control["label"]
      assert "Phone" in control["accessible_name"]
      assert control["native_validity"]["valid"] is False
      assert control["native_validity"]["value_missing"] is True
      assert control["native_validity"]["type_mismatch"] is False
      assert error_message == {
        "element_id": error_message["element_id"],
        "selector": "p#details-phone-error",
        "text": expected_message,
        "relationship_type": "describes",
        "method": "aria-describedby",
      }
      assert error_context["control"]["selector"] == "input#details-phone"
      assert error_context["control"]["value_state"] == "empty"
      assert error_context["control"]["native_validity"]["valid"] is False
      assert error_context["control"]["native_validity"][
        "value_missing"
      ] is True
      assert error_context["control"]["native_validity"][
        "type_mismatch"
      ] is False
      assert error_context["associated_error_messages"] == [error_message]
      assert supporting["parent_form"]["selector"] == "form:nth-of-type(1)"

      _, matched_candidates = _score_booking_recovery(
        run_dir,
        config_id="booking-bs-sem-140",
        score_run_id=f"bs-sem-140-{label}",
        expected_recovered=expected_recovered,
        expected_matched_entries=(2 if expected_recovered else 0),
      )
      matched_candidate_ids = {
        match["candidate_id"]
        for match in matched_candidates
      }
      assert len(matched_candidate_ids) == expected_recovered
      if expected_recovered:
        assert matched_candidate_ids == {candidate["candidate_id"]}

  _run_async(booking_browser, verify())


def test_bs_sem_129_phone_native_label_changes_to_email_with_telephone_purpose_preserved(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    cases = (
      ("clean", BOOKING_CLEAN_PROFILE, "Phone", 0),
      ("seeded", "booking-bs-sem-129", "Email", 1),
    )

    for label, profile, expected_label_text, expected_recovered in cases:
      run_dir = tmp_path / label
      async with open_booking_run(
        browser,
        base_url=booking_spa.base_url,
        profile=profile,
        target_state="details",
      ) as run:
        full_name = run.page.locator('[data-testid="details-full-name"]')
        email = run.page.locator('[data-testid="details-email"]')
        phone = run.page.locator('[data-testid="details-phone"]')
        phone_label = run.page.locator('label[for="details-phone"]')
        submit = run.page.locator('[data-testid="details-submit"]')

        assert urlsplit(run.page.url).path == "/details"
        assert await run.page.title() == (
          "Booking details | Booking Scheduler Benchmark"
        )
        assert await phone_label.locator("span").all_inner_texts() == [
          expected_label_text,
          "REQUIRED",
        ]
        assert await phone.get_attribute("id") == "details-phone"
        assert await phone.get_attribute("name") == "phone"
        assert await phone.get_attribute("type") == "tel"
        assert await phone.get_attribute("autocomplete") == "tel"
        assert await phone.get_attribute("aria-label") is None
        assert await phone.get_attribute("aria-labelledby") is None
        assert await phone.get_attribute("aria-describedby") is None
        assert await phone.evaluate("element => element.required") is True
        assert await phone.input_value() == ""
        assert await phone.aria_snapshot() == (
          f'- textbox "{expected_label_text} Required"'
        )
        assert await run.page.locator(
          'label[for="details-email"] span:first-child'
        ).inner_text() == "Email"
        assert await email.aria_snapshot() == '- textbox "Email Required"'
        assert await full_name.aria_snapshot() == (
          '- textbox "Full name Required"'
        )

        recorder = FocusedRunRecorder(
          run_dir=run_dir,
          app_name="booking-scheduler",
          benchmark_name=f"booking-bs-sem-129-{label}",
          source_script="tests/test_booking_accessgraph_integration.py",
        )
        record = await recorder.capture_page_state(
          run.page,
          FocusedStateSpec(
            benchmark_state_id="BS-S003",
            focused_state_name="details-phone-label",
            action_path=[
              "select Consultation",
              "select June 16 at 09:00",
              "open Booking details",
            ],
            key_validated_selectors=[
              '[data-testid="route-details"]',
              '[data-testid="details-form"]',
              'label[for="details-phone"]',
              "input#details-phone",
            ],
          ),
        )
        recorder.write_run_artifacts()

        assert record.state_id == "state_0000"
        assert record.route == "/details"

        await full_name.fill("Jordan Lee")
        await email.fill("jordan.lee@example.test")
        await phone.fill("555-0134")
        await submit.click()
        await run.page.wait_for_url("**/review")
        assert urlsplit(run.page.url).path == "/review"
        assert await run.page.locator(
          '[data-testid="review-customer-full-name"]'
        ).inner_text() == "Jordan Lee"
        assert await run.page.locator(
          '[data-testid="review-customer-email"]'
        ).inner_text() == "jordan.lee@example.test"
        assert await run.page.locator(
          '[data-testid="review-customer-phone"]'
        ).inner_text() == "555-0134"

      candidates = _build_booking_candidates(
        run_dir,
        "form-label-mismatch",
      )
      assert len(candidates) == 5

      candidate = next(
        item
        for item in candidates
        if item["evidence"]["primary"]["form_control"]["selector"]
        == "input#details-phone"
      )
      control = candidate["evidence"]["primary"]["form_control"]
      supporting = candidate["evidence"]["supporting"]
      label_context = supporting["form_label_context_v1"]
      expected_compact_label = f"{expected_label_text}Required"
      expected_visible_label = f"{expected_label_text} REQUIRED"

      assert candidate["candidate_type"] == "form-label-mismatch"
      assert candidate["state_id"] == "state_0000"
      assert candidate["state_context"]["url"].endswith("/details")
      assert control["selector"] == "input#details-phone"
      assert control["id"] == "details-phone"
      assert control["name"] == "phone"
      assert control["type"] == "tel"
      assert control["autocomplete"] == "tel"
      assert control["required"] is True
      assert control["has_value"] is False
      assert control["aria_label"] is None
      assert control["aria_labelledby"] is None
      assert control["label"] == expected_compact_label
      assert control["accessible_name"] == expected_compact_label
      assert label_context["control"]["selector"] == "input#details-phone"
      assert label_context["control"]["value_state"] == "empty"
      assert label_context["labeling"]["visible_label"] == (
        expected_visible_label
      )
      assert label_context["labeling"]["computed_accessible_name"] == (
        expected_compact_label
      )
      assert label_context["labeling"]["label_sources"] == [
        {
          "element_id": label_context["labeling"]["label_sources"][0][
            "element_id"
          ],
          "selector": "label:nth-of-type(1)",
          "reference_type": "label-wrapper",
          "relationship_type": "labels",
          "method": "for",
          "text": expected_visible_label,
          "text_segments": [expected_label_text, "Required"],
        }
      ]
      purpose = label_context["field_purpose_evidence"]
      assert purpose["type"] == "tel"
      assert purpose["name"] == "phone"
      assert purpose["id"] == "details-phone"
      assert purpose["autocomplete"] == "tel"
      assert purpose["form_step_or_route_context"]["route"] == "/details"
      assert supporting["parent_form"]["selector"] == "form:nth-of-type(1)"

      _, matched_candidates = _score_booking_recovery(
        run_dir,
        config_id="booking-bs-sem-129",
        score_run_id=f"bs-sem-129-{label}",
        expected_recovered=expected_recovered,
        expected_matched_entries=expected_recovered,
      )
      if expected_recovered:
        assert matched_candidates[0]["candidate_id"] == (
          candidate["candidate_id"]
        )

  _run_async(booking_browser, verify())


def test_bs_sem_130_accessibility_needs_native_label_changes_to_phone_with_purpose_preserved(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    cases = (
      ("clean", BOOKING_CLEAN_PROFILE, "Accessibility needs", 0),
      ("seeded", "booking-bs-sem-130", "Phone", 1),
    )

    for label, profile, expected_label_text, expected_recovered in cases:
      run_dir = tmp_path / label
      async with open_booking_run(
        browser,
        base_url=booking_spa.base_url,
        profile=profile,
        target_state="details",
      ) as run:
        full_name = run.page.locator('[data-testid="details-full-name"]')
        email = run.page.locator('[data-testid="details-email"]')
        phone = run.page.locator('[data-testid="details-phone"]')
        accessibility_needs = run.page.locator(
          '[data-testid="details-accessibility-needs"]'
        )
        accessibility_label = run.page.locator(
          'label[for="details-accessibilityNeeds"]'
        )
        submit = run.page.locator('[data-testid="details-submit"]')

        assert urlsplit(run.page.url).path == "/details"
        assert await run.page.title() == (
          "Booking details | Booking Scheduler Benchmark"
        )
        assert await accessibility_label.locator("span").all_inner_texts() == [
          expected_label_text,
          "OPTIONAL",
        ]
        assert await accessibility_needs.get_attribute("id") == (
          "details-accessibilityNeeds"
        )
        assert await accessibility_needs.get_attribute("name") == (
          "accessibilityNeeds"
        )
        assert await accessibility_needs.get_attribute("rows") == "4"
        assert await accessibility_needs.get_attribute("placeholder") == (
          "Accessibility needs, preparation notes, or special requests"
        )
        assert await accessibility_needs.get_attribute("aria-describedby") == (
          "details-accessibilityNeeds-hint"
        )
        assert await accessibility_needs.get_attribute("aria-label") is None
        assert await accessibility_needs.get_attribute("aria-labelledby") is None
        assert await accessibility_needs.evaluate(
          "element => element.required"
        ) is False
        assert await accessibility_needs.input_value() == ""
        assert await accessibility_needs.aria_snapshot() == (
          f'- textbox "{expected_label_text} Optional":\n'
          "  - /placeholder: Accessibility needs, preparation notes, or special requests"
        )
        assert await run.page.locator(
          '#details-accessibilityNeeds-hint'
        ).inner_text() == (
          "Share accessibility needs, preparation notes, or special requests "
          "for this appointment."
        )
        assert await run.page.locator(
          'label[for="details-phone"] span:first-child'
        ).inner_text() == "Phone"
        assert await phone.aria_snapshot() == '- textbox "Phone Required"'

        recorder = FocusedRunRecorder(
          run_dir=run_dir,
          app_name="booking-scheduler",
          benchmark_name=f"booking-bs-sem-130-{label}",
          source_script="tests/test_booking_accessgraph_integration.py",
        )
        record = await recorder.capture_page_state(
          run.page,
          FocusedStateSpec(
            benchmark_state_id="BS-S003",
            focused_state_name="details-accessibility-needs-label",
            action_path=[
              "select Consultation",
              "select June 16 at 09:00",
              "open Booking details",
            ],
            key_validated_selectors=[
              '[data-testid="route-details"]',
              '[data-testid="details-form"]',
              'label[for="details-accessibilityNeeds"]',
              "textarea#details-accessibilityNeeds",
              "p#details-accessibilityNeeds-hint",
            ],
          ),
        )
        recorder.write_run_artifacts()

        assert record.state_id == "state_0000"
        assert record.route == "/details"

        accessibility_value = "Please allow extra time for mobility support."
        await full_name.fill("Jordan Lee")
        await email.fill("jordan.lee@example.test")
        await phone.fill("555-0134")
        await accessibility_needs.fill(accessibility_value)
        await submit.click()
        await run.page.wait_for_url("**/review")
        assert urlsplit(run.page.url).path == "/review"
        await run.page.locator('[data-testid="edit-details"]').click()
        await run.page.wait_for_url("**/details")
        assert await run.page.locator(
          '[data-testid="details-accessibility-needs"]'
        ).input_value() == accessibility_value
        assert await run.page.locator(
          '[data-testid="details-phone"]'
        ).input_value() == "555-0134"

      candidates = _build_booking_candidates(
        run_dir,
        "form-label-mismatch",
      )
      assert len(candidates) == 5

      candidate = next(
        item
        for item in candidates
        if item["evidence"]["primary"]["form_control"]["selector"]
        == "textarea#details-accessibilityNeeds"
      )
      control = candidate["evidence"]["primary"]["form_control"]
      supporting = candidate["evidence"]["supporting"]
      label_context = supporting["form_label_context_v1"]
      expected_compact_label = f"{expected_label_text}Optional"
      expected_visible_label = f"{expected_label_text} OPTIONAL"

      assert candidate["candidate_type"] == "form-label-mismatch"
      assert candidate["state_id"] == "state_0000"
      assert candidate["state_context"]["url"].endswith("/details")
      assert control["selector"] == "textarea#details-accessibilityNeeds"
      assert control["id"] == "details-accessibilityNeeds"
      assert control["name"] == "accessibilityNeeds"
      assert control["tag"] == "textarea"
      assert control["type"] == ""
      assert control["autocomplete"] is None
      assert control["required"] is False
      assert control["has_value"] is False
      assert control["aria_label"] is None
      assert control["aria_labelledby"] is None
      assert control["aria_describedby"] == "details-accessibilityNeeds-hint"
      assert control["placeholder"] == (
        "Accessibility needs, preparation notes, or special requests"
      )
      assert control["label"] == expected_compact_label
      assert control["accessible_name"] == expected_compact_label
      assert label_context["control"]["selector"] == (
        "textarea#details-accessibilityNeeds"
      )
      assert label_context["control"]["value_state"] == "empty"
      assert label_context["labeling"]["visible_label"] == (
        expected_visible_label
      )
      assert label_context["labeling"]["computed_accessible_name"] == (
        expected_compact_label
      )
      label_source = label_context["labeling"]["label_sources"][0]
      assert label_source["relationship_type"] == "labels"
      assert label_source["method"] == "for"
      assert label_source["text"] == expected_visible_label
      assert label_source["text_segments"] == [expected_label_text, "Optional"]
      purpose = label_context["field_purpose_evidence"]
      assert purpose["name"] == "accessibilityNeeds"
      assert purpose["id"] == "details-accessibilityNeeds"
      assert purpose["placeholder"] == (
        "Accessibility needs, preparation notes, or special requests"
      )
      assert purpose["form_step_or_route_context"]["route"] == "/details"
      description = purpose["descriptions"][0]
      assert description["selector"] == "p#details-accessibilityNeeds-hint"
      assert description["relationship_type"] == "describes"
      assert description["method"] == "aria-describedby"
      assert description["text"] == (
        "Share accessibility needs, preparation notes, or special requests "
        "for this appointment."
      )
      assert supporting["parent_form"]["selector"] == "form:nth-of-type(1)"

      _, matched_candidates = _score_booking_recovery(
        run_dir,
        config_id="booking-bs-sem-130",
        score_run_id=f"bs-sem-130-{label}",
        expected_recovered=expected_recovered,
        expected_matched_entries=expected_recovered,
      )
      if expected_recovered:
        assert matched_candidates[0]["candidate_id"] == (
          candidate["candidate_id"]
        )

  _run_async(booking_browser, verify())


def test_bs_sem_128_schedule_date_native_label_changes_to_time_with_date_purpose_preserved(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    cases = (
      ("clean", BOOKING_CLEAN_PROFILE, "Appointment date", 0),
      ("seeded", "booking-bs-sem-128", "Appointment time", 1),
    )

    for label, profile, expected_label_text, expected_recovered in cases:
      run_dir = tmp_path / label
      async with open_booking_run(
        browser,
        base_url=booking_spa.base_url,
        profile=profile,
        target_state="schedule",
      ) as run:
        date_input = run.page.locator('[data-testid="schedule-date-input"]')
        date_label = run.page.locator('label[for="booking-date"]')
        date_help = run.page.locator("#booking-date-help")

        assert urlsplit(run.page.url).path == "/schedule"
        assert await run.page.title() == (
          "Schedule appointment | Booking Scheduler Benchmark"
        )
        assert await date_label.inner_text() == expected_label_text
        assert await date_label.get_attribute("for") == "booking-date"
        assert await date_input.get_attribute("id") == "booking-date"
        assert await date_input.get_attribute("type") == "date"
        assert await date_input.get_attribute("name") is None
        assert await date_input.get_attribute("min") == "2026-06-16"
        assert await date_input.get_attribute("max") == "2026-06-18"
        assert await date_input.get_attribute("step") == "2"
        assert await date_input.get_attribute("aria-describedby") == (
          "booking-date-help"
        )
        assert await date_input.get_attribute("aria-label") is None
        assert await date_input.get_attribute("aria-labelledby") is None
        assert await date_input.evaluate("element => element.required") is False
        assert await date_input.input_value() == ""
        assert await date_input.aria_snapshot() == (
          f'- textbox "{expected_label_text}"'
        )
        assert await date_help.inner_text() == (
          "Supported fixture dates: June 16, 2026 and June 18, 2026."
        )
        assert await run.page.locator(
          '[data-testid="slot-empty-prompt"]'
        ).inner_text() == (
          "Choose a supported fixture date to show appointment times."
        )
        assert await run.page.locator('[data-testid^="slot-button-"]').count() == 0

        recorder = FocusedRunRecorder(
          run_dir=run_dir,
          app_name="booking-scheduler",
          benchmark_name=f"booking-bs-sem-128-{label}",
          source_script="tests/test_booking_accessgraph_integration.py",
        )
        record = await recorder.capture_page_state(
          run.page,
          FocusedStateSpec(
            benchmark_state_id="BS-S002",
            focused_state_name="schedule-appointment-date-label",
            action_path=[
              "select Consultation",
              "continue to Schedule",
            ],
            key_validated_selectors=[
              '[data-testid="route-schedule"]',
              'label[for="booking-date"]',
              "input#booking-date",
              "p#booking-date-help",
              '[data-testid="slot-empty-prompt"]',
            ],
          ),
        )
        recorder.write_run_artifacts()

        assert record.state_id == "state_0000"
        assert record.route == "/schedule"

        await date_input.fill("2026-06-16")
        assert await date_input.input_value() == "2026-06-16"
        assert await date_label.inner_text() == expected_label_text
        assert await date_help.inner_text() == (
          "Supported fixture dates: June 16, 2026 and June 18, 2026."
        )
        slot_0900 = run.page.locator('[data-testid="slot-button-0900"]')
        slot_1300 = run.page.locator('[data-testid="slot-button-1300"]')
        assert await slot_0900.aria_snapshot() == '- button "09:00 Available"'
        assert await slot_1300.aria_snapshot() == '- button "13:00 Available"'
        await slot_0900.click()
        await run.page.locator('[data-testid="continue-to-details"]').click()
        await run.page.wait_for_url("**/details")
        await run.page.locator('[data-testid="back-to-schedule"]').click()
        await run.page.wait_for_url("**/schedule")
        assert await run.page.locator(
          '[data-testid="schedule-date-input"]'
        ).input_value() == "2026-06-16"
        assert await run.page.locator(
          '[data-testid="slot-button-0900"]'
        ).get_attribute("aria-pressed") == "true"

      candidates = _build_booking_candidates(
        run_dir,
        "form-label-mismatch",
      )
      assert len(candidates) == 1

      candidate = candidates[0]
      control = candidate["evidence"]["primary"]["form_control"]
      supporting = candidate["evidence"]["supporting"]
      label_context = supporting["form_label_context_v1"]

      assert candidate["candidate_type"] == "form-label-mismatch"
      assert candidate["state_id"] == "state_0000"
      assert candidate["state_context"]["url"].endswith("/schedule")
      assert control["selector"] == "input#booking-date"
      assert control["id"] == "booking-date"
      assert control["name"] is None
      assert control["tag"] == "input"
      assert control["type"] == "date"
      assert control["required"] is False
      assert control["has_value"] is False
      assert control["aria_label"] is None
      assert control["aria_labelledby"] is None
      assert control["aria_describedby"] == "booking-date-help"
      assert control["label"] == expected_label_text
      assert control["accessible_name"] == expected_label_text
      assert label_context["control"]["selector"] == "input#booking-date"
      assert label_context["control"]["type"] == "date"
      assert label_context["control"]["value_state"] == "empty"
      assert label_context["labeling"]["visible_label"] == expected_label_text
      assert label_context["labeling"]["computed_accessible_name"] == (
        expected_label_text
      )
      label_source = label_context["labeling"]["label_sources"][0]
      assert label_source["relationship_type"] == "labels"
      assert label_source["method"] == "for"
      assert label_source["text"] == expected_label_text
      assert label_source["text_segments"] == [expected_label_text]
      purpose = label_context["field_purpose_evidence"]
      assert purpose["type"] == "date"
      assert purpose["id"] == "booking-date"
      assert purpose["form_step_or_route_context"]["route"] == "/schedule"
      description = purpose["descriptions"][0]
      assert description["selector"] == "p#booking-date-help"
      assert description["relationship_type"] == "describes"
      assert description["method"] == "aria-describedby"
      assert description["text"] == (
        "Supported fixture dates: June 16, 2026 and June 18, 2026."
      )
      assert supporting["structure"]["nearest_heading"] == {
        "element_id": supporting["structure"]["nearest_heading"]["element_id"],
        "tag": "h2",
        "text": "Choose a date and time",
        "selector": "h2#schedule-heading",
      }

      _, matched_candidates = _score_booking_recovery(
        run_dir,
        config_id="booking-bs-sem-128",
        score_run_id=f"bs-sem-128-{label}",
        expected_recovered=expected_recovered,
        expected_matched_entries=expected_recovered,
      )
      if expected_recovered:
        assert matched_candidates[0]["candidate_id"] == (
          candidate["candidate_id"]
        )

  _run_async(booking_browser, verify())


def test_bs_sem_151_email_autocomplete_changes_to_telephone_purpose_only(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    cases = (
      ("clean", BOOKING_CLEAN_PROFILE, "email", "email address", 0),
      ("seeded", "booking-bs-sem-151", "tel", "telephone number", 1),
    )

    for (
      label,
      profile,
      expected_autocomplete,
      expected_recognized_purpose,
      expected_recovered,
    ) in cases:
      run_dir = tmp_path / label
      async with open_booking_run(
        browser,
        base_url=booking_spa.base_url,
        profile=profile,
        target_state="details",
      ) as run:
        full_name = run.page.locator('[data-testid="details-full-name"]')
        email = run.page.locator('[data-testid="details-email"]')
        phone = run.page.locator('[data-testid="details-phone"]')
        email_label = run.page.locator('label[for="details-email"]')
        phone_label = run.page.locator('label[for="details-phone"]')
        submit = run.page.locator('[data-testid="details-submit"]')

        assert urlsplit(run.page.url).path == "/details"
        assert await run.page.title() == (
          "Booking details | Booking Scheduler Benchmark"
        )
        assert await email_label.locator("span").all_inner_texts() == [
          "Email",
          "REQUIRED",
        ]
        assert await email.get_attribute("id") == "details-email"
        assert await email.get_attribute("name") == "email"
        assert await email.get_attribute("type") == "email"
        assert await email.get_attribute("autocomplete") == (
          expected_autocomplete
        )
        assert await email.get_attribute("aria-label") is None
        assert await email.get_attribute("aria-labelledby") is None
        assert await email.get_attribute("aria-describedby") is None
        assert await email.evaluate("element => element.required") is True
        assert await email.input_value() == ""
        assert await email.aria_snapshot() == '- textbox "Email Required"'

        assert await phone_label.locator("span").all_inner_texts() == [
          "Phone",
          "REQUIRED",
        ]
        assert await phone.get_attribute("id") == "details-phone"
        assert await phone.get_attribute("name") == "phone"
        assert await phone.get_attribute("type") == "tel"
        assert await phone.get_attribute("autocomplete") == "tel"
        assert await phone.evaluate("element => element.required") is True
        assert await phone.aria_snapshot() == '- textbox "Phone Required"'
        assert await full_name.get_attribute("autocomplete") == "name"

        recorder = FocusedRunRecorder(
          run_dir=run_dir,
          app_name="booking-scheduler",
          benchmark_name=f"booking-bs-sem-151-{label}",
          source_script="tests/test_booking_accessgraph_integration.py",
        )
        record = await recorder.capture_page_state(
          run.page,
          FocusedStateSpec(
            benchmark_state_id="BS-S003",
            focused_state_name="details-email-autocomplete",
            action_path=[
              "select Consultation",
              "select June 16 at 09:00",
              "open Booking details",
            ],
            key_validated_selectors=[
              '[data-testid="route-details"]',
              '[data-testid="details-form"]',
              'label[for="details-email"]',
              "input#details-email",
              "input#details-phone",
            ],
          ),
        )
        recorder.write_run_artifacts()

        assert record.state_id == "state_0000"
        assert record.route == "/details"

        await full_name.fill("Jordan Lee")
        await phone.fill("555-0134")
        await submit.click()
        assert urlsplit(run.page.url).path == "/details"
        assert await email.get_attribute("aria-invalid") == "true"
        assert await email.get_attribute("aria-describedby") == (
          "details-email-error"
        )
        assert await run.page.locator("#details-email-error").inner_text() == (
          "Email is required."
        )
        assert await run.page.locator(".field-error").count() == 1

        await email.fill("jordan.lee@example.test")
        await submit.click()
        await run.page.wait_for_url("**/review")
        assert urlsplit(run.page.url).path == "/review"
        assert await run.page.locator(
          '[data-testid="review-customer-full-name"]'
        ).inner_text() == "Jordan Lee"
        assert await run.page.locator(
          '[data-testid="review-customer-email"]'
        ).inner_text() == "jordan.lee@example.test"
        assert await run.page.locator(
          '[data-testid="review-customer-phone"]'
        ).inner_text() == "555-0134"

      candidates = _build_booking_candidates(
        run_dir,
        "autocomplete-purpose-mismatch",
      )
      assert len(candidates) == 3

      candidates_by_selector = {
        item["evidence"]["primary"]["form_control"]["selector"]: item
        for item in candidates
      }
      candidate = candidates_by_selector["input#details-email"]
      phone_candidate = candidates_by_selector["input#details-phone"]
      control = candidate["evidence"]["primary"]["form_control"]
      context = candidate["evidence"]["supporting"][
        "autocomplete_purpose_context_v1"
      ]

      assert candidate["candidate_type"] == "autocomplete-purpose-mismatch"
      assert candidate["state_id"] == "state_0000"
      assert candidate["state_context"]["url"].endswith("/details")
      assert control["selector"] == "input#details-email"
      assert control["id"] == "details-email"
      assert control["name"] == "email"
      assert control["type"] == "email"
      assert control["autocomplete"] == expected_autocomplete
      assert control["required"] is True
      assert control["has_value"] is False
      assert control["label"] == "EmailRequired"
      assert control["accessible_name"] == "EmailRequired"

      assert context["control"]["selector"] == "input#details-email"
      assert context["control"]["id"] == "details-email"
      assert context["control"]["name"] == "email"
      assert context["control"]["type"] == "email"
      assert context["control"]["autocomplete"] == expected_autocomplete
      assert context["control"]["value_state"] == "empty"
      assert context["labeling"]["visible_label"] == "Email REQUIRED"
      assert context["labeling"]["computed_accessible_name"] == (
        "EmailRequired"
      )
      assert context["labeling"]["label_sources"][0][
        "relationship_type"
      ] == "labels"
      assert context["labeling"]["label_sources"][0]["method"] == "for"
      assert context["labeling"]["label_sources"][0]["text_segments"] == [
        "Email",
        "Required",
      ]

      purpose = context["field_purpose_evidence"]
      assert purpose["input_type"] == "email"
      assert purpose["name"] == "email"
      assert purpose["id"] == "details-email"
      assert purpose["visible_label"] == "Email REQUIRED"
      assert purpose["computed_accessible_name"] == "EmailRequired"
      assert purpose["form_step_or_route_context"]["route"] == "/details"
      assert purpose["form_step_or_route_context"]["section_heading"] == (
        "Customer details"
      )

      assert context["autocomplete_evidence"] == {
        "raw_value": expected_autocomplete,
        "tokens": [expected_autocomplete],
        "section_tokens": [],
        "context_tokens": [],
        "purpose_token": expected_autocomplete,
        "recognized_purpose": expected_recognized_purpose,
        "token_category": (
          "email" if expected_autocomplete == "email" else "tel"
        ),
        "is_known_token": True,
        "unknown_tokens": [],
      }

      phone_control = phone_candidate["evidence"]["primary"]["form_control"]
      assert phone_control["selector"] == "input#details-phone"
      assert phone_control["id"] == "details-phone"
      assert phone_control["name"] == "phone"
      assert phone_control["type"] == "tel"
      assert phone_control["autocomplete"] == "tel"
      assert phone_control["label"] == "PhoneRequired"
      assert phone_control["accessible_name"] == "PhoneRequired"

      _, matched_candidates = _score_booking_recovery(
        run_dir,
        config_id="booking-bs-sem-151",
        score_run_id=f"bs-sem-151-{label}",
        expected_recovered=expected_recovered,
        expected_matched_entries=expected_recovered,
      )
      if expected_recovered:
        assert matched_candidates[0]["candidate_id"] == (
          candidate["candidate_id"]
        )

  _run_async(booking_browser, verify())


def test_bs_sem_152_phone_autocomplete_changes_to_email_purpose_only(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    cases = (
      ("clean", BOOKING_CLEAN_PROFILE, "tel", "telephone number", 0),
      ("seeded", "booking-bs-sem-152", "email", "email address", 1),
    )

    for (
      label,
      profile,
      expected_autocomplete,
      expected_recognized_purpose,
      expected_recovered,
    ) in cases:
      run_dir = tmp_path / label
      async with open_booking_run(
        browser,
        base_url=booking_spa.base_url,
        profile=profile,
        target_state="details",
      ) as run:
        full_name = run.page.locator('[data-testid="details-full-name"]')
        email = run.page.locator('[data-testid="details-email"]')
        phone = run.page.locator('[data-testid="details-phone"]')
        email_label = run.page.locator('label[for="details-email"]')
        phone_label = run.page.locator('label[for="details-phone"]')
        submit = run.page.locator('[data-testid="details-submit"]')

        assert urlsplit(run.page.url).path == "/details"
        assert await run.page.title() == (
          "Booking details | Booking Scheduler Benchmark"
        )
        assert await phone_label.locator("span").all_inner_texts() == [
          "Phone",
          "REQUIRED",
        ]
        assert await phone.get_attribute("id") == "details-phone"
        assert await phone.get_attribute("name") == "phone"
        assert await phone.get_attribute("type") == "tel"
        assert await phone.get_attribute("autocomplete") == (
          expected_autocomplete
        )
        assert await phone.get_attribute("aria-label") is None
        assert await phone.get_attribute("aria-labelledby") is None
        assert await phone.get_attribute("aria-describedby") is None
        assert await phone.evaluate("element => element.required") is True
        assert await phone.input_value() == ""
        assert await phone.aria_snapshot() == '- textbox "Phone Required"'

        assert await email_label.locator("span").all_inner_texts() == [
          "Email",
          "REQUIRED",
        ]
        assert await email.get_attribute("id") == "details-email"
        assert await email.get_attribute("name") == "email"
        assert await email.get_attribute("type") == "email"
        assert await email.get_attribute("autocomplete") == "email"
        assert await email.evaluate("element => element.required") is True
        assert await email.aria_snapshot() == '- textbox "Email Required"'
        assert await full_name.get_attribute("autocomplete") == "name"

        recorder = FocusedRunRecorder(
          run_dir=run_dir,
          app_name="booking-scheduler",
          benchmark_name=f"booking-bs-sem-152-{label}",
          source_script="tests/test_booking_accessgraph_integration.py",
        )
        record = await recorder.capture_page_state(
          run.page,
          FocusedStateSpec(
            benchmark_state_id="BS-S003",
            focused_state_name="details-phone-autocomplete",
            action_path=[
              "select Consultation",
              "select June 16 at 09:00",
              "open Booking details",
            ],
            key_validated_selectors=[
              '[data-testid="route-details"]',
              '[data-testid="details-form"]',
              'label[for="details-phone"]',
              "input#details-phone",
              "input#details-email",
            ],
          ),
        )
        recorder.write_run_artifacts()

        assert record.state_id == "state_0000"
        assert record.route == "/details"

        await full_name.fill("Jordan Lee")
        await email.fill("jordan.lee@example.test")
        await submit.click()
        assert urlsplit(run.page.url).path == "/details"
        assert await phone.get_attribute("aria-invalid") == "true"
        assert await phone.get_attribute("aria-describedby") == (
          "details-phone-error"
        )
        assert await run.page.locator("#details-phone-error").inner_text() == (
          "Phone is required."
        )
        assert await run.page.locator(".field-error").count() == 1

        await phone.fill("555-0134")
        await submit.click()
        await run.page.wait_for_url("**/review")
        assert urlsplit(run.page.url).path == "/review"
        assert await run.page.locator(
          '[data-testid="review-customer-full-name"]'
        ).inner_text() == "Jordan Lee"
        assert await run.page.locator(
          '[data-testid="review-customer-email"]'
        ).inner_text() == "jordan.lee@example.test"
        assert await run.page.locator(
          '[data-testid="review-customer-phone"]'
        ).inner_text() == "555-0134"

      candidates = _build_booking_candidates(
        run_dir,
        "autocomplete-purpose-mismatch",
      )
      assert len(candidates) == 3

      candidates_by_selector = {
        item["evidence"]["primary"]["form_control"]["selector"]: item
        for item in candidates
      }
      candidate = candidates_by_selector["input#details-phone"]
      email_candidate = candidates_by_selector["input#details-email"]
      control = candidate["evidence"]["primary"]["form_control"]
      context = candidate["evidence"]["supporting"][
        "autocomplete_purpose_context_v1"
      ]

      assert candidate["candidate_type"] == "autocomplete-purpose-mismatch"
      assert candidate["state_id"] == "state_0000"
      assert candidate["state_context"]["url"].endswith("/details")
      assert control["selector"] == "input#details-phone"
      assert control["id"] == "details-phone"
      assert control["name"] == "phone"
      assert control["type"] == "tel"
      assert control["autocomplete"] == expected_autocomplete
      assert control["required"] is True
      assert control["has_value"] is False
      assert control["label"] == "PhoneRequired"
      assert control["accessible_name"] == "PhoneRequired"

      assert context["control"]["selector"] == "input#details-phone"
      assert context["control"]["id"] == "details-phone"
      assert context["control"]["name"] == "phone"
      assert context["control"]["type"] == "tel"
      assert context["control"]["autocomplete"] == expected_autocomplete
      assert context["control"]["value_state"] == "empty"
      assert context["labeling"]["visible_label"] == "Phone REQUIRED"
      assert context["labeling"]["computed_accessible_name"] == (
        "PhoneRequired"
      )
      assert context["labeling"]["label_sources"][0][
        "relationship_type"
      ] == "labels"
      assert context["labeling"]["label_sources"][0]["method"] == "for"
      assert context["labeling"]["label_sources"][0]["text_segments"] == [
        "Phone",
        "Required",
      ]

      purpose = context["field_purpose_evidence"]
      assert purpose["input_type"] == "tel"
      assert purpose["name"] == "phone"
      assert purpose["id"] == "details-phone"
      assert purpose["visible_label"] == "Phone REQUIRED"
      assert purpose["computed_accessible_name"] == "PhoneRequired"
      assert purpose["form_step_or_route_context"]["route"] == "/details"
      assert purpose["form_step_or_route_context"]["section_heading"] == (
        "Customer details"
      )

      assert context["autocomplete_evidence"] == {
        "raw_value": expected_autocomplete,
        "tokens": [expected_autocomplete],
        "section_tokens": [],
        "context_tokens": [],
        "purpose_token": expected_autocomplete,
        "recognized_purpose": expected_recognized_purpose,
        "token_category": (
          "tel" if expected_autocomplete == "tel" else "email"
        ),
        "is_known_token": True,
        "unknown_tokens": [],
      }

      email_control = email_candidate["evidence"]["primary"]["form_control"]
      assert email_control["selector"] == "input#details-email"
      assert email_control["id"] == "details-email"
      assert email_control["name"] == "email"
      assert email_control["type"] == "email"
      assert email_control["autocomplete"] == "email"
      assert email_control["label"] == "EmailRequired"
      assert email_control["accessible_name"] == "EmailRequired"

      _, matched_candidates = _score_booking_recovery(
        run_dir,
        config_id="booking-bs-sem-152",
        score_run_id=f"bs-sem-152-{label}",
        expected_recovered=expected_recovered,
        expected_matched_entries=expected_recovered,
      )
      if expected_recovered:
        assert matched_candidates[0]["candidate_id"] == (
          candidate["candidate_id"]
        )

  _run_async(booking_browser, verify())


def test_bs_sem_153_full_name_autocomplete_changes_to_organization_title_only(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    cases = (
      ("clean", BOOKING_CLEAN_PROFILE, "name", "full name", "name", 0),
      (
        "seeded",
        "booking-bs-sem-153",
        "organization-title",
        "organization title",
        "organization",
        1,
      ),
    )

    for (
      label,
      profile,
      expected_autocomplete,
      expected_recognized_purpose,
      expected_token_category,
      expected_recovered,
    ) in cases:
      run_dir = tmp_path / label
      async with open_booking_run(
        browser,
        base_url=booking_spa.base_url,
        profile=profile,
        target_state="details",
      ) as run:
        full_name = run.page.locator('[data-testid="details-full-name"]')
        email = run.page.locator('[data-testid="details-email"]')
        phone = run.page.locator('[data-testid="details-phone"]')
        full_name_label = run.page.locator('label[for="details-fullName"]')
        email_label = run.page.locator('label[for="details-email"]')
        phone_label = run.page.locator('label[for="details-phone"]')
        submit = run.page.locator('[data-testid="details-submit"]')

        assert urlsplit(run.page.url).path == "/details"
        assert await run.page.title() == (
          "Booking details | Booking Scheduler Benchmark"
        )
        assert await full_name_label.locator("span").all_inner_texts() == [
          "Full name",
          "REQUIRED",
        ]
        assert await full_name.get_attribute("id") == "details-fullName"
        assert await full_name.get_attribute("name") == "fullName"
        assert await full_name.get_attribute("type") == "text"
        assert await full_name.get_attribute("autocomplete") == (
          expected_autocomplete
        )
        assert await full_name.get_attribute("aria-label") is None
        assert await full_name.get_attribute("aria-labelledby") is None
        assert await full_name.get_attribute("aria-describedby") is None
        assert await full_name.evaluate("element => element.required") is True
        assert await full_name.input_value() == ""
        assert await full_name.aria_snapshot() == (
          '- textbox "Full name Required"'
        )

        assert await email_label.locator("span").all_inner_texts() == [
          "Email",
          "REQUIRED",
        ]
        assert await email.get_attribute("id") == "details-email"
        assert await email.get_attribute("name") == "email"
        assert await email.get_attribute("type") == "email"
        assert await email.get_attribute("autocomplete") == "email"
        assert await email.evaluate("element => element.required") is True
        assert await email.aria_snapshot() == '- textbox "Email Required"'

        assert await phone_label.locator("span").all_inner_texts() == [
          "Phone",
          "REQUIRED",
        ]
        assert await phone.get_attribute("id") == "details-phone"
        assert await phone.get_attribute("name") == "phone"
        assert await phone.get_attribute("type") == "tel"
        assert await phone.get_attribute("autocomplete") == "tel"
        assert await phone.evaluate("element => element.required") is True
        assert await phone.aria_snapshot() == '- textbox "Phone Required"'

        recorder = FocusedRunRecorder(
          run_dir=run_dir,
          app_name="booking-scheduler",
          benchmark_name=f"booking-bs-sem-153-{label}",
          source_script="tests/test_booking_accessgraph_integration.py",
        )
        record = await recorder.capture_page_state(
          run.page,
          FocusedStateSpec(
            benchmark_state_id="BS-S003",
            focused_state_name="details-full-name-autocomplete",
            action_path=[
              "select Consultation",
              "select June 16 at 09:00",
              "open Booking details",
            ],
            key_validated_selectors=[
              '[data-testid="route-details"]',
              '[data-testid="details-form"]',
              'label[for="details-fullName"]',
              "input#details-fullName",
              "input#details-email",
              "input#details-phone",
            ],
          ),
        )
        recorder.write_run_artifacts()

        assert record.state_id == "state_0000"
        assert record.route == "/details"

        await email.fill("jordan.lee@example.test")
        await phone.fill("555-0134")
        await submit.click()
        assert urlsplit(run.page.url).path == "/details"
        assert await full_name.get_attribute("aria-invalid") == "true"
        assert await full_name.get_attribute("aria-describedby") == (
          "details-fullName-error"
        )
        assert await run.page.locator(
          "#details-fullName-error"
        ).inner_text() == "Full name is required."
        assert await run.page.locator(".field-error").count() == 1

        await full_name.fill("Jordan Lee")
        await submit.click()
        await run.page.wait_for_url("**/review")
        assert urlsplit(run.page.url).path == "/review"
        assert await run.page.locator(
          '[data-testid="review-customer-full-name"]'
        ).inner_text() == "Jordan Lee"
        assert await run.page.locator(
          '[data-testid="review-customer-email"]'
        ).inner_text() == "jordan.lee@example.test"
        assert await run.page.locator(
          '[data-testid="review-customer-phone"]'
        ).inner_text() == "555-0134"

      candidates = _build_booking_candidates(
        run_dir,
        "autocomplete-purpose-mismatch",
      )
      assert len(candidates) == 3

      candidates_by_selector = {
        item["evidence"]["primary"]["form_control"]["selector"]: item
        for item in candidates
      }
      candidate = candidates_by_selector["input#details-fullName"]
      email_candidate = candidates_by_selector["input#details-email"]
      phone_candidate = candidates_by_selector["input#details-phone"]
      control = candidate["evidence"]["primary"]["form_control"]
      context = candidate["evidence"]["supporting"][
        "autocomplete_purpose_context_v1"
      ]

      assert candidate["candidate_type"] == "autocomplete-purpose-mismatch"
      assert candidate["state_id"] == "state_0000"
      assert candidate["state_context"]["url"].endswith("/details")
      assert control["selector"] == "input#details-fullName"
      assert control["id"] == "details-fullName"
      assert control["name"] == "fullName"
      assert control["type"] == "text"
      assert control["autocomplete"] == expected_autocomplete
      assert control["required"] is True
      assert control["has_value"] is False
      assert control["label"] == "Full nameRequired"
      assert control["accessible_name"] == "Full nameRequired"

      assert context["control"]["selector"] == "input#details-fullName"
      assert context["control"]["id"] == "details-fullName"
      assert context["control"]["name"] == "fullName"
      assert context["control"]["type"] == "text"
      assert context["control"]["autocomplete"] == expected_autocomplete
      assert context["control"]["value_state"] == "empty"
      assert context["labeling"]["visible_label"] == "Full name REQUIRED"
      assert context["labeling"]["computed_accessible_name"] == (
        "Full nameRequired"
      )
      assert context["labeling"]["label_sources"][0][
        "relationship_type"
      ] == "labels"
      assert context["labeling"]["label_sources"][0]["method"] == "for"
      assert context["labeling"]["label_sources"][0]["text_segments"] == [
        "Full name",
        "Required",
      ]

      purpose = context["field_purpose_evidence"]
      assert purpose["input_type"] == "text"
      assert purpose["name"] == "fullName"
      assert purpose["id"] == "details-fullName"
      assert purpose["visible_label"] == "Full name REQUIRED"
      assert purpose["computed_accessible_name"] == "Full nameRequired"
      assert purpose["form_step_or_route_context"]["route"] == "/details"
      assert purpose["form_step_or_route_context"]["section_heading"] == (
        "Customer details"
      )

      assert context["autocomplete_evidence"] == {
        "raw_value": expected_autocomplete,
        "tokens": [expected_autocomplete],
        "section_tokens": [],
        "context_tokens": [],
        "purpose_token": expected_autocomplete,
        "recognized_purpose": expected_recognized_purpose,
        "token_category": expected_token_category,
        "is_known_token": True,
        "unknown_tokens": [],
      }

      email_control = email_candidate["evidence"]["primary"]["form_control"]
      assert email_control["selector"] == "input#details-email"
      assert email_control["autocomplete"] == "email"
      assert email_control["label"] == "EmailRequired"
      assert email_control["accessible_name"] == "EmailRequired"

      phone_control = phone_candidate["evidence"]["primary"]["form_control"]
      assert phone_control["selector"] == "input#details-phone"
      assert phone_control["autocomplete"] == "tel"
      assert phone_control["label"] == "PhoneRequired"
      assert phone_control["accessible_name"] == "PhoneRequired"

      _, matched_candidates = _score_booking_recovery(
        run_dir,
        config_id="booking-bs-sem-153",
        score_run_id=f"bs-sem-153-{label}",
        expected_recovered=expected_recovered,
        expected_matched_entries=expected_recovered,
      )
      if expected_recovered:
        assert matched_candidates[0]["candidate_id"] == (
          candidate["candidate_id"]
        )

  _run_async(booking_browser, verify())


def test_bs_sem_154_full_name_autocomplete_changes_to_given_name_only(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    snapshots = {}
    candidate_ids = {}
    cases = (
      ("clean", BOOKING_CLEAN_PROFILE, "name", "full name", 0),
      ("seeded", "booking-bs-sem-154", "given-name", "given name", 1),
    )

    for (
      label,
      profile,
      expected_autocomplete,
      expected_recognized_purpose,
      expected_recovered,
    ) in cases:
      run_dir = tmp_path / label
      async with open_booking_run(
        browser,
        base_url=booking_spa.base_url,
        profile=profile,
        target_state="details",
      ) as run:
        full_name = run.page.locator("input#details-fullName")
        full_name_label = run.page.locator('label[for="details-fullName"]')
        email = run.page.locator("input#details-email")
        phone = run.page.locator("input#details-phone")
        submit = run.page.locator('[data-testid="details-submit"]')

        assert urlsplit(run.page.url).path == "/details"
        assert await run.page.title() == (
          "Booking details | Booking Scheduler Benchmark"
        )
        assert await full_name_label.locator("span").all_inner_texts() == [
          "Full name",
          "REQUIRED",
        ]
        assert await full_name.get_attribute("id") == "details-fullName"
        assert await full_name.get_attribute("name") == "fullName"
        assert await full_name.get_attribute("type") == "text"
        assert await full_name.get_attribute("autocomplete") == (
          expected_autocomplete
        )
        assert await full_name.get_attribute("aria-label") is None
        assert await full_name.get_attribute("aria-labelledby") is None
        assert await full_name.get_attribute("aria-describedby") is None
        assert await full_name.evaluate("element => element.required") is True
        assert await full_name.input_value() == ""
        assert await email.get_attribute("autocomplete") == "email"
        assert await phone.get_attribute("autocomplete") == "tel"

        snapshots[label] = {
          "html": await full_name.evaluate("element => element.outerHTML"),
          "aria": await full_name.aria_snapshot(),
        }
        assert snapshots[label]["aria"] == '- textbox "Full name Required"'

        recorder = FocusedRunRecorder(
          run_dir=run_dir,
          app_name="booking-scheduler",
          benchmark_name=f"booking-bs-sem-154-{label}",
          source_script="tests/test_booking_accessgraph_integration.py",
        )
        record = await recorder.capture_page_state(
          run.page,
          FocusedStateSpec(
            benchmark_state_id="BS-S003",
            focused_state_name="details-full-name-autocomplete-given-name",
            action_path=[
              "select Consultation",
              "select June 16 at 09:00",
              "open Booking details",
            ],
            key_validated_selectors=[
              '[data-testid="route-details"]',
              '[data-testid="details-form"]',
              'label[for="details-fullName"]',
              "input#details-fullName",
              "input#details-email",
              "input#details-phone",
            ],
          ),
        )
        recorder.write_run_artifacts()

        assert record.state_id == "state_0000"
        assert record.route == "/details"

        await email.fill("jordan.lee@example.test")
        await phone.fill("555-0134")
        await submit.click()
        assert urlsplit(run.page.url).path == "/details"
        assert await full_name.get_attribute("aria-invalid") == "true"
        assert await full_name.get_attribute("aria-describedby") == (
          "details-fullName-error"
        )
        assert await run.page.locator(
          "#details-fullName-error"
        ).inner_text() == "Full name is required."

        await full_name.fill("Jordan Lee")
        await submit.click()
        await run.page.wait_for_url("**/review")
        assert await run.page.locator(
          '[data-testid="review-customer-full-name"]'
        ).inner_text() == "Jordan Lee"

      candidates = _build_booking_candidates(
        run_dir,
        "autocomplete-purpose-mismatch",
      )
      assert len(candidates) == 3

      candidates_by_selector = {
        item["evidence"]["primary"]["form_control"]["selector"]: item
        for item in candidates
      }
      candidate = candidates_by_selector["input#details-fullName"]
      control = candidate["evidence"]["primary"]["form_control"]
      context = candidate["evidence"]["supporting"][
        "autocomplete_purpose_context_v1"
      ]
      candidate_ids[label] = candidate["candidate_id"]

      assert candidate["state_id"] == "state_0000"
      assert candidate["state_context"]["url"].endswith("/details")
      assert control["selector"] == "input#details-fullName"
      assert control["id"] == "details-fullName"
      assert control["name"] == "fullName"
      assert control["type"] == "text"
      assert control["autocomplete"] == expected_autocomplete
      assert control["required"] is True
      assert control["has_value"] is False
      assert control["label"] == "Full nameRequired"
      assert control["accessible_name"] == "Full nameRequired"
      assert context["labeling"]["visible_label"] == "Full name REQUIRED"
      assert context["labeling"]["computed_accessible_name"] == (
        "Full nameRequired"
      )
      assert context["labeling"]["label_sources"][0]["method"] == "for"
      assert context["field_purpose_evidence"]["name"] == "fullName"
      assert context["field_purpose_evidence"]["id"] == "details-fullName"
      assert context["field_purpose_evidence"][
        "form_step_or_route_context"
      ]["section_heading"] == "Customer details"
      assert context["autocomplete_evidence"] == {
        "raw_value": expected_autocomplete,
        "tokens": [expected_autocomplete],
        "section_tokens": [],
        "context_tokens": [],
        "purpose_token": expected_autocomplete,
        "recognized_purpose": expected_recognized_purpose,
        "token_category": "name",
        "is_known_token": True,
        "unknown_tokens": [],
      }
      assert candidates_by_selector["input#details-email"]["evidence"][
        "primary"
      ]["form_control"]["autocomplete"] == "email"
      assert candidates_by_selector["input#details-phone"]["evidence"][
        "primary"
      ]["form_control"]["autocomplete"] == "tel"

      _, matched_candidates = _score_booking_recovery(
        run_dir,
        config_id="booking-bs-sem-154",
        score_run_id=f"bs-sem-154-{label}",
        expected_recovered=expected_recovered,
        expected_matched_entries=expected_recovered,
      )
      if expected_recovered:
        assert matched_candidates[0]["candidate_id"] == candidate_ids[label]

    assert snapshots["clean"]["aria"] == snapshots["seeded"]["aria"]
    assert snapshots["seeded"]["html"].replace(
      'autocomplete="given-name"',
      'autocomplete="name"',
    ) == snapshots["clean"]["html"]
    assert candidate_ids["clean"] != candidate_ids["seeded"]

  _run_async(booking_browser, verify())


def test_bs_sem_155_cancellation_policy_declares_wrong_local_language(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    snapshots = {}
    cases = (
      ("clean", BOOKING_CLEAN_PROFILE, None, 0, 0),
      ("seeded", "booking-bs-sem-155", "fr", 1, 1),
    )
    policy_text = (
      "Contact the clinic at least 24 hours before your appointment if you "
      "need to cancel. Late cancellations may require a new booking."
    )

    for (
      label,
      profile,
      expected_lang,
      expected_candidates,
      expected_recovered,
    ) in cases:
      run_dir = tmp_path / label
      async with open_booking_run(
        browser,
        base_url=booking_spa.base_url,
        profile=profile,
        target_state="help",
      ) as run:
        policy = run.page.locator(
          '[data-testid="cancellation-policy-text"]'
        )
        cancellation = run.page.locator("section#cancellation")
        rescheduling = run.page.locator("section#rescheduling")

        assert urlsplit(run.page.url).path == "/help"
        assert await run.page.title() == (
          "Help & policies | Booking Scheduler Benchmark"
        )
        assert await run.page.locator("html").get_attribute("lang") == "en"
        assert await cancellation.locator("h2").inner_text() == (
          "Cancellation policy"
        )
        assert await policy.evaluate("element => element.tagName") == "P"
        assert " ".join((await policy.inner_text()).split()) == policy_text
        assert await policy.get_attribute("lang") == expected_lang
        assert await rescheduling.locator("h2").inner_text() == "Rescheduling"
        assert await rescheduling.locator("p").get_attribute("lang") is None
        assert "Staff will help you choose" in await rescheduling.inner_text()

        snapshots[label] = {
          "html": await policy.evaluate("element => element.outerHTML"),
          "aria": await policy.aria_snapshot(),
        }

        recorder = FocusedRunRecorder(
          run_dir=run_dir,
          app_name="booking-scheduler",
          benchmark_name=f"booking-bs-sem-155-{label}",
          source_script="tests/test_booking_accessgraph_integration.py",
        )
        record = await recorder.capture_page_state(
          run.page,
          FocusedStateSpec(
            benchmark_state_id="",
            focused_state_name="help-cancellation-policy-local-language",
            action_path=["open Help and policies"],
            key_validated_selectors=[
              '[data-testid="route-help"]',
              '[data-testid="help-content"]',
              "section#cancellation > h2",
              '[data-testid="cancellation-policy-text"]',
              "section#rescheduling > h2",
              "section#rescheduling > p",
            ],
          ),
        )
        recorder.write_run_artifacts()

        assert record.state_id == "state_0000"
        assert record.benchmark_state_id == ""
        assert record.route == "/help"

      _, context = _assert_neutral_state_artifacts(
        run_dir,
        "state_0000",
        dom_marker='data-testid="cancellation-policy-text"',
      )
      policy_samples = [
        sample
        for sample in context["language_samples"]
        if sample.get("context", {}).get("section_heading")
        == "Cancellation policy"
        and " ".join(sample.get("text", "").split()) == policy_text
      ]
      assert len(policy_samples) == 1
      policy_sample = policy_samples[0]
      assert policy_sample["tag"] == "p"
      assert policy_sample["root_lang"] == "en"
      assert policy_sample["local_lang"] == (expected_lang or "")
      assert policy_sample["effective_lang"] == (expected_lang or "en")
      assert " ".join(policy_sample["text"].split()) == policy_text

      candidates = _build_booking_candidates(
        run_dir,
        "language-of-parts-mismatch",
      )
      assert len(candidates) == expected_candidates

      if candidates:
        candidate = candidates[0]
        sample = candidate["evidence"]["primary"]["language_sample"]
        context_evidence = candidate["evidence"]["supporting"][
          "language_of_parts_context_v1"
        ]
        assert candidate["state_id"] == "state_0000"
        assert candidate["state_context"]["url"].endswith("/help")
        assert sample["tag"] == "p"
        assert sample["local_lang"] == "fr"
        assert sample["root_lang"] == "en"
        assert sample["effective_lang"] == "fr"
        assert " ".join(sample["text"].split()) == policy_text
        assert context_evidence["declared_language"]["local_lang"] == "fr"
        assert context_evidence["passage_text_evidence"][
          "strongest_marker_language_hint"
        ] == "en"

      _score_booking_recovery(
        run_dir,
        config_id="booking-bs-sem-155",
        score_run_id=f"bs-sem-155-{label}",
        expected_recovered=expected_recovered,
        expected_matched_entries=expected_recovered,
      )

    assert snapshots["clean"]["aria"] == snapshots["seeded"]["aria"]
    assert snapshots["seeded"]["html"].replace(
      ' lang="fr"',
      "",
    ) == snapshots["clean"]["html"]

  _run_async(booking_browser, verify())


def test_bs_sem_156_confirmation_message_declares_wrong_local_language(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    snapshots = {}
    cases = (
      ("clean", BOOKING_CLEAN_PROFILE, None, 0, 0),
      ("seeded", "booking-bs-sem-156", "es", 1, 1),
    )
    message_text = (
      "Your booking is complete. A confirmation has been prepared for the "
      "contact details below."
    )

    for (
      label,
      profile,
      expected_lang,
      expected_candidates,
      expected_recovered,
    ) in cases:
      run_dir = tmp_path / label
      async with open_booking_run(
        browser,
        base_url=booking_spa.base_url,
        profile=profile,
        target_state="confirmation",
      ) as run:
        message = run.page.locator('[data-testid="confirmation-message"]')

        assert urlsplit(run.page.url).path == "/confirmation"
        assert await run.page.title() == (
          "Booking confirmed | Booking Scheduler Benchmark"
        )
        assert await run.page.locator("html").get_attribute("lang") == "en"
        assert await run.page.get_by_role(
          "heading",
          name="Your appointment is confirmed",
        ).count() == 1
        assert await message.evaluate("element => element.tagName") == "P"
        assert " ".join((await message.inner_text()).split()) == message_text
        assert await message.get_attribute("lang") == expected_lang
        assert await run.page.locator(
          '[data-testid="confirmation-reference"]'
        ).inner_text() == "BKG-20260616-0900-CONSULTATION"
        assert await run.page.locator(
          '[data-testid="confirmation-service"]'
        ).inner_text() == "Consultation"
        assert await run.page.locator(
          '[data-testid="confirmation-customer-name"]'
        ).inner_text() == "Jordan Lee"

        snapshots[label] = {
          "html": await message.evaluate("element => element.outerHTML"),
          "aria": await message.aria_snapshot(),
          "page_html": await run.page.content(),
          "route_aria": await run.page.locator(
            '[data-testid="route-confirmation"]'
          ).aria_snapshot(),
        }

        recorder = FocusedRunRecorder(
          run_dir=run_dir,
          app_name="booking-scheduler",
          benchmark_name=f"booking-bs-sem-156-{label}",
          source_script="tests/test_booking_accessgraph_integration.py",
        )
        record = await recorder.capture_page_state(
          run.page,
          FocusedStateSpec(
            benchmark_state_id="",
            focused_state_name="confirmation-message-local-language",
            action_path=[
              "select Consultation",
              "select June 16 2026",
              "select 09:00",
              "enter valid customer details",
              "review appointment",
              "confirm booking",
            ],
            key_validated_selectors=[
              '[data-testid="route-confirmation"]',
              "#confirmation-heading",
              '[data-testid="confirmation-message"]',
              '[data-testid="confirmation-reference"]',
              '[data-testid="confirmation-service"]',
              '[data-testid="confirmation-customer-name"]',
            ],
          ),
        )
        recorder.write_run_artifacts()

        assert record.state_id == "state_0000"
        assert record.benchmark_state_id == ""
        assert record.route == "/confirmation"

      _, context = _assert_neutral_state_artifacts(
        run_dir,
        "state_0000",
        dom_marker='data-testid="confirmation-message"',
      )
      message_samples = [
        sample
        for sample in context["language_samples"]
        if 'data-testid="confirmation-message"' in sample.get("raw_html", "")
        and " ".join(sample.get("text", "").split()) == message_text
      ]
      assert len(message_samples) == 1
      message_sample = message_samples[0]
      assert message_sample["tag"] == "p"
      assert message_sample["root_lang"] == "en"
      assert message_sample["local_lang"] == (expected_lang or "")
      assert message_sample["effective_lang"] == (expected_lang or "en")
      assert " ".join(message_sample["text"].split()) == message_text

      candidates = _build_booking_candidates(
        run_dir,
        "language-of-parts-mismatch",
      )
      assert len(candidates) == expected_candidates

      if candidates:
        candidate = candidates[0]
        sample = candidate["evidence"]["primary"]["language_sample"]
        context_evidence = candidate["evidence"]["supporting"][
          "language_of_parts_context_v1"
        ]
        assert candidate["state_id"] == "state_0000"
        assert candidate["state_context"]["url"].endswith("/confirmation")
        assert sample["tag"] == "p"
        assert sample["local_lang"] == "es"
        assert sample["root_lang"] == "en"
        assert sample["effective_lang"] == "es"
        assert " ".join(sample["text"].split()) == message_text
        assert context_evidence["declared_language"]["local_lang"] == "es"
        assert context_evidence["passage_text_evidence"][
          "strongest_marker_language_hint"
        ] == "en"

      _score_booking_recovery(
        run_dir,
        config_id="booking-bs-sem-156",
        score_run_id=f"bs-sem-156-{label}",
        expected_recovered=expected_recovered,
        expected_matched_entries=expected_recovered,
      )

    assert snapshots["clean"]["aria"] == snapshots["seeded"]["aria"]
    assert snapshots["clean"]["route_aria"] == snapshots["seeded"]["route_aria"]
    assert snapshots["seeded"]["html"].replace(
      ' lang="es"',
      "",
    ) == snapshots["clean"]["html"]
    assert snapshots["seeded"]["page_html"].replace(
      ' lang="es"',
      "",
    ) == snapshots["clean"]["page_html"]

  _run_async(booking_browser, verify())


def test_bs_sem_157_preparation_instructions_declare_wrong_local_language(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    snapshots = {}
    cases = (
      ("clean", BOOKING_CLEAN_PROFILE, None, 0, 0),
      ("seeded", "booking-bs-sem-157", "de", 1, 1),
    )
    instructions_text = (
      "Arrive 10 minutes early and bring any documents or notes relevant to "
      "the service you selected."
    )

    for (
      label,
      profile,
      expected_lang,
      expected_candidates,
      expected_recovered,
    ) in cases:
      run_dir = tmp_path / label
      async with open_booking_run(
        browser,
        base_url=booking_spa.base_url,
        profile=profile,
        target_state="help",
      ) as run:
        instructions = run.page.locator(
          '[data-testid="preparation-instructions-text"]'
        )
        preparation = run.page.locator("section#preparation")
        cancellation = run.page.locator("section#cancellation")

        assert urlsplit(run.page.url).path == "/help"
        assert await run.page.title() == (
          "Help & policies | Booking Scheduler Benchmark"
        )
        assert await run.page.locator("html").get_attribute("lang") == "en"
        assert await preparation.locator("h2").inner_text() == (
          "Preparing for your appointment"
        )
        assert await instructions.evaluate("element => element.tagName") == "P"
        assert " ".join((await instructions.inner_text()).split()) == (
          instructions_text
        )
        assert await instructions.get_attribute("lang") == expected_lang
        assert await cancellation.locator("h2").inner_text() == (
          "Cancellation policy"
        )
        assert await cancellation.locator(
          '[data-testid="cancellation-policy-text"]'
        ).get_attribute("lang") is None

        snapshots[label] = {
          "html": await instructions.evaluate("element => element.outerHTML"),
          "aria": await instructions.aria_snapshot(),
          "page_html": await run.page.content(),
          "route_aria": await run.page.locator(
            '[data-testid="route-help"]'
          ).aria_snapshot(),
        }

        recorder = FocusedRunRecorder(
          run_dir=run_dir,
          app_name="booking-scheduler",
          benchmark_name=f"booking-bs-sem-157-{label}",
          source_script="tests/test_booking_accessgraph_integration.py",
        )
        record = await recorder.capture_page_state(
          run.page,
          FocusedStateSpec(
            benchmark_state_id="",
            focused_state_name="help-preparation-instructions-local-language",
            action_path=["open Help and policies"],
            key_validated_selectors=[
              '[data-testid="route-help"]',
              '[data-testid="help-content"]',
              "section#preparation > h2",
              '[data-testid="preparation-instructions-text"]',
              "section#cancellation > h2",
              '[data-testid="cancellation-policy-text"]',
            ],
          ),
        )
        recorder.write_run_artifacts()

        assert record.state_id == "state_0000"
        assert record.benchmark_state_id == ""
        assert record.route == "/help"

      _, context = _assert_neutral_state_artifacts(
        run_dir,
        "state_0000",
        dom_marker='data-testid="preparation-instructions-text"',
      )
      instruction_samples = [
        sample
        for sample in context["language_samples"]
        if 'data-testid="preparation-instructions-text"'
        in sample.get("raw_html", "")
        and " ".join(sample.get("text", "").split()) == instructions_text
      ]
      assert len(instruction_samples) == 1
      instruction_sample = instruction_samples[0]
      assert instruction_sample["tag"] == "p"
      assert instruction_sample["root_lang"] == "en"
      assert instruction_sample["local_lang"] == (expected_lang or "")
      assert instruction_sample["effective_lang"] == (expected_lang or "en")
      assert instruction_sample["context"]["section_heading"] == (
        "Preparing for your appointment"
      )

      candidates = _build_booking_candidates(
        run_dir,
        "language-of-parts-mismatch",
      )
      assert len(candidates) == expected_candidates

      if candidates:
        candidate = candidates[0]
        sample = candidate["evidence"]["primary"]["language_sample"]
        context_evidence = candidate["evidence"]["supporting"][
          "language_of_parts_context_v1"
        ]
        assert candidate["state_id"] == "state_0000"
        assert candidate["state_context"]["url"].endswith("/help")
        assert sample["tag"] == "p"
        assert sample["local_lang"] == "de"
        assert sample["root_lang"] == "en"
        assert sample["effective_lang"] == "de"
        assert " ".join(sample["text"].split()) == instructions_text
        assert context_evidence["declared_language"]["local_lang"] == "de"
        assert context_evidence["passage_text_evidence"][
          "strongest_marker_language_hint"
        ] == "en"

      _score_booking_recovery(
        run_dir,
        config_id="booking-bs-sem-157",
        score_run_id=f"bs-sem-157-{label}",
        expected_recovered=expected_recovered,
        expected_matched_entries=expected_recovered,
      )

    assert snapshots["clean"]["aria"] == snapshots["seeded"]["aria"]
    assert snapshots["clean"]["route_aria"] == snapshots["seeded"]["route_aria"]
    assert snapshots["seeded"]["html"].replace(
      ' lang="de"',
      "",
    ) == snapshots["clean"]["html"]
    assert snapshots["seeded"]["page_html"].replace(
      ' lang="de"',
      "",
    ) == snapshots["clean"]["page_html"]

  _run_async(booking_browser, verify())


def test_bs_sem_158_arrival_instructions_declare_wrong_local_language(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    snapshots = {}
    cases = (
      ("clean", BOOKING_CLEAN_PROFILE, None, 0, 0),
      ("seeded", "booking-bs-sem-158", "it", 1, 1),
    )
    instructions_text = (
      "Use the Cedar Lane entrance and check in at reception on the ground "
      "floor."
    )

    for (
      label,
      profile,
      expected_lang,
      expected_candidates,
      expected_recovered,
    ) in cases:
      run_dir = tmp_path / label
      async with open_booking_run(
        browser,
        base_url=booking_spa.base_url,
        profile=profile,
        target_state="help",
      ) as run:
        instructions = run.page.locator(
          '[data-testid="arrival-instructions-text"]'
        )
        directions = run.page.locator("section#directions")
        preparation = run.page.locator("section#preparation")

        assert urlsplit(run.page.url).path == "/help"
        assert await run.page.title() == (
          "Help & policies | Booking Scheduler Benchmark"
        )
        assert await run.page.locator("html").get_attribute("lang") == "en"
        assert await directions.locator("h2").inner_text() == "Directions"
        assert await directions.locator("strong").inner_text() == (
          "Harbor Point Clinic"
        )
        assert "24 Cedar Lane, Northbridge" in await directions.inner_text()
        assert await instructions.evaluate("element => element.tagName") == "P"
        assert " ".join((await instructions.inner_text()).split()) == (
          instructions_text
        )
        assert await instructions.get_attribute("lang") == expected_lang
        assert await preparation.locator(
          '[data-testid="preparation-instructions-text"]'
        ).get_attribute("lang") is None

        snapshots[label] = {
          "html": await instructions.evaluate("element => element.outerHTML"),
          "aria": await instructions.aria_snapshot(),
          "page_html": await run.page.content(),
          "route_aria": await run.page.locator(
            '[data-testid="route-help"]'
          ).aria_snapshot(),
        }

        recorder = FocusedRunRecorder(
          run_dir=run_dir,
          app_name="booking-scheduler",
          benchmark_name=f"booking-bs-sem-158-{label}",
          source_script="tests/test_booking_accessgraph_integration.py",
        )
        record = await recorder.capture_page_state(
          run.page,
          FocusedStateSpec(
            benchmark_state_id="",
            focused_state_name="help-arrival-instructions-local-language",
            action_path=["open Help and policies"],
            key_validated_selectors=[
              '[data-testid="route-help"]',
              '[data-testid="help-content"]',
              "section#directions > h2",
              "section#directions > p:first-of-type",
              '[data-testid="arrival-instructions-text"]',
              "section#preparation > h2",
              '[data-testid="preparation-instructions-text"]',
            ],
          ),
        )
        recorder.write_run_artifacts()

        assert record.state_id == "state_0000"
        assert record.benchmark_state_id == ""
        assert record.route == "/help"

      _, context = _assert_neutral_state_artifacts(
        run_dir,
        "state_0000",
        dom_marker='data-testid="arrival-instructions-text"',
      )
      instruction_samples = [
        sample
        for sample in context["language_samples"]
        if 'data-testid="arrival-instructions-text"'
        in sample.get("raw_html", "")
        and " ".join(sample.get("text", "").split()) == instructions_text
      ]
      assert len(instruction_samples) == 1
      instruction_sample = instruction_samples[0]
      assert instruction_sample["tag"] == "p"
      assert instruction_sample["root_lang"] == "en"
      assert instruction_sample["local_lang"] == (expected_lang or "")
      assert instruction_sample["effective_lang"] == (expected_lang or "en")
      assert instruction_sample["context"]["section_heading"] == "Directions"

      candidates = _build_booking_candidates(
        run_dir,
        "language-of-parts-mismatch",
      )
      assert len(candidates) == expected_candidates

      if candidates:
        candidate = candidates[0]
        sample = candidate["evidence"]["primary"]["language_sample"]
        context_evidence = candidate["evidence"]["supporting"][
          "language_of_parts_context_v1"
        ]
        assert candidate["state_id"] == "state_0000"
        assert candidate["state_context"]["url"].endswith("/help")
        assert sample["tag"] == "p"
        assert sample["local_lang"] == "it"
        assert sample["root_lang"] == "en"
        assert sample["effective_lang"] == "it"
        assert " ".join(sample["text"].split()) == instructions_text
        assert context_evidence["declared_language"]["local_lang"] == "it"
        assert context_evidence["passage_text_evidence"][
          "strongest_marker_language_hint"
        ] == "en"
        assert context_evidence["local_context"]["section_heading"] == (
          "Directions"
        )

      _score_booking_recovery(
        run_dir,
        config_id="booking-bs-sem-158",
        score_run_id=f"bs-sem-158-{label}",
        expected_recovered=expected_recovered,
        expected_matched_entries=expected_recovered,
      )

    assert snapshots["clean"]["aria"] == snapshots["seeded"]["aria"]
    assert snapshots["clean"]["route_aria"] == snapshots["seeded"]["route_aria"]
    assert snapshots["seeded"]["html"].replace(
      ' lang="it"',
      "",
    ) == snapshots["clean"]["html"]
    assert snapshots["seeded"]["page_html"].replace(
      ' lang="it"',
      "",
    ) == snapshots["clean"]["page_html"]

  _run_async(booking_browser, verify())


def test_bs_sem_160_confirmation_page_declares_wrong_document_language(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    snapshots = {}
    cases = (
      ("clean", BOOKING_CLEAN_PROFILE, "en", 0),
      ("seeded", "booking-bs-sem-160", "es", 1),
    )

    for label, profile, expected_lang, expected_recovered in cases:
      run_dir = tmp_path / label
      async with open_booking_run(
        browser,
        base_url=booking_spa.base_url,
        profile=profile,
        target_state="confirmation",
      ) as run:
        route = run.page.locator('[data-testid="route-confirmation"]')
        message = run.page.locator('[data-testid="confirmation-message"]')

        assert urlsplit(run.page.url).path == "/confirmation"
        assert await run.page.title() == (
          "Booking confirmed | Booking Scheduler Benchmark"
        )
        assert await run.page.locator("html").get_attribute("lang") == expected_lang
        assert await route.locator("h1").inner_text() == "Booking confirmed"
        assert await route.get_by_role(
          "heading",
          name="Your appointment is confirmed",
        ).count() == 1
        assert await route.locator("[lang]").count() == 0
        assert await message.inner_text() == (
          "Your booking is complete. A confirmation has been prepared for the "
          "contact details below."
        )
        assert await run.page.locator(
          '[data-testid="confirmation-reference"]'
        ).inner_text() == "BKG-20260616-0900-CONSULTATION"
        assert await run.page.locator(
          '[data-testid="confirmation-service"]'
        ).inner_text() == "Consultation"
        assert await run.page.locator(
          '[data-testid="confirmation-date"]'
        ).inner_text() == "June 16, 2026"
        assert await run.page.locator(
          '[data-testid="confirmation-time"]'
        ).inner_text() == "09:00"
        assert await run.page.locator(
          '[data-testid="confirmation-customer-name"]'
        ).inner_text() == "Jordan Lee"
        assert await run.page.locator(
          '[data-testid="confirmation-customer-email"]'
        ).inner_text() == "jordan.lee@example.test"

        snapshots[label] = {
          "html": await run.page.content(),
          "aria": await route.aria_snapshot(),
          "text": await route.inner_text(),
          "links": await route.locator("a").evaluate_all(
            "elements => elements.map(element => ({text: element.textContent, href: element.getAttribute('href')}))"
          ),
        }

        recorder = FocusedRunRecorder(
          run_dir=run_dir,
          app_name="booking-scheduler",
          benchmark_name=f"booking-bs-sem-160-{label}",
          source_script="tests/test_booking_accessgraph_integration.py",
        )
        record = await recorder.capture_page_state(
          run.page,
          FocusedStateSpec(
            benchmark_state_id="",
            focused_state_name="confirmation-document-language",
            action_path=[
              "select Consultation",
              "select June 16 2026",
              "select 09:00",
              "enter valid customer details",
              "review appointment",
              "confirm booking",
            ],
            key_validated_selectors=[
              '[data-testid="route-confirmation"]',
              "#confirmation-heading",
              '[data-testid="confirmation-message"]',
              '[data-testid="confirmation-reference"]',
              '[data-testid="confirmation-service"]',
              '[data-testid="confirmation-customer-name"]',
              '[data-testid="confirmation-provider-summary"]',
              '[data-testid="book-another-appointment"]',
            ],
          ),
        )
        recorder.write_run_artifacts()

        assert record.state_id == "state_0000"
        assert record.benchmark_state_id == ""
        assert record.route == "/confirmation"

      _, context = _assert_neutral_state_artifacts(
        run_dir,
        "state_0000",
        dom_marker='data-testid="route-confirmation"',
      )
      page_evidence = context["page"]
      assert page_evidence["html_lang"] == expected_lang
      assert page_evidence["document_lang"] == expected_lang
      assert page_evidence["title"] == (
        "Booking confirmed | Booking Scheduler Benchmark"
      )
      assert "Booking confirmed" in page_evidence["body_text_sample"]
      assert "Your appointment is confirmed" in page_evidence["body_text_sample"]

      candidates = _build_booking_candidates(
        run_dir,
        "lang-mismatch",
      )
      assert len(candidates) == 1
      candidate = candidates[0]
      page = candidate["evidence"]["primary"]["page"]
      context_evidence = candidate["evidence"]["supporting"][
        "lang_mismatch_context_v1"
      ]
      assert candidate["state_id"] == "state_0000"
      assert candidate["state_context"]["url"].endswith("/confirmation")
      assert page["html_lang"] == expected_lang
      assert page["document_lang"] == expected_lang
      assert page["title"] == "Booking confirmed | Booking Scheduler Benchmark"
      assert "Booking confirmed" in page["body_text_sample"]
      assert context_evidence["declared_page_language"]["route"] == (
        "/confirmation"
      )
      assert context_evidence["declared_page_language"]["html_lang"] == (
        expected_lang
      )
      assert context_evidence["page_text_evidence"][
        "strongest_marker_language_hint"
      ] == "en"
      assert "seed" not in json.dumps(candidate).casefold()
      assert "profile" not in json.dumps(candidate).casefold()

      _score_booking_recovery(
        run_dir,
        config_id="booking-bs-sem-160",
        score_run_id=f"bs-sem-160-{label}",
        expected_recovered=expected_recovered,
        expected_matched_entries=expected_recovered,
      )

    assert snapshots["clean"]["aria"] == snapshots["seeded"]["aria"]
    assert snapshots["clean"]["text"] == snapshots["seeded"]["text"]
    assert snapshots["clean"]["links"] == snapshots["seeded"]["links"]
    assert snapshots["seeded"]["html"].replace(
      '<html lang="es">',
      '<html lang="en">',
    ) == snapshots["clean"]["html"]

    async with open_booking_run(
      browser,
      base_url=booking_spa.base_url,
      profile="booking-bs-sem-160",
      target_state="review",
    ) as run:
      assert await run.page.locator("html").get_attribute("lang") == "en"
      await run.page.get_by_role("button", name="Confirm booking").click()
      await run.page.wait_for_url("**/confirmation")
      assert await run.page.locator("html").get_attribute("lang") == "es"
      await run.page.get_by_role("link", name="Directions").click()
      await run.page.wait_for_url("**/help#directions")
      assert await run.page.locator("html").get_attribute("lang") == "en"
      await run.page.go_back()
      await run.page.wait_for_url("**/confirmation")
      assert await run.page.locator("html").get_attribute("lang") == "es"

  _run_async(booking_browser, verify())


def test_bs_sem_161_details_page_declares_wrong_document_language(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    snapshots = {}
    cases = (
      ("clean", BOOKING_CLEAN_PROFILE, "en", 0),
      ("seeded", "booking-bs-sem-161", "de", 1),
    )

    for label, profile, expected_lang, expected_recovered in cases:
      run_dir = tmp_path / label
      async with open_booking_run(
        browser,
        base_url=booking_spa.base_url,
        profile=profile,
        target_state="details",
      ) as run:
        route = run.page.locator('[data-testid="route-details"]')
        form = run.page.locator('[data-testid="details-form"]')
        full_name = run.page.locator('[data-testid="details-full-name"]')
        email = run.page.locator('[data-testid="details-email"]')
        phone = run.page.locator('[data-testid="details-phone"]')

        assert urlsplit(run.page.url).path == "/details"
        assert await run.page.title() == (
          "Booking details | Booking Scheduler Benchmark"
        )
        assert await run.page.locator("html").get_attribute("lang") == expected_lang
        assert await route.locator("h1").inner_text() == "Booking details"
        assert await route.locator(".route-heading p").inner_text() == (
          "Enter required customer details for the selected appointment."
        )
        assert await route.get_by_role(
          "heading",
          name="Customer details",
        ).count() == 1
        assert await route.locator("[lang]").count() == 0
        assert await form.count() == 1
        assert await full_name.get_attribute("id") == "details-fullName"
        assert await full_name.get_attribute("name") == "fullName"
        assert await full_name.get_attribute("type") == "text"
        assert await full_name.get_attribute("autocomplete") == "name"
        assert await email.get_attribute("type") == "email"
        assert await email.get_attribute("autocomplete") == "email"
        assert await phone.get_attribute("type") == "tel"
        assert await phone.get_attribute("autocomplete") == "tel"
        assert await run.page.get_by_test_id(
          "booking-progress-details"
        ).get_attribute("aria-current") == "step"
        assert await run.page.get_by_test_id(
          "summary-service"
        ).inner_text() == "Consultation"
        assert await run.page.get_by_test_id(
          "summary-date"
        ).inner_text() == "June 16, 2026"
        assert await run.page.get_by_test_id("summary-slot").inner_text() == "09:00"

        snapshots[label] = {
          "html": await run.page.content(),
          "aria": await route.aria_snapshot(),
          "text": await route.inner_text(),
          "links": await route.locator("a").evaluate_all(
            "elements => elements.map(element => ({text: element.textContent, href: element.getAttribute('href')}))"
          ),
        }

        recorder = FocusedRunRecorder(
          run_dir=run_dir,
          app_name="booking-scheduler",
          benchmark_name=f"booking-bs-sem-161-{label}",
          source_script="tests/test_booking_accessgraph_integration.py",
        )
        record = await recorder.capture_page_state(
          run.page,
          FocusedStateSpec(
            benchmark_state_id="BS-S003",
            focused_state_name="details-document-language",
            action_path=[
              "select Consultation",
              "select June 16 2026",
              "select 09:00",
              "continue to details",
            ],
            key_validated_selectors=[
              '[data-testid="route-details"]',
              '[data-testid="booking-progress"]',
              '[data-testid="details-form"]',
              '[data-testid="details-full-name"]',
              '[data-testid="details-email"]',
              '[data-testid="details-phone"]',
              '[data-testid="summary-service"]',
              '[data-testid="summary-date"]',
              '[data-testid="summary-slot"]',
            ],
          ),
        )
        recorder.write_run_artifacts()

        assert record.state_id == "state_0000"
        assert record.benchmark_state_id == "BS-S003"
        assert record.route == "/details"

      _, context = _assert_neutral_state_artifacts(
        run_dir,
        "state_0000",
        dom_marker='data-testid="route-details"',
      )
      page_evidence = context["page"]
      assert page_evidence["html_lang"] == expected_lang
      assert page_evidence["document_lang"] == expected_lang
      assert page_evidence["title"] == (
        "Booking details | Booking Scheduler Benchmark"
      )
      assert "Booking details" in page_evidence["body_text_sample"]
      assert "Customer details" in page_evidence["body_text_sample"]

      candidates = _build_booking_candidates(
        run_dir,
        "lang-mismatch",
      )
      assert len(candidates) == 1
      candidate = candidates[0]
      page = candidate["evidence"]["primary"]["page"]
      context_evidence = candidate["evidence"]["supporting"][
        "lang_mismatch_context_v1"
      ]
      assert candidate["state_id"] == "state_0000"
      assert candidate["state_context"]["url"].endswith("/details")
      assert page["html_lang"] == expected_lang
      assert page["document_lang"] == expected_lang
      assert page["title"] == "Booking details | Booking Scheduler Benchmark"
      assert "Booking details" in page["body_text_sample"]
      assert context_evidence["declared_page_language"]["route"] == "/details"
      assert context_evidence["declared_page_language"]["html_lang"] == (
        expected_lang
      )
      assert context_evidence["page_text_evidence"][
        "strongest_marker_language_hint"
      ] == "en"
      assert "seed" not in json.dumps(candidate).casefold()
      assert "profile" not in json.dumps(candidate).casefold()

      _score_booking_recovery(
        run_dir,
        config_id="booking-bs-sem-161",
        score_run_id=f"bs-sem-161-{label}",
        expected_recovered=expected_recovered,
        expected_matched_entries=expected_recovered,
      )

    assert snapshots["clean"]["aria"] == snapshots["seeded"]["aria"]
    assert snapshots["clean"]["text"] == snapshots["seeded"]["text"]
    assert snapshots["clean"]["links"] == snapshots["seeded"]["links"]
    assert snapshots["seeded"]["html"].replace(
      '<html lang="de">',
      '<html lang="en">',
    ) == snapshots["clean"]["html"]

    async with open_booking_run(
      browser,
      base_url=booking_spa.base_url,
      profile="booking-bs-sem-161",
      target_state="schedule",
    ) as run:
      assert await run.page.locator("html").get_attribute("lang") == "en"
      await run.page.locator('[data-testid="schedule-date-input"]').fill(
        "2026-06-16"
      )
      await run.page.locator('[data-testid="slot-button-0900"]').click()
      await run.page.locator('[data-testid="continue-to-details"]').click()
      await run.page.wait_for_url("**/details")
      assert await run.page.locator("html").get_attribute("lang") == "de"
      await run.page.get_by_role("link", name="Back to schedule").click()
      await run.page.wait_for_url("**/schedule")
      assert await run.page.locator("html").get_attribute("lang") == "en"
      await run.page.go_back()
      await run.page.wait_for_url("**/details")
      assert await run.page.locator("html").get_attribute("lang") == "de"
      await run.page.go_forward()
      await run.page.wait_for_url("**/schedule")
      assert await run.page.locator("html").get_attribute("lang") == "en"

  _run_async(booking_browser, verify())


def test_bs_sem_162_review_page_declares_wrong_document_language(
  booking_spa,
  booking_browser,
  tmp_path,
):
  async def verify():
    _, browser = booking_browser
    snapshots = {}
    cases = (
      ("clean", BOOKING_CLEAN_PROFILE, "en", 0),
      ("seeded", "booking-bs-sem-162", "fr", 1),
    )

    for label, profile, expected_lang, expected_recovered in cases:
      run_dir = tmp_path / label
      async with open_booking_run(
        browser,
        base_url=booking_spa.base_url,
        profile=profile,
        target_state="review",
      ) as run:
        route = run.page.locator('[data-testid="route-review"]')
        review_note = run.page.locator('[data-testid="review-only-note"]')

        assert urlsplit(run.page.url).path == "/review"
        assert await run.page.title() == (
          "Review appointment | Booking Scheduler Benchmark"
        )
        assert await run.page.locator("html").get_attribute("lang") == expected_lang
        assert await route.locator("h1").inner_text() == "Review appointment"
        assert await route.locator(".route-heading p").inner_text() == (
          "Review the selected appointment and submitted customer details."
        )
        assert await route.get_by_role(
          "heading",
          name="Review appointment details",
        ).count() == 1
        assert await route.locator("[lang]").count() == 0
        assert await review_note.inner_text() == (
          "Review only. No appointment has been confirmed yet."
        )
        assert await run.page.get_by_test_id(
          "booking-progress-review"
        ).get_attribute("aria-current") == "step"
        assert await run.page.get_by_test_id(
          "review-service-name"
        ).inner_text() == "Consultation"
        assert await run.page.get_by_test_id(
          "review-date"
        ).inner_text() == "June 16, 2026"
        assert await run.page.get_by_test_id("review-slot").inner_text() == "09:00"
        assert await run.page.get_by_test_id(
          "review-customer-full-name"
        ).inner_text() == "Jordan Lee"
        assert await run.page.get_by_test_id(
          "review-customer-email"
        ).inner_text() == "jordan.lee@example.test"
        assert await run.page.get_by_test_id(
          "review-customer-phone"
        ).inner_text() == "555-0134"
        assert await run.page.get_by_role(
          "button",
          name="Confirm booking",
          exact=True,
        ).count() == 1

        snapshots[label] = {
          "html": await run.page.content(),
          "aria": await route.aria_snapshot(),
          "text": await route.inner_text(),
          "links": await route.locator("a").evaluate_all(
            "elements => elements.map(element => ({text: element.textContent, href: element.getAttribute('href')}))"
          ),
        }

        recorder = FocusedRunRecorder(
          run_dir=run_dir,
          app_name="booking-scheduler",
          benchmark_name=f"booking-bs-sem-162-{label}",
          source_script="tests/test_booking_accessgraph_integration.py",
        )
        record = await recorder.capture_page_state(
          run.page,
          FocusedStateSpec(
            benchmark_state_id="BS-S004",
            focused_state_name="review-document-language",
            action_path=[
              "select Consultation",
              "select June 16 2026",
              "select 09:00",
              "enter valid customer details",
              "continue to review",
            ],
            key_validated_selectors=[
              '[data-testid="route-review"]',
              '[data-testid="booking-progress"]',
              '[data-testid="review-only-note"]',
              '[data-testid="review-service-summary"]',
              '[data-testid="review-schedule-summary"]',
              '[data-testid="review-customer-summary"]',
              '[data-testid="review-provider-summary"]',
              '[data-testid="confirm-booking"]',
            ],
          ),
        )
        recorder.write_run_artifacts()

        assert record.state_id == "state_0000"
        assert record.benchmark_state_id == "BS-S004"
        assert record.route == "/review"

      _, context = _assert_neutral_state_artifacts(
        run_dir,
        "state_0000",
        dom_marker='data-testid="route-review"',
      )
      page_evidence = context["page"]
      assert page_evidence["html_lang"] == expected_lang
      assert page_evidence["document_lang"] == expected_lang
      assert page_evidence["title"] == (
        "Review appointment | Booking Scheduler Benchmark"
      )
      assert "Review appointment" in page_evidence["body_text_sample"]

      candidates = _build_booking_candidates(
        run_dir,
        "lang-mismatch",
      )
      assert len(candidates) == 1
      candidate = candidates[0]
      page = candidate["evidence"]["primary"]["page"]
      context_evidence = candidate["evidence"]["supporting"][
        "lang_mismatch_context_v1"
      ]
      assert candidate["state_id"] == "state_0000"
      assert candidate["state_context"]["url"].endswith("/review")
      assert page["html_lang"] == expected_lang
      assert page["document_lang"] == expected_lang
      assert page["title"] == "Review appointment | Booking Scheduler Benchmark"
      assert "Review appointment" in page["body_text_sample"]
      assert context_evidence["declared_page_language"]["route"] == "/review"
      assert context_evidence["declared_page_language"]["html_lang"] == (
        expected_lang
      )
      assert context_evidence["page_text_evidence"][
        "strongest_marker_language_hint"
      ] == "en"
      assert "seed" not in json.dumps(candidate).casefold()
      assert "profile" not in json.dumps(candidate).casefold()

      _score_booking_recovery(
        run_dir,
        config_id="booking-bs-sem-162",
        score_run_id=f"bs-sem-162-{label}",
        expected_recovered=expected_recovered,
        expected_matched_entries=expected_recovered,
      )

    assert snapshots["clean"]["aria"] == snapshots["seeded"]["aria"]
    assert snapshots["clean"]["text"] == snapshots["seeded"]["text"]
    assert snapshots["clean"]["links"] == snapshots["seeded"]["links"]
    assert snapshots["seeded"]["html"].replace(
      '<html lang="fr">',
      '<html lang="en">',
    ) == snapshots["clean"]["html"]

    async with open_booking_run(
      browser,
      base_url=booking_spa.base_url,
      profile="booking-bs-sem-162",
      target_state="details",
    ) as run:
      assert await run.page.locator("html").get_attribute("lang") == "en"
      await run.page.locator('[data-testid="details-full-name"]').fill(
        "Jordan Lee"
      )
      await run.page.locator('[data-testid="details-email"]').fill(
        "jordan.lee@example.test"
      )
      await run.page.locator('[data-testid="details-phone"]').fill("555-0134")
      await run.page.locator('[data-testid="details-submit"]').click()
      await run.page.wait_for_url("**/review")
      assert await run.page.locator("html").get_attribute("lang") == "fr"
      await run.page.get_by_role("link", name="Edit details").click()
      await run.page.wait_for_url("**/details")
      assert await run.page.locator("html").get_attribute("lang") == "en"
      await run.page.go_back()
      await run.page.wait_for_url("**/review")
      assert await run.page.locator("html").get_attribute("lang") == "fr"
      await run.page.go_forward()
      await run.page.wait_for_url("**/details")
      assert await run.page.locator("html").get_attribute("lang") == "en"

  _run_async(booking_browser, verify())
