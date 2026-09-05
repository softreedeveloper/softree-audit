# Softree Audit — Architecture Specification

## 1. Vista general

```
                    ┌──────────────────┐
                    │ Astro + React    │
                    │ Frontend         │
                    └────────┬─────────┘
                             │ REST (same-origin /api)
                             ▼
                    ┌──────────────────┐
                    │ FastAPI          │────── PostgreSQL
                    │ Backend          │────── Redis (queue + rate limit)
                    └────────┬─────────┘
                             │ enqueue
                             ▼
                    ┌──────────────────┐
                    │ arq worker       │
                    │ Scan Orchestrator│
                    └────────┬─────────┘
                ┌────────────┼────────────┬──────────────┐
                ▼            ▼            ▼              ▼
             Security       SEO       Performance   Search Console
                │            │            │              │
               ZAP        Crawler      PageSpeed        GSC API
                │            │            │              │
                └────────────┴─────┬──────┴──────────────┘
                                   ▼
                            Findings Engine
                                   ▼
                          Scoring (packages/scoring)
                                   ▼
                              PostgreSQL
                     ┌─────────────┼─────────────┐
                     ▼             ▼             ▼
                 Dashboard      Reports       History
```

## 2. Componentes

| Componente | Responsabilidad | Tecnología |
|-----------|-----------------|-----------|
| `apps/web` | UI, estados de pantalla, temas | Astro, React, TypeScript, Tailwind |
| `apps/api` | REST, autenticación, validación, persistencia, encolado | FastAPI, Pydantic, SQLAlchemy, Alembic |
| `apps/api` (worker) | Orquestación del pipeline de scan | arq |
| `services/common` | Guard de URL y SSRF, cliente HTTP seguro, utilidades de reintento | httpx |
| `services/crawler` | Descubrimiento y extracción por página | httpx, selectolax |
| `services/security` | Adapter de OWASP ZAP y normalizador de alertas | ZAP API |
| `services/seo` | Reglas SEO-001…016 y datos estructurados | — |
| `services/performance` | Adapter de PageSpeed Insights | httpx |
| `services/search_console` | OAuth y Search Analytics | httpx |
| `services/findings` | Normalización, fingerprint, deduplicación | — |
| `services/reports` | PDF, HTML y JSON | WeasyPrint, Jinja2 |
| `packages/scoring` | Cálculo de scores, sin dependencias de IO | — |
| `packages/shared-types` | Tipos TypeScript generados desde OpenAPI | openapi-typescript |

Regla de dependencias: `packages/scoring` no importa nada de `services/` ni de
`apps/`. `services/*` no importa de `apps/api`. `apps/api` importa de ambos.

## 3. Contrato de módulo de scan

Todo módulo del pipeline implementa la misma interfaz:

```python
class ScanModule(Protocol):
    name: str                       # "crawler" | "security" | ...
    async def run(self, ctx: ScanContext) -> ModuleResult: ...
```

`ModuleResult` contiene los findings producidos, los artefactos a persistir y
métricas de ejecución. El orquestador es el único responsable de:

- aplicar el timeout del módulo,
- capturar la excepción y marcar el `ScanModule` como `failed`,
- registrar duración y error,
- continuar con el siguiente módulo.

Ningún módulo escribe en base de datos directamente; devuelve datos y el
orquestador persiste. Esto mantiene los módulos testeables sin base de datos.

## 4. Estados

Scan: `queued | running | completed | failed | cancelled | partial`.

Módulo: `pending | running | completed | failed | skipped`.

Reglas de transición del scan al finalizar:

| Condición | Estado final |
|-----------|--------------|
| Todos los módulos aplicables `completed` o `skipped` | `completed` |
| Al menos uno `completed` y al menos uno `failed` | `partial` |
| Todos los aplicables `failed` | `failed` |
| Cancelación solicitada y atendida | `cancelled` |

## 5. Concurrencia

- El worker corre con `max_jobs` configurable (defecto 2).
- Dentro del crawler, semáforo por `scope.concurrency` (defecto 4, máximo 16).
- `request_delay_ms` entre peticiones al mismo host.
- PageSpeed se limita a 1 petición por segundo y se cachea 6 horas por
  `(url, strategy)`.
