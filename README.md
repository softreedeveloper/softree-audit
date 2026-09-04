# SOFTREE AUDIT

Plataforma **interna** de auditoría de sitios web: seguridad, SEO, rendimiento,
accesibilidad, buenas prácticas y datos de Google Search Console en un informe
profesional que Softree entrega como valor agregado de cada proyecto web.

> **Uso autorizado.** Auditar únicamente sitios propios, sitios desarrollados por
> Softree o sitios de clientes con autorización explícita. Un sitio sin
> autorización registrada no puede escanearse.

| | |
|---|---|
| Producto | Softree Audit 0.1.0 |
| Scan Engine | 0.1.0 |
| Report | v1 |
| Estado | **MVP completo**: los 11 slices entregados y verificados |

## Qué hace

```
        Introducir URL autorizada
                   │
                   ▼
              Full Audit
     ┌─────────────┼─────────────┐
     ▼             ▼             ▼
  Security        SEO       Performance
    ZAP         Crawler      PageSpeed
     └─────────────┼─────────────┘
                   ▼
            Search Console
                   ▼
            Findings Engine
                   ▼
             Softree Score
        ┌──────────┼──────────┐
        ▼          ▼          ▼
    Dashboard  Comparison   Report → PDF
```

## Arranque rápido

```bash
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # pegar en SECRET_KEY

make up          # postgres, redis, api, web
make migrate     # aplica las migraciones
make user        # crea el primer usuario
```

| Servicio | URL |
|----------|-----|
| Frontend | http://localhost:4321 |
| API | http://localhost:8000/api/v1 |
| OpenAPI | http://localhost:8000/api/v1/docs |
| Health | http://localhost:8000/api/v1/health |

Perfiles opcionales:

```bash
docker compose --profile scanner up -d   # OWASP ZAP
docker compose --profile testing up -d   # sitio de pruebas con defectos controlados
```

`make help` lista todos los comandos.

## Stack

| Capa | Tecnología |
|------|-----------|
| Frontend | Astro, React, TypeScript, Tailwind CSS |
| Backend | Python, FastAPI, Pydantic, SQLAlchemy, Alembic |
| Base de datos | PostgreSQL |
| Cola y límites de tasa | Redis con arq |
| Escáner | OWASP ZAP (passive scan) |
| Contenedores | Docker, Docker Compose |

## Estructura

```
softree-seo/
├── apps/api/       FastAPI, modelos, migraciones, services y scoring
├── apps/web/       Astro + React
├── tests/          unit, integration, e2e
├── test-target/    sitio con defectos controlados para pruebas
├── docs/           especificaciones, guías y ADRs
├── docker/         Dockerfiles y bootstrap de PostgreSQL
└── docker-compose.yml
```

## Documentación

| Documento | Contenido |
|-----------|-----------|
| [docs/spec/requirements.md](docs/spec/requirements.md) | Requisitos, inconsistencias resueltas y alcance |
| [docs/spec/product.md](docs/spec/product.md) | Usuario, casos de uso y pantallas |
| [docs/spec/architecture.md](docs/spec/architecture.md) | Componentes, contrato de módulo y estados |
| [docs/spec/database.md](docs/spec/database.md) | Tablas, índices y constraints |
| [docs/spec/security.md](docs/spec/security.md) | SSRF, autenticación, secretos y modelo de amenazas |
| [docs/spec/api.md](docs/spec/api.md) | Endpoints, errores y contrato para n8n |
| [docs/spec/seo-rules.md](docs/spec/seo-rules.md) | Catálogo SEO-001 a SEO-016 |
| [docs/spec/scoring.md](docs/spec/scoring.md) | Google Score y Softree Score |
| [docs/spec/reports.md](docs/spec/reports.md) | PDF, HTML, JSON y doble nivel de lectura |
| [docs/spec/decisions.md](docs/spec/decisions.md) | Decisiones menores documentadas |
| [docs/decisions/](docs/decisions/) | ADR-000 a ADR-008 |
| [docs/development/setup.md](docs/development/setup.md) | Entorno de desarrollo |
| [docs/development/slice-1.md](docs/development/slice-1.md) | Alcance y verificación del Slice 1 |
| [docs/development/slice-2.md](docs/development/slice-2.md) | Alcance y verificación del Slice 2 |
| [docs/development/slice-3.md](docs/development/slice-3.md) | Alcance y verificación del Slice 3 |
| [docs/development/slice-4.md](docs/development/slice-4.md) | Alcance y verificación del Slice 4 |
| [docs/development/slice-5.md](docs/development/slice-5.md) | Alcance y verificación del Slice 5 |
| [docs/development/slice-6.md](docs/development/slice-6.md) | Alcance y verificación del Slice 6 |
| [docs/development/slice-7.md](docs/development/slice-7.md) | Alcance y verificación del Slice 7 |
| [docs/development/slice-8.md](docs/development/slice-8.md) | Alcance y verificación del Slice 8 |
| [docs/development/slice-9.md](docs/development/slice-9.md) | Alcance y verificación del Slice 9 |
| [docs/development/slice-10.md](docs/development/slice-10.md) | Alcance y verificación del Slice 10 |
| [docs/development/slice-11.md](docs/development/slice-11.md) | Alcance y verificación del Slice 11 |
| [docs/development/final-verification.md](docs/development/final-verification.md) | Verificación final del MVP contra la especificación |
| [docs/development/testing.md](docs/development/testing.md) | Estrategia de pruebas |
| [docs/development/deployment.md](docs/development/deployment.md) | Despliegue y rotación de secretos |

## Estado por slice

| Slice | Contenido | Estado |
|-------|-----------|--------|
| 1 | Setup, Docker, base de datos, FastAPI, Astro, autenticación | Completado |
| 2 | Projects, Sites, Scope | Completado |
| 3 | Orquestación de scans y crawler | Completado |
| 4 | Motor SEO | Completado |
| 5 | OWASP ZAP | Completado |
| 6 | PageSpeed Insights | Completado |
| 7 | Search Console | Completado |
| 8 | Findings y scoring | Completado |
| 9 | Dashboard, histórico y comparación | Completado |
| 10 | Reportes PDF, HTML y JSON | Completado |
| 11 | E2E y validación de seguridad | Completado |

## Seguridad

- Toda petición saliente hacia un target pasa por un único guard con protección
  contra SSRF, incluida la revalidación en cada redirect.
- Contraseñas con Argon2id. Access token de 15 minutos y refresh token rotativo
  revocable en cookie `HttpOnly`.
- Límites de tasa en Redis. Cabeceras de seguridad en todas las respuestas.
- Credenciales de terceros cifradas en reposo.
- Sin secretos en el repositorio.

Detalle completo en [docs/spec/security.md](docs/spec/security.md).

## Licencia

Software propietario de Softree. Uso interno.
