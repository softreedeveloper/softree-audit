# Softree Audit — Product Specification

## Usuario principal

**Softree internal user.** Miembro del equipo de Softree (desarrollo, SEO o
cuentas) que audita sitios propios, entregados o autorizados por clientes.

No hay usuarios finales del cliente en el MVP. El cliente recibe el PDF, no el
acceso a la plataforma.

## Propuesta de valor

> «Tu sitio fue entregado con una auditoría técnica de seguridad, SEO y
> rendimiento realizada por Softree.»

## Caso de uso principal

```
Login
 ↓
Create Project
 ↓
Add Website
 ↓
Configure Scope
 ↓
Run Audit
 ↓
Wait
 ↓
View Results
 ↓
Review Findings
 ↓
Generate Report
```

### Detalle del flujo

1. **Login.** Email y contraseña. Sesión con access token de vida corta.
2. **Create Project.** Nombre, cliente y notas. Agrupa los sitios de una cuenta.
3. **Add Website.** URL base y datos de autorización (`authorized_by`,
   `authorization_date`). Sin autorización no se habilita el botón de auditar.
4. **Configure Scope.** Dominios y rutas permitidas, exclusiones y límites de
   crawling. Se ofrecen valores por defecto seguros.
5. **Run Audit.** Se elige el tipo (`full`, `security`, `seo`, `performance`).
   La API responde de inmediato con un `scan_id`.
6. **Wait.** Progreso por módulo con indicación de porcentaje aproximado.
7. **View Results.** Dashboard con Softree Score, Google Score, conteo de
   findings por severidad y métricas del crawl.
8. **Review Findings.** Filtros por severidad, fuente y estado. Cada finding se
   puede marcar como `fixed`, `accepted` o `false_positive`.
9. **Generate Report.** PDF con branding Softree, más HTML y JSON.

## Casos de uso secundarios

| Caso | Descripción |
|------|-------------|
| Compare audits | Comparar el scan actual con el anterior y ver qué es nuevo, corregido, sin cambios o en regresión |
| Review SEO | Detalle por página y por regla SEO |
| Review Security | Alertas normalizadas de ZAP con evidencia, CWE y OWASP |
| Review Performance | Scores y Core Web Vitals en mobile y desktop |
| Review Search Console | Clicks, impresiones, CTR y posición por consulta y página |
| Download PDF | Descargar el reporte generado |

## Pantallas del MVP

| Pantalla | Contenido |
|----------|-----------|
| Login | Formulario y errores de credenciales |
| Dashboard | Resumen agregado de proyectos, últimos scans y findings críticos |
| Projects | Listado y CRUD |
| Project detail | Overview, Security, SEO, Performance, Search Console, Pages, Findings, History, Reports |
| Audits | Listado global de scans con estado y progreso |
| Findings | Vista transversal con filtros |
| Reports | Reportes generados y descarga |
| Integrations | Conexión con Google Search Console y estado de PageSpeed |
| Settings | Perfil, tema y pesos de scoring |

## Métricas de éxito del MVP

1. Auditar un sitio real de Softree de principio a fin sin intervención manual.
2. Generar un PDF entregable a cliente sin edición posterior.
3. Reproducir el mismo scan dos veces con resultados equivalentes salvo cambios
   reales del sitio.
4. Menos de 5 % de findings marcados como falso positivo tras la primera revisión.

## No objetivos

Competir con Burp Suite, OWASP ZAP como producto, Semrush o Ahrefs. Softree
Audit es una herramienta interna de entrega.
