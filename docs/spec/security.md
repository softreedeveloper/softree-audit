# Softree Audit — Security Specification

## Principio

La plataforma asume que **el target puede ser malicioso**. Que un usuario pueda
introducir una URL no significa que el servidor pueda conectarse a cualquier IP.

El scanner opera únicamente sobre el `authorized scope`.

## 1. Autorización de auditoría

Un `Site` solo es escaneable si tiene `authorized_by` y `authorization_date`.
La validación ocurre en el servidor al crear el scan; deshabilitar el botón en el
frontend es únicamente una cortesía de interfaz.

## 2. Protección contra SSRF

Toda petición saliente hacia un target pasa por un único punto:
`softree_audit/services/common/url_guard.py`. No existe otra ruta autorizada
para emitir tráfico hacia un host controlado por el usuario.

### Secuencia obligatoria

1. Parsear la URL. Rechazar si falla.
2. Aceptar solo esquemas `http` y `https`.
3. Rechazar credenciales embebidas (`user:pass@host`).
4. Rechazar puertos fuera de la lista permitida (80, 443 y los declarados en
   configuración).
5. Extraer el hostname; rechazar si está vacío o contiene caracteres inválidos.
6. Resolver DNS con `getaddrinfo` para IPv4 e IPv6.
7. Validar **todas** las direcciones resueltas. Una sola dirección bloqueada
   invalida el host completo.
8. Verificar el scope: dominio permitido, ruta permitida, ruta no excluida.
9. Emitir la petición con la IP validada fijada (`pin`), enviando la cabecera
   `Host` original, para evitar DNS rebinding entre la validación y la conexión.
10. No seguir redirects automáticamente. Ante un `3xx`, volver al paso 1 con la
    URL de destino.
11. Máximo 5 redirects.
12. Registrar cada rechazo con motivo.

### Rangos bloqueados

