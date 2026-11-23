from src.crawler.crawl.navigation.scope import CrawlScope


def test_same_origin_allows_matching_scheme_host_and_port():
  scope = CrawlScope.from_start_url("https://Example.test/app", "same_origin")

  assert scope.contains("https://example.test/other")


def test_same_origin_blocks_different_port():
  scope = CrawlScope.from_start_url("http://example.test:8080/app", "same_origin")

  assert not scope.contains("http://example.test:9090/app")


def test_same_origin_treats_default_ports_as_equivalent():
  scope = CrawlScope.from_start_url("http://example.test/app", "same_origin")

  assert scope.contains("http://example.test:80/other")


def test_same_host_ignores_scheme_and_port_but_blocks_external_host():
  scope = CrawlScope.from_start_url("https://example.test:8443/app", "same_host")

  assert scope.contains("http://example.test:8080/other")
  assert not scope.contains("https://external.test/other")


def test_same_domain_allows_www_normalized_host_and_subdomains():
  scope = CrawlScope.from_start_url("https://www.example.test/app", "same_domain")

  assert scope.contains("https://example.test/other")
  assert scope.contains("https://docs.example.test/other")
  assert scope.contains("https://www.example.test/other")


def test_same_domain_blocks_external_domain():
  scope = CrawlScope.from_start_url("https://www.example.test/app", "same_domain")

  assert not scope.contains("https://example.org/other")


def test_hostless_relative_urls_are_allowed_for_scoped_crawls():
  scope = CrawlScope.from_start_url("https://example.test/app", "same_origin")

  assert scope.contains("/relative/path")
  assert scope.contains("#section")


def test_any_policy_allows_external_urls():
  scope = CrawlScope.from_start_url("https://example.test/app", "any")

  assert scope.contains("https://external.test/other")
