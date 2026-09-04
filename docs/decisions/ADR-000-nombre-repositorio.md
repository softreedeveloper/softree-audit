# ADR-000 — Nombre del repositorio y del producto

Estado: Aceptado · Fecha: 2026-09-03

## Contexto

El proyecto se solicitó con el nombre `softree-seo`. La especificación de
producto define el nombre comercial «Softree Audit» y sugiere el directorio
`softree-audit/`. El alcance no es solo SEO: incluye seguridad, rendimiento,
accesibilidad y buenas prácticas.

## Decisión

El repositorio se llama `softree-seo`. El producto, la marca, el paquete Python
(`softree_audit`) y el branding de los reportes son `SOFTREE AUDIT`.

## Alternativas

1. Renombrar el repositorio a `softree-audit`. Coherente, pero contradice el
   nombre pedido.
2. Llamar al producto «Softree SEO». Describe mal el alcance y confundiría al
   cliente al recibir un reporte de seguridad.

## Consecuencias

- Hay una diferencia deliberada entre el nombre del repositorio y el del
  producto, documentada aquí y en `docs/spec/decisions.md` (D-001).
- Si más adelante se decide alinear los nombres, el cambio afecta únicamente al
  directorio y a las URLs de git, no al código.
