# Verificación final del MVP

Fecha: 2026-09-03 · Versión: Softree Audit 0.1.0

Este documento recorre la especificación completa y comprueba, requisito por
requisito, qué existe realmente en el repositorio. No es un resumen de lo que se
pretendía construir: cada fila cita el archivo o la prueba que lo respalda, y las
carencias se declaran como tales.

## 1. Cómo se verificó

| Comprobación | Comando | Resultado |
|--------------|---------|-----------|
| Suite Python completa | `make test` | 738 pruebas, 0 fallos |
| Linters y tipos | `make lint` | ruff, ruff format, mypy (125 archivos) y `astro check` + `tsc` sin errores |
| Esquema OpenAPI | `make openapi` | 37 rutas, 45 operaciones, 72 esquemas |
| Migraciones al día | `alembic check` | Sin cambios pendientes |
| Auditoría real de extremo a extremo | `test-target` en la red Docker | 18 páginas, 16 reglas SEO, 83 alertas ZAP normalizadas a 6 findings, score 87.1, PDF de 22 páginas |
| Cadena de performance contra la API real | `PageSpeedClient` sobre `https://example.com` | Dos estrategias, 8 Google Scores, 6 métricas, caché en Redis acertando en la repetición y un finding PSI-008 por estrategia |

Reparto de pruebas: 549 unitarias, 189 de integración, 182 marcadas `security`
(los marcadores se solapan: una prueba de integración puede ser además de
seguridad). Las E2E son 20 especificaciones de Playwright: 11 de flujo y 9 de
seguridad.

## 2. Requisitos funcionales

