"""Cliente HTTP seguro para hablar con el target.

Aplica los límites de `docs/spec/security.md` §3 y fija la IP validada por el
guard, de modo que la conexión no pueda desviarse entre la validación y el
`connect` (DNS rebinding).

La fijación se hace sustituyendo el host por la IP validada y conservando la
cabecera `Host` y el `sni_hostname`, para que TLS siga verificando el
certificado contra el nombre real.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from types import TracebackType
from urllib.parse import urlsplit, urlunsplit

import httpx

from softree_audit.core.logging import get_logger
from softree_audit.services.common.url_guard import (
    BlockedTargetError,
    ScopePolicy,
    UrlGuard,
    ValidatedTarget,
)

logger = get_logger(__name__)

# Las cabeceras HTTP deben ser ASCII: sin acentos ni caracteres no ASCII.
USER_AGENT = "SoftreeAudit/0.1 (+https://softree.mx; authorized-audit)"

# Solo estos tipos se parsean; el resto se descarga y se descarta.
PARSEABLE_CONTENT_TYPES = (
    "text/html",
    "application/xhtml+xml",
    "text/xml",
    "application/xml",
    "text/plain",
)

# Un cociente de descompresión mayor indica una bomba de compresión.
MAX_DECOMPRESSION_RATIO = 100


class ResponseTooLargeError(Exception):
    """La respuesta supera el límite configurado."""


@dataclass(slots=True)
class FetchedResponse:
    """Respuesta ya validada y acotada."""

    url: str
    status_code: int
    headers: httpx.Headers
    content: bytes
    elapsed_ms: int
    redirect_chain: list[dict[str, object]] = field(default_factory=list)
    truncated: bool = False

    @property
    def content_type(self) -> str:
        raw: str = self.headers.get("content-type", "")
        return raw.split(";")[0].strip().lower()

    @property
    def is_parseable(self) -> bool:
        return self.content_type in PARSEABLE_CONTENT_TYPES

    def text(self) -> str:
        charset: str = self.headers.get("content-type", "")
        encoding = "utf-8"
        if "charset=" in charset:
            encoding = charset.split("charset=")[-1].split(";")[0].strip() or "utf-8"
        try:
            return self.content.decode(encoding, errors="replace")
        except LookupError:
            return self.content.decode("utf-8", errors="replace")

    @property
    def is_redirect(self) -> bool:
        return 300 <= self.status_code < 400


class SafeHttpClient:
    """Cliente que solo alcanza destinos aprobados por el guard."""

    def __init__(
        self,
        guard: UrlGuard,
        *,
        timeout_seconds: float = 20.0,
        max_response_bytes: int = 5_242_880,
        user_agent: str = USER_AGENT,
    ) -> None:
        self._guard = guard
        self._max_bytes = max_response_bytes
        self._client = httpx.AsyncClient(
            # Los redirects se siguen a mano para revalidar cada salto.
            follow_redirects=False,
            timeout=httpx.Timeout(timeout_seconds),
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            limits=httpx.Limits(max_connections=16, max_keepalive_connections=8),
            trust_env=False,
        )

    async def __aenter__(self) -> SafeHttpClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch(
        self,
        url: str,
        *,
        scope: ScopePolicy | None = None,
        method: str = "GET",
    ) -> FetchedResponse:
        """Descarga una URL siguiendo los redirects con revalidación por salto."""
        chain: list[dict[str, object]] = []
        current = url

        for hop in range(self._guard.policy.max_redirects + 1):
            target = await self._guard.validate(current, scope=scope)
            response = await self._request(target, method=method)
            response.redirect_chain = list(chain)

            if not response.is_redirect:
                return response

            location = response.headers.get("location")
            if not location:
                return response

            next_url = self._resolve_location(target.url, location)
            chain.append({"from": target.url, "to": next_url, "status": response.status_code})

            if hop == self._guard.policy.max_redirects:
                raise BlockedTargetError(
                    f"Se superó el máximo de {self._guard.policy.max_redirects} redirecciones.",
                    reason="too_many_redirects",
                    url=url,
                )
            current = next_url

        raise BlockedTargetError(
            "Se superó el máximo de redirecciones.", reason="too_many_redirects", url=url
        )

    async def _request(self, target: ValidatedTarget, *, method: str) -> FetchedResponse:
        parts = urlsplit(target.url)
        netloc = target.pinned_host
        if target.port not in (80, 443):
            netloc = f"{netloc}:{target.port}"
        pinned_url = urlunsplit((parts.scheme, netloc, parts.path or "/", parts.query, ""))

        host_header = target.host
        if target.port not in (80, 443):
            host_header = f"{target.host}:{target.port}"

        request = self._client.build_request(
            method,
            pinned_url,
            headers={"Host": host_header},
            # `sni_hostname` mantiene la verificación TLS contra el nombre real
            # aunque la conexión vaya a la IP fijada.
            extensions={"sni_hostname": target.host},
        )

        started = time.perf_counter()
        response = await self._client.send(request, stream=True)
        try:
            content, truncated = await self._read_capped(response, target.url)
        finally:
            await response.aclose()
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        return FetchedResponse(
            url=target.url,
            status_code=response.status_code,
            headers=response.headers,
            content=content,
            elapsed_ms=elapsed_ms,
            truncated=truncated,
        )

    async def _read_capped(self, response: httpx.Response, url: str) -> tuple[bytes, bool]:
        """Lee en streaming con corte por tamaño y control de descompresión."""
        chunks: list[bytes] = []
        decoded = 0
        truncated = False

        async for chunk in response.aiter_bytes():
            decoded += len(chunk)
            if decoded > self._max_bytes:
                keep = self._max_bytes - (decoded - len(chunk))
                if keep > 0:
                    chunks.append(chunk[:keep])
                truncated = True
                logger.warning("http.response_truncated", url=url, limit=self._max_bytes)
                break
            chunks.append(chunk)

            raw = response.num_bytes_downloaded
            if raw > 0 and decoded / raw > MAX_DECOMPRESSION_RATIO:
                logger.warning(
                    "http.decompression_ratio_exceeded",
                    url=url,
                    decoded=decoded,
                    raw=raw,
                )
                raise ResponseTooLargeError(
                    "La respuesta se descomprime con un cociente sospechoso."
                )

        return b"".join(chunks), truncated

    @staticmethod
    def _resolve_location(base: str, location: str) -> str:
        return str(httpx.URL(base).join(location))
