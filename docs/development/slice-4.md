# Slice 4 — Motor SEO

Estado: **completado**.

## Alcance entregado

| Área | Contenido |
|------|-----------|
| Reglas | SEO-001 a SEO-016, con catálogo separado de la lógica |
| Findings | Modelo normalizado, huella de deduplicación y agregación por huella |
| Agregados | `seo_results` completo, incluido el resumen de datos estructurados |
| Enlaces externos | Comprobación opcional por sitio, acotada y a través del guard |
| API | `GET /findings`, `PATCH /findings/{id}`, `GET /scans/{id}/findings`, `GET /scans/{id}/severity-counts`, `GET /sites/{id}/seo` |
| Frontend | Vista de hallazgos con filtros y cambio de estado, pestañas SEO y hallazgos en el detalle de la auditoría |
| Pruebas | 423 en total (347 previas más 76 nuevas) |

## Criterios de aceptación

| Criterio | Resultado |
|----------|-----------|
| Las 16 reglas de la especificación existen y se ejecutan | Cumplido |
| Cada regla produce un finding normalizado | Cumplido |
| Cada regla aporta detalle técnico y explicación para el cliente | Cumplido |
| Los findings equivalentes se deduplican | Cumplido |
| La huella es estable entre variantes de la misma URL | Cumplido |
| Una regla que falla no invalida el análisis | Cumplido |
| Los agregados SEO se persisten y se consultan | Cumplido |
| Un hallazgo puede marcarse corregido, aceptado o falso positivo | Cumplido |
| Un hallazgo resuelto deja de contar en las severidades | Cumplido |
| Los hallazgos de otro usuario no son visibles ni modificables | Cumplido |
| `ruff`, `ruff format`, `mypy --strict`, `alembic check` sin hallazgos | Cumplido |
| `astro check`, `tsc --noEmit` sin errores | Cumplido |

## Verificación de extremo a extremo

Auditoría real del `test-target` con el motor SEO:

```
discovery  completed
crawler    completed   18 páginas
seo        completed   16/16 reglas, 0 fallidas, 15 hallazgos
```

Severidades: 2 altas, 4 medias, 6 bajas.

| Regla | Se dispara | Comprobación |
|-------|-----------|--------------|
| SEO-001 | sí | `/sin-title.html` |
| SEO-002 | sí, 2 grupos | `duplicado-a/b` y `copia-a/b` |
| SEO-003 | sí | `/sin-description.html` |
| SEO-004 | sí, 2 grupos | mismas páginas |
| SEO-005 | sí | `/sin-h1.html` |
| SEO-006 | sí | `/multi-h1.html`, 3 encabezados |
| SEO-007 | sí | `/sin-alt.html`, 2 imágenes, categoría accesibilidad |
| SEO-008 | sí | `/no-existe`, con la página que la enlaza |
| SEO-009 | no | el enlace externo no resuelve: se registra como error de red, no como roto |
| SEO-010 | sí | `/sin-canonical.html` |
| SEO-011 | sí | canonical a `example.com` |
| SEO-012 | sí | `/noindex.html` |
| SEO-013 | no | el sitio sí publica sitemap |
| SEO-014 | no | el sitio sí publica robots.txt |
| SEO-015 | sí | `/redirect-1 → /redirect-2 → /final.html` |
| SEO-016 | sí | `copia-a/b`, con title, description y H1 idénticos |

Las cuatro reglas que no se disparan lo hacen por el motivo correcto, y así lo
verifica el fixture: es tan importante que una regla calle cuando debe como que
avise cuando toca.

Cambio de estado comprobado en la interfaz: marcar `SEO-012` como aceptado lo
retira del recuento de severidades sin borrarlo, y sigue consultable con el
filtro de estado.

## Ampliación del sitio de pruebas

Se añadieron al `test-target` los casos que faltaban: `/copia-a.html` y
`/copia-b.html` con title, description y H1 idénticos (SEO-016), y un enlace a
un dominio externo inexistente (camino de error de SEO-009).

## Deuda declarada

- El **scoring** a partir de estos hallazgos llega en el Slice 8, junto con el
  arrastre de los estados `accepted` y `false_positive` entre scans del mismo
  sitio. La huella ya es estable entre scans, que es lo que ese arrastre
  necesita.
- La validación profunda de datos estructurados sigue fuera del MVP (§20): se
  registra presencia, tipos y bloques JSON-LD inválidos.

## Siguiente

Slice 5: integración con OWASP ZAP, con passive scan y normalización de alertas.
