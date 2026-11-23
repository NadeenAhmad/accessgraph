class CrawlerError(Exception):
  """Base class for crawler-specific exceptions."""


class NavigationTimeout(CrawlerError):
  """Raised when page navigation exceeds the allowed timeout."""
