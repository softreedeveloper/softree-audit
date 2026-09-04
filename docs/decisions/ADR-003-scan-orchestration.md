# ADR-003 — Orquestación de scans y cola de trabajos

Estado: Aceptado · Fecha: 2026-09-03

## Contexto

Los scans duran minutos y combinan varias integraciones externas. El frontend no
puede esperar bloqueado. Cada módulo debe poder fallar sin cancelar el scan
completo, y el scan debe poder cancelarse. La especificación sugiere «Celery o RQ
solamente si realmente es necesario», sobre Redis.

El resto del backend es asíncrono: FastAPI, SQLAlchemy async y un crawler basado
en httpx con concurrencia por semáforo.

## Decisión

Cola de trabajos con **arq** sobre Redis. Un worker dedicado ejecuta el
orquestador, que recorre el pipeline llamando a módulos que implementan el
protocolo `ScanModule`.

El orquestador es el único que persiste, aplica timeouts y captura excepciones.
La cancelación se señaliza con una bandera en Redis, consultada entre etapas.

## Alternativas

1. **`BackgroundTasks` de FastAPI.** Cero dependencias, pero sin persistencia:
   un reinicio pierde scans en curso, no hay cancelación ni concurrencia
   controlada, y el proceso de la API compite por CPU con el crawler.
2. **Celery.** Maduro y ampliamente conocido, pero su modelo es síncrono; correr
   corrutinas exige envolturas con `asyncio.run` por tarea y se pierde el pool de
   conexiones asíncrono. Además su configuración es notablemente más pesada de lo
   que este alcance justifica.
3. **RQ.** Simple, pero también síncrono y con el mismo problema de impedancia.
4. **Dramatiq.** Similar a Celery en modelo de ejecución.

## Consecuencias

- Un solo modelo de concurrencia en todo el backend, sin puentes entre síncrono y
  asíncrono.
- `arq` tiene una comunidad menor que Celery; el riesgo se acota porque el
  orquestador no depende de características avanzadas de la cola (solo encolar,
  ejecutar y reintentar), por lo que sustituirlo sería un cambio localizado.
- La desviación respecto a la sugerencia original queda registrada aquí y en
  `docs/spec/decisions.md` (R2).
- El worker se introduce en el Slice 3, junto con el pipeline (D-010).
