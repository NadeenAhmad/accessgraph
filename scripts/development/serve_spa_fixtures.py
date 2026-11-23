from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Iterator

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "spas"


class FixtureRequestHandler(SimpleHTTPRequestHandler):
  def end_headers(self) -> None:
    self.send_header("Cache-Control", "no-store, max-age=0")
    super().end_headers()

  def log_message(self, _format: str, *_args: object) -> None:
    return


@dataclass(frozen=True)
class FixtureServer:
  server: ThreadingHTTPServer
  thread: Thread
  root: Path
  base_url: str

  def stop(self) -> None:
    self.server.shutdown()
    self.server.server_close()
    self.thread.join(timeout=5)


@contextmanager
def serve_fixture_root(
  root: Path | None = None,
  *,
  host: str = "127.0.0.1",
  port: int = 0,
) -> Iterator[FixtureServer]:
  fixture_root = (root or FIXTURE_ROOT).resolve()
  if not fixture_root.exists():
    raise FileNotFoundError(f"SPA fixture root does not exist: {fixture_root}")

  handler = partial(FixtureRequestHandler, directory=str(fixture_root))
  httpd = ThreadingHTTPServer((host, port), handler)
  actual_host, actual_port = httpd.server_address[:2]
  thread = Thread(target=httpd.serve_forever, name="spa-fixture-server", daemon=True)
  thread.start()

  fixture_server = FixtureServer(
    server=httpd,
    thread=thread,
    root=fixture_root,
    base_url=f"http://{actual_host}:{actual_port}",
  )
  try:
    yield fixture_server
  finally:
    fixture_server.stop()


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description="Serve local SPA crawler fixtures.")
  parser.add_argument("--host", default="127.0.0.1")
  parser.add_argument("--port", type=int, default=8008)
  parser.add_argument("--root", type=Path, default=FIXTURE_ROOT)
  args = parser.parse_args(argv)

  root = args.root.resolve()
  if not root.exists():
    parser.error(f"fixture root does not exist: {root}")

  handler = partial(FixtureRequestHandler, directory=str(root))
  httpd = ThreadingHTTPServer((args.host, args.port), handler)
  host, port = httpd.server_address[:2]
  print(f"Serving SPA fixtures from {root}")
  print(f"Open http://{host}:{port}/")
  try:
    httpd.serve_forever()
  except KeyboardInterrupt:
    print()
  finally:
    httpd.server_close()
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
