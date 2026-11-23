"""Same-page link targets (C3, deterministic): what an in-page link (`#id`) points to.

For a link to a fragment on the same page, the target section's heading and the first 200 characters of its
text are read from the saved DOM of the same state. This is state-local evidence, so it is shown in every
context mode. Hash-router fragments (`#/route`) are routes, not in-page targets, and are skipped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

SCHEMA_VERSION = "same_page_target_v1"
TEXT_LIMIT = 200
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
SKIP_TEXT_TAGS = {"script", "style", "noscript", "template"}


@dataclass
class _Node:
  tag: str
  attrs: dict[str, str]
  parent: int | None
  start: int                     # index into the document text stream where this element starts
  end: int = -1
  children: list[int] = field(default_factory=list)


class _Tree(HTMLParser):
  def __init__(self) -> None:
    super().__init__(convert_charrefs=True)
    self.nodes: list[_Node] = []
    self.stack: list[int] = []
    self.chunks: list[tuple[int, str]] = []   # (owner node, text)
    self._skip = 0

  def handle_starttag(self, tag, attrs):
    parent = self.stack[-1] if self.stack else None
    node = _Node(tag, {k: (v or "") for k, v in attrs}, parent, len(self.chunks))
    self.nodes.append(node)
    index = len(self.nodes) - 1
    if parent is not None:
      self.nodes[parent].children.append(index)
    if tag in SKIP_TEXT_TAGS:
      self._skip += 1
    if tag in VOID_TAGS:
      node.end = len(self.chunks)
    else:
      self.stack.append(index)

  def handle_endtag(self, tag):
    for pos in range(len(self.stack) - 1, -1, -1):
      if self.nodes[self.stack[pos]].tag == tag:
        for closed in self.stack[pos:]:
          self.nodes[closed].end = len(self.chunks)
        del self.stack[pos:]
        break
    if tag in SKIP_TEXT_TAGS and self._skip:
      self._skip -= 1

  def handle_data(self, data):
    if self._skip or not data.strip():
      return
    self.chunks.append((self.stack[-1] if self.stack else -1, data))

  def close(self):
    super().close()
    for index in self.stack:
      self.nodes[index].end = len(self.chunks)


def _text(tree: _Tree, start: int, end: int) -> str:
  return " ".join(" ".join(chunk for _, chunk in tree.chunks[start:end]).split())


def _is_heading(node: _Node) -> bool:
  return node.tag in HEADING_TAGS or node.attrs.get("role") == "heading"


def _descends_from(tree: _Tree, index: int, ancestor: int) -> bool:
  parent = tree.nodes[index].parent
  while parent is not None:
    if parent == ancestor:
      return True
    parent = tree.nodes[parent].parent
  return False


_CACHE: dict[Path, _Tree] = {}


def _tree(dom_path: Path) -> _Tree | None:
  if dom_path not in _CACHE:
    if not dom_path.exists():
      return None
    tree = _Tree()
    tree.feed(dom_path.read_text(encoding="utf-8", errors="replace"))
    tree.close()
    _CACHE[dom_path] = tree
  return _CACHE[dom_path]


def same_page_target(dom_path: Path, fragment: str) -> dict[str, object] | None:
  if not fragment or fragment.startswith(("/", "!")):
    return None
  tree = _tree(dom_path)
  if tree is None:
    return None
  target = next((i for i, n in enumerate(tree.nodes) if n.attrs.get("id") == fragment), None)
  if target is None:
    target = next((i for i, n in enumerate(tree.nodes) if n.tag == "a" and n.attrs.get("name") == fragment), None)
  if target is None:
    return {"schema_version": SCHEMA_VERSION, "fragment": fragment, "target_found": False}
  node = tree.nodes[target]
  heading, heading_basis = "", ""
  if _is_heading(node):
    heading, heading_basis = _text(tree, node.start, node.end), "target_is_heading"
  else:
    inner = next((i for i in range(target + 1, len(tree.nodes))
                  if _is_heading(tree.nodes[i]) and _descends_from(tree, i, target)), None)
    if inner is not None:
      heading, heading_basis = _text(tree, tree.nodes[inner].start, tree.nodes[inner].end), "first_heading_inside_target"
    else:
      before = [n for n in tree.nodes[:target] if _is_heading(n) and n.end <= node.start]
      if before:
        heading, heading_basis = _text(tree, before[-1].start, before[-1].end), "nearest_preceding_heading"
  excerpt = _text(tree, node.start, node.end)
  basis = "target_text"
  if not excerpt:  # empty anchor: use the text that follows it
    excerpt, basis = _text(tree, node.end, min(len(tree.chunks), node.end + 40)), "text_after_empty_target"
  return {"schema_version": SCHEMA_VERSION, "fragment": fragment, "target_found": True, "target_tag": node.tag,
          "target_heading": heading[:160], "heading_basis": heading_basis, "text_excerpt": excerpt[:TEXT_LIMIT],
          "excerpt_basis": basis}
