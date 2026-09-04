"""Versiones del producto, del motor de scan y del formato de reporte.

Se persisten en cada scan y reporte para poder comparar resultados producidos
por versiones distintas del motor (requisito §57).
"""

APP_VERSION = "0.1.0"
SCAN_ENGINE_VERSION = "0.1.0"
REPORT_VERSION = "v1"

__all__ = ["APP_VERSION", "REPORT_VERSION", "SCAN_ENGINE_VERSION"]
