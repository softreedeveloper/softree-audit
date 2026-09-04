# Estrategia de pruebas

Una funcionalidad no está terminada porque el código funcione, sino cuando cumple
su especificación y sus criterios de aceptación.

## Niveles

### Unit

Sin IO, sin base de datos, sin red. Cubren:

- validación y normalización de URL,
- protección contra SSRF (casos adversarios),
- validación de scope,
- parsing del crawler,
- reglas SEO,
- normalización de findings,
- deduplicación y fingerprint,
- scoring.

### Integration

Con Postgres y Redis reales sobre Docker. Cubren:

- migraciones y modelos,
- endpoints de la API,
- orquestación de scans,
- adapter de ZAP, de PageSpeed y de Search Console **contra mocks de transporte**,
  nunca contra los servicios reales.

Se ejecutan solo si `TEST_DATABASE_URL` está definida; en caso contrario se
omiten con un motivo explícito, sin fingir éxito.

### E2E

Playwright contra la aplicación en Docker, en `tests/e2e/`. Dos suites:

- **`audit-flow.spec.ts`**: el flujo completo de la especificación §43.

  ```
  Login → Create project → Create site → Configure scope → Run audit
        → View results → View findings → Generate report → Compare
  ```

- **`security.spec.ts`**: comprobaciones sobre la aplicación en ejecución.
  Acceso sin sesión, rechazo de peticiones sin token, indistinguibilidad de
  credenciales, cabeceras de seguridad, alcance de la cookie de sesión, el
  refresh token que no sirve como token de acceso y el bloqueo de auditar un
  sitio sin autorización.

El target del E2E es el `test-target` local. No se usan sitios de terceros como
dependencia de pruebas.

Requisitos:

```bash
make up
make e2e-up          # añade el test-target y OWASP ZAP
# En .env: SSRF_ALLOW_PRIVATE_NETWORKS=true, para poder auditar el test-target
make test-e2e E2E_EMAIL=usuario@softree.mx E2E_PASSWORD='...'
```

Las credenciales se pasan por variable de entorno y nunca se versionan: una
contraseña en el repositorio es una credencial filtrada aunque sea de un
entorno local.

Las pruebas corren con un solo worker y en serie: comparten el estado del
backend, y el flujo depende del orden.

## Reglas

1. Los mocks solo existen en pruebas. En producción las integraciones son reales.
2. No se elimina ni se marca como omitida una prueba para que el build pase.
3. Toda corrección de bug incorpora una prueba que falla antes del arreglo.
4. Las pruebas de seguridad del guard de URL son obligatorias en cada cambio del
   módulo.

## Ejecución

```bash
make test           # unit + integration
make test-unit
make test-integration
make test-e2e       # requiere make up y el perfil testing
```

## Marcadores de pytest

| Marcador | Significado |
|----------|-------------|
| `unit` | Sin dependencias externas |
| `integration` | Requiere Postgres y Redis |
| `security` | Casos adversarios de SSRF y autorización |
| `slow` | Excluido del ciclo rápido |
