# Slice 8 — Findings y scoring

Estado: **completado**.

## Alcance entregado

| Área | Contenido |
|------|-----------|
| Motor de scoring | `softree_audit/scoring`, función pura sin IO ni base de datos |
| Pesos | Configurables, con redistribución cuando falta una categoría |
| Arrastre de estados | `accepted` y `false_positive` se heredan entre scans del mismo sitio |
| Persistencia | `scores` con `system = softree`, incluidos los pesos aplicados |
| API | `GET /scans/{id}/scores`, con los dos sistemas separados |
| Frontend | Tarjeta de puntuación en el detalle de la auditoría |
| Pruebas | 645 en total (587 previas más 58 nuevas) |

## El motor es una función pura

`packages/scoring` no importa base de datos, red ni framework web; hay una
prueba que lo verifica desde el Slice 1 (`test_dependency_rules.py`). La
traducción de artefactos del scan a la entrada del motor vive aparte, en
`scans/scoring_inputs.py`, de modo que el cálculo se prueba con datos fijos y es
determinista.

## Una categoría sin datos no cuenta como cero

Es la decisión de ADR-006 y se verifica en la auditoría real: sin PageSpeed
(cuota agotada) ni Search Console (sin conectar), los pesos se renormalizaron de
30/25 a 55 % seguridad y 45 % SEO, y el score global quedó en 86,7 en lugar de
hundirse por dos APIs ausentes. Penalizar al sitio por una falla de
infraestructura haría el score no reproducible.

## Techos por severidad

Un sitio con cien hallazgos leves no debe puntuar peor que uno con un crítico.
Cada severidad tiene su tope de penalización acumulada (100 / 60 / 35 / 15 / 0),
y la confianza del hallazgo modula su peso (1,0 / 0,75 / 0,5). Con pruebas para
cada caso.

## Arrastre de estados entre auditorías

`accepted` y `false_positive` son decisiones humanas sobre un hallazgo concreto;
obligar a repetirlas en cada auditoría haría el producto inutilizable. Se
heredan por huella, que es estable entre scans desde el Slice 4.

`fixed` **no** se hereda: si el problema vuelve a detectarse es que no está
corregido. Y el arrastre no cruza sitios: aceptar algo en un sitio no lo silencia
en otro. Ambas cosas con prueba.

Verificado de extremo a extremo: se marcaron dos hallazgos como aceptados, se
lanzó una auditoría nueva del mismo sitio y aparecieron ya aceptados junto con un
tercero aceptado en una auditoría anterior. Los hallazgos de severidad alta
pasaron de 2 a 0.

## Los dos scores, en el dato y en la pantalla

`GET /scans/{id}/scores` devuelve `softree` y `google` en listas separadas, con
el aviso de metodología incluido en la respuesta. La interfaz muestra el Softree
Score con su desglose y sus pesos, y las puntuaciones de Lighthouse bajo el
rótulo «Google Lighthouse (puntuación oficial de Google)».

## Límite conocido

Aceptar un hallazgo **SEO** no cambia el score SEO. La especificación define el
score de seguridad a partir de los hallazgos (§3) y el de SEO a partir de la
cobertura de indicadores sobre las páginas rastreadas (§4). Aceptar «página sin
title» como intencional no hace que la página tenga title, así que la cobertura
sigue siendo honesta. Es deliberado y se documenta aquí para que no se lea como
un fallo.

## Criterios de aceptación

| Criterio | Resultado |
|----------|-----------|
| El motor de scoring es puro y determinista | Cumplido |
| Los pesos se leen de configuración, no del código | Cumplido |
| Una categoría sin datos redistribuye su peso | Cumplido |
| Los hallazgos resueltos no penalizan | Cumplido |
| El ruido de hallazgos leves no domina el score | Cumplido |
| La confianza modula la penalización | Cumplido |
| Los pesos aplicados se persisten con cada score | Cumplido |
| `accepted` y `false_positive` se heredan entre scans | Cumplido |
| `fixed` no se hereda | Cumplido |
| El arrastre no cruza sitios | Cumplido |
| Softree Score y Google Score se devuelven separados | Cumplido |
| `ruff`, `ruff format`, `mypy --strict` sin hallazgos | Cumplido |
| `astro check`, `tsc --noEmit` sin errores | Cumplido |

## Hallazgo corregido durante el slice

El crawler informaba `completed` con cero páginas útiles cuando el guard
bloqueaba todas sus peticiones, lo que se leía como «el sitio no tiene
contenido». Ahora el módulo falla con un mensaje explícito. Apareció al ejecutar
una auditoría con el worker arrastrando la configuración anterior.

## Siguiente

Slice 9: dashboard, histórico y comparación entre auditorías.
