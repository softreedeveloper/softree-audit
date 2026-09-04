# ADR-005 — Integración con Search Console

Estado: Aceptado · Fecha: 2026-09-03

## Contexto

Se requieren datos reales de Google Search Console (clicks, impresiones, CTR y
posición). Los datos pertenecen a la propiedad autorizada y no deben mezclarse
entre proyectos. La conexión puede no existir, y eso no debe considerarse un
error del scan.

## Decisión

OAuth 2.0 Authorization Code con el scope
`https://www.googleapis.com/auth/webmasters.readonly`. La conexión se asocia a un
único `project_id`. Solo se persiste el refresh token, cifrado con Fernet y clave
derivada de `SECRET_KEY`. El access token se obtiene en memoria en cada uso.

Si no hay conexión, el módulo queda `skipped` y el scan continúa. Si el refresh
token fue revocado (`invalid_grant`), la conexión pasa a `revoked` y se solicita
reconectar.

## Alternativas

1. **Cuenta de servicio.** No requiere consentimiento interactivo, pero exige que
   el cliente añada la cuenta como usuario de su propiedad en Search Console, un
   paso operativo frágil en cada proyecto.
2. **Carga manual de CSV exportado.** Sin dependencias de OAuth, pero rompe el
   requisito de datos reales automatizados y no es reproducible.
3. **Guardar también el access token.** Ahorra un intercambio por sesión a cambio
   de ampliar la superficie de datos sensibles en reposo.

## Consecuencias

- Se necesita registrar una aplicación OAuth en Google Cloud y mantener la
  pantalla de consentimiento.
- El aislamiento por proyecto es una invariante verificada en pruebas: no existe
  endpoint que devuelva métricas sin acotar por proyecto.
- Rotar `SECRET_KEY` requiere recifrar los tokens; el procedimiento está en
  `docs/development/deployment.md`.
