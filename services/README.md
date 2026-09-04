# services/

Este directorio existe para mantener la correspondencia con la estructura
propuesta en la especificación, pero no contiene código.

Los servicios de scan viven dentro del paquete Python de la API:

| Servicio | Ubicación real |
|----------|----------------|
| Crawler | `apps/api/softree_audit/services/crawler/` |
| Seguridad (OWASP ZAP) | `apps/api/softree_audit/services/security/` |
| SEO | `apps/api/softree_audit/services/seo/` |
| Performance (PageSpeed) | `apps/api/softree_audit/services/performance/` |
| Search Console | `apps/api/softree_audit/services/search_console/` |
| Findings | `apps/api/softree_audit/services/findings/` |
| Reportes | `apps/api/softree_audit/services/reports/` |
| Utilidades compartidas (SSRF, HTTP, retry) | `apps/api/softree_audit/services/common/` |

Motivo: un solo entorno Python y una sola imagen Docker. Los imports ya usan
`softree_audit.services.<módulo>`, de modo que extraerlos a paquetes
independientes sería un cambio mecánico. Ver ADR-001 y la decisión D-009.
