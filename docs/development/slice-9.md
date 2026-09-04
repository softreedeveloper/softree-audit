# Slice 9 — Dashboard, histórico y comparación

Estado: **completado**.

## Alcance entregado

| Área | Contenido |
|------|-----------|
| Dashboard | Score medio, conteos, hallazgos abiertos por severidad y últimas auditorías |
| Histórico | Listado de auditorías del sitio con score, hallazgos y duración |
| Comparación | Clasificación `NEW`, `FIXED`, `UNCHANGED`, `REGRESSED` y deltas de métricas |
| API | `GET /dashboard`, `GET /sites/{id}/history`, `GET /scans/{id}/comparison` |
| Frontend | Dashboard reescrito, histórico en el sitio y pestaña de comparación |
| Pruebas | 685 en total (645 previas más 40 nuevas) |

## El dashboard suma el estado actual, no el histórico

Cada sitio aporta su **última auditoría terminada**. Sumar todos los scans
multiplicaría los hallazgos por el número de auditorías realizadas y daría una
cifra sin significado. Se resuelve con `DISTINCT ON (site_id)` ordenado por
identificador descendente, aprovechando que los UUID v7 son ordenables por
tiempo.

## Qué cuenta como regresión

Un hallazgo empeora si sube de severidad **o** si aparece en más páginas que
antes. Bajar de severidad o afectar a menos páginas no se marca como regresión,
pero tampoco como corregido: sigue ahí.

Los hallazgos resueltos se excluyen de los dos lados de la comparación, así que
aceptar uno lo saca de la lista de pendientes sin fabricar un «nuevo» ni un
«corregido» falso.

## Solo se compara lo que ambas auditorías midieron

Es el hallazgo más importante del slice. Comparar una auditoría SEO con una
completa reportaba los seis hallazgos de seguridad como **corregidos**, cuando
lo único que había pasado es que ese módulo no se ejecutó. Un reporte así le
diría al cliente que corrigió problemas que siguen ahí.

La comparación toma ahora las fuentes cuyo módulo se completó en cada scan, se
limita a la intersección y declara en la respuesta qué quedó fuera:

```json
{
  "compared_sources": ["crawler", "seo"],
  "sources_only_in_previous": ["zap"]
}
```

La interfaz lo explica en texto, y hay pruebas unitarias y de integración del
caso.

## Verificación de extremo a extremo

Se modificó el `test-target` de forma controlada: se añadió un H1 a
`/sin-h1.html` y se puso un canonical de otro dominio en `/formulario.html`. La
comparación entre las dos auditorías completas detectó exactamente esos dos
cambios y nada más:

```
conteos: {'new': 1, 'fixed': 1, 'unchanged': 17, 'regressed': 0}
fuentes comparadas: ['crawler', 'seo', 'zap']

   [new    ] SEO-011  Enlace canonical inválido      /formulario.html
   [fixed  ] SEO-005  Página sin encabezado H1       /sin-h1.html

   Softree Score      86.7 -> 87.1   (mejora)
   Score SEO          90.8 -> 91.7   (mejora)
   Páginas sin H1     1.0 -> 0.0     (mejora)
```

Antes de la corrección, la misma comparación entre tipos distintos reportaba
seis «corregidos» inexistentes.

## Criterios de aceptación

| Criterio | Resultado |
|----------|-----------|
| Dashboard con score, conteos y hallazgos por severidad | Cumplido |
| El dashboard solo suma la última auditoría de cada sitio | Cumplido |
| Los hallazgos resueltos no cuentan | Cumplido |
| Histórico por sitio con score y hallazgos | Cumplido |
| Comparación con `NEW`, `FIXED`, `UNCHANGED`, `REGRESSED` | Cumplido |
| Deltas de métricas con su sentido de mejora | Cumplido |
| No se comparan módulos que no se ejecutaron en ambas | Cumplido |
| No se comparan auditorías de sitios distintos | Cumplido |
| Los datos de otro usuario no son accesibles | Cumplido |
| `ruff`, `ruff format`, `mypy --strict` sin hallazgos | Cumplido |
| `astro check`, `tsc --noEmit` sin errores | Cumplido |

## Hallazgos corregidos durante el slice

| Hallazgo | Corrección |
|----------|-----------|
| Comparar auditorías de distinto tipo reportaba hallazgos como corregidos cuando su módulo no se había ejecutado | La comparación se limita a las fuentes medidas por ambas y declara las excluidas |
| `max(uuid)` no existe en PostgreSQL: el dashboard fallaba al buscar el último scan de cada sitio | `DISTINCT ON (site_id)` con orden descendente |

## Siguiente

Slice 10: generación de reportes en PDF, HTML y JSON.
