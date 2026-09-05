# ADR-000 — Nombre del repositorio y del producto

Estado: Aceptado · Fecha: 2026-09-03 · Revisado: 2026-09-04

## Contexto

El proyecto se solicitó con el nombre `softree-seo`. La especificación de
producto define el nombre comercial «Softree Audit» y sugiere el directorio
`softree-audit/`. El alcance no es solo SEO: incluye seguridad, rendimiento,
accesibilidad y buenas prácticas.

Durante el desarrollo convivió en la misma máquina otro proyecto llamado
`softree-audit`, ya retirado. Mientras existió, ambos compartían nombre de
proyecto de Docker Compose y sus contenedores se sustituían entre sí.

## Decisión

El repositorio se llama `softree-audit`, igual que el producto, la marca, el
paquete Python (`softree_audit`) y el branding de los reportes.

La decisión inicial fue conservar `softree-seo` por ser el nombre pedido
explícitamente. Se revisó el 2026-09-04 a petición expresa: mantener dos
nombres para la misma cosa obligaba a explicar la diferencia en cada
documento, y el proyecto que ocupaba el nombre `softree-audit` ya no existe.

## Alternativas

1. Conservar `softree-seo`. Es el nombre con el que nació, pero describe mal el
   alcance y obliga a aclarar la diferencia con el producto una y otra vez.
2. Llamar al producto «Softree SEO». Describe mal el alcance y confundiría al
   cliente al recibir un reporte de seguridad.

## Consecuencias

- Repositorio, producto, paquete y marca comparten nombre. Desaparece la
  aclaración que antes hacía falta en la documentación.
- El cambio afecta al directorio y a las URLs de git. No afecta al código: el
  paquete Python ya se llamaba `softree_audit`, y el proyecto de Docker Compose
  ya se declaraba como `softree-audit`, de modo que los volúmenes con los datos
  locales se conservan.
