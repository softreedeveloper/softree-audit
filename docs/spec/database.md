# Softree Audit — Database Specification

- Motor: PostgreSQL 16
- Migraciones: Alembic, una sola cabeza
- Identificadores: UUID v7 generados en la aplicación, expuestos públicamente
- Timestamps: `TIMESTAMPTZ`, siempre UTC, `created_at` y `updated_at` en toda tabla
- Enumerados: `VARCHAR` con `CHECK` constraint (D-006)
- Borrado: `ON DELETE CASCADE` en sentido descendente de la jerarquía

## Jerarquía

```
users
 └── projects
       └── sites
             ├── scopes (1:1)
             └── scans
                   ├── scan_modules
                   ├── pages
                   ├── findings
                   ├── seo_results
                   ├── performance_results
                   ├── search_console_metrics
                   ├── scores
                   └── reports
projects
 └── search_console_connections
```

## Tablas

### users

| Columna | Tipo | Notas |
|---------|------|-------|
| id | uuid | PK |
| email | text | UNIQUE, NOT NULL. Normalizado a minúsculas en la capa de esquema |
| password_hash | text | NOT NULL, Argon2id |
| full_name | text | NOT NULL |
| is_active | boolean | NOT NULL, default true |
| last_login_at | timestamptz | NULL |
| created_at / updated_at | timestamptz | NOT NULL |

Índices: `UNIQUE (email)`.

Se normaliza el email a minúsculas antes de persistir, en lugar de usar `citext`,
para no depender de una extensión de PostgreSQL.

### projects

| Columna | Tipo | Notas |
|---------|------|-------|
| id | uuid | PK |
| owner_id | uuid | FK users(id) ON DELETE CASCADE |
| name | text | NOT NULL |
| client_name | text | NULL |
| notes | text | NULL |
| created_at / updated_at | timestamptz | NOT NULL |

Índices: `(owner_id)`, `UNIQUE (owner_id, name)`.

### sites

| Columna | Tipo | Notas |
|---------|------|-------|
| id | uuid | PK |
| project_id | uuid | FK projects(id) ON DELETE CASCADE |
| name | text | NOT NULL |
| base_url | text | NOT NULL, normalizada con esquema y host |
| authorized_by | text | NULL. Requerido para escanear |
| authorization_date | date | NULL. Requerido para escanear |
| authorization_notes | text | NULL |
| is_active | boolean | NOT NULL, default true |
| created_at / updated_at | timestamptz | NOT NULL |

Índices: `(project_id)`, `UNIQUE (project_id, base_url)`.
Constraint: `CHECK (base_url ~* '^https?://')`.

### scopes

Relación 1:1 con `sites`.

| Columna | Tipo | Notas |
|---------|------|-------|
| id | uuid | PK |
| site_id | uuid | FK sites(id) ON DELETE CASCADE, UNIQUE |
| allowed_domains | text[] | NOT NULL, al menos el host de `base_url` |
| allowed_paths | text[] | NOT NULL, default `{}` = todas |
| excluded_paths | text[] | NOT NULL, default `{}` |
| max_pages | integer | NOT NULL, default 200, CHECK 1..5000 |
| max_depth | integer | NOT NULL, default 3, CHECK 1..10 |
| timeout_seconds | integer | NOT NULL, default 20, CHECK 1..120 |
| request_delay_ms | integer | NOT NULL, default 200, CHECK 0..10000 |
| concurrency | integer | NOT NULL, default 4, CHECK 1..16 |
| respect_robots | boolean | NOT NULL, default true |
| zap_spider_enabled | boolean | NOT NULL, default true |
| auth_profile_id | uuid | NULL, reservado para scanning autenticado |
| created_at / updated_at | timestamptz | NOT NULL |

### scans

| Columna | Tipo | Notas |
|---------|------|-------|
| id | uuid | PK |
| site_id | uuid | FK sites(id) ON DELETE CASCADE |
| triggered_by | uuid | FK users(id) ON DELETE SET NULL |
| scan_type | varchar(20) | CHECK IN (full, security, seo, performance) |
| status | varchar(20) | CHECK IN (queued, running, completed, failed, cancelled, partial) |
| progress | smallint | NOT NULL, default 0, CHECK 0..100 |
| queued_at | timestamptz | NOT NULL |
| started_at | timestamptz | NULL |
| finished_at | timestamptz | NULL |
| duration_ms | integer | NULL |
| error | text | NULL |
| scope_snapshot | jsonb | NOT NULL. Scope efectivo al momento del scan |
| engine_version | text | NOT NULL |
| app_version | text | NOT NULL |
| created_at / updated_at | timestamptz | NOT NULL |

Índices: `(site_id, queued_at)`, `(status)`.

El índice no declara `DESC`: PostgreSQL recorre un B-tree en orden inverso sin
coste adicional, y así el autogenerado de Alembic es estable.

Se guarda `scope_snapshot` para que un scan histórico sea reproducible aunque el
scope del sitio cambie después.

### scan_modules

