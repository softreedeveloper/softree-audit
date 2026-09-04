# Slice 5 — OWASP ZAP

Estado: **completado**.

## Alcance entregado

| Área | Contenido |
|------|-----------|
| Cliente ZAP | API HTTP con `apikey`, timeouts, reintentos acotados y paginación de alertas |
| Contexto | El scope se inyecta en ZAP como expresiones de inclusión y exclusión (doble barrera) |
| Flujo | Sesión limpia, envío de las URL ya rastreadas, spider opcional, espera del passive scan, recogida de alertas y limpieza del contexto |
| Normalizador | Alerta de ZAP a finding unificado, con severidad, confianza, CWE y OWASP |
| Timeouts por módulo | Aplicados de verdad en el orquestador, con límite propio para ZAP |
| API | `GET /sites/{id}/security` |
| Frontend | Pestaña de seguridad en el detalle de la auditoría |
| Pruebas | 484 en total (423 previas más 61 nuevas) |

## Doble barrera de alcance

ZAP emite sus propias peticiones y **no** pasa por el guard de SSRF de la
aplicación. Por eso el alcance se aplica dos veces:

1. Solo se le entregan las URL que el crawler ya rastreó, todas validadas por el
   guard.
2. El scope se traduce a expresiones regulares y se inyecta en el contexto de
   ZAP, de modo que ni su spider pueda salir del alcance autorizado.

Las expresiones respetan los límites de etiqueta y de segmento: `softree.mx`
cubre `www.softree.mx` pero no `malicioso-softree.mx`, y excluir `/admin` no
excluye `/administracion`.

## Solo passive scan

No se ejecuta active scan. El análisis examina las respuestas del sitio sin
enviarle peticiones de ataque, así que no puede alterar datos del cliente. La
interfaz y el futuro reporte lo declaran explícitamente, junto con el aviso de
que la ausencia de hallazgos no significa que el sitio esté limpio.

## Agrupación de alertas

ZAP emite una alerta por URL. Una cabecera de seguridad ausente en diecinueve
páginas produce diecinueve alertas, pero es **un** problema de configuración del
servidor. El normalizador agrupa por regla, parámetro y riesgo:

- si el grupo afecta a una sola URL, el finding la conserva;
- si afecta a varias, la lista completa vive en la evidencia y el número de
  casos en `occurrences`.

En la prueba real, 83 alertas se convirtieron en 6 hallazgos legibles.

## Criterios de aceptación

| Criterio | Resultado |
|----------|-----------|
| ZAP se integra en modo passive scan, sin active scan | Cumplido |
| El scope se inyecta en el contexto de ZAP | Cumplido |
| Las alertas se normalizan y nunca se muestran crudas | Cumplido |
| La alerta original se conserva para trazabilidad | Cumplido |
| Las alertas que ZAP marca como falso positivo se descartan | Cumplido |
| Severidad, confianza, CWE y OWASP se mapean correctamente | Cumplido |
| ZAP ausente o caído deja el módulo `skipped`, no rompe la auditoría | Cumplido |
| El contexto se retira aunque el scan falle | Cumplido |
| La cancelación detiene el envío de URL | Cumplido |
| Cada módulo tiene un tiempo máximo real | Cumplido |
| `ruff`, `ruff format`, `mypy --strict` sin hallazgos | Cumplido |
| `astro check`, `tsc --noEmit` sin errores | Cumplido |

## Verificación de extremo a extremo

ZAP 2.17.0 en su contenedor, sin puertos publicados al host, contra el
`test-target`:

```
discovery  completed
crawler    completed   18 páginas
seo        completed   16/16 reglas, 15 hallazgos
security   completed   18 URL enviadas, spider 24 URL, 83 alertas → 6 hallazgos
```

| Hallazgo | Severidad | Casos | CWE | OWASP |
|----------|-----------|-------|-----|-------|
| Content Security Policy (CSP) Header Not Set | media | 19 | CWE-693 | 2025 A02 |
| Missing Anti-clickjacking Header | media | 17 | CWE-1021 | 2025 A02 |
| Absence of Anti-CSRF Tokens | media | 1 | CWE-352 | 2025 A01 |
| Server Leaks Version Information | baja | 24 | CWE-497 | 2025 A02 |
| X-Content-Type-Options Header Missing | baja | 20 | CWE-693 | 2025 A02 |
| In Page Banner Information Leak | baja | 2 | CWE-497 | 2025 A02 |

Todos corresponden a defectos deliberados de la configuración del `test-target`:
sin cabeceras de seguridad, `server_tokens on` y un formulario sin protección
CSRF.

## Hallazgos corregidos durante el slice

| Hallazgo | Corrección |
|----------|-----------|
| Los timeouts por módulo estaban documentados pero **no implementados**: un módulo colgado habría bloqueado el scan hasta el timeout global del worker | `asyncio.timeout` por módulo, con límite propio para ZAP y estado `failed` con mensaje explícito |
| `spider_urls` se reportaba siempre como 0 sin poblarse: un dato falso en el detalle del módulo | Se consulta el resultado real del spider a ZAP |
| `site_seo_summary` duplicaba la búsqueda del último scan terminado | Extraída a `_last_finished_scan`, compartida con el resumen de seguridad |

## Deuda declarada

- El **active scan** sigue fuera del MVP. Incorporarlo exigirá consentimiento
  explícito por sitio, no solo la autorización general de auditoría.
- ZAP no emite severidad `critical` en passive scan; el modelo la admite para
  cuando entren otras fuentes.

## Siguiente

Slice 6: Google PageSpeed Insights, con API real y las métricas de Core Web
Vitals.
