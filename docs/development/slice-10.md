# Slice 10 — Reportes PDF, HTML y JSON

Estado: **completado**.

## Alcance entregado

| Área | Contenido |
|------|-----------|
| Modelo | `ReportModel`, única fuente de la que salen los tres formatos |
| Plantilla | Jinja2 con la estructura completa de `docs/spec/reports.md` §2 |
| PDF | WeasyPrint, con branding Softree, portada, numeración y aviso de confidencialidad |
| Almacenamiento | Archivos en volumen, con tamaño y suma de verificación en base de datos |
| API | `POST /reports/{scan_id}/generate`, `GET /reports/{scan_id}`, `GET /reports/{scan_id}/download` |
| Frontend | Pestaña de reporte en la auditoría y página de reportes |
| Pruebas | 712 en total (685 previas más 27 nuevas) |

## Un solo modelo, tres formatos

PDF, HTML y JSON se generan del mismo `ReportModel`. El PDF es el HTML pasado por
WeasyPrint, así que no pueden divergir en contenido, y hay una prueba que compara
un dato concreto en los dos formatos.

WeasyPrint no ejecuta JavaScript: toda la composición es HTML y CSS con
`@page`, incluidos la numeración y el pie de confidencialidad.

## Doble nivel de lectura

Cada hallazgo del reporte incluye el detalle técnico y, destacada en un bloque
aparte, la explicación para el cliente:

> **En términos claros:** Esta página no tiene título. Es el texto que aparece
> como titular cuando alguien la encuentra en Google.

Es el requisito §34, y viene de `findings.client_explanation`, que los catálogos
SEO y PageSpeed rellenan desde el Slice 4.

## Lo que no se midió se dice

Una sección cuyo módulo no se ejecutó no aparece vacía: lleva una nota con el
motivo y la advertencia de que la ausencia de hallazgos no significa que no
existan problemas. En la auditoría de ejemplo, la sección de rendimiento declara
`quota_exceeded`.

El reporte incluye además los dos avisos obligatorios: el de metodología (§5),
que separa el Google Score del Softree Score, y el de alcance del análisis
pasivo.

## Trazabilidad

Cada reporte guarda `report_version`, tamaño y `sha256`, y el PDF lleva en su
última página el identificador de la auditoría y las tres versiones. Un PDF
entregado se puede reasociar a los datos exactos que lo originaron.

## Criterios de aceptación

| Criterio | Resultado |
|----------|-----------|
| Se generan PDF, HTML y JSON | Cumplido |
| Los tres salen del mismo modelo de datos | Cumplido |
| El PDF lleva branding, portada, numeración y confidencialidad | Cumplido |
| Estructura completa de `reports.md` §2 | Cumplido |
| Doble nivel de lectura en cada hallazgo | Cumplido |
| Aviso de metodología presente | Cumplido |
| Los módulos no ejecutados se declaran | Cumplido |
| Se incluye la comparación cuando hay auditoría anterior | Cumplido |
| Se guarda versión, tamaño y suma de verificación | Cumplido |
| El contenido del sitio auditado se escapa en el HTML | Cumplido |
| Una auditoría en curso no puede reportarse | Cumplido |
| Regenerar sustituye, no acumula | Cumplido |
| Los reportes de otro usuario no son accesibles | Cumplido |
| `ruff`, `ruff format`, `mypy --strict` sin hallazgos | Cumplido |
| `astro check`, `tsc --noEmit` sin errores | Cumplido |

## Verificación de extremo a extremo

Reporte generado de una auditoría real del `test-target`:

```
pdf     92 446 bytes   22 páginas A4
html    88 067 bytes
json    45 469 bytes
```

Contenido comprobado en el navegador: portada con marca y datos del cliente,
resumen ejecutivo con Softree Score 87,1 «Bueno» y sus pesos aplicados
(seguridad 55 %, SEO 45 %), tabla de severidades, secciones por módulo con los
hallazgos y sus dos niveles de lectura, recomendaciones priorizadas,
comparación con la auditoría anterior y conclusión con el alcance declarado.

## Hallazgos corregidos durante el slice

| Hallazgo | Corrección |
|----------|-----------|
| El logo de la identidad corporativa es de 6250 × 6250 px: embebido como data URI dejaba el PDF en 1,1 MB y el HTML en 1,9 MB | Activos redimensionados; el PDF baja a 92 KB y el HTML a 88 KB |
| Las etiquetas del resumen de cada sección salían en inglés (`Pages crawled`) | Mapa de etiquetas en español |
| Una coma suelta en el resumen ejecutivo por el control de espacios de Jinja | Control explícito de espacios en la plantilla |

## Deuda declarada

- Los gráficos del reporte serían SVG generados en el servidor; por ahora los
  datos se presentan en tablas, que son legibles y no añaden dependencias.
- El público del reporte (`technical`, `executive`, `combined`) se persiste pero
  todavía no cambia el contenido: el reporte combinado incluye ambos niveles.

## Siguiente

Slice 11: pruebas end to end y validación de seguridad.