| Columna | Tipo | Notas |
|---------|------|-------|
| id | uuid | PK |
| scan_id | uuid | FK scans(id) ON DELETE CASCADE |
| module | varchar(30) | CHECK IN (discovery, crawler, security, seo, performance, search_console, findings, scoring, report) |
| status | varchar(20) | CHECK IN (pending, running, completed, failed, skipped) |
| started_at / finished_at | timestamptz | NULL |
| duration_ms | integer | NULL |
| error | text | NULL |
| detail | jsonb | NULL. Contadores del módulo |
| created_at / updated_at | timestamptz | NOT NULL |

Índices: `UNIQUE (scan_id, module)`.

### pages

| Columna | Tipo | Notas |
|---------|------|-------|
| id | uuid | PK |
| scan_id | uuid | FK scans(id) ON DELETE CASCADE |
| url | text | NOT NULL |
| url_hash | bytea | NOT NULL, sha256(url). Base del índice único |
| depth | smallint | NOT NULL |
| discovered_from | text | NULL. URL que enlazaba a esta página |
| status_code | smallint | NULL |
| content_type | text | NULL |
| response_time_ms | integer | NULL |
| content_length | integer | NULL |
| title | text | NULL |
| meta_description | text | NULL |
| canonical | text | NULL |
| meta_robots | text | NULL |
| h1 | text[] | NOT NULL, default `{}` |
| h2 | text[] | NOT NULL, default `{}` |
| internal_links | integer | NOT NULL, default 0 |
| external_links | integer | NOT NULL, default 0 |
| images_total | integer | NOT NULL, default 0 |
| images_missing_alt | integer | NOT NULL, default 0 |
| scripts_total | integer | NOT NULL, default 0 |
| forms_total | integer | NOT NULL, default 0 |
| redirect_chain | jsonb | NOT NULL, default `[]` |
| structured_data | jsonb | NOT NULL, default `{}`. JSON-LD, OpenGraph, Twitter |
| is_indexable | boolean | NULL |
| error | text | NULL |
| created_at / updated_at | timestamptz | NOT NULL |

Índices: `UNIQUE (scan_id, url_hash)`, `(scan_id, status_code)`.

Se indexa por hash porque una URL puede exceder el límite de tamaño de índice
B-tree de PostgreSQL.

### findings

| Columna | Tipo | Notas |
|---------|------|-------|
| id | uuid | PK |
| scan_id | uuid | FK scans(id) ON DELETE CASCADE |
| source | varchar(30) | CHECK IN (zap, seo, crawler, pagespeed, search_console) |
| category | varchar(30) | CHECK IN (security, seo, performance, accessibility, best_practices) |
| rule_id | text | NULL. Ej. `SEO-001` o el pluginId de ZAP |
| title | text | NOT NULL |
| severity | varchar(10) | CHECK IN (critical, high, medium, low, info) |
| confidence | varchar(10) | CHECK IN (high, medium, low) |
| url | text | NULL |
| parameter | text | NULL |
| evidence | text | NULL |
| description | text | NOT NULL |
| impact | text | NULL |
| remediation | text | NULL |
| client_explanation | text | NULL. Redacción no técnica para el reporte |
| cwe | text | NULL |
| owasp | text | NULL |
| references | jsonb | NOT NULL, default `[]` |
| occurrences | integer | NOT NULL, default 1 |
| fingerprint | text | NOT NULL |
| status | varchar(20) | CHECK IN (open, fixed, accepted, false_positive), default open |
| raw | jsonb | NULL. Payload original de la fuente |
| created_at / updated_at | timestamptz | NOT NULL |

Índices: `UNIQUE (scan_id, fingerprint)`, `(scan_id, severity)`,
`(scan_id, source)`, `(fingerprint)`.

El índice único sobre `(scan_id, fingerprint)` implementa la deduplicación a
nivel de base de datos; el contador `occurrences` acumula las repeticiones.
El índice sobre `fingerprint` solo sirve para arrastrar el estado
`false_positive` o `accepted` entre scans del mismo sitio.

### seo_results

Agregados por scan; el detalle por página vive en `pages`.

| Columna | Tipo | Notas |
|---------|------|-------|
| id | uuid | PK |
| scan_id | uuid | FK scans(id) ON DELETE CASCADE, UNIQUE |
| pages_crawled | integer | NOT NULL |
| urls_discovered | integer | NOT NULL |
| missing_title | integer | NOT NULL |
| duplicate_title | integer | NOT NULL |
| missing_description | integer | NOT NULL |
| duplicate_description | integer | NOT NULL |
| missing_h1 | integer | NOT NULL |
| multiple_h1 | integer | NOT NULL |
| images_missing_alt | integer | NOT NULL |
| broken_internal_links | integer | NOT NULL |
| broken_external_links | integer | NOT NULL |
| missing_canonical | integer | NOT NULL |
| noindex_pages | integer | NOT NULL |
| redirect_chains | integer | NOT NULL |
| robots_txt_found | boolean | NOT NULL |
| sitemap_found | boolean | NOT NULL |
| sitemap_urls | integer | NOT NULL, default 0 |
| structured_data_summary | jsonb | NOT NULL, default `{}` |
| created_at / updated_at | timestamptz | NOT NULL |

