# Pruebas

| Directorio | Nivel | Dependencias |
|-----------|-------|--------------|
| `unit/` | Sin IO, sin base de datos, sin red | ninguna |
| `integration/` | API, base de datos y Redis reales | PostgreSQL, Redis |
| `e2e/` | Navegador contra la aplicación en Docker | Slice 11 |

Las pruebas de integración se omiten si `TEST_DATABASE_URL` no está definida.
Detalle en `docs/development/testing.md`.

```bash
make test            # unit + integration
make test-unit
make test-integration
```