| Categoría | Rangos |
|-----------|--------|
| Loopback | `127.0.0.0/8`, `::1` |
| Privadas | `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `fc00::/7` |
| Link-local | `169.254.0.0/16`, `fe80::/10` |
| CGNAT | `100.64.0.0/10` |
| Reservadas y especiales | `0.0.0.0/8`, `192.0.0.0/24`, `192.0.2.0/24`, `198.18.0.0/15`, `198.51.100.0/24`, `203.0.113.0/24`, `240.0.0.0/4`, `255.255.255.255/32` |
| Multicast | `224.0.0.0/4`, `ff00::/8` |
| IPv4 mapeada en IPv6 | `::ffff:0:0/96` se desempaqueta y se valida como IPv4 |

### Endpoints de metadatos bloqueados por nombre e IP

`169.254.169.254`, `metadata.google.internal`, `metadata.goog`,
`instance-data`, `100.100.100.200`, `fd00:ec2::254`.

### Excepción controlada para desarrollo

`SSRF_ALLOW_PRIVATE_NETWORKS=true` permite auditar el `test-target` en la red
Docker. Solo debe activarse en desarrollo y pruebas. La API expone el valor
efectivo en `GET /api/v1/health` para que sea evidente si quedó activo.

## 3. Límites de las respuestas del target

| Límite | Valor por defecto |
|--------|-------------------|
| Tamaño máximo de respuesta | 5 MB, lectura en streaming con corte |
| Timeout de conexión y lectura | `scope.timeout_seconds` |
| Content types parseados | `text/html`, `application/xhtml+xml`, `text/xml`, `application/xml`, `text/plain` |
| Redirects | 5 |
| Descompresión | Se rechaza una ratio de descompresión superior a 100:1 |

El XML (`sitemap.xml`) se parsea con resolución de entidades externas y DTD
deshabilitadas para evitar XXE y billion laughs.

## 4. Autenticación

| Aspecto | Decisión |
|---------|----------|
| Hash de contraseña | Argon2id, `time_cost=3`, `memory_cost=65536` KiB, `parallelism=4` |
| Access token | JWT HS256, 15 minutos, claim `typ=access` |
| Refresh token | JWT HS256, 7 días, claim `typ=refresh` y `jti` registrado en base de datos |
| Transporte del access token | `Authorization: Bearer` |
| Transporte del refresh token | Cookie `HttpOnly`, `Secure` en producción, `SameSite=Strict`, `Path=/api/v1/auth` |
| Rotación | Cada refresh emite un token nuevo y marca el anterior como reemplazado |
| Reuso de refresh token revocado | Fuera de una ventana de gracia de 15 segundos, se revoca toda la cadena de sesión del usuario, se confirma en base de datos aunque la petición termine en 401, y se registra el evento |
| Repetición dentro de la ventana de gracia | Se considera una carrera benigna (dos pestañas, una recarga) y se emite un par nuevo. Un robo real se produce mucho después de la rotación |
| Logout | Revoca el `jti` actual y borra la cookie |

No se acepta autenticación por cookie para operaciones de escritura, por lo que
no hay superficie CSRF en los endpoints de negocio. El único endpoint que lee la
cookie es `POST /auth/refresh`, cuya respuesta no es legible por un origen
externo.

### Validación del email en el login

El login valida la forma del email, no su entregabilidad. La validación estricta
rechaza dominios de uso reservado (`.test`, `.local`, `.internal`), legítimos en
una herramienta interna, y rechazar un intento por el formato no aporta
protección: la comprobación real es la búsqueda del usuario. La validación
estricta sí se aplica al crear la cuenta.

### Enumeración de usuarios

El login devuelve el mismo error y un tiempo de respuesta equivalente tanto si el
email no existe como si la contraseña es incorrecta. Cuando el usuario no existe
se ejecuta una verificación contra un hash señuelo.

## 5. Rate limiting

Implementado en Redis con ventana deslizante, por IP y ruta.

| Ruta | Límite |
|------|--------|
| `POST /auth/login` | 5 por 15 minutos |
| `POST /auth/refresh` | 30 por hora |
| `POST /scans` | 10 por hora |
| `POST /reports/{id}/generate` | 20 por hora |
| Resto de la API | 300 por minuto |

Si Redis no está disponible, la política es **fail closed** en autenticación y
**fail open** en el resto, registrando el incidente.

## 6. Autorización de recursos

Toda consulta incluye la pertenencia en la cláusula `WHERE`. Un identificador
válido de otro usuario devuelve `404`, no `403`, para no confirmar existencia.

## 7. Cifrado en reposo

Los refresh tokens de Google se cifran con Fernet. La clave se deriva de
`SECRET_KEY` con HKDF-SHA256 e info `softree-audit/oauth/v1`.

- El access token de Google nunca se persiste.
- Rotación de clave: se añade `SECRET_KEY_PREVIOUS`, se descifra con la anterior
  y se recifra con la nueva mediante `softree-audit rotate-secrets`.
- Si el descifrado falla, la conexión se marca `error` y se pide reconectar. No
  se registra el contenido del token en ningún log.

## 8. Aislamiento de datos de Search Console

Los datos pertenecen a la propiedad autorizada. Una conexión está ligada a un
único `project_id` y toda consulta de métricas filtra por el scan, que a su vez
pertenece a un sitio de ese proyecto. No existe endpoint que devuelva métricas
sin acotar por proyecto.

## 9. OWASP ZAP

- El contenedor de ZAP no publica puertos al host; solo es alcanzable en la red
  interna de Docker.
- La API de ZAP se protege con `ZAP_API_KEY`.
- Solo passive scan. El active scan no está implementado y su activación futura
  requerirá un consentimiento explícito por sitio.
- El scope se inyecta en ZAP como contexto con expresiones include y exclude, de
  modo que ZAP tampoco pueda salir del alcance autorizado. Además, solo se le
  entregan las URL que el crawler ya rastreó y que el guard ya validó.
- El contexto se retira al terminar, incluso si el scan falla.
- Las alertas que el propio ZAP marca como falso positivo se descartan.

## 10. Manejo de secretos

- `.env` está en `.gitignore`. `.env.example` no contiene valores reales.
- El arranque falla si `SECRET_KEY` tiene menos de 32 caracteres o es el valor de
  ejemplo, salvo en `APP_ENV=development`.
- Los logs filtran las claves `password`, `token`, `secret`, `authorization`,
  `cookie`, `api_key` y `refresh_token`.
- El frontend nunca recibe secretos. Las llamadas a APIs de Google salen siempre
  del backend.

## 11. Cabeceras de la propia aplicación

`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: no-referrer`, `Content-Security-Policy` restrictiva,
`Strict-Transport-Security` cuando `APP_ENV=production`.

## 12. Validación de entrada

Toda entrada se valida con Pydantic. Longitudes máximas explícitas en todo campo
de texto. Las listas de dominios y rutas del scope se normalizan y validan
carácter por carácter; no se aceptan comodines arbitrarios.

## 13. Registro de auditoría

Se registran en log estructurado: login exitoso y fallido, logout, creación y
borrado de proyectos y sitios, creación y cancelación de scans, conexión y
desconexión de Google, cambios de estado de findings y rechazos del guard de URL.

## 14. Modelo de amenazas resumido

| Amenaza | Vector | Mitigación |
|---------|--------|-----------|
| SSRF a red interna | URL de sitio maliciosa | §2 |
| DNS rebinding | TTL corto entre validación y conexión | Fijado de IP validada |
| Redirect a IP privada | `3xx` desde el target | Re-validación por salto |
| Agotamiento de memoria | Respuesta enorme o bomba de compresión | §3 |
| XXE en sitemap | XML con entidades externas | Parser sin DTD |
| IDOR | Id de otro usuario | §6 |
| Robo de sesión | XSS o token filtrado | Access token de 15 min, refresh en cookie `HttpOnly`, CSP |
| Fuerza bruta de contraseñas | Login repetido | §5 y Argon2id |
| Exfiltración de tokens de Google | Acceso a base de datos | §7 |
| Abuso de la plataforma como escáner | Sitio no autorizado | §1 |
