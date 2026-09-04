# Softree Audit — API Specification

- Base: `/api/v1`
- Formato: JSON, UTF-8
- Autenticación: `Authorization: Bearer <access_token>`
- OpenAPI: `GET /api/v1/openapi.json`, documentación en `GET /api/v1/docs`
- Versionado: el prefijo `/v1` es estable; los cambios incompatibles crean `/v2`

## Formato de error

```json
{
  "error": {
    "code": "invalid_credentials",
    "message": "Email o contraseña incorrectos.",
    "details": null
  }
}
```

| Código HTTP | Uso |
|-------------|-----|
| 400 | Petición mal formada |
| 401 | Sin autenticación o token inválido o expirado |
| 403 | Autenticado pero sin permiso para la operación |
| 404 | Recurso inexistente o no perteneciente al usuario |
| 409 | Conflicto de estado (por ejemplo, cancelar un scan ya terminado) |
| 422 | Validación de campos, con `details` por campo |
| 429 | Límite de tasa excedido, con cabecera `Retry-After` |
| 502 | Falla de una integración externa en una operación sincrónica |
| 503 | Dependencia interna no disponible |

## Paginación

Listados con `?limit=<1..100>&cursor=<opaco>`. Respuesta:

```json
{ "items": [], "next_cursor": null, "total": 0 }
```

## Endpoints

### Health

```
GET  /api/v1/health          → 200 sin autenticación
```

Devuelve estado, versiones (`app`, `scan_engine`, `report`), entorno y banderas
de seguridad relevantes.

### Auth

```
POST /api/v1/auth/login      { email, password } → { access_token, token_type, expires_in, user }
POST /api/v1/auth/refresh    (cookie refresh)    → { access_token, token_type, expires_in }
POST /api/v1/auth/logout     (cookie refresh)    → 204
GET  /api/v1/auth/me                             → { user }
```

`login` y `refresh` establecen la cookie `softree_refresh`.

### Projects

```
GET    /api/v1/projects
POST   /api/v1/projects        { name, client_name?, notes? }
GET    /api/v1/projects/{id}
PUT    /api/v1/projects/{id}
DELETE /api/v1/projects/{id}   → 204
```

### Sites

```
GET    /api/v1/sites?project_id=
POST   /api/v1/sites           { project_id, name, base_url, authorized_by?, authorization_date?, authorization_notes?, is_active }
GET    /api/v1/sites/{id}                → incluye el scope
PUT    /api/v1/sites/{id}
DELETE /api/v1/sites/{id}?force=false    → 204
GET    /api/v1/sites/scope-limits        → máximos admitidos para el scope
```

`base_url` se normaliza en el servidor: esquema y host en minúsculas, puerto por
defecto eliminado, consulta y fragmento descartados. Se rechazan las URL con
credenciales embebidas.

`authorized_by` y `authorization_date` se informan juntos o se dejan vacíos: una
autorización a medias no es auditable. El campo derivado `is_authorized` indica
si el sitio puede escanearse.

Borrar un sitio con auditorías devuelve `409` con el código `site_has_scans`; la
operación se repite con `?force=true` para eliminar también el histórico. Lo
mismo aplica a un proyecto con sitios (`project_has_sites`).

### Scope

```
GET /api/v1/sites/{id}/scope
PUT /api/v1/sites/{id}/scope   { allowed_domains, allowed_paths, excluded_paths, max_pages, max_depth, timeout_seconds, request_delay_ms, concurrency, respect_robots, zap_spider_enabled }
```

El scope se crea automáticamente al crear el sitio, acotado al host de la URL
base y con valores por defecto conservadores.

Validaciones del servidor:

- Los dominios se normalizan y deduplican; deben cubrir el host de la URL base o
  la respuesta es `422` con el código `scope_excludes_site`.
- Las rutas se comparan por prefijo respetando los límites de segmento y no
  admiten comodines. Una ruta presente a la vez en `allowed_paths` y
  `excluded_paths` devuelve `422` con el código `scope_path_conflict`.
- Los máximos coinciden con los `CHECK` de la base de datos y se publican en
  `GET /sites/scope-limits`, de modo que la interfaz no los duplique.
