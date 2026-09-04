# Softree Audit — Scoring Specification

## 1. Dos sistemas de score

| Sistema | Origen | Presentación |
|---------|--------|--------------|
| **Google Score** | Lighthouse vía PageSpeed Insights, sin transformación | «Google Lighthouse» con la estrategia indicada |

El Google Score se persiste desde el Slice 6 en `scores` con `system = google`
y el valor exacto de la API. El Softree Score llega en el Slice 8 con
`system = softree`. La separación es de dato, no solo de presentación.

| **Softree Score** | Cálculo propio agregado | «Softree Score», con nota de metodología |

Nunca se presenta el Softree Score como score oficial de Google. En UI y PDF
ambos aparecen etiquetados y separados.

## 2. Categorías y pesos por defecto

| Categoría | Peso |
|-----------|------|
| Security | 30 % |
| Performance | 25 % |
| SEO | 25 % |
| Accessibility | 10 % |
| Best Practices | 10 % |

Los pesos se leen de configuración (`SCORING_WEIGHTS`, JSON) y se persisten en la
tabla `scores` junto con cada valor. Un cambio de pesos no altera scans
históricos.

Regla: la suma de pesos de las categorías con datos disponibles se renormaliza a
1. Si Performance no pudo calcularse, su peso se redistribuye proporcionalmente
entre las demás en lugar de contar como cero.

## 3. Score de Security

Parte de 100 y descuenta por finding abierto, con techo por severidad para que un
número grande de hallazgos leves no domine el resultado.

| Severidad | Penalización por finding | Penalización máxima acumulada |
|-----------|--------------------------|-------------------------------|
| critical | 25 | 100 |
| high | 12 | 60 |
| medium | 5 | 35 |
| low | 2 | 15 |
| info | 0 | 0 |

Se aplica un factor por confianza: `high` 1.0, `medium` 0.75, `low` 0.5.

Los findings en estado `fixed`, `accepted` o `false_positive` no penalizan.

Resultado acotado a `[0, 100]`.

## 4. Score de SEO

Compuesto por indicadores normalizados sobre las páginas rastreadas.

| Indicador | Peso interno |
|-----------|--------------|
| Cobertura de title correcto | 15 % |
| Title sin duplicados | 10 % |
| Cobertura de meta description | 10 % |
| Description sin duplicados | 5 % |
| Exactamente un H1 | 15 % |
| Imágenes con `alt` | 10 % |
| Ausencia de enlaces internos roto | 15 % |
| Canonical presente y válido | 10 % |
| `robots.txt` y `sitemap.xml` presentes | 5 % |
| Ausencia de cadenas de redirección | 5 % |

Cada indicador se expresa como razón `páginas conformes / páginas evaluables`.
Si no hay páginas evaluables para un indicador, su peso se redistribuye.

## 5. Score de Performance

Media de los `performance_score` de Lighthouse ponderada 70 % mobile y 30 %
desktop, que es la proporción usada en el criterio de Softree por el tráfico
predominante de los sitios auditados. Si solo hay una estrategia, se usa esa.

## 6. Accessibility y Best Practices

Se toman directamente de Lighthouse con la misma ponderación mobile/desktop. En
el MVP no existe motor propio de accesibilidad; queda documentado como extensión.

## 7. Score global

```
softree_overall = Σ (score_categoría × peso_renormalizado)
```

Redondeado a un decimal. Se persiste con `engine_version` para permitir
comparaciones entre versiones del motor.

## 8. Bandas de interpretación

| Rango | Etiqueta | Color |
|-------|----------|-------|
| 90–100 | Excelente | verde |
| 75–89 | Bueno | verde claro |
| 50–74 | Mejorable | ámbar |
| 25–49 | Deficiente | naranja |
| 0–24 | Crítico | rojo |

## 9. Determinismo y pruebas

`packages/scoring` es una función pura sin IO. Requisitos de prueba:

- Mismos datos de entrada producen el mismo resultado.
- Sin findings y con cobertura SEO completa produce 100.
- Un finding `critical` con confianza `high` deja Security en 75.
- Categoría ausente no produce cero, sino redistribución de peso.
- Los pesos leídos de configuración se respetan y se persisten.
