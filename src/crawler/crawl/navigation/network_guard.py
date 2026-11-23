"""Network guard (C1): during exploration, block every request that could write somewhere else.

Requests other than GET/HEAD/OPTIONS are aborted unless their host is in `allow_hosts`. This keeps exploration
from changing data on public sites or on external APIs that a local app talks to (e.g. a demo backend); every
blocked request is recorded.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass
class NetworkGuard:
  allow_hosts: tuple[str, ...] = ()
  blocked: list[dict[str, str]] = field(default_factory=list)

  def allows(self, method: str, url: str) -> bool:
    if method.upper() in SAFE_METHODS:
      return True
    host = (urlparse(url).hostname or "").lower()
    return host in {h.lower() for h in self.allow_hosts}

  async def handle(self, route: Any) -> None:
    request = route.request
    if self.allows(request.method, request.url):
      await route.fallback()
      return
    self.blocked.append({"method": request.method, "url": request.url[:300]})
    await route.abort("blockedbyclient")

  async def install(self, page: Any) -> None:
    await page.route("**/*", self.handle)
