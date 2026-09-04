"""Reglas derivadas de PageSpeed Insights.

Traducen métricas y puntuaciones a findings del modelo unificado. Los umbrales
son los públicos de Google (`thresholds.py`), no criterios propios.
"""

from __future__ import annotations

from dataclasses import dataclass

from softree_audit.models.enums import FindingCategory


@dataclass(frozen=True, slots=True)
class PerformanceRule:
    id: str
    title: str
    category: FindingCategory
    description: str
    impact: str
    remediation: str
    client_explanation: str


CATALOG: dict[str, PerformanceRule] = {
    rule.id: rule
    for rule in (
        PerformanceRule(
            id="PSI-001",
            title="Puntuación de rendimiento baja",
            category=FindingCategory.PERFORMANCE,
            description=(
                "La puntuación de rendimiento de Lighthouse queda por debajo del umbral "
                "recomendado por Google."
            ),
            impact=(
                "Una carga lenta aumenta el abandono antes de que la página llegue a "
                "mostrarse y penaliza el posicionamiento en móvil."
            ),
            remediation=(
                "Revisar el detalle de las auditorías de Lighthouse: suelen dominar el peso "
                "de las imágenes, el JavaScript que bloquea el renderizado y la ausencia de "
                "caché en el servidor."
            ),
            client_explanation=(
                "La página tarda más de lo recomendable en cargar, lo que hace que parte de "
                "las visitas se pierdan antes de verla."
            ),
        ),
        PerformanceRule(
            id="PSI-002",
            title="LCP por encima del umbral recomendado",
            category=FindingCategory.PERFORMANCE,
            description=(
                "El Largest Contentful Paint mide cuánto tarda en aparecer el elemento "
                "principal de la página. Google considera bueno un valor de hasta 2,5 s."
            ),
            impact="El visitante percibe la página como lenta desde el primer momento.",
            remediation=(
                "Optimizar la imagen o el bloque de texto principal, precargarlo y reducir "
                "el tiempo de respuesta del servidor."
            ),
            client_explanation=(
                "El contenido principal de la página tarda en aparecer más de lo que Google "
                "considera aceptable."
            ),
        ),
        PerformanceRule(
            id="PSI-003",
            title="CLS por encima del umbral recomendado",
            category=FindingCategory.PERFORMANCE,
            description=(
                "El Cumulative Layout Shift mide cuánto se mueve el contenido mientras "
                "carga. Google considera bueno un valor de hasta 0,1."
            ),
            impact=(
                "El contenido salta mientras el visitante lee o intenta pulsar, lo que "
                "provoca clics accidentales."
            ),
            remediation=(
                "Reservar el espacio de imágenes y anuncios con width y height, y evitar "
                "insertar contenido por encima de lo ya visible."
            ),
            client_explanation=(
                "Los elementos de la página se mueven mientras carga, lo que resulta "
                "incómodo y provoca pulsaciones equivocadas."
            ),
        ),
        PerformanceRule(
            id="PSI-004",
            title="INP por encima del umbral recomendado",
            category=FindingCategory.PERFORMANCE,
            description=(
                "El Interaction to Next Paint mide la respuesta a las interacciones reales "
                "de los visitantes. Google considera bueno un valor de hasta 200 ms. Solo "
                "está disponible si el sitio tiene datos de campo."
            ),
            impact="La página responde con retraso perceptible al pulsar o escribir.",
            remediation=(
                "Reducir el trabajo de JavaScript en el hilo principal y dividir las tareas largas."
            ),
            client_explanation=(
                "La página tarda en responder cuando alguien pulsa o escribe en ella."
            ),
        ),
        PerformanceRule(
            id="PSI-005",
            title="Tiempo de bloqueo total elevado",
            category=FindingCategory.PERFORMANCE,
            description=(
                "El Total Blocking Time mide cuánto tiempo el hilo principal queda "
                "bloqueado y no puede atender interacciones."
            ),
            impact="La página parece cargada pero no reacciona.",
            remediation="Reducir y dividir el JavaScript que se ejecuta durante la carga.",
            client_explanation=(
                "Durante la carga la página se queda un rato sin responder aunque ya se vea."
            ),
        ),
        PerformanceRule(
            id="PSI-006",
            title="Puntuación de accesibilidad baja",
            category=FindingCategory.ACCESSIBILITY,
            description=(
                "La auditoría de accesibilidad de Lighthouse queda por debajo del umbral "
                "recomendado."
            ),
            impact=(
                "Personas que navegan con lectores de pantalla o con el teclado encuentran "
                "barreras para usar el sitio."
            ),
            remediation=(
                "Revisar el detalle de Lighthouse: contraste de color, etiquetas de los "
                "formularios, textos alternativos y orden de foco."
            ),
            client_explanation=(
                "El sitio presenta barreras para personas con discapacidad visual o que "
                "navegan sin ratón."
            ),
        ),
        PerformanceRule(
            id="PSI-007",
            title="Puntuación de buenas prácticas baja",
            category=FindingCategory.BEST_PRACTICES,
            description=(
                "La auditoría de buenas prácticas de Lighthouse queda por debajo del umbral "
                "recomendado."
            ),
            impact=(
                "Suele indicar bibliotecas obsoletas, errores en consola o contenido servido "
                "de forma insegura."
            ),
            remediation="Revisar el detalle de Lighthouse y corregir lo señalado.",
            client_explanation=(
                "El sitio incumple algunas recomendaciones técnicas generales de la web."
            ),
        ),
        PerformanceRule(
            id="PSI-008",
            title="Puntuación SEO de Lighthouse baja",
            category=FindingCategory.SEO,
            description=(
                "La auditoría SEO de Lighthouse queda por debajo del umbral recomendado. "
                "Complementa al motor SEO propio, que analiza el sitio completo."
            ),
            impact="La página presenta carencias técnicas básicas de posicionamiento.",
            remediation="Revisar el detalle de Lighthouse junto con los hallazgos SEO propios.",
            client_explanation=(
                "La revisión automática de Google detecta carencias básicas de "
                "posicionamiento en esta página."
            ),
        ),
    )
}
