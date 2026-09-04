# ADR-004 — Escáner de seguridad

Estado: Aceptado · Fecha: 2026-09-03

## Contexto

Se requiere análisis de seguridad real, no simulado, sobre sitios autorizados,
sin construir capacidades ofensivas. El resultado debe integrarse en un modelo
unificado de findings junto con SEO y rendimiento.

## Decisión

OWASP ZAP en contenedor propio, en modo daemon, consumido por su API HTTP.
Únicamente **passive scan**, con spider limitado por scope. Las alertas de ZAP se
transforman mediante un adapter y un normalizador:

```
ZAP Alert → Finding Normalizer → Softree Finding
```

Las alertas crudas se conservan en `findings.raw`, pero nunca se muestran ni se
reportan sin normalizar.

## Alternativas

1. **Comprobaciones propias** (cabeceras, cookies, TLS). Fáciles de escribir,
   pero cobertura muy inferior y mantenimiento continuo de reglas.
2. **Nuclei.** Excelente cobertura por plantillas, pero su naturaleza es de
   comprobación activa; encaja mejor en una fase posterior con autorización
   explícita.
3. **Nikto o Wapiti.** Activos por diseño y con salidas menos estructuradas.
4. **ZAP con active scan desde el inicio.** Se descarta: genera tráfico intrusivo
   y podría alterar datos del sitio del cliente.

## Consecuencias

- El contenedor de ZAP añade consumo de memoria notable; se ejecuta bajo el
  perfil `scanner` de Compose y puede detenerse cuando no se audita.
- La cobertura pasiva no detecta clases enteras de vulnerabilidades. El reporte lo
  declara explícitamente para no dar una falsa sensación de completitud.
- El active scan queda como extensión futura, condicionada a consentimiento por
  sitio.
- El scope se inyecta también en ZAP como contexto include/exclude, porque ZAP
  emite sus propias peticiones y no pasa por el guard de URL de la aplicación
  (R6).
