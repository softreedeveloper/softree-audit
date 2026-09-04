import { defineConfig, devices } from '@playwright/test';

/**
 * Pruebas end to end contra la aplicación levantada en Docker.
 *
 * Requisitos previos (docs/development/testing.md):
 *   make up
 *   docker compose --profile testing --profile scanner up -d
 *   SSRF_ALLOW_PRIVATE_NETWORKS=true en .env, para poder auditar el test-target
 */
export default defineConfig({
  testDir: './specs',
  // Las auditorías reales tardan; el flujo completo necesita margen.
  timeout: 180_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  // Un solo worker: las pruebas comparten el estado del backend.
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:4321',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    // Nunca hay diálogos modales en la interfaz: la confirmación es en línea.
    actionTimeout: 15_000,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