- Si cambia el host de la URL base, el scope se realinea al host nuevo.

### Scans

```
POST /api/v1/scans                 { site_id, scan_type }  → 202 { id, status: "queued" }
GET  /api/v1/scans?site_id=&status=
GET  /api/v1/scans/{id}                                    → scan con modules[] y progress
POST /api/v1/scans/{id}/cancel                             → 202
GET  /api/v1/scans/{id}/modules
GET  /api/v1/scans/{id}/pages
GET  /api/v1/scans/{id}/findings?severity=&source=&status=
GET  /api/v1/scans/{id}/comparison?against=previous|<scan_id>
```

`POST /scans` valida de forma sincrónica y rechaza rápido; el trabajo real se
encola. Nunca bloquea. Validaciones previas, en este orden:

| Comprobación | Respuesta si falla |
|--------------|--------------------|
| El sitio existe y pertenece al usuario | `404 not_found` |
| El sitio está activo | `409 site_inactive` |
| El sitio tiene autorización registrada | `409 site_not_authorized` |
| El scope cubre la URL base | `422 scope_excludes_site` |
| El guard de SSRF aprueba el destino | `422 target_unreachable`, con `details.reason` |

Acepta la cabecera `Idempotency-Key`: repetir el POST con la misma clave
devuelve la auditoría ya creada en lugar de lanzar otra. La clave vive 24 horas.

`GET /scans/{id}` responde con `Cache-Control: no-store` y devuelve el estado de
cada módulo, pensado para polling cada 2 segundos. Solo aparecen los módulos que
realmente se ejecutan: un módulo aún no implementado no genera fila.

El scan guarda un `scope_snapshot` con el scope efectivo en el momento de
lanzarlo, de modo que un scan histórico sea reproducible aunque el scope del
sitio cambie después.

### Findings

```
GET   /api/v1/findings?site_id=&severity=&status=
PATCH /api/v1/findings/{id}   { status: open|fixed|accepted|false_positive }
```

### Vistas por sitio

```
GET /api/v1/sites/{id}/security       último resultado de seguridad
GET /api/v1/sites/{id}/seo            último resultado SEO
GET /api/v1/sites/{id}/performance    último resultado de performance
GET /api/v1/sites/{id}/scans          histórico
```

### Search Console

```
GET  /api/v1/integrations/google/status?project_id=
POST /api/v1/integrations/google/connect     → { authorization_url, state }
GET  /api/v1/integrations/google/callback    (redirect de Google)
GET  /api/v1/integrations/google/properties?project_id=
PUT  /api/v1/integrations/google/property    { project_id, property_url }
DELETE /api/v1/integrations/google/connection?project_id=  → 204
GET  /api/v1/scans/{id}/search-console?period=7d|28d|90d&dimension=
```

Cuando no hay conexión, `status` devuelve `{"status": "not_connected"}` con
HTTP 200. La ausencia de conexión no es un error.

### Reports

```
POST /api/v1/reports/{scan_id}/generate   { formats: ["pdf","html","json"], audience }  → 202
GET  /api/v1/reports/{scan_id}                                                          → listado
GET  /api/v1/reports/{scan_id}/download?format=pdf                                      → binario
```

## Contrato para n8n

No se construye un adaptador específico. El flujo soportado es:

```
POST /api/v1/auth/login          → access_token
POST /api/v1/scans               → scan_id
GET  /api/v1/scans/{scan_id}     → polling hasta status terminal
GET  /api/v1/scans/{id}/findings → resultados
POST /api/v1/reports/{id}/generate
GET  /api/v1/reports/{id}/download?format=pdf
```

Requisitos que esto impone y que se respetan en el diseño: todo endpoint devuelve
JSON estable, los estados terminales son explícitos (`completed`, `failed`,
`cancelled`, `partial`) y `POST /scans` es idempotente respecto a la cabecera
opcional `Idempotency-Key`.

## Cabeceras de respuesta

`X-Request-ID` en toda respuesta, propagado al log estructurado.
`X-App-Version` con la versión de la aplicación.