- Los módulos independientes (`security`, `seo`, `performance`,
  `search_console`) pueden ejecutarse concurrentemente; `crawler` es
  prerrequisito de `seo`.

## 6. Estructura del repositorio

```
softree-audit/
├── apps/
│   ├── api/                 proyecto Python (FastAPI + worker + services + scoring)
│   │   ├── softree_audit/
│   │   ├── alembic/
│   │   ├── pyproject.toml
│   │   └── alembic.ini
│   └── web/                 Astro + React
├── services/                README que apunta a softree_audit/services
├── packages/                README que apunta a softree_audit/scoring
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── test-target/             sitio con defectos controlados
├── docs/
├── docker/
├── docker-compose.yml
├── .env.example
├── Makefile
└── README.md
```

### Desviación respecto a la estructura propuesta

La especificación original sugiere `services/` y `packages/` como proyectos
hermanos de `apps/`. En el MVP los subpaquetes Python viven dentro del paquete
`softree_audit` de `apps/api`, y los directorios `services/` y `packages/` de la
raíz contienen únicamente un README que indica dónde está cada módulo. Los
tipos TypeScript generados viven en `apps/web/src/lib/api-types.ts`.

Motivo: un único entorno Python, una única imagen Docker y ningún paquete
interno que publicar. Los imports usan `softree_audit.services.crawler`, por lo
que extraerlos a paquetes independientes más adelante es un cambio mecánico.
Registrado en ADR-001 y D-009.

## 7. Comunicación

- Frontend a backend: REST JSON, same-origin bajo `/api/v1`.
- Progreso de scan: polling cada 2 segundos sobre `GET /scans/{id}`. No se usa
  WebSocket en el MVP; el endpoint devuelve el estado por módulo y el porcentaje
  aproximado, suficiente para el requisito §30.
- Backend a worker: cola Redis vía arq. Payload mínimo (`scan_id`), el worker
  releé el estado de base de datos.

## 8. Configuración

Toda la configuración se lee de variables de entorno mediante
`pydantic-settings`. No hay valores sensibles por defecto. Arrancar sin
`SECRET_KEY` es un error fatal en producción.

## 9. Versionado

`APP_VERSION`, `SCAN_ENGINE_VERSION` y `REPORT_VERSION` se definen en
`softree_audit/version.py`, se exponen en `GET /api/v1/health` y se persisten en
cada scan y reporte para permitir comparaciones entre versiones del motor.

## 10. Riesgos técnicos

| Riesgo | Impacto | Mitigación |
|--------|---------|-----------|
| Cuota de PageSpeed agotada | Módulo `failed` | Cache 6 h, límite 1 rps, degradación elegante |
| ZAP no responde o tarda indefinidamente | Scan bloqueado | Timeout por módulo, cierre de sesión de ZAP, `failed` |
| Sitio muy grande | Crawl interminable | `max_pages`, `max_depth`, timeout global de scan |
| Respuestas enormes o comprimidas maliciosamente | Memoria agotada | Límite de 5 MB por respuesta, lectura en streaming |
| Refresh token de Google revocado | Search Console `skipped` | Detección de `invalid_grant`, marcado de conexión como `revoked` |
| Generación de PDF pesada | Worker ocupado | Reporte como etapa final del pipeline, no bloqueante para la API |
| Deriva del esquema | Migraciones inconsistentes | Alembic con una sola cabeza, verificación en CI |

## 11. Extensibilidad

Puntos de extensión previstos, no implementados en el MVP:

- **Nuevos módulos de scan**: implementar el protocolo `ScanModule` y registrar
  en el orquestador. Cubre accessibility dedicado, detección de tecnologías,
  correlación de CVE, análisis de JavaScript, auditoría de OpenAPI.
- **Navegador**: `services/common` define una interfaz `PageRenderer`; el MVP usa
  la implementación HTTP. Playwright entraría como segunda implementación.
- **Scanning autenticado**: `Scope` reserva el campo `auth_profile_id`, sin uso.
- **Monitoreo y alertas**: los scans ya son trabajos encolados; basta un
  disparador programado.
- **n8n**: la REST API es el contrato. No se construye adaptador específico.
- **Análisis con IA**: interfaz conceptual documentada en `docs/spec/reports.md`.
  El módulo de IA nunca podrá ejecutar acciones ofensivas ni emitir tráfico hacia
  el target.