| Requisito | Estado | Evidencia |
|-----------|--------|-----------|
| RF-01.1 Login email + contraseña | Cumplido | `api/v1/auth.py`, `tests/integration/test_auth_flow.py` |
| RF-01.2 Argon2id | Cumplido | `core/security.py`: `time_cost=3, memory_cost=65536, parallelism=4`; hash señuelo contra enumeración de usuarios |
| RF-01.3 JWT corto + refresh rotativo revocable | Cumplido | Access 15 min, refresh en cookie `HttpOnly` con rotación, detección de reuso y ventana de gracia de 15 s (D-059) |
| RF-01.4 Logout revoca el refresh | Cumplido | `POST /auth/logout`, `tests/integration/test_auth_flow.py` |
| RF-01.5 Rate limiting en login | Cumplido | `core/rate_limit.py`: 5 intentos / 15 min, `fail_closed=True` |
| RF-01.6 Sin registro público | Cumplido | No existe ninguna ruta de alta; los usuarios se crean con `softree-audit create-user` |
| RF-02 Proyectos CRUD | Cumplido | `api/v1/projects.py`, aislados por `owner_id` |
| RF-03 Sitios CRUD con autorización | Cumplido | `api/v1/sites.py`; sin `authorized_by` y `authorization_date` el scan se rechaza |
| RF-04 Scope con máximos no superables | Cumplido | `models/site.py` define `MAX_PAGES_LIMIT`, `MAX_DEPTH_LIMIT`, `MAX_TIMEOUT_SECONDS`, `MAX_REQUEST_DELAY_MS`, `MAX_CONCURRENCY`; visibles en `GET /sites/scope-limits` y en la pantalla de configuración |
| RF-05 Tipos y estados de scan | Cumplido | `models/enums.py`: `ScanType` (4), `ScanStatus` (6), `ModuleStatus` (5). Un módulo que falla no cancela el scan: `scans/orchestrator.py` |
| RF-05 Ejecución en segundo plano | Cumplido | `POST /scans` devuelve 202 y encola en arq; el cliente nunca espera bloqueado |
| RF-05 Cancelación | Cumplido | `POST /scans/{id}/cancel`, `scans/cancellation.py` |
| RF-06 Crawler | Cumplido | `services/crawler/`: redirects, `robots.txt`, `sitemap.xml` con defusedxml, control de duplicados y de scope |
| RF-07 Passive scan únicamente | Cumplido | `services/security/` no invoca `ascan` en ningún punto; solo `pscan` y el spider acotado |
| RF-07 Normalización de alertas | Cumplido | `services/security/normalizer.py`; las alertas crudas nunca se guardan como finding |
| RF-08 SEO-001…016 | Cumplido | `services/seo/catalog.py` define las 16 reglas con explicación para cliente |
| RF-08 Datos estructurados | Cumplido | JSON-LD, Schema.org, OpenGraph y Twitter Cards en `services/seo/` |
| RF-09 PageSpeed real, mobile y desktop | Cumplido y verificado en vivo | Con `PAGESPEED_API_KEY` configurada, `https://example.com` devuelve las dos estrategias con Lighthouse 13.4.1: performance 100, accessibility 96, best practices 96, SEO 80. La ruta de degradación ante el 429 real de Google se verificó antes, sin clave |
| RF-09 Métricas y respuesta original | Cumplido y verificado en vivo | `models/results.py`: `lcp_ms`, `cls`, `inp_ms`, `fcp_ms`, `tbt_ms`, `speed_index_ms` y `raw` en JSONB. En la medición real llegaron las seis, `inp_ms` incluido, porque el objetivo tiene datos de campo (`has_field_data=True`) |
| RF-10 OAuth y cifrado en reposo | Implementado, falta el consentimiento real | `services/search_console/oauth.py`, token cifrado con Fernet derivada por HKDF de `SECRET_KEY`. Credenciales ya configuradas; el callback se corrigió para funcionar sin sesión, como llega el navegador (D-064) |
| RF-10 Módulo `skipped` si no hay conexión | Cumplido | `scans/orchestrator.py`; el resto del scan continúa |
| RF-11 Modelo unificado de finding | Cumplido | `models/finding.py` con `source`, severidad, confianza, evidencia, remediación, CWE y OWASP |
| RF-11 Fingerprint y deduplicación | Cumplido | `services/findings/models.py`: `sha256(source \| rule \| url canónica \| parámetro)` |
| RF-11 Estados | Cumplido | `open`, `fixed`, `accepted`, `false_positive`; solo los dos últimos se arrastran entre scans |
| RF-12 Módulo de scoring independiente | Cumplido | `softree_audit/scoring/` no importa nada fuera de sí mismo. Verificado leyendo sus imports |
| RF-12 Pesos configurables | Cumplido | `scoring/weights.py`: 30/25/25/10/10 por defecto, sobreescribibles por entorno, nunca hardcodeados en el cálculo |
| RF-12 Google Score y Softree Score | Cumplido | `ScoreSystem` distingue ambos; el de Google se persiste sin alterar |
| RF-13 Histórico y comparación | Cumplido | `GET /sites/{id}/history`, `GET /scans/{id}/comparison` con `NEW`, `FIXED`, `UNCHANGED`, `REGRESSED` |
| RF-14 PDF, HTML y JSON | Cumplido | `ReportFormat`; un solo `ReportModel` alimenta los tres |
| RF-14 Branding y doble nivel de lectura | Cumplido y verificado en vivo | `services/reports/templates/report.html.j2`. La audiencia compone tres documentos del mismo modelo: sobre una auditoría real de 26 páginas, la versión ejecutiva ocupa 8 páginas, la técnica 33 y la completa 40 (D-067) |
| RF-15 REST versionada con OpenAPI válido | Cumplido | `docs/api/openapi.json` regenerado; tipos TypeScript derivados de él |
| RF-16 Logs estructurados por scan | Cumplido | structlog con `scan_id`, `module`, `status`, `duration` y `error` |

## 3. Requisitos no funcionales

| Requisito | Estado | Evidencia |
|-----------|--------|-----------|
| RNF-01 Trabajos en segundo plano con concurrencia limitada | Cumplido | arq sobre Redis, concurrencia acotada por scope y por worker |
| RNF-02 Timeout, retry acotado y degradación | Cumplido | Timeout explícito en los tres clientes externos; `with_retry(..., attempts=3)` en PageSpeed; sin reintentos infinitos. Timeout por módulo en `scans/modules.py` (D-039) |
| RNF-03 Sin datos simulados en producción | Cumplido | Ninguna importación de `unittest.mock` ni de `respx` fuera de `tests/` |
| RNF-04 Identificadores UUID | Cumplido | Toda clave primaria pública es UUID |
| RNF-05 Sin secretos en el repositorio | Cumplido | `.env` y `.env.*` ignorados salvo `.env.example`; las credenciales de E2E son variables obligatorias sin valor por defecto |
| RNF-06 Docker Compose | Cumplido | `postgres`, `redis`, `api`, `worker`, `web`, más los perfiles `scanner` (ZAP) y `testing` (test-target) |
| RNF-07 Responsive, claro y oscuro | Cumplido | `styles/global.css` cubre `data-theme` explícito y `prefers-color-scheme` |
| RNF-08 Estados de pantalla | Cumplido | `UiStates.tsx` exporta Loading, Empty, Error, Unauthorized, NotConnected, Partial y Success |
| RNF-09 Versionado persistido | Cumplido | `engine_version` en cada scan y `report_version` en cada reporte; ambos visibles en `/health` y en la configuración |

