# ADR-002 — Base de datos y estrategia de identificadores

Estado: Aceptado · Fecha: 2026-09-03

## Contexto

Se necesita persistencia relacional para una jerarquía clara
(usuario → proyecto → sitio → scan → resultados), más almacenamiento de
respuestas originales de APIs externas para trazabilidad. Los identificadores no
deben exponer secuencias.

## Decisión

PostgreSQL 16 con SQLAlchemy asíncrono (asyncpg) y Alembic. Identificadores
UUID versión 7 generados en la aplicación. Enumerados como `VARCHAR` con
`CHECK`. Payloads originales en columnas `jsonb` no indexadas.

## Alternativas

1. **SQLite.** Suficiente en volumen inicial, pero sin tipos array ni `jsonb`
   comparables, y sin concurrencia real para worker y API simultáneos.
2. **MongoDB.** Los datos son fuertemente relacionales; perderíamos integridad
   referencial y las consultas de comparación entre scans se complicarían.
3. **UUID v4.** Igual de opaco, pero aleatorio: peor localidad en los índices
   B-tree con inserción masiva de páginas y findings.
4. **Enumerados nativos de PostgreSQL.** Más estrictos, pero añadir un valor
   exige `ALTER TYPE`, que no es reversible con facilidad en Alembic.

## Consecuencias

- Se puede ordenar por id como aproximación temporal, útil en paginación por
  cursor.
- Añadir un estado nuevo es una migración de `CHECK`, sencilla y reversible.
- Las columnas `jsonb` crecen; se documenta una política de retención de
  respuestas originales para versiones posteriores.
