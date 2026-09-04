# Setup de desarrollo

## Requisitos

- Docker y Docker Compose
- Node 20 o superior (para trabajar el frontend fuera de Docker)
- Python 3.12 o superior (para trabajar el backend fuera de Docker)
- `make`

## Arranque rápido

```bash
cp .env.example .env
# Generar una clave real:
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
# Pegar el valor en SECRET_KEY

make up          # levanta postgres, redis, api y web
make migrate     # aplica las migraciones
make user        # crea el primer usuario de forma interactiva
```

| Servicio | URL |
|----------|-----|
| Frontend | http://localhost:4321 |
| API | http://localhost:8000/api/v1 |
| OpenAPI | http://localhost:8000/api/v1/docs |
| Health | http://localhost:8000/api/v1/health |

## Perfiles opcionales

```bash
docker compose --profile scanner up -d      # añade OWASP ZAP
docker compose --profile testing up -d      # añade el test-target
```

## Comandos

```bash
make up            # levantar
make down          # detener
make logs          # seguir logs
make migrate       # alembic upgrade head
make revision m="mensaje"   # nueva migración autogenerada
make user          # crear usuario
make test          # suite completa
make test-unit     # solo unit
make lint          # ruff + mypy + tsc
make fmt           # formateo
make openapi       # exporta openapi.json y regenera tipos TS
```

## Trabajo local sin Docker

Backend:

```bash
cd apps/api
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn softree_audit.main:app --reload
```

Frontend:

```bash
cd apps/web
npm install
npm run dev
```

El servidor de desarrollo de Astro hace proxy de `/api` hacia
`http://localhost:8000`, de modo que frontend y API comparten origen y la cookie
de refresh funciona sin relajar `SameSite`.

## Variables de entorno

Ver `.env.example`. Las relevantes para el Slice 1:

| Variable | Obligatoria | Notas |
|----------|-------------|-------|
| `APP_ENV` | sí | `development`, `staging` o `production` |
| `SECRET_KEY` | sí | Mínimo 32 caracteres. El valor de ejemplo se rechaza fuera de desarrollo |
| `DATABASE_URL` | sí | `postgresql+asyncpg://...` |
| `REDIS_URL` | sí | |
| `CORS_ORIGINS` | no | Vacío cuando se sirve same-origin |
| `SSRF_ALLOW_PRIVATE_NETWORKS` | no | Solo desarrollo y pruebas |

## Credenciales de Google

Ninguna es obligatoria para arrancar. Sin ellas, el módulo de performance queda
`failed` y el de Search Console `skipped`, y el resto de la auditoría continúa.

### PageSpeed Insights

1. En [Google Cloud Console](https://console.cloud.google.com), **APIs y
   servicios > Biblioteca**, habilitar `PageSpeed Insights API`.
2. **Credenciales > Crear credenciales > Clave de API**.
3. Restringir la clave a esa única API. No hace falta restricción por referente:
   las peticiones salen del servidor, no del navegador.
4. `PAGESPEED_API_KEY=<clave>` en `.env`.

Sin clave se usa la cuota anónima compartida de Google, habitualmente agotada.
Con clave, 25 000 consultas diarias.

### Search Console

1. Habilitar `Google Search Console API` en el mismo proyecto.
2. **Pantalla de consentimiento de OAuth**: añadir el scope
   `https://www.googleapis.com/auth/webmasters.readonly`. En modo *Testing*,
   añadir la cuenta que va a conectarse como usuario de prueba.
3. **Credenciales > Crear credenciales > ID de cliente de OAuth > Aplicación
   web**. En **URIs de redirección autorizados**, exactamente:

   ```
   http://localhost:4321/api/v1/integrations/google/callback
   ```

   Es el origen de la interfaz, no el de la API. El servidor de desarrollo hace
   proxy de `/api` hacia la API, de modo que el callback llega igual y, al
   terminar, el navegador vuelve a la interfaz. Apuntarlo al puerto 8000 haría
   aterrizar al usuario en el origen de la API, donde `/integrations` no existe.
   En producción, con API e interfaz en el mismo dominio, es
   `https://<dominio>/api/v1/integrations/google/callback`.

4. `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` y `GOOGLE_REDIRECT_URI` en `.env`.
   El valor de `GOOGLE_REDIRECT_URI` debe coincidir carácter por carácter con el
   registrado en Google.

Dos condiciones más para que devuelva datos: la propiedad debe estar verificada
en Search Console con esa misma cuenta, y en modo *Testing* el refresh token
caduca a los siete días.

Tras editar `.env`:

```bash
docker compose up -d api worker
```

El estado de las tres integraciones se comprueba en `/settings` de la interfaz.
