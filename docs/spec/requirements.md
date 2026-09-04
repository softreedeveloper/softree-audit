# Softree Audit — Requirements

- Documento: `docs/spec/requirements.md`
- Versión: 0.1.0
- Estado: aprobado para MVP

## 1. Propósito

Softree Audit es una plataforma **interna** de auditoría de sitios web. Combina
seguridad, SEO, rendimiento, accesibilidad, buenas prácticas y datos de Google
Search Console en un informe profesional que Softree entrega como valor agregado
de cada proyecto web.

No es un escáner público ni una plataforma de pentesting ofensivo.

## 2. Alcance de uso autorizado

La plataforma solo debe auditar:

1. Sitios propios de Softree.
2. Sitios desarrollados por Softree.
3. Sitios de clientes con autorización explícita.

Control técnico: un `Site` no puede escanearse si no tiene registrados
`authorized_by` y `authorization_date`. Ver `security.md` §Autorización.

## 3. Requisitos funcionales

### RF-01 Autenticación
- RF-01.1 Login con email + contraseña.
- RF-01.2 Contraseñas con hash Argon2id. Nunca en texto plano.
- RF-01.3 Access token JWT de vida corta y refresh token rotativo revocable.
- RF-01.4 Logout que revoca el refresh token activo.
- RF-01.5 Rate limiting en login.
- RF-01.6 Sin registro público. Los usuarios se crean por CLI.

### RF-02 Proyectos
- CRUD completo. Cada proyecto pertenece a un usuario.

### RF-03 Sitios
- CRUD completo. Cada sitio pertenece a un proyecto.
- Campos de autorización obligatorios para escanear.

### RF-04 Scope
- Dominios permitidos, rutas permitidas, rutas excluidas, `max_pages`,
  `max_depth`, `timeout`, `request_delay_ms`, `concurrency`.
- Valores por defecto seguros y límites máximos no superables por el usuario.

### RF-05 Auditoría
- Tipos: `full`, `security`, `seo`, `performance`.
- Ejecución como trabajo en segundo plano. El cliente HTTP nunca espera bloqueado.
- Estado global: `queued | running | completed | failed | cancelled | partial`.
- Estado por módulo: `pending | running | completed | failed | skipped`.
- Un módulo que falla no cancela el scan completo.
- Cancelación bajo demanda.

### RF-06 Crawler
- Soporta HTTP, HTTPS, redirects, HTML, `robots.txt`, `sitemap.xml`.
- Extrae: URL, status code, content type, title, meta description, canonical,
  meta robots, H1, H2, links, imágenes, `alt`, scripts, forms, tiempo de respuesta.
- Evita loops, duplicados, crawling infinito y URLs fuera de scope.

### RF-07 Seguridad (OWASP ZAP)
- Passive scan por defecto. Active scan no habilitado en el MVP.
- Las alertas de ZAP se normalizan a `Finding`; no se almacenan como finding final
  sin normalizar.

### RF-08 SEO
- Reglas modulares `SEO-001` … `SEO-016`, documentadas en
  `docs/spec/seo-rules.md`. Cada regla produce un finding normalizado.
- Detección de datos estructurados: JSON-LD, Schema.org, OpenGraph, Twitter Cards.

### RF-09 Performance
- Google PageSpeed Insights API real, estrategias `mobile` y `desktop`.
- Guarda scores `performance`, `accessibility`, `best_practices`, `seo` y métricas
  LCP, CLS, INP, FCP, TBT, Speed Index.
- Guarda la respuesta original para trazabilidad.

### RF-10 Search Console
- OAuth 2.0, credenciales cifradas en reposo, selección de propiedad.
- Métricas `clicks`, `impressions`, `ctr`, `position` por `date`, `query`, `page`,
  `country`, `device`; periodos 7 días, 28 días y 3 meses.
- Si no está conectado, el módulo queda `skipped` y el resto del scan continúa.

### RF-11 Findings
- Modelo unificado con `source`, severidad, confianza, evidencia, remediación,
  CWE y OWASP.
- Deduplicación por fingerprint de `source + rule + url + parameter`.
- Estados `open | fixed | accepted | false_positive`.

