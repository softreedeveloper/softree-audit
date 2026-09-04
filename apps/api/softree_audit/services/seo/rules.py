"""Reglas SEO-001 a SEO-016.

Cada regla es una función pura que recibe el contexto y devuelve findings ya
normalizados (`docs/spec/requirements.md` RF-08).

Convención: las incidencias de página producen un finding por página; las
incidencias de grupo (duplicados) producen un finding por grupo, con las URL
afectadas en la evidencia y el número de páginas en `occurrences`.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from urllib.parse import urlsplit

from softree_audit.models.enums import FindingSource, Severity
from softree_audit.services.crawler.models import PageData
from softree_audit.services.findings.models import NormalizedFinding
from softree_audit.services.seo.catalog import CATALOG, RuleDefinition
from softree_audit.services.seo.context import SeoContext

Rule = Callable[[SeoContext], list[NormalizedFinding]]

# Máximo de URL listadas en la evidencia de un finding de grupo.
MAX_EVIDENCE_URLS = 20


def _finding(
    definition: RuleDefinition,
    *,
    url: str | None = None,
    parameter: str | None = None,
    evidence: str | None = None,
    occurrences: int = 1,
    severity: Severity | None = None,
) -> NormalizedFinding:
    return NormalizedFinding(
        source=FindingSource.SEO,
        category=definition.category,
        rule_id=definition.id,
        title=definition.title,
        severity=severity or definition.severity,
        confidence=definition.confidence,
        url=url,
        parameter=parameter,
        evidence=evidence,
        description=definition.description,
        impact=definition.impact,
        remediation=definition.remediation,
        client_explanation=definition.client_explanation,
        occurrences=occurrences,
    )


def _url_list(urls: Iterable[str]) -> str:
    items = list(urls)
    shown = items[:MAX_EVIDENCE_URLS]
    text = "\n".join(shown)
    if len(items) > len(shown):
        text += f"\n… y {len(items) - len(shown)} más"
    return text


def _normalize_text(value: str) -> str:
    return " ".join(value.split()).strip().lower()


# ── Reglas de página ───────────────────────────────────────────────────────


def missing_title(context: SeoContext) -> list[NormalizedFinding]:
    """SEO-001."""
    definition = CATALOG["SEO-001"]
    return [
        _finding(definition, url=page.url)
        for page in context.html_pages
        if not (page.title or "").strip()
    ]


def missing_description(context: SeoContext) -> list[NormalizedFinding]:
    """SEO-003."""
    definition = CATALOG["SEO-003"]
    return [
        _finding(definition, url=page.url)
        for page in context.html_pages
        if not (page.meta_description or "").strip()
    ]


def missing_h1(context: SeoContext) -> list[NormalizedFinding]:
    """SEO-005."""
    definition = CATALOG["SEO-005"]
    return [_finding(definition, url=page.url) for page in context.html_pages if not page.h1]


def multiple_h1(context: SeoContext) -> list[NormalizedFinding]:
    """SEO-006."""
    definition = CATALOG["SEO-006"]
    return [
        _finding(
            definition,
            url=page.url,
            occurrences=len(page.h1),
            evidence=_url_list(page.h1),
        )
        for page in context.html_pages
        if len(page.h1) > 1
    ]


def missing_alt(context: SeoContext) -> list[NormalizedFinding]:
    """SEO-007."""
    definition = CATALOG["SEO-007"]
    return [
        _finding(
            definition,
            url=page.url,
            occurrences=page.images_missing_alt,
            evidence=(
                f"{page.images_missing_alt} de {page.images_total} imágenes sin texto alternativo."
            ),
        )
        for page in context.html_pages
        if page.images_missing_alt > 0
    ]


def missing_canonical(context: SeoContext) -> list[NormalizedFinding]:
    """SEO-010."""
    definition = CATALOG["SEO-010"]
    return [
        _finding(definition, url=page.url)
        for page in context.indexable_pages
        if not (page.canonical or "").strip()
    ]


def invalid_canonical(context: SeoContext) -> list[NormalizedFinding]:
    """SEO-011.

    Se considera inválido si apunta fuera de los dominios del scope, si no es
    una URL http(s), o si apunta a una página del propio crawl que no responde
    correctamente.
    """
    definition = CATALOG["SEO-011"]
    status_by_url = {page.url: page.status_code for page in context.pages}
    findings: list[NormalizedFinding] = []

    for page in context.indexable_pages:
        canonical = (page.canonical or "").strip()
        if not canonical:
            continue

        parts = urlsplit(canonical)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            findings.append(
                _finding(
                    definition,
                    url=page.url,
                    parameter=canonical,
                    evidence=f"El canonical «{canonical}» no es una URL http(s) válida.",
                )
            )
            continue

        if not context.is_internal(canonical):
            findings.append(
                _finding(
                    definition,
                    url=page.url,
                    parameter=canonical,
                    evidence=f"El canonical apunta a un dominio ajeno al sitio: {canonical}",
                )
            )
            continue

        status = status_by_url.get(canonical)
        if status is not None and status >= 400:
            findings.append(
                _finding(
                    definition,
                    url=page.url,
                    parameter=canonical,
                    evidence=f"El canonical apunta a {canonical}, que responde {status}.",
                )
            )

    return findings


def noindex_pages(context: SeoContext) -> list[NormalizedFinding]:
    """SEO-012."""
    definition = CATALOG["SEO-012"]
    return [
        _finding(
            definition,
            url=page.url,
            evidence=f"meta robots: {page.meta_robots}",
        )
        for page in context.html_pages
        if page.is_indexable is False
    ]


def redirect_chains(context: SeoContext) -> list[NormalizedFinding]:
    """SEO-015.

    Un solo salto es habitual y se reporta como informativo; encadenar dos o más
    sí penaliza y se reporta como incidencia leve.
    """
    definition = CATALOG["SEO-015"]
    findings: list[NormalizedFinding] = []

    for page in context.pages:
        hops = len(page.redirect_chain)
        if hops < 1:
            continue
        trail = " → ".join([page.url, *[str(hop.get("to", "")) for hop in page.redirect_chain]])
        findings.append(
            _finding(
                definition,
                url=page.url,
                occurrences=hops,
                evidence=f"{hops} salto(s): {trail}",
                severity=Severity.LOW if hops >= 2 else Severity.INFO,
            )
        )
    return findings


def broken_internal_links(context: SeoContext) -> list[NormalizedFinding]:
    """SEO-008."""
    definition = CATALOG["SEO-008"]
    findings: list[NormalizedFinding] = []

    for page in context.pages:
        if page.status_code is None or page.status_code < 400:
            continue
        if not context.is_internal(page.url):
            continue
        origin = page.discovered_from or "origen desconocido"
        findings.append(
            _finding(
                definition,
                url=page.url,
                evidence=f"Responde {page.status_code}. Enlazada desde: {origin}",
            )
        )
    return findings


def broken_external_links(context: SeoContext) -> list[NormalizedFinding]:
    """SEO-009.

    Solo produce findings si la comprobación de enlaces externos estaba
    habilitada en el scope; en caso contrario no hay datos y la regla calla en
    lugar de inventar un resultado.
    """
    definition = CATALOG["SEO-009"]
    return [
        _finding(
            definition,
            url=check.url,
            evidence=(
                f"Responde {check.status_code}. Enlazado desde: "
                f"{check.referrer or 'origen desconocido'}"
            ),
        )
        for check in context.external_checks
        if check.is_broken
    ]


# ── Reglas de grupo ────────────────────────────────────────────────────────


def _duplicate_groups(
    pages: list[PageData], key: Callable[[PageData], str | None]
) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for page in pages:
        raw = key(page)
        if not raw or not raw.strip():
            continue
        groups[_normalize_text(raw)].append(page.url)
    return {value: urls for value, urls in groups.items() if len(urls) > 1}


def duplicate_titles(context: SeoContext) -> list[NormalizedFinding]:
    """SEO-002."""
    definition = CATALOG["SEO-002"]
    return [
        _finding(
            definition,
            parameter=value[:200],
            occurrences=len(urls),
            evidence=f"Title «{value}» en {len(urls)} páginas:\n{_url_list(urls)}",
        )
        for value, urls in _duplicate_groups(
            context.indexable_pages, lambda page: page.title
        ).items()
    ]


def duplicate_descriptions(context: SeoContext) -> list[NormalizedFinding]:
    """SEO-004."""
    definition = CATALOG["SEO-004"]
    return [
        _finding(
            definition,
            parameter=value[:200],
            occurrences=len(urls),
            evidence=f"Description repetida en {len(urls)} páginas:\n{_url_list(urls)}",
        )
        for value, urls in _duplicate_groups(
            context.indexable_pages, lambda page: page.meta_description
        ).items()
    ]


def duplicate_content(context: SeoContext) -> list[NormalizedFinding]:
    """SEO-016.

    Señal más fuerte que SEO-002 y SEO-004: coinciden a la vez title, meta
    description y primer H1.
    """
    definition = CATALOG["SEO-016"]
    groups: dict[str, list[str]] = defaultdict(list)

    for page in context.indexable_pages:
        title = _normalize_text(page.title or "")
        description = _normalize_text(page.meta_description or "")
        heading = _normalize_text(page.h1[0]) if page.h1 else ""
        if not title and not description and not heading:
            continue
        groups[f"{title}|{description}|{heading}"].append(page.url)

    return [
        _finding(
            definition,
            parameter=key[:200],
            occurrences=len(urls),
            evidence=(
                f"{len(urls)} páginas con el mismo title, description y H1:\n{_url_list(urls)}"
            ),
        )
        for key, urls in groups.items()
        if len(urls) > 1
    ]


# ── Reglas de sitio ────────────────────────────────────────────────────────


def sitemap_missing(context: SeoContext) -> list[NormalizedFinding]:
    """SEO-013."""
    if context.crawl.sitemap_found:
        return []
    return [_finding(CATALOG["SEO-013"], url=context.base_url)]


def robots_missing(context: SeoContext) -> list[NormalizedFinding]:
    """SEO-014."""
    if context.crawl.robots_txt_found:
        return []
    return [_finding(CATALOG["SEO-014"], url=context.base_url)]


# Registro de reglas, en el orden en que se evalúan.
RULES: dict[str, Rule] = {
    "SEO-001": missing_title,
    "SEO-002": duplicate_titles,
    "SEO-003": missing_description,
    "SEO-004": duplicate_descriptions,
    "SEO-005": missing_h1,
    "SEO-006": multiple_h1,
    "SEO-007": missing_alt,
    "SEO-008": broken_internal_links,
    "SEO-009": broken_external_links,
    "SEO-010": missing_canonical,
    "SEO-011": invalid_canonical,
    "SEO-012": noindex_pages,
    "SEO-013": sitemap_missing,
    "SEO-014": robots_missing,
    "SEO-015": redirect_chains,
    "SEO-016": duplicate_content,
}
