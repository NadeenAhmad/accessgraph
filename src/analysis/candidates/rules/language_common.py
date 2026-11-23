from __future__ import annotations

import re

from ..evidence_helpers import truncate_text

_TOKEN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
_LANGUAGE_MARKERS: dict[str, frozenset[str]] = {
  "en": frozenset({"the", "and", "with", "for", "your", "welcome", "search", "contact"}),
  "fr": frozenset({"bonjour", "merci", "avec", "pour", "votre", "produits", "recherche"}),
  "es": frozenset({
    "hola", "gracias", "con", "para", "usted", "productos", "buscar", "contenido",
    "resumen", "espacio", "trabajo", "espanol",
  }),
  "de": frozenset({"hallo", "danke", "mit", "fuer", "deutsch", "produkte", "suche"}),
  "it": frozenset({"ciao", "grazie", "con", "per", "italiano", "prodotti", "cerca"}),
  "pt": frozenset({"ola", "obrigado", "com", "para", "produtos", "pesquisa"}),
  "nl": frozenset({"hallo", "dank", "met", "voor", "nederlands", "producten", "zoeken"}),
}


def marker_matches_by_language(text: object) -> dict[str, list[str]]:
  tokens = {token.casefold() for token in _TOKEN_RE.findall(str(text or ""))}
  return {
    language: sorted(tokens.intersection(markers))
    for language, markers in _LANGUAGE_MARKERS.items()
  }


def infer_language_signal(text: object) -> tuple[str, list[str]]:
  scores = marker_matches_by_language(text)
  language, markers = max(scores.items(), key=lambda item: len(item[1]))
  return (language, markers) if markers else ("", [])


def primary_language(value: object) -> str:
  normalized = truncate_text(value, max_length=80).replace("_", "-").casefold()
  return normalized.split("-", 1)[0] if normalized else ""