### RF-12 Scoring
- Módulo independiente `packages/scoring`.
- Categorías Security, Performance, SEO, Accessibility, Best Practices.
- Pesos configurables (defecto 30/25/25/10/10). Nunca hardcodeados.
- Dos scores visibles y diferenciados: **Google Score** y **Softree Score**.

### RF-13 Histórico y comparación
- Listado histórico de scans por sitio.
- Comparación scan anterior vs actual con clasificación `NEW | FIXED | UNCHANGED
  | REGRESSED` y deltas de métricas.

### RF-14 Reportes
- Formatos PDF, HTML y JSON.
- PDF con branding Softree, doble nivel de lectura (técnico y ejecutivo).

### RF-15 API
- REST versionada con OpenAPI válido. Utilizable por n8n sin capa adicional.

### RF-16 Observabilidad
- Logs estructurados. Cada scan registra `scan_id`, `module`, `status`,
  `duration`, `error`.

## 4. Requisitos no funcionales

- RNF-01 Los scans se ejecutan como trabajos en segundo plano con concurrencia limitada.
- RNF-02 Toda integración externa tiene timeout, retry acotado, normalización de
  error, logging y degradación elegante. Sin retries infinitos.
- RNF-03 Sin datos simulados en producción. Los mocks solo existen en tests.
- RNF-04 Identificadores públicos UUID. No se exponen IDs secuenciales.
- RNF-05 Sin secretos en el repositorio. Configuración por variables de entorno.
- RNF-06 Despliegue con Docker Compose. Sin Kubernetes en el MVP.
- RNF-07 Frontend responsive con temas claro y oscuro.
- RNF-08 Toda pantalla maneja los estados Loading, Empty, Error, Success, Partial,
  Unauthorized y Not connected.
- RNF-09 Versionado explícito de `APP_VERSION`, `SCAN_ENGINE_VERSION` y
  `REPORT_VERSION` persistido en cada scan y reporte.

## 5. Fuera de alcance del MVP

Active pentesting avanzado, ejecución de exploits, ataques a credenciales, fuerza
bruta, detección de malware, escáner público, escaneo arbitrario de Internet,
explotación automatizada, facturación, registro público, equipos, RBAC complejo y
agentes de IA autónomos.

La arquitectura debe permitir incorporarlos después si fueran apropiados y
autorizados. Ver `docs/spec/architecture.md` §Extensibilidad.

## 6. Inconsistencias detectadas y resolución

| ID | Inconsistencia | Resolución |
|----|----------------|------------|
| R1 | El proyecto se solicitó como `softree-seo`; el producto especificado es «Softree Audit» | Directorio `softree-seo/`, producto y branding `SOFTREE AUDIT`. ADR-000 |
| R2 | Se sugiere Celery o RQ, pero el stack es asíncrono | Cola `arq`, nativa asíncrona sobre Redis. ADR-003 |
| R3 | Accessibility y Best Practices provienen de Lighthouse, y también pesan en el score propio | Se persisten los scores de Google sin alterar y se calcula aparte el agregado propio. ADR-006 |
| R4 | INP solo existe con datos de campo (CrUX) | Campo anulable. `null` significa «sin datos de campo», no cero |
| R5 | El spider de ZAP genera tráfico activo aunque el scan sea pasivo | Spider limitado por scope y `request_delay`, configurable y desactivable. AJAX spider deshabilitado |
| R6 | El scope se valida en la API, pero ZAP emite sus propias peticiones | El scope se inyecta además como contexto include/exclude en ZAP. Doble barrera |
| R7 | El criterio de aceptación usa `https://example.test`, un TLD no resoluble | La prueba de aceptación usa el `test-target` en la red Docker |

## 7. Dependencias externas

| Dependencia | Uso | Falla tolerable |
|-------------|-----|-----------------|
| PostgreSQL | Persistencia | No |
| Redis | Cola y rate limiting | No |
| OWASP ZAP | Passive scan | Sí, módulo `failed` |
| PageSpeed Insights API | Performance | Sí, módulo `failed` |
| Google Search Console API | Métricas de búsqueda | Sí, módulo `skipped` |

## 8. Riesgos

Ver `docs/spec/security.md` para riesgos de seguridad y
`docs/spec/architecture.md` §Riesgos para riesgos técnicos.
