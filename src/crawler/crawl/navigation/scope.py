from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from ..crawl_config import CrawlScopePolicy


def _normalize_host(host: str) -> str:
  return host.strip().lower().strip(".")


def _base_domain_for_scope(host: str) -> str:
  normalized = _normalize_host(host)
  if normalized.startswith("www."):
    return normalized[4:]
  return normalized


def _origin_for_scope(url: str) -> tuple[str, str, int | None]:
  parsed = urlparse(url)
  scheme = parsed.scheme.lower()
  host = _normalize_host(parsed.hostname or "")
  port = parsed.port
  if port is None:
    if scheme == "http":
      port = 80
    elif scheme == "https":
      port = 443
  return scheme, host, port


@dataclass(frozen=True)
class CrawlScope:
  policy: CrawlScopePolicy
  start_host: str
  start_base_domain: str
  start_origin: tuple[str, str, int | None]

  @classmethod
  def from_start_url(cls, start_url: str, policy: CrawlScopePolicy) -> CrawlScope:
    start_host = _normalize_host(urlparse(start_url).hostname or "")
    return cls(
      policy=policy,
      start_host=start_host,
      start_base_domain=_base_domain_for_scope(start_host),
      start_origin=_origin_for_scope(start_url),
    )

  def contains(self, target_url: str) -> bool:
    if self.policy == "any":
      return True

    if self.policy == "same_origin":
      target_origin = _origin_for_scope(target_url)
      if not target_origin[1]:
        return True
      return target_origin == self.start_origin

    target_host = _normalize_host(urlparse(target_url).hostname or "")
    if not target_host:
      # Relative or odd URL forms should not be blocked here.
      return True

    if self.policy == "same_host":
      return target_host == self.start_host

    if self.policy == "same_domain":
      if not self.start_base_domain:
        return True
      return target_host == self.start_base_domain or target_host.endswith(f".{self.start_base_domain}")

    return False


__all__ = ["CrawlScope"]
