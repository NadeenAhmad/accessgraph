from __future__ import annotations

from types import SimpleNamespace

from src.crawler.state.hashing import html_hash, raw_html_state_identity_hash


class FakePage:
  def __init__(self, url: str):
    self.url = url

  async def content(self) -> str:
    return "<html><body>same-dom</body></html>"

  async def wait_for_load_state(self, *_args, **_kwargs) -> None:
    return None


async def make_state_artifact(
  page_obj: FakePage,
  state_id: str,
  *,
  route: str,
  include_dom_identity_hash: bool = False,
) -> SimpleNamespace:
  html = await page_obj.content()
  payload: dict[str, object] = {
    "url": page_obj.url,
    "html_hash": html_hash(html),
    "title": state_id,
    "route": route,
  }
  if include_dom_identity_hash:
    payload["dom_identity_hash"] = raw_html_state_identity_hash(html)
  return SimpleNamespace(**payload)
