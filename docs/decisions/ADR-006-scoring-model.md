# ADR-006 — Modelo de scoring

Estado: Aceptado · Fecha: 2026-09-03

## Contexto

Se requiere un indicador agregado propio con pesos configurables, y a la vez
mostrar los scores de Google. Presentar un cálculo propio como si fuera oficial
de Google sería incorrecto frente al cliente.

Además, Accessibility y Best Practices provienen de Lighthouse y también forman
parte de los pesos del score propio, lo que podría confundir ambos sistemas (R3).

## Decisión

Dos sistemas persistidos por separado en la tabla `scores`, discriminados por la
columna `system`:

- `google`: valores de Lighthouse sin transformación.
- `softree`: agregado ponderado propio, con los pesos usados guardados junto a
  cada valor y con `engine_version`.

Los pesos se leen de configuración. Las categorías sin datos no cuentan como
cero: su peso se redistribuye proporcionalmente entre las disponibles.

`packages/scoring` es una función pura sin IO.

## Alternativas

1. **Un solo score.** Más simple de comunicar, pero o se pierde la referencia de
   Google o se presenta un cálculo propio bajo su nombre.
2. **Pesos fijos en código.** Prohibido por la especificación y poco útil, porque
   la prioridad relativa cambia según el tipo de sitio.
3. **Categoría ausente como cero.** Penalizaría al sitio por una falla de una API
   externa, lo que haría el score no reproducible.

## Consecuencias

- La UI y el PDF deben etiquetar siempre el origen del score, con aviso de
  metodología.
- Un cambio de pesos no altera scans históricos, porque el peso aplicado queda
  persistido.
- Comparar scans entre versiones distintas del motor requiere leer
  `engine_version`; la UI lo advierte cuando difiere.
