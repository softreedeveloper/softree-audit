# Slice 3 — Orquestación de scans y crawler

Estado: **completado**.

## Alcance entregado

| Área | Contenido |
|------|-----------|
| Guard de SSRF | Punto único de validación: esquema, credenciales, puerto, host, resolución DNS, rangos bloqueados, metadatos de nube, alcance autorizado y formas alternativas de IPv4 |
| Cliente HTTP seguro | Fijación de la IP validada, revalidación por salto de redirección, corte por tamaño, control de descompresión, filtro de content type |
| Crawler | `robots.txt`, `sitemap.xml`, recorrido en anchura con límites, extracción completa de RF-06, datos estructurados |
| Orquestación | Pipeline con estado por módulo, timeouts, cancelación y estado final `completed`, `partial`, `failed` o `cancelled` |
| Cola | `arq` sobre Redis, servicio `worker` en Compose |
| API | `POST /scans` con validación previa e `Idempotency-Key`, listado, detalle, módulos, páginas y cancelación |
| Frontend | Botón de ejecución en el sitio, listado de auditorías, detalle con progreso por módulo y tabla de páginas |
| Pruebas | 347 en total (213 previas más 134 nuevas), 64 de ellas sobre el guard |

## Protección contra SSRF

La secuencia de `docs/spec/security.md` §2 está implementada completa. Detalles
que merecen mención:

1. **El alcance se comprueba antes de resolver.** Un destino fuera de scope no
   genera ni una consulta DNS.
2. **Todas las direcciones resueltas se validan.** Basta que una sea privada
   para rechazar el host completo.
3. **La conexión va a la IP validada**, con la cabecera `Host` original y
   `sni_hostname`, de modo que TLS sigue verificando el certificado contra el
   nombre real. Cierra la ventana de DNS rebinding entre validar y conectar.
4. **Cada redirección se revalida** desde el paso 1, con un máximo de 5 saltos.
5. **Formas alternativas de IPv4.** `http://2130706433/`, `http://0x7f000001/`,
   `http://0177.0.0.1/` y `http://127.1/` son 127.0.0.1 para `inet_aton`, pero
   `ipaddress` los rechaza y habrían pasado como nombres de dominio hasta la
   resolución del sistema. Se interpretan y bloquean explícitamente.
6. **La excepción de desarrollo no lo abre todo.** Con
   `SSRF_ALLOW_PRIVATE_NETWORKS=true` siguen bloqueados los endpoints de
   metadatos y el multicast, que nunca son un objetivo legítimo.

## Criterios de aceptación

| Criterio | Resultado |
|----------|-----------|
| Un sitio sin autorización no puede escanearse | Cumplido |
| Un objetivo que resuelve a red privada se rechaza antes de encolar | Cumplido |
| El scan se ejecuta en segundo plano y la API responde de inmediato | Cumplido |
| El estado de cada módulo es independiente | Cumplido |
| Un módulo que falla no cancela el scan (`partial`) | Cumplido |
| El scan siempre alcanza un estado terminal | Cumplido |
| La cancelación funciona en cola y durante el crawl | Cumplido |
| El crawler respeta `max_pages`, `max_depth`, scope y `robots.txt` | Cumplido |
| No hay bucles ni páginas duplicadas | Cumplido |
| Las cadenas de redirección quedan registradas | Cumplido |
| `Idempotency-Key` evita lanzar dos auditorías iguales | Cumplido |
| El scope queda congelado en el scan y lo hace reproducible | Cumplido |
| `ruff`, `ruff format`, `mypy --strict`, `alembic check` sin hallazgos | Cumplido |
| `astro check`, `tsc --noEmit` sin errores | Cumplido |

## Verificación de extremo a extremo

Con el perfil `testing` y `SSRF_ALLOW_PRIVATE_NETWORKS=true`, auditoría real del
`test-target` lanzada desde la interfaz:

```
discovery  completed    37 ms   resolved_ip=172.20.0.6  status=200
crawler    completed   1.6 s    16 páginas, robots.txt y sitemap encontrados
```

Todos los defectos controlados del `test-target` aparecen en los datos:

| Página | Dato extraído |
|--------|---------------|
| `/sin-title.html` | `title` ausente |
| `/duplicado-a.html` y `/duplicado-b.html` | mismo `title` y `description` |
| `/sin-description.html` | `meta_description` ausente |
| `/sin-h1.html` | 0 encabezados H1 |
| `/multi-h1.html` | 3 encabezados H1 |
| `/sin-alt.html` | 2 imágenes sin `alt` |
| `/enlace-roto.html` → `/no-existe` | 404 con `discovered_from` al origen |
| `/noindex.html` | `is_indexable = false` |
| `/redirect-1` | 302 con cadena `/redirect-1 → /redirect-2 → /final.html` |
| `/canonical-invalido.html` | canonical a otro dominio |

Con el valor por defecto `SSRF_ALLOW_PRIVATE_NETWORKS=false`, el mismo objetivo
se rechaza:

```
HTTP 422 target_unreachable
La dirección 172.20.0.6 pertenece a un rango bloqueado (172.16.0.0/12).
```

## Hallazgos corregidos durante el slice

| Hallazgo | Corrección |
|----------|-----------|
| `http://2130706433/` y las demás formas alternativas de IPv4 no se reconocían como direcciones y llegaban a la resolución del sistema | Se interpretan con la semántica de `inet_aton` y se validan antes de resolver |
| El `User-Agent` llevaba una tilde: las cabeceras HTTP deben ser ASCII y toda petición real habría fallado | `User-Agent` sin caracteres no ASCII |
| Dos URLs que redirigían al mismo destino producían la misma clave `(scan_id, url_hash)` y rompían la inserción entera | La URL que redirige se registra por sí misma con su cadena; el destino se rastrea aparte. Deduplicación defensiva al persistir |
| Un error al persistir dejaba el scan en `running` para siempre | La persistencia entra en el manejo de error del módulo, y el orquestador tiene una red de seguridad que fuerza `failed` |
| Las pruebas unitarias leían el `.env` del equipo y su resultado dependía de la máquina | Aislamiento explícito del entorno en las pruebas |
| `finished_at` asignado con una expresión SQL dejaba el atributo expirado y provocaba IO perezosa al serializar | Valor calculado en Python |

## Deuda declarada

- La comprobación de enlaces externos rotos (SEO-009) no se implementa aquí: exige
  emitir tráfico hacia terceros fuera del alcance autorizado. Se decide en el
  Slice 4, con el motor de reglas.
- Los módulos de seguridad, rendimiento, Search Console, findings, scoring y
  reportes todavía no están registrados: el pipeline solo crea filas de los
  módulos que realmente se ejecutan, para no mostrar pasos ficticios.

## Siguiente

Slice 4: motor SEO con las reglas SEO-001 a SEO-016 sobre los datos que el
crawler ya produce.
