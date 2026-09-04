# Pruebas end to end

Se implementan en el **Slice 11** con Playwright, sobre la aplicación levantada
en Docker y el `test-target` como sitio auditado.

Flujo cubierto (§43):

```
Login → Create project → Create site → Configure scope → Run audit
      → View results → View findings → Generate report
```

Requisitos previos:

```bash
make up
docker compose --profile testing --profile scanner up -d
make test-e2e
```

No se usan sitios de terceros como dependencia de las pruebas (§44).
