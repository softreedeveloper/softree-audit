# ADR-008 — Modelo de sesión y autenticación

Estado: Aceptado · Fecha: 2026-09-03

## Contexto

La aplicación es interna, sin registro público. Debe ser consumible por n8n
mediante REST y por un frontend en el navegador, con expiración, revocación,
límites de tasa y protección de contraseñas.

## Decisión

- Contraseñas con Argon2id (`t=3`, `m=64 MiB`, `p=4`).
- Access token JWT HS256 de 15 minutos, transportado en `Authorization: Bearer`.
- Refresh token JWT HS256 de 7 días con `jti` registrado en la tabla
  `refresh_tokens`, transportado en cookie `HttpOnly`, `SameSite=Strict`,
  `Path=/api/v1/auth`, `Secure` en producción.
- Rotación en cada refresh; el reuso de un token revocado invalida toda la cadena
  de la sesión.
- Frontend y API se sirven en el mismo origen (proxy en desarrollo, reverse proxy
  en producción).

## Alternativas

1. **Solo cookies de sesión.** Cómodo para el navegador, pero obliga a implementar
   CSRF y complica el consumo desde n8n.
2. **Solo tokens en `localStorage`.** Consumible por n8n, pero el refresh token
   queda expuesto a XSS.
3. **Sesiones opacas en Redis.** Revocación inmediata trivial, a cambio de una
   consulta a Redis por petición y de acoplar la autenticación a la
   disponibilidad de Redis.
4. **Proveedor externo de identidad.** Innecesario para un equipo interno pequeño
   y añade dependencia y costo.

## Consecuencias

- No se acepta autenticación por cookie en endpoints de escritura, por lo que no
  hay superficie CSRF en la API de negocio. El único endpoint que lee la cookie es
  `/auth/refresh`.
- La revocación del access token no es inmediata: su ventana máxima de validez es
  de 15 minutos. Se considera aceptable para una herramienta interna y queda
  documentado.
- Servir frontend y API en el mismo origen es un requisito de despliegue, no una
  preferencia. Está recogido en `docs/development/deployment.md`.
- Rotar `SECRET_KEY` invalida todas las sesiones, que es el comportamiento
  deseado ante un incidente.
