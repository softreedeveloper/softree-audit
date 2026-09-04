# Despliegue

## Modelo

Docker Compose sobre un único host. Sin Kubernetes en el MVP.

```
Internet → Reverse proxy (TLS) → web (estático) y /api → api
                                            api → postgres, redis
                                            worker → postgres, redis, zap
```

El reverse proxy sirve el frontend y la API bajo el **mismo origen**, requisito
del modelo de sesión (D-005).

## Preparación

1. Crear `.env` a partir de `.env.example` con valores reales.
2. `SECRET_KEY` único por entorno, generado con un CSPRNG.
3. `APP_ENV=production` activa cookies `Secure` y HSTS.
4. `SSRF_ALLOW_PRIVATE_NETWORKS` debe estar ausente o en `false`.
5. ZAP no publica puertos al host.

## Pasos

```bash
docker compose --profile scanner build
docker compose --profile scanner up -d
docker compose exec api alembic upgrade head
docker compose exec api softree-audit create-user
```

## Verificación posterior al despliegue

```bash
curl -s https://<host>/api/v1/health | jq
```

Debe devolver `status: ok`, las tres versiones y
`ssrf_allow_private_networks: false`.

## Respaldos

- `pg_dump` diario, retención de 30 días.
- Los reportes generados viven en el volumen `reports_data`; se respaldan junto
  con la base de datos.
- Redis no requiere respaldo: solo contiene cola y límites de tasa.

## Rotación de secretos

```bash
# Añadir SECRET_KEY_PREVIOUS con el valor anterior y SECRET_KEY con el nuevo
docker compose exec api softree-audit rotate-secrets
# Retirar SECRET_KEY_PREVIOUS al terminar
```

Rotar `SECRET_KEY` invalida todas las sesiones activas, lo cual es el
comportamiento deseado.

## Actualización

```bash
git pull
docker compose build
docker compose up -d
docker compose exec api alembic upgrade head
```

Las migraciones son compatibles hacia atrás dentro de una versión menor, por lo
que el orden build, up, migrate no deja la aplicación inconsistente.
