import json

from src.analysis.candidates.destination_peek import _needs_peek, _peekable, _same_name_targets


def test_peekable_schemes():
  assert _peekable("https://example.org/a")
  assert _peekable("file:///site/contact-us.html?page=3")
  assert not _peekable("file:///etc/passwd")
  assert not _peekable("mailto:a@b.c")


def test_same_name_targets_resolve_against_the_page(tmp_path):
  state = tmp_path / "states" / "s0"
  state.mkdir(parents=True)
  (state / "metadata.json").write_text(json.dumps({"url": "file:///site/pages/p.html"}))
  candidate = {"candidate_type": "link-text-mismatch", "state_id": "s0", "evidence": {"supporting": {
    "link_destination_context_v1": {"resolved_url": "file:///site/assets/c.html?page=4"},
    "links_with_the_same_name": [{"href": "../assets/c.html?page=3"}, {"href": "tel:000"}]}}}
  assert _needs_peek(candidate) == "file:///site/assets/c.html?page=4"
  targets = _same_name_targets(tmp_path, candidate)
  assert [url for _, url in targets] == ["file:///site/assets/c.html?page=3"]
