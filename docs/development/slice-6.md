# Slice 6 — Google PageSpeed Insights

Estado: **completado**, con una verificación en vivo pendiente de una API key.

## Alcance entregado

| Área | Contenido |
|------|-----------|
| Cliente PSI | API real, caché en Redis, límite de una petición por segundo, reintentos acotados y errores diferenciados |
| Normalizador | Puntuaciones, Core Web Vitals y datos de campo, con la respuesta original conservada |
| Reglas | PSI-001 a PSI-008 sobre los umbrales públicos de Google |
| Google Score | Puntuaciones de Lighthouse persistidas con `system = google`, sin transformar |
| API | `GET /sites/{id}/performance` |
| Frontend | Pestaña de rendimiento con tabla de Lighthouse y Core Web Vitals por estrategia |
| Pruebas | 539 en total (484 previas más 55 nuevas) |

## Los dos scores, separados desde el dato

El requisito §27 exige no presentar un cálculo propio como si fuera de Google.
Se cumple desde la persistencia, no solo en la presentación:

- las puntuaciones de Lighthouse se guardan en `scores` con `system = google` y
  el valor exacto que devuelve la API, sin transformar;
- el Softree Score se guardará con `system = softree` en el Slice 8;
- la interfaz etiqueta la tabla como «Google Lighthouse» y añade el aviso de que
  el Softree Score es un indicador propio.

Cuando hay dos estrategias, el score de Google se representa con el de móvil,
que es el criterio declarado en `docs/spec/scoring.md` §5, y el desglose completo
queda en `detail.by_strategy`.

## INP: sin datos no es cero

INP solo existe si el sitio tiene datos de campo en el informe de experiencia de
usuario de Chrome. Cuando no los hay, el valor se guarda como nulo y la interfaz
muestra «sin datos de campo», nunca un cero que se leería como excelente. Es el
requisito R4, y tiene prueba propia.

## Degradación ante fallos de la API

| Situación | Respuesta |
|-----------|-----------|
| Cuota agotada (429) | Módulo `skipped` con motivo `quota_exceeded` y mensaje accionable |
| Objetivo no accesible desde Internet (400) | Módulo `skipped` con motivo `target_not_reachable` |
| API inalcanzable | Tres intentos con espera creciente, luego `api_unreachable` |
| Falla una estrategia | La otra continúa; solo se omite el módulo si fallan las dos |

## Criterios de aceptación

| Criterio | Resultado |
|----------|-----------|
| Se usa la API real, sin datos simulados en producción | Cumplido |
| Se analizan móvil y escritorio | Cumplido |
| Se guardan las cuatro puntuaciones de Lighthouse | Cumplido |
| Se guardan LCP, CLS, INP, FCP, TBT y Speed Index | Cumplido |
| Se conserva la respuesta original para trazabilidad | Cumplido |
| INP nulo cuando no hay datos de campo | Cumplido |
| Google Score y Softree Score no se confunden | Cumplido |
| Los resultados se cachean para no agotar la cuota | Cumplido |
| Una estrategia que falla no invalida la otra | Cumplido |
| La cuota agotada se explica de forma accionable | Cumplido, verificado contra la API real |
| `ruff`, `ruff format`, `mypy --strict` sin hallazgos | Cumplido |
| `astro check`, `tsc --noEmit` sin errores | Cumplido |

## Verificación

Contra la **API real** de Google, sin `PAGESPEED_API_KEY`:

```
discovery    completed
performance  skipped   reason=quota_exceeded
                       failures={"mobile":"quota_exceeded","desktop":"quota_exceeded"}
```

La cuota anónima compartida de `pagespeedonline.googleapis.com` está agotada, lo
que ejercita de verdad el camino de degradación: el scan termina `completed`, el
módulo queda `skipped` con el motivo exacto y la interfaz muestra «La cuota de la
API de PageSpeed Insights está agotada. Configure PAGESPEED_API_KEY o inténtelo
más tarde».

El camino de éxito está cubierto por 55 pruebas con respuestas fieles a la forma
documentada de la API v5, pero **no se ha ejecutado en vivo**. Para completarlo
hace falta una `PAGESPEED_API_KEY` en `.env`.

### Cómo obtener la clave

1. En Google Cloud Console, crear o elegir un proyecto.
2. Habilitar «PageSpeed Insights API».
3. Crear una credencial de tipo clave de API y restringirla a esa API.
4. Ponerla en `.env` como `PAGESPEED_API_KEY` y reiniciar `api` y `worker`.

Sin clave la cuota es la anónima compartida; con clave son 25 000 consultas
diarias y 240 por minuto, holgado para el uso previsto.

## Deuda declarada

- Se analiza **la URL base**, no todas las páginas rastreadas: cada llamada
  consume cuota y tarda decenas de segundos. Ampliar el conjunto es una decisión
  de producto que puede tomarse después sin cambiar el módulo.
- El detalle de auditorías individuales de Lighthouse (imágenes sin optimizar,
  JavaScript sin usar) se conserva en `raw` pero todavía no se explota.

## Siguiente

Slice 7: Google Search Console, con OAuth y cifrado de credenciales en reposo.
