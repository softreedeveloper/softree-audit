"""Catálogo de reglas SEO.

Cada regla declara aquí su identidad y sus textos. Separar el catálogo de la
lógica permite revisar la redacción sin tocar código, y aporta el texto no
técnico que necesita el resumen ejecutivo del reporte (§34).
"""

from __future__ import annotations

from dataclasses import dataclass

from softree_audit.models.enums import Confidence, FindingCategory, Severity


@dataclass(frozen=True, slots=True)
class RuleDefinition:
    id: str
    title: str
    severity: Severity
    category: FindingCategory
    description: str
    impact: str
    remediation: str
    client_explanation: str
    confidence: Confidence = Confidence.HIGH


CATALOG: dict[str, RuleDefinition] = {
    rule.id: rule
    for rule in (
        RuleDefinition(
            id="SEO-001",
            title="Página sin elemento title",
            severity=Severity.HIGH,
            category=FindingCategory.SEO,
            description=(
                "La página no declara un elemento <title>. Es el principal indicador de "
                "contenido para los buscadores y el texto que se muestra como titular en "
                "los resultados de búsqueda."
            ),
            impact=(
                "Los buscadores generan un titular a partir del contenido, normalmente peor "
                "que uno redactado, lo que reduce la tasa de clic."
            ),
            remediation=(
                "Añadir un <title> único y descriptivo de entre 50 y 60 caracteres dentro "
                "del <head> de la página."
            ),
            client_explanation=(
                "Esta página no tiene título. Es el texto que aparece como titular cuando "
                "alguien la encuentra en Google, así que conviene definirlo."
            ),
        ),
        RuleDefinition(
            id="SEO-002",
            title="Title duplicado en varias páginas",
            severity=Severity.MEDIUM,
            category=FindingCategory.SEO,
            description=(
                "Varias páginas comparten exactamente el mismo <title>, por lo que los "
                "buscadores no pueden distinguir de qué trata cada una."
            ),
            impact=(
                "Las páginas compiten entre sí por las mismas búsquedas y el buscador puede "
                "elegir mostrar la que menos interesa."
            ),
            remediation="Redactar un título único para cada página.",
            client_explanation=(
                "Varias páginas del sitio tienen el mismo título, lo que dificulta que se "
                "distingan entre sí en los resultados de búsqueda."
            ),
        ),
        RuleDefinition(
            id="SEO-003",
            title="Página sin meta description",
            severity=Severity.MEDIUM,
            category=FindingCategory.SEO,
            description=(
                "La página no declara una meta description, el resumen que suele mostrarse "
                "bajo el título en los resultados de búsqueda."
            ),
            impact=(
                "El buscador improvisa un fragmento del contenido, con menos control sobre "
                "el mensaje y menor tasa de clic."
            ),
            remediation=(
                "Añadir una meta description propia de entre 120 y 160 caracteres que "
                "resuma el contenido de la página."
            ),
            client_explanation=(
                "Falta el resumen que aparece debajo del título en Google. Sin él, el "
                "buscador escoge un fragmento cualquiera de la página."
            ),
        ),
        RuleDefinition(
            id="SEO-004",
            title="Meta description duplicada en varias páginas",
            severity=Severity.LOW,
            category=FindingCategory.SEO,
            description="Varias páginas comparten la misma meta description.",
            impact="El resumen deja de describir el contenido concreto de cada página.",
            remediation="Redactar una descripción específica para cada página.",
            client_explanation=(
                "Varias páginas usan el mismo resumen, así que no describen bien su "
                "contenido particular."
            ),
        ),
        RuleDefinition(
            id="SEO-005",
            title="Página sin encabezado H1",
            severity=Severity.MEDIUM,
            category=FindingCategory.SEO,
            description=(
                "La página no tiene un encabezado H1, que marca el tema principal del "
                "contenido para buscadores y lectores de pantalla."
            ),
            impact="Se pierde la señal más clara sobre el tema de la página.",
            remediation="Añadir un único H1 que describa el contenido principal.",
            client_explanation=(
                "Falta el encabezado principal de la página, el que indica de qué trata."
            ),
        ),
        RuleDefinition(
            id="SEO-006",
            title="Página con varios encabezados H1",
            severity=Severity.LOW,
            category=FindingCategory.SEO,
            description=(
                "La página declara más de un H1. La jerarquía de encabezados deja de ser "
                "clara y se diluye la señal del tema principal."
            ),
            impact="Buscadores y lectores de pantalla reciben señales contradictorias.",
            remediation="Dejar un solo H1 y convertir el resto en H2 o H3.",
            client_explanation=(
                "La página tiene varios encabezados principales; debería tener solo uno."
            ),
        ),
        RuleDefinition(
            id="SEO-007",
            title="Imágenes sin texto alternativo",
            severity=Severity.LOW,
            # Es antes un problema de accesibilidad que de posicionamiento, y así
            # alimenta el score de accesibilidad (docs/spec/scoring.md §6).
            category=FindingCategory.ACCESSIBILITY,
            description=(
                "Hay imágenes sin atributo alt o con un alt vacío. El texto alternativo es "
                "lo que leen los lectores de pantalla y lo que se muestra si la imagen no "
                "carga."
            ),
            impact=(
                "Las personas que usan lectores de pantalla pierden esa información, y los "
                "buscadores no pueden interpretar la imagen."
            ),
            remediation=(
                "Añadir un alt descriptivo. Las imágenes puramente decorativas deben llevar "
                'alt="" de forma explícita.'
            ),
            client_explanation=(
                "Algunas imágenes no tienen descripción de texto, necesaria para quienes "
                "navegan con lectores de pantalla."
            ),
        ),
        RuleDefinition(
            id="SEO-008",
            title="Enlace interno roto",
            severity=Severity.HIGH,
            category=FindingCategory.SEO,
            description=(
                "Una página del sitio enlaza a una dirección interna que responde con un "
                "código de error."
            ),
            impact=(
                "El visitante llega a una página de error y el buscador desperdicia "
                "presupuesto de rastreo en una dirección que no existe."
            ),
            remediation=(
                "Corregir el enlace o redirigir la dirección antigua a la nueva con un 301."
            ),
            client_explanation=("Hay un enlace del sitio que lleva a una página que ya no existe."),
        ),
        RuleDefinition(
            id="SEO-009",
            title="Enlace externo roto",
            severity=Severity.LOW,
            category=FindingCategory.SEO,
            description=(
                "Una página enlaza a una dirección de otro dominio que responde con un "
                "código de error."
            ),
            impact="El visitante llega a una página inexistente fuera del sitio.",
            remediation="Actualizar o retirar el enlace.",
            client_explanation="Hay un enlace hacia otro sitio web que ya no funciona.",
            # El destino puede fallar de forma temporal o bloquear a los robots.
            confidence=Confidence.MEDIUM,
        ),
        RuleDefinition(
            id="SEO-010",
            title="Página sin enlace canonical",
            severity=Severity.LOW,
            category=FindingCategory.SEO,
            description=(
                "La página no declara un enlace canonical, que indica cuál es su dirección "
                "preferida cuando el mismo contenido es accesible por varias URL."
            ),
            impact="Aumenta el riesgo de que el buscador indexe direcciones duplicadas.",
            remediation='Añadir <link rel="canonical"> con la dirección preferida.',
            client_explanation=(
                "La página no indica cuál es su dirección oficial, algo útil cuando el "
                "mismo contenido se puede abrir desde varias direcciones."
            ),
        ),
        RuleDefinition(
            id="SEO-011",
            title="Enlace canonical inválido",
            severity=Severity.MEDIUM,
            category=FindingCategory.SEO,
            description=(
                "El enlace canonical apunta a un dominio ajeno al sitio o a una dirección "
                "que no responde correctamente."
            ),
            impact=(
                "El buscador puede dejar de indexar la página y atribuir su contenido a "
                "otra dirección."
            ),
            remediation=(
                "Apuntar el canonical a una dirección propia del sitio que responda con 200."
            ),
            client_explanation=(
                "La página indica como dirección oficial una que no corresponde al sitio o "
                "que no funciona."
            ),
        ),
        RuleDefinition(
            id="SEO-012",
            title="Página marcada como noindex",
            severity=Severity.LOW,
            category=FindingCategory.SEO,
            description=(
                "La página declara la directiva noindex, por lo que queda fuera del índice "
                "de los buscadores."
            ),
            impact="La página no aparecerá en resultados de búsqueda.",
            remediation=(
                "Si la exclusión es intencional, no hay nada que corregir. Si no lo es, "
                "retirar la directiva noindex."
            ),
            client_explanation=(
                "Esta página está marcada para no aparecer en buscadores. Conviene "
                "confirmar que es lo que se quiere."
            ),
            # Excluir una página del índice suele ser deliberado.
            confidence=Confidence.MEDIUM,
        ),
        RuleDefinition(
            id="SEO-013",
            title="El sitio no publica un sitemap.xml",
            severity=Severity.LOW,
            category=FindingCategory.SEO,
            description=("No se encontró un sitemap.xml accesible ni declarado en robots.txt."),
            impact=(
                "Los buscadores tienen que descubrir las páginas solo siguiendo enlaces, lo "
                "que retrasa la indexación del contenido nuevo."
            ),
            remediation=(
                "Publicar un sitemap.xml con las direcciones indexables y declararlo en robots.txt."
            ),
            client_explanation=(
                "El sitio no tiene un mapa de páginas, que ayuda a los buscadores a "
                "encontrar y actualizar el contenido más rápido."
            ),
        ),
        RuleDefinition(
            id="SEO-014",
            title="El sitio no publica un robots.txt",
            severity=Severity.LOW,
            category=FindingCategory.SEO,
            description="No se encontró un archivo robots.txt en la raíz del sitio.",
            impact=(
                "No se puede indicar a los buscadores qué zonas no deben rastrear ni dónde "
                "está el sitemap."
            ),
            remediation="Publicar un robots.txt en la raíz, aunque sea permisivo.",
            client_explanation=(
                "Falta el archivo que indica a los buscadores qué partes del sitio pueden recorrer."
            ),
        ),
        RuleDefinition(
            id="SEO-015",
            title="Cadena de redirecciones",
            severity=Severity.LOW,
            category=FindingCategory.SEO,
            description=("Una dirección llega a su destino tras encadenar varias redirecciones."),
            impact=(
                "Cada salto añade latencia para el visitante y consume presupuesto de rastreo."
            ),
            remediation="Redirigir la dirección original directamente al destino final.",
            client_explanation=(
                "Al abrir esta dirección el navegador pasa por varias redirecciones antes "
                "de llegar a la página, lo que la hace más lenta."
            ),
        ),
        RuleDefinition(
            id="SEO-016",
            title="Señal de contenido duplicado",
            severity=Severity.MEDIUM,
            category=FindingCategory.SEO,
            description=(
                "Varias páginas indexables comparten a la vez title, meta description y "
                "encabezado H1, lo que sugiere contenido duplicado."
            ),
            impact=(
                "Los buscadores reparten la relevancia entre las copias y pueden indexar "
                "solo una de ellas."
            ),
            remediation=(
                "Unificar las páginas, diferenciar su contenido o marcar la versión "
                "preferida con un canonical."
            ),
            client_explanation=(
                "Varias páginas parecen tener el mismo contenido, lo que hace que compitan "
                "entre sí en los buscadores."
            ),
        ),
    )
}

RULE_IDS: tuple[str, ...] = tuple(CATALOG)
