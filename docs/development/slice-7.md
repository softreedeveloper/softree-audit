# Slice 7 — Google Search Console

Estado: **completado**, con la conexión en vivo pendiente de credenciales OAuth.

## Alcance entregado

| Área | Contenido |
|------|-----------|
| OAuth | URL de consentimiento, `state` de un solo uso, canje de código y renovación de access token |
| Credenciales | Solo se persiste el refresh token, cifrado con Fernet; el access token nunca toca la base de datos |
| Cliente | Listado de propiedades y Search Analytics, con errores diferenciados |
| Sincronización | 3 periodos × 5 dimensiones, con totales calculados sobre la dimensión `date` |
| API | `status`, `connect`, `callback`, `properties`, `property`, `connection` y `GET /scans/{id}/search-console` |
| Frontend | Página de integraciones por proyecto y pestaña de Search Console en la auditoría |
| Pruebas | 587 en total (542 previas más 45 nuevas) |

## Aislamiento entre proyectos

Una conexión pertenece a un único proyecto (`UNIQUE (project_id)`), y toda
consulta recorre la cadena proyecto → usuario. No existe endpoint que devuelva
métricas sin acotar por scan, y el scan pertenece a un sitio de ese proyecto.
Hay pruebas de que un proyecto sin conexión no ve la del proyecto vecino y de
que otro usuario recibe 404.

## Seguridad de las credenciales

- Solo el refresh token se persiste, cifrado con Fernet y clave derivada de
  `SECRET_KEY`. Hay prueba de que el valor en claro no aparece en la columna.
- El access token se obtiene en memoria en cada uso.
- La API nunca devuelve el refresh token; también con prueba.
- El `state` de OAuth es aleatorio, vive diez minutos, se consume al usarse y
  está ligado a usuario y proyecto: un `state` inventado o ajeno se rechaza.
- Se pide únicamente el scope `webmasters.readonly`: la plataforma no puede
  modificar la propiedad del cliente.
- El cuerpo de los errores de token no se registra, porque puede contener el
  `client_secret` reflejado.

## No estar conectado no es un error

Requisito §23, implementado en tres niveles:

1. `GET /integrations/google/status` responde **200** con
   `{"status": "not_connected"}`.
2. El módulo del pipeline queda `skipped` con motivo `no_conectado` y el resto
   de la auditoría continúa.
3. La interfaz muestra el estado «Search Console: no conectado» con el enlace
   para configurarlo, no un error.

## Retraso de consolidación

Search Console publica los datos con dos o tres días de retraso. Pedir hasta hoy
devolvería un tramo final vacío que se leería como una caída de tráfico, así que
la ventana termina tres días antes de la fecha de la auditoría. Está en el
cliente, con pruebas, y se explica en la interfaz.

## Totales calculados sobre `date`

Sumar clics por consulta o por página inflaría las cifras: Search Console omite
filas por privacidad y una misma visita aparece en varias dimensiones. Los
totales se calculan sobre la dimensión `date`, y la posición media se pondera
por impresiones en lugar de promediarse a secas.

## Criterios de aceptación

| Criterio | Resultado |
|----------|-----------|
| OAuth con consentimiento y callback | Cumplido |
| Solo se pide permiso de lectura | Cumplido |
| El refresh token se guarda cifrado | Cumplido |
| El access token no se persiste | Cumplido |
| El `state` es de un solo uso y está ligado al usuario | Cumplido |
| Selección de propiedad, validada contra las que la cuenta puede ver | Cumplido |
| Métricas de clics, impresiones, CTR y posición | Cumplido |
| Dimensiones `date`, `query`, `page`, `country`, `device` | Cumplido |
| Periodos de 7, 28 y 90 días | Cumplido |
| Sin conexión, el resto de la auditoría se ejecuta con normalidad | Cumplido |
| El acceso revocado marca la conexión y pide reconectar | Cumplido |
| Los datos no se cruzan entre proyectos | Cumplido |
| `ruff`, `ruff format`, `mypy --strict` sin hallazgos | Cumplido |
| `astro check`, `tsc --noEmit` sin errores | Cumplido |

## Hallazgo corregido durante el slice

La marca de conexión revocada se perdía: el servicio la escribía y a
continuación la petición terminaba en 409, cuyo rollback deshacía el cambio. Es
el mismo patrón que apareció con el reuso de refresh token en el Slice 1, así
que ahora se confirma la transacción antes de propagar el error. Lo detectó una
prueba, no una revisión.

## Verificación pendiente

Falta ejecutar el flujo de consentimiento real. Requiere registrar una
aplicación OAuth:

1. Google Cloud Console, mismo proyecto que la clave de PageSpeed o uno nuevo.
2. Habilitar «Google Search Console API».
3. Configurar la pantalla de consentimiento (tipo interno si la organización lo
   permite).
4. Crear credenciales de tipo «ID de cliente de OAuth» para aplicación web, con
   el URI de redirección
   `http://localhost:8000/api/v1/integrations/google/callback` en desarrollo.
5. Poner `GOOGLE_CLIENT_ID` y `GOOGLE_CLIENT_SECRET` en `.env`.

Sin ellas, la interfaz lo dice con claridad y el botón de conectar queda
deshabilitado, lo cual está verificado en el navegador.

## Siguiente

Slice 8: motor de findings y scoring, sin dependencias externas.
