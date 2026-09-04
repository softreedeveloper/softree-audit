# Slice 1 — Setup, Docker, base de datos, API, frontend y autenticación

Estado: **completado**.

## Alcance entregado

| Área | Contenido |
|------|-----------|
| Especificación | `docs/spec/` completo y ADR-000 a ADR-008 |
| Infraestructura | Docker Compose con PostgreSQL, Redis, API y frontend; perfiles `scanner` y `testing` |
| Base de datos | 14 tablas con UUID v7, timestamps, CHECK de enumerados y migración inicial de Alembic |
| API | FastAPI con OpenAPI, formato único de error, cabeceras de seguridad y `X-Request-ID` |
| Autenticación | Argon2id, JWT de acceso, refresh rotativo revocable en cookie `HttpOnly`, detección de reuso |
| Protección | Límites de tasa en Redis, redacción de secretos en logs, cifrado en reposo para credenciales de terceros |
| Frontend | Astro 7 + React 19 + Tailwind 4, login, shell con barra lateral, temas y los siete estados de pantalla |
| CLI | `create-user`, `rotate-secrets`, `version` |
| Pruebas | 81 pruebas: unitarias, de integración y de seguridad |
| Sitio de pruebas | `test-target` con defectos controlados |

## Criterios de aceptación

| Criterio | Resultado |
|----------|-----------|
| `docker compose up -d` levanta los servicios sanos | Cumplido |
| Migraciones aplicables y coherentes con los modelos (`alembic check`) | Cumplido |
| `POST /auth/login` devuelve access token y cookie de refresh | Cumplido |
| Credenciales inválidas devuelven 401 sin revelar si el email existe | Cumplido |
| El límite de tasa dispara 429 en el sexto intento, con `Retry-After` | Cumplido |
| `GET /auth/me` responde 401 sin token y 200 con token | Cumplido |
| El refresh rota el token y el reuso revoca toda la sesión | Cumplido |
| El logout revoca el refresh token | Cumplido |
| La interfaz permite iniciar sesión y llegar al dashboard | Cumplido |
| Los estados Loading, Empty, Error y Unauthorized se muestran correctamente | Cumplido |
| `ruff`, `ruff format` y `mypy --strict` sin hallazgos | Cumplido |
| `astro check` y `tsc --noEmit` sin errores | Cumplido |
| `npm audit` sin vulnerabilidades | Cumplido |
| Sin secretos en el repositorio | Cumplido |

## Verificación

```bash
make up && make migrate && make user
make test          # 81 passed
make lint
curl -s http://localhost:8000/api/v1/health | jq
```

## Hallazgos corregidos durante el slice

| Hallazgo | Corrección |
|----------|-----------|
| La revocación por reuso de refresh token se perdía con el rollback de la petición fallida | Se confirma la transacción antes de devolver 401 (D-018) |
| `EmailStr` rechazaba dominios reservados y bloqueaba el login interno | Validación de forma en el login; `EmailStr` se mantiene en la creación de cuentas (D-016) |
| Una consulta fallida en `/health` dejaba la sesión inutilizable y convertía el 503 en 500 | Rollback explícito en el manejo del error |
| `alembic check` reportaba los CHECK de los enumerados como eliminados en cada ejecución | Exclusión mediante `include_object` (D-017) |
| `Redis[str]` rompía la construcción de rutas de FastAPI | Alias `RedisClient` genérico solo bajo `TYPE_CHECKING` (D-019) |
| Astro 5 arrastraba vulnerabilidades altas (XSS, SSRF) | Actualización a Astro 7 |

## Siguiente

Slice 2: Projects, Sites y Scope, con su CRUD, validación de scope y las vistas
correspondientes.
