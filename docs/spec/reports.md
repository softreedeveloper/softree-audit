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