### performance_results

| Columna | Tipo | Notas |
|---------|------|-------|
| id | uuid | PK |
| scan_id | uuid | FK scans(id) ON DELETE CASCADE |
| url | text | NOT NULL |
| strategy | varchar(10) | CHECK IN (mobile, desktop) |
| performance_score | smallint | NULL, 0..100 |
| accessibility_score | smallint | NULL |
| best_practices_score | smallint | NULL |
| seo_score | smallint | NULL |
| lcp_ms | integer | NULL |
| cls | numeric(6,4) | NULL |
| inp_ms | integer | NULL. `null` si no hay datos de campo |
| fcp_ms | integer | NULL |
| tbt_ms | integer | NULL |
| speed_index_ms | integer | NULL |
| lighthouse_version | text | NULL |
| has_field_data | boolean | NOT NULL, default false |
| raw | jsonb | NOT NULL. Respuesta original completa |
| created_at / updated_at | timestamptz | NOT NULL |

Índices: `UNIQUE (scan_id, url, strategy)`.

### search_console_connections

| Columna | Tipo | Notas |
|---------|------|-------|
| id | uuid | PK |
| project_id | uuid | FK projects(id) ON DELETE CASCADE |
| google_account_email | text | NULL |
| property_url | text | NULL. Seleccionada por el usuario |
| refresh_token_encrypted | bytea | NOT NULL |
| scopes | text[] | NOT NULL |
| status | varchar(20) | CHECK IN (connected, revoked, error), default connected |
| last_sync_at | timestamptz | NULL |
| last_error | text | NULL |
| created_at / updated_at | timestamptz | NOT NULL |

Índices: `UNIQUE (project_id)`.

El token de acceso no se persiste; se obtiene en memoria a partir del refresh
token. Ver `security.md` §Cifrado en reposo.

### search_console_metrics

| Columna | Tipo | Notas |
|---------|------|-------|
| id | uuid | PK |
| scan_id | uuid | FK scans(id) ON DELETE CASCADE |
| period | varchar(10) | CHECK IN (7d, 28d, 90d) |
| dimension | varchar(20) | CHECK IN (date, query, page, country, device) |
| dimension_value | text | NOT NULL |
| clicks | integer | NOT NULL |
| impressions | integer | NOT NULL |
| ctr | numeric(7,6) | NOT NULL |
| position | numeric(6,2) | NOT NULL |
| created_at / updated_at | timestamptz | NOT NULL |

Índices: `(scan_id, period, dimension)`,
`UNIQUE (scan_id, period, dimension, dimension_value)`.

### scores

| Columna | Tipo | Notas |
|---------|------|-------|
| id | uuid | PK |
| scan_id | uuid | FK scans(id) ON DELETE CASCADE |
| system | varchar(10) | CHECK IN (softree, google) |
| category | varchar(30) | CHECK IN (overall, security, performance, seo, accessibility, best_practices) |
| value | numeric(5,2) | NULL, 0..100 |
| weight | numeric(5,4) | NULL. Solo para `softree` |
| detail | jsonb | NOT NULL, default `{}` |
| engine_version | text | NOT NULL |
| created_at / updated_at | timestamptz | NOT NULL |

Índices: `UNIQUE (scan_id, system, category)`.

Separar el sistema evita presentar un cálculo propio como si fuera oficial de
Google (requisito §27).

### reports

| Columna | Tipo | Notas |
|---------|------|-------|
| id | uuid | PK |
| scan_id | uuid | FK scans(id) ON DELETE CASCADE |
| format | varchar(10) | CHECK IN (pdf, html, json) |
| report_version | text | NOT NULL |
| audience | varchar(20) | CHECK IN (technical, executive, combined), default combined |
| storage_path | text | NOT NULL |
| size_bytes | integer | NULL |
| checksum_sha256 | text | NULL |
| generated_at | timestamptz | NOT NULL |
| created_at / updated_at | timestamptz | NOT NULL |

Índices: `UNIQUE (scan_id, format, audience, report_version)`.

### refresh_tokens

Tabla de soporte para la sesión. No aparece en el modelo de dominio original,
pero es necesaria para revocar sesiones (RF-01.4).

| Columna | Tipo | Notas |
|---------|------|-------|
| id | uuid | PK. Coincide con el claim `jti` del refresh token |
| user_id | uuid | FK users(id) ON DELETE CASCADE |
| expires_at | timestamptz | NOT NULL |
| revoked_at | timestamptz | NULL |
| replaced_by_id | uuid | NULL, FK refresh_tokens(id). Cadena de rotación |
| user_agent | text | NULL |
| ip_address | inet | NULL |
| created_at / updated_at | timestamptz | NOT NULL |

Índices: `(user_id)`, `(expires_at)`.

## Convenciones

1. Ninguna consulta de la API filtra solo por el id del recurso: siempre se
   incluye la pertenencia (`owner_id`) para prevenir IDOR.
2. Los campos `jsonb` que guardan respuestas originales no se indexan; existen
   para trazabilidad y reproceso.
3. Las migraciones nunca borran columnas con datos en el mismo release en que se
   deja de usarlas.
