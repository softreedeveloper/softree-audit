# Slice 2 — Projects, Sites y Scope

Estado: **completado**.

## Alcance entregado

| Área | Contenido |
|------|-----------|
| Proyectos | CRUD completo, unicidad de nombre por propietario, contador de sitios |
| Sitios | CRUD completo, normalización de la URL base, autorización obligatoria para escanear |
| Scope | Lectura y actualización, creación automática con valores por defecto, límites publicados por la API |
| Paginación | Cursor opaco sobre UUID v7, con `limit` acotado |
| Seguridad | Aislamiento por propietario en toda consulta, 404 en lugar de 403, borrados protegidos |
| Frontend | Listado y alta de proyectos, detalle con sus sitios, editor de sitio y de scope |
| Pruebas | 213 pruebas en total (81 del Slice 1 más 132 nuevas) |

## Decisiones de esta iteración

| Tema | Decisión | Motivo |
|------|----------|--------|
| Borrado con dependencias | `409` y repetición con `?force=true` | Un borrado en cascada silencioso destruiría el histórico de auditorías, que es el valor del producto |
| Comodines en las rutas del scope | No se aceptan; la comparación es por prefijo con límite de segmento | Un comodín amplía el alcance real de forma difícil de razonar, y el scope es un control de seguridad |
| Coincidencia de dominios | Dominio exacto y subdominios, nunca sufijo textual | `malicioso-softree.mx` no debe entrar en el scope de `softree.mx` |
| Límites del scope | Los publica la API en `GET /sites/scope-limits` | Duplicarlos en el frontend haría que se desincronizaran |
| Cambio de host de un sitio | El scope se realinea automáticamente | Un scope heredado dejaría de cubrir el sitio y el scan sería inútil |
| Rutas del detalle | `?id=` resuelto en el cliente en vez de rutas dinámicas | El frontend se compila como sitio estático; una ruta dinámica exigiría SSR |
| Confirmación de borrado | Confirmación en línea, nunca `window.confirm` | Los diálogos modales bloquean el hilo del navegador y romperían las pruebas E2E del Slice 11 |

## Criterios de aceptación

| Criterio | Resultado |
|----------|-----------|
| CRUD de proyectos y de sitios completo desde la API y la interfaz | Cumplido |
| La URL base se normaliza y rechaza esquemas y credenciales inválidos | Cumplido |
| Un sitio sin autorización completa queda marcado como no escaneable | Cumplido |
| Una autorización a medias se rechaza | Cumplido |
| El scope se crea solo, acotado al host del sitio | Cumplido |
| El scope no puede excluir el host del propio sitio | Cumplido |
| Los máximos del scope no pueden superarse | Cumplido |
| Los recursos de otro usuario devuelven 404 en lectura, escritura y borrado | Cumplido |
| El propietario no puede falsificarse desde el cuerpo de la petición | Cumplido |
| La paginación por cursor recorre todas las páginas sin repetir ni perder elementos | Cumplido |
| Un cursor inválido devuelve 400 | Cumplido |
| Borrar con dependencias exige confirmación explícita | Cumplido |
| Todas las vistas manejan Loading, Empty, Error y Unauthorized | Cumplido |
| `ruff`, `ruff format`, `mypy --strict`, `alembic check` sin hallazgos | Cumplido |
| `astro check` y `tsc --noEmit` sin errores ni avisos | Cumplido |

## Verificación

```bash
make test          # 213 passed
make lint
```

Comprobación manual en navegador: alta de proyecto, alta de sitio con
`HTTP://Test-Target:80/` normalizada a `http://test-target`, edición del scope y
rechazo con mensaje claro de un scope que no cubre el host del sitio.

## Hallazgos corregidos durante el slice

| Hallazgo | Corrección |
|----------|-----------|
| `MissingGreenlet` al serializar `updated_at` tras un UPDATE: SQLAlchemy dejaba la columna expirada y la recargaba de forma perezosa fuera del contexto asíncrono | `eager_defaults` en la base declarativa, que recupera los valores del servidor con RETURNING |
| `model_validate(..., update=...)` no existe en Pydantic v2 | `model_validate(...).model_copy(update=...)` |
| El tipo `FormEvent` está marcado como obsoleto en `@types/react` 19 | `preventDefault` en el JSX y manejadores sin parámetro |

## Siguiente

Slice 3: orquestación de scans y crawler, con el guard de SSRF como pieza
central (`docs/spec/security.md` §2).
