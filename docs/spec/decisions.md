# Decisiones tomadas ante ambigüedad

Registro breve de decisiones que no ameritan un ADR completo. Las decisiones
arquitectónicas mayores viven en `docs/decisions/`.

| ID | Ambigüedad | Decisión | Motivo |
|----|-----------|----------|--------|
| D-001 | Nombre del directorio del repositorio | `softree-audit`, igual que el producto | Inicialmente fue `softree-seo`, el nombre pedido. Se renombró el 2026-09-04: sostener dos nombres para la misma cosa obligaba a aclarar la diferencia en cada documento. Ver ADR-000 |
| D-002 | Idioma del código y de la documentación | Documentación en español, código, identificadores, API y mensajes de log en inglés | La documentación la leen cliente y equipo; el código lo leen herramientas |
| D-003 | Cómo se crean los usuarios sin registro público | Comando CLI `softree-audit create-user` | Evita exponer superficie de registro |
| D-004 | Transporte del token de sesión | Access token JWT vía `Authorization: Bearer`, refresh token en cookie `HttpOnly` | Bearer es directamente consumible por n8n; el refresh en cookie evita persistirlo en el navegador |
| D-005 | Origen del frontend respecto a la API | Same-origin mediante proxy en desarrollo y reverse proxy en producción | Elimina CORS permisivo y CSRF cross-site |
| D-006 | Representación de enumerados en base de datos | `VARCHAR` con `CHECK` constraint | Añadir valores no requiere `ALTER TYPE` ni migraciones frágiles |
| D-007 | Tipo de UUID | UUID versión 7 generado en la aplicación | Ordenable temporalmente, mejor localidad de índice que v4, sin exponer secuencias |
| D-008 | Alcance del esquema en el Slice 1 | Se crean todas las tablas del modelo de dominio en la migración inicial | El modelo ya está especificado; evita una cadena larga de migraciones durante el MVP |
| D-009 | Ubicación de `services/` y `packages/scoring` | Subpaquetes Python instalados junto a `apps/api` | Un solo entorno y una sola imagen; se pueden extraer después sin cambiar imports |
| D-010 | Momento de introducir el worker | Slice 3, junto con la orquestación de scans | Un worker sin tareas en el Slice 1 sería código muerto |
| D-011 | Periodos de Search Console | 7, 28 y 90 días, expresados como `period` configurable | Cubre lo pedido y deja abierta la extensión |
| D-012 | Política de reintentos | Máximo 2 reintentos con backoff exponencial y jitter, solo en errores transitorios | Evita amplificar fallas de terceros |
| D-013 | Zona horaria | Todo `timestamptz` en UTC; la conversión ocurre en el frontend | Comparaciones históricas consistentes |
| D-014 | Cifrado de tokens OAuth | Fernet con clave derivada de `SECRET_KEY` mediante HKDF | Sin dependencia de un KMS en el MVP, rotación documentada |
| D-015 | Unicidad del email sin `citext` | Columna `text` normalizada a minúsculas en el esquema Pydantic | Evita depender de una extensión de PostgreSQL |
| D-016 | Validación del email en el login | Solo validación de forma; `EmailStr` se reserva para la creación de cuentas | `EmailStr` rechaza dominios reservados como `.test`, y el formato no es un control de seguridad |
| D-017 | CHECK de los enumerados en `alembic check` | Se excluyen del autogenerado mediante `include_object` | SQLAlchemy los marca «type bound»: Alembic los refleja de la base de datos pero no los ve en los modelos, y los reportaría como eliminados en cada ejecución |
| D-018 | Persistencia de la revocación ante reuso de token | Se confirma la transacción antes de devolver 401 | El rollback de la petición fallida desharía la medida de seguridad |
| D-020 | Borrado de recursos con dependencias | `409` y repetición con `?force=true` | Un borrado en cascada silencioso destruiría el histórico de auditorías |
| D-021 | Comodines en las rutas del scope | No se aceptan; comparación por prefijo con límite de segmento | El scope es un control de seguridad y debe ser fácil de razonar |
| D-022 | Rutas de detalle en el frontend | Parámetro `?id=` resuelto en el cliente | La salida es estática; una ruta dinámica exigiría SSR |
| D-023 | Confirmación de borrado en la interfaz | En línea, nunca `window.confirm` | Los diálogos modales bloquean el navegador y romperían las pruebas E2E |
| D-025 | Fijación de la IP validada | URL con la IP, cabecera `Host` original y `sni_hostname` | Cierra el DNS rebinding sin tocar interiores de httpx y mantiene la verificación TLS |
| D-026 | Formas alternativas de IPv4 | Se interpretan con la semántica de `inet_aton` antes de resolver | `http://2130706433/` es 127.0.0.1 para el sistema pero un nombre de dominio para `ipaddress` |
| D-027 | Páginas que redirigen | La URL que redirige tiene su propia fila, con su cadena; el destino se rastrea aparte | Conserva el dato de SEO-015 sin duplicar contenido ni claves |
| D-028 | Módulos no implementados | No generan fila de `scan_modules` | Mostrar pasos que no se ejecutan sería información falsa |
| D-030 | Categoría de SEO-007 | `accessibility`, no `seo` | Una imagen sin `alt` afecta antes a quien usa un lector de pantalla; así alimenta el score correcto |
| D-031 | Findings de duplicados | Uno por grupo, con las URL en la evidencia | Un finding por página multiplicaría el mismo problema y ocultaría su alcance real |
| D-032 | Comprobación de enlaces externos | Opcional por sitio, desactivada por defecto | Exige tráfico a terceros; es una comprobación de disponibilidad, no una auditoría del destino |
| D-033 | Fallos de red en SEO-009 | No se reportan como enlace roto | Un timeout o un fallo de DNS no demuestra que el recurso no exista |
| D-035 | Alertas de ZAP en varias URL | Un finding por regla y parámetro, con las URL en la evidencia | Una cabecera ausente en 19 páginas es un problema de servidor, no 19 hallazgos |
| D-036 | URL que se entregan a ZAP | Las que ya rastreó el crawler, más el spider si el scope lo permite | Mantiene el tráfico acotado a lo ya validado por el guard |
| D-037 | Alertas marcadas «False Positive» por ZAP | Se descartan en el normalizador | Incorporarlas sería ruido que la propia herramienta ya descartó |
| D-038 | ZAP no disponible | El módulo queda `skipped` con el motivo | Es una integración externa; su ausencia no debe hacer fracasar la auditoría |
| D-040 | Alcance de PageSpeed | Solo la URL base, en móvil y escritorio | Cada llamada consume cuota y tarda decenas de segundos; ampliarla es una decisión de producto |
| D-041 | Estrategia que representa al sitio | Móvil, con el desglose completo en `detail.by_strategy` | Criterio declarado en scoring.md §5 por el tráfico predominante |
| D-042 | Findings de móvil y escritorio | Separados, distinguidos por `parameter` | Son medidas distintas del mismo problema y ambas deben poder verse |
| D-044 | Ventana de Search Console | Termina tres días antes de la auditoría | Los datos se consolidan con retraso; incluir el tramo final parecería una caída de tráfico |
| D-045 | Totales de Search Console | Se calculan sobre la dimensión `date` | Sumar por consulta o página inflaría las cifras por las filas omitidas y el solapamiento |
| D-046 | Posición media | Ponderada por impresiones | Una media simple daría el mismo peso a una consulta con 3 impresiones que a otra con 3000 |
| D-048 | Arrastre de estados entre scans | Solo `accepted` y `false_positive` | Son decisiones humanas; `fixed` debe volver a demostrarse en cada auditoría |
| D-049 | Alcance del arrastre | Por sitio, nunca entre sitios | Aceptar un hallazgo en un sitio no dice nada sobre otro |
| D-050 | Aceptar un hallazgo SEO | No altera el score SEO | El score SEO mide cobertura sobre las páginas, no hallazgos (scoring.md §4) |
| D-052 | Alcance de la comparación | Solo las fuentes que midieron ambas auditorías | Comparar tipos distintos reportaría como corregido lo que simplemente no se midió |
| D-053 | Agregados del dashboard | Última auditoría terminada de cada sitio | Sumar el histórico multiplicaría los hallazgos por auditoría |
| D-055 | Formatos del reporte | Los tres se generan del mismo `ReportModel` | Generarlos por separado los haría divergir en contenido |
| D-056 | Logo del reporte | Redimensionado y embebido como data URI | El original de 6250 px dejaba el PDF en 1,1 MB; embebido, el HTML es autocontenido |
| D-057 | Regenerar un reporte | Sustituye el archivo y su registro | No tiene sentido acumular versiones idénticas del mismo reporte |
| D-059 | Repetición inmediata de un refresh token | Ventana de gracia de 15 s; fuera de ella se revoca todo | Dos pestañas o una recarga son una carrera benigna; cerrar la sesión ahí es hostil y no aporta seguridad |
| D-060 | CSS del reporte | Se inserta sin escapar | Es un archivo propio; con autoescape, WeasyPrint descartaba las reglas con comillas |
| D-062 | Límite del refresco | 120 por hora y por usuario, no por IP | Cada navegación renueva el token; por IP, varios usuarios tras un proxy se expulsarían entre sí |
| D-061 | Pruebas de rendimiento sintéticas | No se construyen en el MVP | Los límites de carga ya están acotados por diseño y verificados; una prueba de carga sobre un producto interno de un tenant no daría información accionable |
| D-058 | Gráficos del reporte | Tablas por ahora, SVG en servidor más adelante | WeasyPrint no ejecuta JavaScript y las tablas ya son legibles |
| D-054 | Qué cuenta como regresión | Subir de severidad o afectar a más páginas | Bajar de severidad no es corregir, pero tampoco empeorar |
| D-051 | Crawl con todas las peticiones bloqueadas | El módulo falla, no se reporta `completed` | Cero páginas se leería como «el sitio no tiene contenido» |
| D-047 | Credencial de Search Console en el pipeline | La resuelve el orquestador y la pasa por contexto | Los módulos no acceden a base de datos por contrato |
| D-043 | Errores de PageSpeed | Cuota, objetivo inalcanzable y API caída se distinguen con motivos propios | «Falló» sin más no permite al usuario saber qué hacer |
| D-039 | Tiempo máximo por módulo | `asyncio.timeout` en el orquestador, con límite propio para ZAP | Sin él un módulo colgado bloquearía el scan hasta el timeout global |
| D-034 | Alcance de las reglas de contenido | Solo páginas HTML con 2xx y sin redirección | Exigir un title a un 404 o a un PDF sería ruido |
| D-029 | Reintentos de un scan completo | `max_tries = 1` en arq | Reintentar repetiría todo el tráfico contra el sitio del cliente |
| D-024 | Valores generados por el servidor en los modelos | `eager_defaults` en la base declarativa | Sin ello SQLAlchemy recarga `updated_at` de forma perezosa y falla en contexto asíncrono |
| D-019 | Anotación del cliente de Redis | Alias `RedisClient`, genérico solo bajo `TYPE_CHECKING` | `redis.asyncio.Redis` no es genérico en tiempo de ejecución y FastAPI evalúa las anotaciones de las dependencias |
| D-063 | Qué muestra la pantalla de configuración | Solo lectura: valores efectivos y, de cada integración, si tiene credenciales y qué variable la define | La configuración vive en el `.env` del despliegue. Editarla desde la interfaz obligaría a persistir secretos en base de datos; publicar su valor los filtraría a cualquiera con sesión |
| D-064 | Autenticación del callback de OAuth | El callback no exige `Authorization`: la identidad sale del `state`, token de un solo uso de 256 bits y diez minutos de vida, consumido con `GETDEL` | Google devuelve al usuario con una navegación de primer nivel del navegador. No lleva el token de acceso, que vive en memoria del cliente, y tampoco la cookie de refresco, que es `SameSite=Strict` y está limitada a `/api/v1/auth`. Exigir sesión hacía imposible completar el flujo |
| D-065 | Origen del `GOOGLE_REDIRECT_URI` en desarrollo | El de la API (`http://localhost:8000`); el retorno usa `APP_URL` | Google llama directamente al callback de la API y la API redirige explícitamente al frontend, evitando depender del proxy de Astro para OAuth |
| D-066 | Recuperación de acceso sin endpoint de contraseña | Comando `softree-audit reset-password`, que además revoca las sesiones abiertas del usuario | No hay registro ni recuperación pública, así que sin este comando una contraseña olvidada dejaba la cuenta inaccesible. El email se valida como en el login, no como al crear la cuenta: un dominio de uso reservado es legítimo aquí |
| D-067 | Qué cambia la audiencia de un reporte | Cambia qué se muestra, no qué se midió: `executive` sin evidencia ni detalle por módulo, `technical` sin las paráfrasis para el cliente, `combined` con todo. El JSON nunca se recorta | Un documento para dirección con volcados de cabeceras no se lee, y uno técnico con paráfrasis estorba a quien va a corregir. Recortar el JSON, en cambio, rompería a quien lo consume por API |
| D-068 | Nombre del archivo de un reporte | Incluye la audiencia: `softree-audit-<scan>-<audiencia>.<extensión>` | Sin ella, generar la versión ejecutiva sobrescribía el archivo de la técnica y los dos registros apuntaban al mismo documento |
| D-069 | Cuándo se ejecuta el análisis con IA | Al generar el reporte, no durante el scan | Necesita los hallazgos ya deduplicados y las puntuaciones ya calculadas, que es justo lo que contiene el `ReportModel`. Como módulo del pipeline vería datos aún sin consolidar |
| D-070 | Qué se envía al modelo de lenguaje | Un resumen estructurado sin evidencia, con todos los campos recortados y hasta 25 hallazgos | La evidencia es la mayor superficie de inyección de prompt y la que menos aporta para redactar. El sitio auditado se asume hostil |
| D-071 | Reutilización del análisis | Se guarda uno por auditoría y se reutiliza al regenerar cualquier formato o audiencia | Un reporte ya entregado no debe cambiar de redacción al volver a descargarlo. Además cada llamada cuesta tiempo: la primera real tardó 179 s |
| D-072 | Formato de la respuesta del modelo | Se pide JSON y se parsea con tolerancia; si no hay JSON aprovechable, el texto se usa como resumen | Un modelo pequeño envuelve el JSON en bloques de código o añade una frase. Descartar la llamada por eso desperdiciaría el trabajo, e inventar el contenido está prohibido |
| D-073 | Retirada de la suite de pruebas | Se eliminan `tests/`, el `test-target`, las dependencias de pytest y los objetivos de test del Makefile | Decisión expresa del responsable del proyecto el 2026-09-04, al preparar el despliegue. Contradice la regla §58 «no eliminar tests», que existe para impedir que se borren pruebas con tal de que pase el build; aquí es una decisión deliberada y no una forma de esquivar un fallo. Consecuencia asumida: no queda red de seguridad automática, y cualquier cambio futuro se verifica a mano. El histórico conserva las 769 pruebas hasta el commit anterior |
