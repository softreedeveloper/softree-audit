# Despliegue

## Modelo

Docker Compose sobre un único host. Sin Kubernetes en el MVP.

```
Internet → TLS (Traefik, Caddy o nginx) → web:80
                                            ├── /        sitio estático
                                            └── /api/    proxy hacia api:8000
                                                          api    → postgres, redis
                                                          worker → postgres, redis, zap
```

El contenedor `web` sirve el frontend compilado **y** hace de proxy de `/api`,
de modo que el navegador ve un solo origen. Es un requisito del modelo de
sesión (D-005, ADR-008): el refresh token viaja en una cookie `SameSite=Strict`
limitada a `/api/v1/auth`, que un origen distinto no enviaría.

Por eso el proxy de TLS que haya delante solo necesita enrutar un servicio,
`web`, y no repartir rutas entre dos.

## Archivos

| Archivo | Uso |
|---------|-----|
| `docker-compose.yml` | Desarrollo. Monta el código, publica puertos en localhost y arranca Astro en modo desarrollo |
| `docker-compose.prod.yml` | Producción. Imágenes inmutables, un solo puerto publicado, ZAP incluido sin perfil |
| `docker/web.prod.Dockerfile` | Compila el sitio y lo sirve con nginx |
| `docker/web-nginx.conf` | Rutas estáticas, proxy de `/api` y cabeceras de seguridad |

## Preparación

1. Crear `.env` a partir de `.env.example` con valores reales.
2. `SECRET_KEY` único por entorno, generado con un CSPRNG.
3. `APP_ENV=production` activa cookies `Secure` y HSTS.
4. `SSRF_ALLOW_PRIVATE_NETWORKS` debe estar ausente o en `false`.
5. ZAP no publica puertos al host.

## Pasos con Docker Compose

```bash
# 1. Configuración
cp .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # SECRET_KEY
$EDITOR .env

# 2. Construir y levantar
docker compose -f docker-compose.prod.yml up -d --build

# 3. Esquema de base de datos
docker compose -f docker-compose.prod.yml exec api alembic upgrade head

# 4. Primer usuario (no hay registro público)
docker compose -f docker-compose.prod.yml exec api softree-audit create-user
```

La aplicación queda en `http://<host>:8080`, o en el puerto que indique
`WEB_PORT`. Delante debe ir el proxy con TLS.

### Variables obligatorias

| Variable | Nota |
|----------|------|
| `SECRET_KEY` | Mínimo 32 caracteres, único por entorno. Cifra los tokens de Google |
| `POSTGRES_USER`, `POSTGRES_PASSWORD` | Sin valor por defecto en producción |
| `DATABASE_URL` | `postgresql+asyncpg://usuario:clave@postgres:5432/softree_audit` |
| `ZAP_API_KEY` | Cadena aleatoria. Sin ella el compose de producción no arranca |
| `APP_ENV=production` | Activa cookies `Secure` y HSTS |
| `SSRF_ALLOW_PRIVATE_NETWORKS` | Ausente o `false`. En `true` la plataforma podría escanear la red interna del servidor |

Opcionales: `PAGESPEED_API_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
`GOOGLE_REDIRECT_URI`, `AI_API_URL`, `AI_API_KEY`. Sin ellas los módulos
correspondientes quedan `failed` o `skipped` y el resto de la auditoría
continúa.

## Despliegue en Dokploy

Dokploy pone Traefik y los certificados; el resto es el mismo compose.

### 1. Crear el proyecto

En el panel, **Projects → Create Project**, nombre `softree-audit`.

### 2. Añadir un servicio de tipo Compose

**Create Service → Compose**. Origen del código:

- **Provider**: el repositorio de git donde esté publicado este proyecto.
- **Branch**: `main`.
- **Compose Path**: `docker-compose.prod.yml`.

Si el repositorio es privado, conectar antes el proveedor en
**Settings → Git Providers**.

### 3. Variables de entorno

En la pestaña **Environment**, pegar las variables de la tabla anterior.
Dokploy las inyecta como `.env` del compose. No subir ese archivo al
repositorio: `.gitignore` ya lo excluye.

`GOOGLE_REDIRECT_URI` debe apuntar al dominio público:

```
https://<dominio>/api/v1/integrations/google/callback
```

y registrarse igual en Google Cloud Console, o la conexión con Search Console
fallará con `redirect_uri_mismatch`.

### 4. Dominio

En **Domains → Add Domain**:

- **Host**: el dominio público.
- **Service Name**: `web`.
- **Container Port**: `80`.
- **HTTPS**: activado, con Let's Encrypt.

Un solo dominio y un solo servicio: `web` ya reparte entre el sitio estático y
`/api`. No hay que crear una entrada aparte para la API, y no conviene
exponerla por su cuenta.

### 5. Desplegar

**Deploy**. La primera construcción tarda: la imagen de la API instala
WeasyPrint y sus dependencias de sistema.

Al terminar, en **Terminal** o por SSH:

```bash
docker compose -p softree-audit exec api alembic upgrade head
docker compose -p softree-audit exec api softree-audit create-user
```

### 6. Comprobar

```bash
curl -s https://<dominio>/api/v1/health | jq
```

### Notas de operación

- **Recursos**: la API y el worker rondan 1,5 GB de imagen cada uno, y ZAP
  3,6 GB. Con PostgreSQL, Redis y el frontend, contar con 8 GB de RAM y 20 GB
  de disco libres.
- **Puertos**: solo `web` publica puerto. PostgreSQL, Redis, la API, el worker
  y ZAP quedan en la red interna. No añadir dominios para ellos.
- **Volúmenes**: `postgres_data` y `reports_data` deben persistir entre
  despliegues. Dokploy los conserva mientras no se borre el servicio.
- **Actualizar**: `git push` y **Redeploy**. Después, `alembic upgrade head`.
- **Auto Deploy**: si se activa el webhook, cada push a `main` despliega. Con
  las migraciones sin automatizar, conviene dejarlo desactivado y desplegar a
  mano.

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
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec api alembic upgrade head
```

Las migraciones son compatibles hacia atrás dentro de una versión menor, por lo
que el orden build, up, migrate no deja la aplicación inconsistente.
