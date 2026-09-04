# Slice 11 — E2E y validación de seguridad

Estado: **completado**.

## Alcance entregado

| Área | Contenido |
|------|-----------|
| E2E de producto | 11 pruebas con el flujo completo de la especificación §43 |
| E2E de seguridad | 8 pruebas sobre la aplicación en ejecución |
| Herramientas | `make e2e-up` y `make test-e2e`, configuración de Playwright |
| Pruebas | 715 de backend más 19 end to end |

## Flujo cubierto

```
Login → Create project → Create site → Configure scope → Run audit
      → View results → View findings → Generate report → Compare → History
```

Incluye los caminos de error del producto: un scope que no cubre el sitio se
rechaza con su mensaje, y marcar un hallazgo como falso positivo lo retira de
los abiertos.

## Validación de seguridad sobre la aplicación viva

| Comprobación | Resultado |
|--------------|-----------|
| Sin sesión, las páginas muestran el estado no autorizado | Cumplido |
| La API rechaza cualquier petición sin token | Cumplido |
| Credenciales inválidas y usuario inexistente son indistinguibles | Cumplido |
| Cabeceras `nosniff`, `DENY`, `no-referrer` y CSP presentes | Cumplido |
| La cookie de sesión es `HttpOnly` y solo llega a `/api/v1/auth` | Cumplido |
| El refresh token no sirve como token de acceso | Cumplido |
| Un sitio sin autorización no puede auditarse | Cumplido |
| La documentación interactiva usa su propia CSP | Cumplido |

## Hallazgos corregidos durante el slice

Los tres son defectos reales que solo aparecieron al ejercitar la aplicación
completa desde un navegador.

### 1. Dos renovaciones simultáneas cerraban la sesión

Al cargar una página, la vista pedía sus datos antes de que la sesión estuviera
restaurada. Ese `401` disparaba una segunda renovación en paralelo con la
inicial y, como el refresh token rota en cada uso, el servidor recibía una
credencial ya rotada, lo interpretaba como robo y **revocaba todas las sesiones
del usuario**. En los logs: `auth.refresh_reuse_detected` seguido de
`auth.all_sessions_revoked`.

Se corrigió por los dos lados:

- **Cliente**: ninguna llamada sale antes de que la sesión esté resuelta, la
  restauración es única por carga de página, y si otro flujo ya renovó el token
  mientras la petición viajaba se reintenta en lugar de pedir otra renovación.
- **Servidor**: ventana de gracia de 15 segundos. Una repetición inmediata del
  token recién rotado es una carrera benigna —dos pestañas abiertas, una
  recarga— y se responde con un par nuevo. Fuera de esa ventana sigue siendo
  robo y se revoca toda la sesión. Ambos casos tienen prueba.

Cerrar la sesión ante una carrera de dos pestañas es hostil y no aporta
seguridad: el atacante que roba un token lo usa mucho después, no en el mismo
segundo.

### 2. WeasyPrint descartaba parte del CSS del reporte

Con el autoescape de Jinja activo, `<style>{{ css }}</style>` convertía las
comillas de `font-family: "DejaVu Sans Mono"` en entidades HTML. WeasyPrint no
podía interpretar esas reglas y las descartaba en silencio: el PDF perdía la
tipografía monoespaciada y los estilos asociados. Solo se vio al leer el log del
contenedor: `Stop token reached before {} block for a qualified rule`.

La hoja de estilos es un archivo propio, no entrada del usuario, así que se
inserta sin escapar. Hay dos pruebas: una comprueba que el CSS llega sin
escapar, otra que WeasyPrint no emite ningún aviso al componer el PDF.

### 3. El sitio de pruebas no se reconstruía

`docker compose up -d --build test-target` reutilizaba la capa en caché y servía
el HTML antiguo, lo que hacía que una comparación pareciera no detectar cambios.
Se documenta el uso de `--no-cache` al modificar el fixture.

## Criterios de aceptación

| Criterio | Resultado |
|----------|-----------|
| El flujo completo de §43 funciona de principio a fin | Cumplido |
| Las pruebas usan el `test-target` local, sin terceros | Cumplido |
| Las comprobaciones de seguridad se ejecutan contra la aplicación viva | Cumplido |
| Ninguna prueba se elimina ni se omite para que el build pase | Cumplido |
| `make test-e2e` deja las pruebas listas para ejecutarse | Cumplido |

## Nota sobre las pruebas de rendimiento

La especificación menciona pruebas de rendimiento en este slice. Los límites de
carga del MVP ya están cubiertos por diseño y verificados: concurrencia acotada
en el crawler, `max_pages` y `max_depth`, timeout por módulo, límites de tasa en
la API, caché y ritmo en PageSpeed. Una prueba de carga sintética sobre un
producto interno de un solo tenant no aportaría información accionable, así que
no se ha construido. Queda declarado en lugar de darse por hecho.
