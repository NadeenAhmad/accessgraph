from __future__ import annotations

import argparse
import json
import mimetypes
import socket
import sys
import webbrowser
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
  sys.path.insert(0, str(REPO_ROOT))

from scripts.benchmarks.case_metadata import (
  LAUNCHABLE_STATUSES,
  BenchmarkCase,
  CaseConfigurationError,
  CaseMetadataError,
  UnknownBenchmarkCaseError,
  load_tracker_cases,
  resolve_case,
)
from scripts.benchmarks.explorer.session import (
  BenchmarkExplorerSession,
  SessionError,
  SUPPORTED_EXPLORER_APPS,
)


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
STATIC_ROOT = Path(__file__).resolve().parent / "static"

LIST_FIELDS = (
  "case_id",
  "violation_type",
  "app",
  "short_description",
  "pattern",
  "tier",
  "evidence_state",
  "status",
)

DETAIL_FIELDS = (
  "case_id",
  "violation_type",
  "app",
  "status",
  "tier",
  "evidence_state",
  "short_description",
  "pattern",
  "baseline",
  "mutation",
  "why_unambiguous",
  "interaction_path",
)


@dataclass(frozen=True)
class ApiError(Exception):
  status: HTTPStatus
  message: str
  code: str = "error"


def main(argv: list[str] | None = None) -> int:
  args = _parse_args(argv)
  port = choose_port(DEFAULT_HOST, args.port)
  session = BenchmarkExplorerSession(skip_build=args.skip_build, logger=print)
  server = create_server(DEFAULT_HOST, port, session=session)
  url = f"http://{DEFAULT_HOST}:{port}/"
  print("AccessGraph Benchmark SPA Explorer")
  print(f"Serving: {url}")
  print("Press Ctrl+C to stop.")
  if not args.no_open:
    webbrowser.open(url)
  try:
    server.serve_forever()
  except KeyboardInterrupt:
    print("\nStopping Benchmark SPA Explorer.")
  finally:
    session.shutdown()
    server.server_close()
  return 0


def create_server(
  host: str,
  port: int,
  *,
  session: BenchmarkExplorerSession | None = None,
) -> ThreadingHTTPServer:
  explorer_session = session or BenchmarkExplorerSession(logger=print)

  class ExplorerHandler(BenchmarkExplorerRequestHandler):
    session = explorer_session

  return ThreadingHTTPServer((host, port), ExplorerHandler)


class BenchmarkExplorerRequestHandler(BaseHTTPRequestHandler):
  session: BenchmarkExplorerSession

  def do_GET(self) -> None:
    try:
      parsed = urlparse(self.path)
      if parsed.path == "/api/cases":
        self._send_json({"cases": list_case_payloads()})
        return
      if parsed.path.startswith("/api/cases/"):
        case_id = unquote(parsed.path.removeprefix("/api/cases/"))
        self._send_json({"case": case_payload(case_id, detail=True)})
        return
      if parsed.path == "/api/session/status":
        self._send_json({"session": self.session.status().to_dict()})
        return
      self._serve_static(parsed.path)
    except ApiError as exc:
      self._send_json(
        {"error": {"code": exc.code, "message": exc.message}},
        status=exc.status,
      )
    except Exception as exc:
      print(f"Benchmark SPA Explorer server error: {exc}", file=sys.stderr)
      self._send_json(
        {
          "error": {
            "code": "server_error",
            "message": "Benchmark SPA Explorer server error.",
          }
        },
        status=HTTPStatus.INTERNAL_SERVER_ERROR,
      )

  def do_POST(self) -> None:
    try:
      parsed = urlparse(self.path)
      if parsed.path == "/api/session/open":
        body = self._read_json_body()
        case_id = body.get("case_id")
        if not isinstance(case_id, str) or not case_id:
          raise ApiError(
            HTTPStatus.BAD_REQUEST,
            "Request body must include case_id.",
            "missing_case_id",
          )
        payload = case_payload(case_id, detail=True)
        if not payload["launchable"]:
          raise ApiError(
            HTTPStatus.CONFLICT,
            str(payload["launch_error"]),
            "case_not_launchable",
          )
        benchmark_case = resolve_case(case_id)
        status = self.session.open_case(benchmark_case)
        self._send_json({"case": payload, "session": status.to_dict()})
        return
      if parsed.path == "/api/session/stop":
        status = self.session.stop()
        self._send_json({"session": status.to_dict()})
        return
      raise ApiError(HTTPStatus.NOT_FOUND, "Unknown endpoint.", "not_found")
    except ApiError as exc:
      self._send_json(
        {"error": {"code": exc.code, "message": exc.message}},
        status=exc.status,
      )
    except (CaseMetadataError, SessionError) as exc:
      print(f"Benchmark SPA Explorer request failed: {exc}", file=sys.stderr)
      self._send_json(
        {"error": {"code": "request_failed", "message": str(exc)}},
        status=HTTPStatus.INTERNAL_SERVER_ERROR,
      )
    except Exception as exc:
      print(f"Benchmark SPA Explorer server error: {exc}", file=sys.stderr)
      self._send_json(
        {
          "error": {
            "code": "server_error",
            "message": "Benchmark SPA Explorer server error.",
          }
        },
        status=HTTPStatus.INTERNAL_SERVER_ERROR,
      )

  def log_message(self, format: str, *args: object) -> None:
    return

  def _send_json(self, payload: dict[str, Any], *, status: HTTPStatus = HTTPStatus.OK) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    self.send_response(status)
    self.send_header("Content-Type", "application/json; charset=utf-8")
    self.send_header("Content-Length", str(len(data)))
    self.end_headers()
    self.wfile.write(data)

  def _serve_static(self, path: str) -> None:
    if path in ("", "/"):
      filename = "index.html"
    else:
      filename = path.lstrip("/")
    if "/" in filename or "\\" in filename:
      raise ApiError(HTTPStatus.NOT_FOUND, "Static file not found.", "not_found")
    file_path = STATIC_ROOT / filename
    if not file_path.exists() or not file_path.is_file():
      raise ApiError(HTTPStatus.NOT_FOUND, "Static file not found.", "not_found")
    data = file_path.read_bytes()
    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    self.send_response(HTTPStatus.OK)
    self.send_header("Content-Type", content_type)
    self.send_header("Content-Length", str(len(data)))
    self.end_headers()
    self.wfile.write(data)

  def _read_json_body(self) -> dict[str, Any]:
    length = int(self.headers.get("Content-Length", "0") or "0")
    if length <= 0:
      return {}
    try:
      data = self.rfile.read(length).decode("utf-8")
      parsed = json.loads(data)
    except json.JSONDecodeError as exc:
      raise ApiError(HTTPStatus.BAD_REQUEST, "Request body is not valid JSON.", "bad_json") from exc
    if not isinstance(parsed, dict):
      raise ApiError(HTTPStatus.BAD_REQUEST, "Request body must be a JSON object.", "bad_json")
    return parsed


