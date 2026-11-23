from pathlib import Path


DEFAULT_CRAWL_SOURCE_PATHS = (
  Path("src/crawler/crawl/entrypoint.py"),
  Path("src/crawler/crawl/crawl_session.py"),
  Path("src/crawler/state/state_extractor.py"),
  Path("src/crawler/evidence/extractor.py"),
)


def _default_crawl_source() -> str:
  return "\n".join(path.read_text(encoding="utf-8") for path in DEFAULT_CRAWL_SOURCE_PATHS)


def test_default_crawl_code_does_not_import_semantic_pipeline_or_later_stages():
  combined = _default_crawl_source()

  assert "build_semantic_pipeline" not in combined
  assert "semantic_pipeline" not in combined
  assert "semantic_handlers" not in combined
  assert "src.crawler.semantic" not in combined
  assert "run_semantic_confirmation" not in combined
  assert "run_semantic_page_report" not in combined
  assert "SemanticJsonlArtifactWriter" not in combined
  assert "scout" not in combined.lower()


def test_default_crawl_code_does_not_write_taxonomy_candidate_jsonl_files():
  combined = _default_crawl_source()

  assert "_candidates.jsonl" not in combined
  assert "image_alt_candidates.jsonl" not in combined
  assert "link_text_mismatch_candidates.jsonl" not in combined
  assert "button_label_mismatch_candidates.jsonl" not in combined
  assert "form_label_mismatch_candidates.jsonl" not in combined
