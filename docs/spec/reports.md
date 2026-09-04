# Softree Audit — Reports Specification

## 1. Formatos

| Formato | Uso | Motor |
|---------|-----|-------|
| PDF | Entregable a cliente | Jinja2 + WeasyPrint |
| HTML | Vista previa en navegador y base del PDF | Jinja2 |
| JSON | Consumo por API, n8n y archivo | Serializador propio |

Los tres formatos se generan del mismo modelo de datos, de modo que no puedan
divergir.

## 2. Estructura del PDF

```
Cover
Executive Summary
Overall Score
Security
SEO
Performance
Search Console
Accessibility
Best Practices
Findings
Recommendations
Historical comparison
Conclusion
```

## 3. Doble nivel de lectura

Cada sección tiene dos bloques:

- **Explicación ejecutiva.** Lenguaje llano, sin jerga, orientada a impacto de
  negocio.
- **Detalle técnico.** Evidencia, URL, parámetro, CWE, OWASP y remediación.

Ejemplo:

| Nivel | Texto |
|-------|-------|
| Técnico | `Missing Content-Security-Policy` |
| Cliente | El sitio no tiene configurada una política CSP que ayude a reducir determinados riesgos relacionados con contenido ejecutado en el navegador. |

El campo `findings.client_explanation` almacena la redacción no técnica. Cuando
una fuente no la provee, el catálogo de reglas aporta el texto; si tampoco
existe, el reporte ejecutivo agrupa el hallazgo por categoría sin inventar
explicación.

### Audiencias

El mismo modelo de datos se compone en tres documentos distintos. La audiencia
decide qué se muestra, nunca qué se midió: los tres declaran las mismas
puntuaciones, la misma auditoría y los mismos avisos de alcance.

| Audiencia | Contiene | Omite |
|-----------|----------|-------|
| `executive` | Portada, puntuaciones, hallazgos críticos y altos en lenguaje de cliente, recomendaciones, comparación y conclusión | Evidencia, CWE, OWASP, resúmenes técnicos por módulo y hallazgos de gravedad baja |
| `technical` | Todo el detalle por módulo, con evidencia, CWE, OWASP y estado de cada módulo | Las paráfrasis dirigidas al cliente |
| `combined` | Ambos niveles. Es el valor por defecto | — |

Si una auditoría no tiene hallazgos críticos ni altos, el documento ejecutivo
enumera las recomendaciones ya priorizadas, para no entregar un documento sin
contenido accionable.

El JSON no se recorta por audiencia: es el formato de integración y quitarle
datos rompería a quien lo consume. Lleva el campo `audience` para saber con qué
intención se generó.

Cada combinación de formato y audiencia es un archivo propio
(`softree-audit-<scan>-<audiencia>.<extensión>`) y un registro propio. Se
descarga con `GET /api/v1/reports/{scan_id}/download?format=pdf&audience=executive`;
sin `audience` se devuelve el más reciente de ese formato.

## 4. Branding

- Marca: `SOFTREE` y `SOFTREE AUDIT`.
- Logo desde `apps/api/softree_audit/services/reports/assets/`.
- Portada con: logo, título, cliente, dominio auditado, periodo analizado,
  fecha de emisión, versión de auditoría (`app`, `scan_engine`, `report`).
- Pie de página con número de página y aviso de confidencialidad.

## 5. Aviso obligatorio

El reporte incluye, en la sección de metodología:

> Los indicadores identificados como «Google Lighthouse» provienen de la API
> pública de Google PageSpeed Insights. El «Softree Score» es un indicador
> propio de Softree y no constituye una calificación oficial de Google.

## 6. Comparación histórica

Si existe un scan previo del mismo sitio, la sección incluye la clasificación
`NEW`, `FIXED`, `UNCHANGED` y `REGRESSED` por finding y los deltas de métricas.

```
Broken links      12 → 3
Missing titles     7 → 2
High findings      4 → 2
LCP              3.1s → 2.2s
```

## 7. Trazabilidad

Cada reporte persiste `report_version`, `engine_version`, `app_version`,
`generated_at` y `checksum_sha256`. Un PDF entregado se puede reasociar a los
datos exactos que lo originaron.

## 8. Módulo futuro de IA

No se implementa en el MVP. Interfaz conceptual prevista:

```
Finding
 ↓
AI Analyzer
 ↓
Explanation
 ↓
Risk prioritization
 ↓
Recommendation
 ↓
Executive summary
```

Restricciones de diseño ya asumidas:

1. El analizador recibe findings ya normalizados y no emite tráfico hacia el
   target.
2. No puede ejecutar acciones ofensivas ni modificar el estado de findings.
3. Su salida se marca como generada automáticamente y es revisable antes de
   incorporarse a un reporte entregable.
