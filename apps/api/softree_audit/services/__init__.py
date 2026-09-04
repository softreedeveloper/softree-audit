"""Servicios del pipeline de auditoría.

Cada subpaquete implementa el protocolo `ScanModule` descrito en
`docs/spec/architecture.md` §3. Ninguno escribe en base de datos: devuelven
datos y el orquestador persiste.
"""
