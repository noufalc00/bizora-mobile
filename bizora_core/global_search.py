"""
Global menu search resolver for sidebar routes and settings sub-sections.

Main menu section headers (Dashboard, Settings, Books, etc.) are intentionally
excluded so search only targets actionable sub-menu items.
"""

from __future__ import annotations

from dataclasses import dataclass

from bizora_core.navigation_catalog import (
    SETTINGS_SUBSECTIONS,
    iter_navigation_routes,
)


@dataclass(frozen=True)
class GlobalSearchResult:
    """Resolved navigation target from a global search query."""

    kind: str
    label: str
    route_name: str | None = None
    section_name: str | None = None
    settings_parent_route: str | None = None
    settings_section_id: str | None = None
    score: int = 0


def _normalize_query(query: str) -> str:
    """Normalize user input for case-insensitive matching."""
    return " ".join((query or "").strip().lower().split())


def _score_match(query: str, candidate: str) -> int:
    """
    Score how well ``candidate`` matches ``query``.

    Higher scores indicate stronger matches. Zero means no match.
    """
    normalized_candidate = _normalize_query(candidate)
    if not query or not normalized_candidate:
        return 0

    if query == normalized_candidate:
        return 1000
    if normalized_candidate.startswith(query):
        return 850
    if query in normalized_candidate:
        return 650

    query_tokens = query.split()
    candidate_tokens = normalized_candidate.split()
    if query_tokens and all(token in candidate_tokens for token in query_tokens):
        return 700

    if len(query_tokens) == 1:
        token = query_tokens[0]
        if any(word.startswith(token) for word in candidate_tokens):
            return 600

    return 0


def collect_search_labels() -> list[str]:
    """Return sorted searchable labels (routes and settings panes only)."""
    labels: set[str] = set()

    for _section_name, route_name in iter_navigation_routes():
        labels.add(route_name)

    for subsection in SETTINGS_SUBSECTIONS:
        labels.add(subsection["label"])
        for keyword in subsection.get("keywords", ()):
            labels.add(str(keyword))

    return sorted(labels, key=str.lower)


def find_search_suggestions(query: str, limit: int = 20) -> list[str]:
    """Return menu labels that match ``query``, best matches first."""
    normalized_query = _normalize_query(query)
    if not normalized_query or limit <= 0:
        return []

    scored: list[tuple[int, str]] = []
    for label in collect_search_labels():
        score = _score_match(normalized_query, label)
        if score > 0:
            scored.append((score, label))

    scored.sort(key=lambda item: (-item[0], item[1].lower()))
    return [label for _, label in scored[:limit]]


def _best_route_match(normalized_query: str) -> GlobalSearchResult | None:
    """Return the strongest matching sidebar route, if any."""
    best: GlobalSearchResult | None = None

    for section_name, route_name in iter_navigation_routes():
        score = _score_match(normalized_query, route_name)
        if score <= 0:
            continue
        result = GlobalSearchResult(
            kind="route",
            label=route_name,
            route_name=route_name,
            section_name=section_name,
            score=score,
        )
        if best is None or result.score > best.score:
            best = result
        elif result.score == best.score and result.label.lower() < best.label.lower():
            best = result

    return best


def _best_settings_match(normalized_query: str) -> GlobalSearchResult | None:
    """Return the strongest matching nested settings pane, if any."""
    best: GlobalSearchResult | None = None

    for subsection in SETTINGS_SUBSECTIONS:
        labels = (subsection["label"], *subsection.get("keywords", ()))
        best_label_score = 0
        for label in labels:
            best_label_score = max(best_label_score, _score_match(normalized_query, label))

        if best_label_score <= 0:
            continue

        result = GlobalSearchResult(
            kind="settings_section",
            label=subsection["label"],
            settings_parent_route=subsection["parent_route"],
            settings_section_id=subsection["section_id"],
            score=best_label_score,
        )
        if best is None or result.score > best.score:
            best = result
        elif result.score == best.score and result.label.lower() < best.label.lower():
            best = result

    return best


def resolve_global_search(query: str) -> GlobalSearchResult | None:
    """
    Resolve a search query to a route or settings sub-section.

    Main menu headers are not searchable; only leaf routes and settings panes
    are considered.
    """
    normalized_query = _normalize_query(query)
    if not normalized_query:
        return None

    route_match = _best_route_match(normalized_query)
    settings_match = _best_settings_match(normalized_query)

    if route_match is None:
        return settings_match
    if settings_match is None:
        return route_match

    if settings_match.score > route_match.score:
        return settings_match
    if route_match.score > settings_match.score:
        return route_match

    if route_match.label.lower() <= settings_match.label.lower():
        return route_match
    return settings_match
