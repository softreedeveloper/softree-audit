# Reglas SEO

Catálogo de las reglas del motor SEO (`RF-08`). La implementación vive en
`apps/api/softree_audit/services/seo/` y los textos en `catalog.py`.

## Convenciones

- Las reglas son funciones puras sobre un `SeoContext`: sin red, sin base de
  datos y sin estado compartido.
- Las incidencias **de página** producen un finding por página.
- Las incidencias **de grupo** (duplicados) producen un finding por grupo, con
  las URL afectadas en la evidencia y el número de páginas en `occurrences`.
- Las reglas de contenido solo evalúan páginas HTML servidas con 2xx y sin
  redirección: exigir un `title` a un 404 o a un PDF sería ruido.
- Las reglas de duplicados y de canonical solo evalúan páginas indexables: una
  página con `noindex` no compite en los mismos resultados.

## Catálogo

| Regla | Título | Severidad | Categoría | Alcance |
|-------|--------|-----------|-----------|---------|
| SEO-001 | Página sin elemento title | alta | seo | página |
| SEO-002 | Title duplicado en varias páginas | media | seo | grupo |
| SEO-003 | Página sin meta description | media | seo | página |
| SEO-004 | Meta description duplicada | baja | seo | grupo |
| SEO-005 | Página sin encabezado H1 | media | seo | página |
| SEO-006 | Página con varios encabezados H1 | baja | seo | página |
| SEO-007 | Imágenes sin texto alternativo | baja | accessibility | página |
| SEO-008 | Enlace interno roto | alta | seo | página |
| SEO-009 | Enlace externo roto | baja | seo | enlace |
| SEO-010 | Página sin enlace canonical | baja | seo | página |
| SEO-011 | Enlace canonical inválido | media | seo | página |
| SEO-012 | Página marcada como noindex | baja | seo | página |
| SEO-013 | El sitio no publica un sitemap.xml | baja | seo | sitio |
| SEO-014 | El sitio no publica un robots.txt | baja | seo | sitio |
| SEO-015 | Cadena de redirecciones | baja o informativa | seo | página |
| SEO-016 | Señal de contenido duplicado | media | seo | grupo |

## Decisiones que conviene conocer

**SEO-007 se clasifica como accesibilidad.** Una imagen sin `alt` es antes un
problema para quien usa un lector de pantalla que para el posicionamiento. Así
alimenta el score de accesibilidad (`docs/spec/scoring.md` §6) en lugar de
inflar el de SEO.

**SEO-016 es más estricto que SEO-002 y SEO-004.** Solo se dispara cuando
coinciden a la vez `title`, `meta description` y el primer `H1`. Dos páginas con
el mismo título pero distinto contenido disparan SEO-002 y no SEO-016.

**SEO-012 y SEO-009 tienen confianza media.** Excluir una página del índice suele
ser deliberado, y un enlace externo puede fallar por causas ajenas al sitio. El
score pondera la confianza, de modo que estos hallazgos pesan menos.

**SEO-015 distingue un salto de una cadena.** Una sola redirección es habitual y
se reporta como informativa; encadenar dos o más sí penaliza y se reporta como
incidencia leve.

**Un fallo de red no es un enlace roto.** En SEO-009 solo se reporta un enlace
que responde con código de error. Un timeout o un fallo de DNS se registra como
error de comprobación, porque no demuestra que el recurso no exista.

## Comprobación de enlaces externos (SEO-009)

Comprobar un enlace saliente exige una petición hacia un dominio de terceros,
fuera del alcance autorizado. Por eso:

- está **desactivada por defecto** y se habilita por sitio con
  `scope.check_external_links`;
- usa `HEAD`, con `GET` de respaldo solo si el servidor no admite `HEAD`;
- pasa por el guard de SSRF, así que sigue sin poder alcanzar redes internas;
- está acotada a 100 URL únicas y espaciada en el tiempo.

Es una comprobación de disponibilidad de un enlace, equivalente a que una
persona lo pulse, no una auditoría del sitio de destino: no se rastrea, no se
analiza su contenido y no se guarda su cuerpo.

## Una regla que falla no invalida el análisis

El motor captura la excepción de cada regla, la registra en
`scan_modules.detail.rules_failed` y continúa con el resto.
