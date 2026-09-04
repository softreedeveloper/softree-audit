# ADR-007 — Generación de reportes

Estado: Aceptado · Fecha: 2026-09-03

## Contexto

Se requiere un PDF profesional con branding Softree, entregable a cliente, más
HTML y JSON. El PDF necesita portada, tablas, gráficos simples, encabezados y
pies de página con numeración.

## Decisión

Plantillas Jinja2 que producen el HTML del reporte, y WeasyPrint para convertir
ese mismo HTML a PDF. El JSON se genera del mismo modelo de datos mediante un
serializador propio. La generación ocurre en el worker, como última etapa del
pipeline, o bajo demanda vía `POST /reports/{scan_id}/generate`.

## Alternativas

1. **ReportLab.** Control total del PDF, pero el maquetado se escribe en código y
   el HTML tendría que construirse aparte, con riesgo de divergencia entre
   formatos.
2. **Playwright en modo `print-to-pdf`.** Fidelidad de navegador y soporte de
   CSS moderno, a cambio de arrastrar un navegador completo a la imagen del
   worker, que la especificación pide evitar en el MVP.
3. **wkhtmltopdf.** Sin mantenimiento activo y con soporte de CSS antiguo.
4. **Servicio externo de PDF.** Enviaría datos de auditoría de clientes a un
   tercero. Descartado por privacidad.

## Consecuencias

- Los tres formatos comparten el modelo de datos, por lo que no pueden divergir
  en contenido.
- WeasyPrint no ejecuta JavaScript: los gráficos se generan como SVG en el
  servidor, no con librerías de cliente.
- La imagen del backend necesita las dependencias nativas de WeasyPrint
  (`pango`, `cairo`, `gdk-pixbuf`), que se instalan en el Dockerfile.
- Si en el futuro se requiere fidelidad de navegador, Playwright entra como
  segundo backend de renderizado sin cambiar las plantillas.
