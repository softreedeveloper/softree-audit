"""Comprobación de enlaces externos (SEO-009).

Comprobar si un enlace saliente responde con error exige una petición hacia un
dominio de terceros, fuera del alcance autorizado. Por eso:

- está **desactivada por defecto** y se habilita por sitio en el scope;
- usa `HEAD`, con `GET` de respaldo solo si el servidor no admite `HEAD`;
- pasa por el guard de SSRF, así que sigue sin poder alcanzar redes internas;
- está acotada en número de URL y ritmo.

Es una comprobación de disponibilidad de un enlace, no una auditoría del sitio
de destino: no se rastrea, no se analiza su contenido y no se guarda su cuerpo.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from softree_audit.core.logging import get_logger
from softree_audit.services.common.http_client import SafeHttpClient
from softree_audit.services.common.url_guard import BlockedTargetError
from softree_audit.services.crawler.models import PageData
from softree_audit.services.seo.context import ExternalLinkCheck

logger = get_logger(__name__)

MAX_EXTERNAL_LINKS = 100
REQUEST_DELAY_SECONDS = 0.2


def collect_external_links(
    pages: list[PageData], limit: int = MAX_EXTERNAL_LINKS
) -> list[tuple[str, str]]:
    """URL externas únicas y la primera página que las enlaza."""
    seen: set[str] = set()
    collected: list[tuple[str, str]] = []

    for page in pages:
        for link in page.links:
            if link.is_internal:
                continue
            parts = urlsplit(link.url)
            if parts.scheme not in ("http", "https"):
                continue
            key = link.url.split("#")[0]
            if key in seen:
                continue
            seen.add(key)
            collected.append((key, page.url))
            if len(collected) >= limit:
                return collected
    return collected


async def check_external_links(
    client: SafeHttpClient,
    pages: list[PageData],
    *,
    limit: int = MAX_EXTERNAL_LINKS,
    is_cancelled: Callable[[], Awaitable[bool]] | None = None,
) -> list[ExternalLinkCheck]:
    """Comprueba secuencialmente los enlaces externos del sitio."""
    results: list[ExternalLinkCheck] = []

    for url, referrer in collect_external_links(pages, limit):
        if is_cancelled and await is_cancelled():
            break

        await asyncio.sleep(REQUEST_DELAY_SECONDS)
        try:
            # Sin `scope`: es un dominio ajeno por definición. El guard sigue
            # aplicando todas las protecciones de red.
            response = await client.fetch(url, method="HEAD")
            status = response.status_code
            if status in (405, 501):
                # Hay servidores que no admiten HEAD; se reintenta con GET.
                status = (await client.fetch(url, method="GET")).status_code
            results.append(ExternalLinkCheck(url=url, status_code=status, referrer=referrer))
        except BlockedTargetError as exc:
            logger.info("seo.external_link_blocked", url=url, reason=exc.reason)
            results.append(
                ExternalLinkCheck(
                    url=url, status_code=None, referrer=referrer, error=f"bloqueado: {exc.reason}"
                )
            )
        except Exception as exc:  # un enlace inaccesible no detiene la comprobación
            logger.info("seo.external_link_failed", url=url, error=type(exc).__name__)
            results.append(
                ExternalLinkCheck(
                    url=url, status_code=None, referrer=referrer, error=type(exc).__name__
                )
            )

    return results