def list_case_payloads() -> list[dict[str, Any]]:
  tracker_rows = load_tracker_cases()
  return [
    case_payload(case_id, detail=False)
    for case_id in sorted(tracker_rows, key=_case_sort_key)
  ]


def case_payload(case_id: str, *, detail: bool) -> dict[str, Any]:
  try:
    benchmark_case = resolve_case(case_id)
  except UnknownBenchmarkCaseError as exc:
    raise ApiError(HTTPStatus.NOT_FOUND, str(exc), "unknown_case") from exc
  except CaseConfigurationError as exc:
    return _configuration_error_payload(case_id, str(exc), detail=detail)
  fields = DETAIL_FIELDS if detail else LIST_FIELDS
  payload = {field: getattr(benchmark_case, field) for field in fields}
  payload.update(_launchability_payload(benchmark_case))
  if detail:
    payload["profile"] = benchmark_case.executable_profile
  return payload


def _configuration_error_payload(
  case_id: str,
  message: str,
  *,
  detail: bool,
) -> dict[str, Any]:
  tracker_rows = load_tracker_cases()
  row = tracker_rows.get(case_id)
  if row is None:
    raise ApiError(HTTPStatus.NOT_FOUND, f"Unknown benchmark case: {case_id}", "unknown_case")
  fields = DETAIL_FIELDS if detail else LIST_FIELDS
  payload = {field: row.get(field, "") for field in fields}
  payload.update({
    "launchable": False,
    "launch_error": f"Configuration error: {message}",
    "config_error": True,
  })
  if detail:
    payload["profile"] = None
  return payload


def _launchability_payload(benchmark_case: BenchmarkCase) -> dict[str, Any]:
  config_error = False
  launch_error: str | None = None
  launchable = False

  if benchmark_case.status == "planned":
    launch_error = "Not implemented yet."
  elif benchmark_case.status not in LAUNCHABLE_STATUSES:
    launch_error = f"Status {benchmark_case.status!r} is not launchable."
  elif benchmark_case.executable_profile is None:
    config_error = True
    launch_error = "Configuration error: executable registry configuration is missing."
  elif benchmark_case.app not in SUPPORTED_EXPLORER_APPS:
    launch_error = "Explorer launcher not available for this app yet."
  else:
    launchable = True

  return {
    "launchable": launchable,
    "launch_error": launch_error,
    "config_error": config_error,
  }


def choose_port(host: str, preferred_port: int) -> int:
  if _port_available(host, preferred_port):
    return preferred_port
  with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.bind((host, 0))
    return int(sock.getsockname()[1])


def _port_available(host: str, port: int) -> bool:
  with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    try:
      sock.bind((host, port))
    except OSError:
      return False
    return True


def _case_sort_key(case_id: str) -> tuple[str, int | str]:
  prefix, _, suffix = case_id.rpartition("-")
  if suffix.isdigit():
    return (prefix, int(suffix))
  return (case_id, case_id)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
  parser = argparse.ArgumentParser(
    description="Serve the local AccessGraph Benchmark SPA Explorer."
  )
  parser.add_argument(
    "--port",
    type=int,
    default=DEFAULT_PORT,
    help=f"Preferred local port. Falls back to a free port if busy. Default: {DEFAULT_PORT}.",
  )
  parser.add_argument(
    "--no-open",
    action="store_true",
    help="Print the Explorer URL without opening the default browser.",
  )
  parser.add_argument(
    "--skip-build",
    action="store_true",
    help="Use existing SPA dist output when launching variants.",
  )
  return parser.parse_args(argv)


if __name__ == "__main__":
  raise SystemExit(main())
