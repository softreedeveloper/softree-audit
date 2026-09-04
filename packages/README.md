# packages/

Este directorio existe para mantener la correspondencia con la estructura
propuesta en la especificación, pero no contiene código.

| Paquete propuesto | Ubicación real |
|-------------------|----------------|
| `packages/scoring` | `apps/api/softree_audit/scoring/` — función pura, sin IO |
| `packages/shared-types` | `apps/web/src/lib/api-types.ts`, generado desde `docs/api/openapi.json` con `make openapi` |

El motor de scoring no importa nada de `services/` ni de la capa de
persistencia: recibe sus entradas ya construidas (`scans/scoring_inputs.py`) y
devuelve el desglose. Esa separación es la que exige la especificación, y se
verifica en `tests/unit/test_scoring_engine.py`.

Ver ADR-001, ADR-006 y la decisión D-009.
