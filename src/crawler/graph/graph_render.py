from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .graph import StateGraph, state_node_dom_identity_hash

DOT_HEADER_LINES = [
  "digraph StateGraph {",
  ' rankdir="LR";',
  "  node [shape=box];",
]


def _escape_dot_label(value: str) -> str:
  return value.replace('"', '\\"')


def _node_label(state_id: str, meta: dict[str, object]) -> str:
  dom_identity_hash = state_node_dom_identity_hash(meta)
  short_hash = dom_identity_hash[:8]
  route = str(meta.get("route", ""))
  title = str(meta.get("title", ""))
  return _escape_dot_label(f"{state_id}\\n{route}\\n{title}\\n{short_hash}")


def _edge_label(edge: dict[str, object]) -> str:
  action = edge.get("action", {})
  if not isinstance(action, dict):
    action = {}
  text = action.get("text", "") or action.get("type", "")
  return _escape_dot_label(str(text))


def export_dot(graph: StateGraph, dot_path: Path) -> None:
  lines = list(DOT_HEADER_LINES)

  for state_id, meta in graph.nodes.items():
    label = _node_label(state_id, meta)
    lines.append(f'  "{state_id}" [label="{label}"]')

  for edge in graph.edges:
    src = str(edge.get("from", ""))
    dst = str(edge.get("to", ""))
    edge_text = _edge_label(edge)
    if edge_text:
      lines.append(f'  "{src}" -> "{dst}" [label="{edge_text}"];')
      continue
    lines.append(f'  "{src}" -> "{dst}";')

  lines.append("}")
  dot_path.write_text("\n".join(lines), encoding="utf-8")


def render_png_from_dot(dot_path: Path, png_path: Path) -> bool:
  """
  Returns True if PNG was rendered (Graphviz 'dot' exists), else False.
  """
  dot_exe = shutil.which("dot")
  if not dot_exe:
    return False

  subprocess.run([dot_exe, "-Tpng", str(dot_path), "-o", str(png_path)], check=False)
  return png_path.exists()
