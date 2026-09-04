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
