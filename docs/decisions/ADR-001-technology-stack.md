# ADR-001 — Stack tecnológico y organización del repositorio

Estado: Aceptado · Fecha: 2026-09-03

## Contexto

Se requiere una plataforma interna con frontend, API, crawler, integraciones
externas y generación de reportes, con prioridad en simplicidad, bajo costo y
mantenibilidad. Se descartan explícitamente Kubernetes, microservicios
innecesarios, Elasticsearch y Kafka.

## Decisión

Stack:

| Capa | Tecnología |
|------|-----------|
| Frontend | Astro, React, TypeScript, Tailwind CSS |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy, Alembic |
| Base de datos | PostgreSQL |
| Cola y límites de tasa | Redis |
| Escáner | OWASP ZAP |
| Contenedores | Docker y Docker Compose |

Organización: un único proyecto Python en `apps/api` que contiene la API, el
worker, los `services/*` y `packages/scoring` como subpaquetes de
`softree_audit`. Los directorios `services/` y `packages/` de la raíz conservan
documentación y los tipos TypeScript generados desde OpenAPI.

## Alternativas

1. **Monorepo con paquetes Python independientes** (`services/crawler` como
   distribución instalable). Aporta aislamiento real, pero exige versionado
   interno, múltiples `pyproject.toml` y varias imágenes para un equipo pequeño.
2. **Node en el backend** para unificar lenguaje. Se descarta porque el
   ecosistema de auditoría y los clientes de ZAP y Google están mejor cubiertos
   en Python, y el equipo ya trabaja Python.
3. **Django en lugar de FastAPI.** Aporta admin y ORM maduro, pero el trabajo es
   API-first y asíncrono, donde FastAPI encaja mejor.

## Consecuencias

- Un solo entorno virtual, una sola imagen de backend, un solo `pyproject.toml`.
- Los límites entre módulos se sostienen por convención e imports, no por
  empaquetado. Se documenta la regla de dependencias en `architecture.md` §2 y se
  verifica con `ruff` (`flake8-tidy-imports` con `banned-api`).
- Extraer un servicio a paquete independiente en el futuro es un cambio mecánico
  porque los imports ya son absolutos y jerárquicos.
