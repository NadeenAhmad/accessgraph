from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
  from playwright.async_api import Page
else:
  Page = Any

from ..graph.graph import StateGraph
from .crawl_config import CrawlConfig
from .crawl_session import CrawlSession


async def run_crawl(
  page: Page,
  start_url: str,
  run_dir: Path,
  cfg: CrawlConfig,
  llm_client: Any | None = None,
) -> StateGraph:
  """
  Run one bounded crawler session and return the discovered state graph.
  `llm_client` optionally replaces the exploration model client (e.g. a budget-guarded wrapper).
  """
  session = CrawlSession(
    page=page,
    start_url=start_url,
    run_dir=run_dir,
    cfg=cfg,
    llm_client=llm_client,
  )
  return await session.crawl()


__all__ = ["CrawlConfig", "run_crawl"]
