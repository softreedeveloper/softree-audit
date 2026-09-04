# test-target

Sitio con defectos controlados para las pruebas automatizadas (§44). No se usan
sitios de terceros como dependencia de las pruebas.

Defectos incluidos, con la regla SEO que deben disparar:

| Página | Defecto | Regla esperada |
|--------|---------|----------------|
| `/` | correcta, sirve de control | — |
| `/sin-title.html` | sin `<title>` | SEO-001 |
| `/duplicado-a.html`, `/duplicado-b.html` | title y description duplicados | SEO-002, SEO-004 |
| `/sin-description.html` | sin meta description | SEO-003 |
| `/sin-h1.html` | sin H1 | SEO-005 |
| `/multi-h1.html` | varios H1 | SEO-006 |
| `/sin-alt.html` | imágenes sin `alt` | SEO-007 |
| `/enlace-roto.html` | enlace interno a `/no-existe` (404) | SEO-008 |
| `/sin-canonical.html` | sin canonical | SEO-010 |
| `/canonical-invalido.html` | canonical a otro dominio | SEO-011 |
| `/noindex.html` | `meta robots noindex` | SEO-012 |
| `/redirect-1` → `/redirect-2` → `/final.html` | cadena de redirección | SEO-015 |
| `/copia-a.html` y `/copia-b.html` | title, description y H1 idénticos | SEO-016 |
| enlace a `http://enlace-externo-roto.test/` desde `/` | dominio externo inexistente | SEO-009 |
| toda respuesta | sin cabeceras de seguridad | findings de ZAP |

`robots.txt` existe y `sitemap.xml` está deliberadamente incompleto, de modo
que SEO-013 y SEO-014 **no** deben dispararse.

El enlace externo apunta a un dominio que no resuelve: la comprobación lo
registra como error de red, no como enlace roto, porque un fallo de
resolución no demuestra que el recurso no exista.

```bash
docker compose --profile testing up -d
curl -s http://localhost:8081/ | head
```