## 4. Límites de seguridad

Son los requisitos que no admiten degradación. Todos se comprobaron ejecutando
la plataforma, no solo leyendo el código.

| Control | Estado | Evidencia |
|---------|--------|-----------|
| Validación de URL y resolución DNS antes de cada petición | Cumplido | `services/common/url_guard.py` |
| Bloqueo de loopback, redes privadas, link-local y endpoints de metadatos | Cumplido | 64 pruebas en `tests/unit/test_url_guard.py`. Verificado en vivo: con el valor por defecto seguro, auditar el test-target devuelve `422 target_unreachable / blocked_network` |
| Formas ofuscadas de IPv4 | Cumplido | `parse_obscured_ipv4` cubre `2130706433`, `0x7f000001`, `0177.0.0.1` y `127.1` (D-026) |
| Revalidación por salto de redirect | Cumplido | Cada destino se vuelve a validar; la IP se fija con `Host` y `sni_hostname` para evitar DNS rebinding |
| El scope de ZAP como segunda barrera | Cumplido | `services/security/scope_regex.py` inyecta include/exclude en el contexto de ZAP |
| Sin active scan | Cumplido | Ninguna llamada a `ascan` en el código |
| Secretos fuera de la respuesta de la API | Cumplido | `GET /settings` publica solo `configured` y el nombre de la variable; `tests/integration/test_settings.py` lo comprueba inyectando credenciales y verificando que no aparecen en el JSON |
| Aislamiento entre cuentas y proyectos | Cumplido | Toda consulta filtra por propietario; hay pruebas de acceso cruzado en proyectos, sitios, scans, findings, reportes y Search Console |
| Tokens cifrados en reposo | Cumplido | Fernet sobre el refresh token de Google |

## 5. Carencias declaradas

1. **Search Console: falta el consentimiento real.** Las credenciales ya están
   configuradas y el callback se corrigió tras descubrir que exigía sesión y
   por tanto era imposible de completar desde un navegador (D-064). El canje
   de código, el cifrado del refresh token y el uso único del `state` están
   verificados en integración contra el contrato real del navegador, sin
   cabecera `Authorization`. Queda pulsar «Conectar» y aceptar en Google con
   una cuenta que tenga una propiedad verificada.
2. **La prueba E2E de la pantalla de configuración no se ha ejecutado.** Se
   añadió en `tests/e2e/specs/security.spec.ts`, pero la suite E2E exige
   `E2E_EMAIL` y `E2E_PASSWORD` de un usuario real, que no se versionan. Lo que
   comprueba esa prueba en la interfaz está cubierto en integración.
3. **El marcador `slow` está declarado y no lo usa ninguna prueba.** Se mantiene
   porque la suite E2E y las auditorías reales lo necesitarán.
4. **`services/reports/builder.py` consulta la base de datos**, a diferencia del
   resto de servicios. Es una excepción consciente: el reporte se construye a
   partir de lo ya persistido. El motor de scoring, que es donde la regla
   importa, sí es una función pura sin IO.
5. **Sin integración continua.** No hay `.github/workflows`. Los comandos que
   ejecutaría (`make lint`, `make test`) están listos y documentados.

## 6. Fuera de alcance, por decisión

Active pentesting, ejecución de exploits, ataques a credenciales, fuerza bruta,
detección de malware, escáner público, escaneo arbitrario de Internet,
explotación automatizada, facturación, registro público, equipos, RBAC complejo
y agentes autónomos. Ninguno está implementado ni parcialmente presente.

## 7. Conclusión

Los 16 requisitos funcionales y los 9 no funcionales están implementados. La
única carencia de verificación que queda por credenciales es Search Console;
no afecta a ningún límite de seguridad. La
plataforma se ejecutó de extremo a extremo contra un objetivo real y produjo el
entregable completo: hallazgos normalizados, score, comparación entre
auditorías y reporte en PDF.
