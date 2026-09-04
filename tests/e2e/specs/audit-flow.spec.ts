import { expect, test } from '@playwright/test';

import { TEST_TARGET_URL, login, uniqueName, waitForScan } from './fixtures';

/**
 * Flujo completo de la especificación (§43):
 *
 *   Login → Create project → Create site → Configure scope → Run audit
 *        → View results → View findings → Generate report
 */
test.describe.configure({ mode: 'serial' });

const projectName = uniqueName('E2E');
let siteUrl = '';
let scanUrl = '';

test('inicia sesión y llega al dashboard', async ({ page }) => {
  await login(page);
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
  await expect(page.getByText('SOFTREE SCORE MEDIO')).toBeVisible();
});

test('crea un proyecto', async ({ page }) => {
  await login(page);
  await page.goto('/projects');

  await page.locator('#project-name').fill(projectName);
  await page.locator('#project-client').fill('Cliente E2E');
  await page.getByRole('button', { name: 'Crear proyecto' }).click();

  await expect(page.getByRole('link', { name: projectName })).toBeVisible();
});

test('registra un sitio con su autorización', async ({ page }) => {
  await login(page);
  await page.goto('/projects');
  await page.getByRole('link', { name: projectName }).click();

  await page.locator('#site-name').fill('Test target E2E');
  await page.locator('#site-url').fill(TEST_TARGET_URL);
  await page.locator('#site-authorized-by').fill('Softree (sitio propio de pruebas)');
  await page.locator('#site-authorization-date').fill('2026-09-01');
  await page.getByRole('button', { name: 'Añadir sitio' }).click();

  const site = page.getByRole('link', { name: 'Test target E2E' });
  await expect(site).toBeVisible();
  // Sin autorización no podría auditarse.
  await expect(page.getByText('Autorizado').first()).toBeVisible();

  await site.click();
  await page.waitForURL('**/sites?id=*');
  siteUrl = page.url();
});

test('configura el scope', async ({ page }) => {
  await login(page);
  await page.goto(siteUrl);

  await page.locator('#scope-max_pages').fill('25');
  await page.locator('#scope-request_delay_ms').fill('50');
  await page.locator('#scope-excluded').fill('/privado');
  await page.getByRole('button', { name: 'Guardar scope' }).click();

  await expect(page.getByText('Scope actualizado.')).toBeVisible();
});

test('rechaza un scope que no cubre el sitio', async ({ page }) => {
  await login(page);
  await page.goto(siteUrl);

  await page.locator('#scope-domains').fill('otro-dominio.test');
  await page.getByRole('button', { name: 'Guardar scope' }).click();

  await expect(
    page.getByText(/debe estar entre los dominios permitidos/),
  ).toBeVisible();
});

test('ejecuta la auditoría y muestra su progreso', async ({ page }) => {
  await login(page);
  await page.goto(siteUrl);

  // Se restaura el scope válido antes de auditar.
  await page.locator('#scope-domains').fill('test-target');
  await page.getByRole('button', { name: 'Guardar scope' }).click();
  await expect(page.getByText('Scope actualizado.')).toBeVisible();

  await page.getByRole('button', { name: 'Ejecutar auditoría' }).click();
  await page.waitForURL('**/audits?id=*', { timeout: 30_000 });
  scanUrl = page.url();

  await expect(page.getByRole('heading', { name: 'Progreso' })).toBeVisible();
  const status = await waitForScan(page);
  expect(['Completada', 'Parcial']).toContain(status);
});

test('muestra los resultados de la auditoría', async ({ page }) => {
  await login(page);
  await page.goto(scanUrl);
  await waitForScan(page);

  // Puntuación y desglose. El rótulo va en mayúsculas por CSS, así que se
  // busca el texto tal como está en el DOM.
  await expect(page.getByText('Softree Score').first()).toBeVisible();
  await expect(
    page.getByText(/no constituye una calificación oficial de Google/),
  ).toBeVisible();

  // Páginas rastreadas.
  await page.getByRole('button', { name: 'páginas', exact: true }).click();
  await expect(page.getByRole('columnheader', { name: 'URL' })).toBeVisible();

  // Resumen SEO.
  await page.getByRole('button', { name: 'seo', exact: true }).click();
  await expect(page.getByText('Indicadores SEO')).toBeVisible();
});

test('lista los hallazgos y permite cambiar su estado', async ({ page }) => {
  await login(page);
  await page.goto(scanUrl);
  await waitForScan(page);

  await page.getByRole('button', { name: 'hallazgos', exact: true }).click();

  const first = page.locator('main ul.divide-y > li').first();
  await expect(first).toBeVisible();

  // El detalle expandido incluye los dos niveles de lectura.
  await first.getByRole('button').first().click();
  await expect(page.getByText('Explicación para el cliente')).toBeVisible();

  // Marcar como falso positivo lo retira de los abiertos.
  const select = first.getByRole('combobox');
  await select.selectOption('false_positive');
  await expect(page.locator('main ul.divide-y > li').first()).not.toContainText(
    await first.innerText().catch(() => 'no-coincide'),
  );
});

test('genera y descarga el reporte', async ({ page }) => {
  await login(page);
  await page.goto(scanUrl);
  await waitForScan(page);

  await page.getByRole('button', { name: 'reporte', exact: true }).click();
  await page.getByRole('button', { name: /Generar reporte|Regenerar/ }).click();

  await expect(page.getByText('PDF', { exact: true })).toBeVisible({ timeout: 60_000 });

  const download = page.waitForEvent('download');
  await page.getByRole('listitem').filter({ hasText: 'PDF' }).getByRole('button', {
    name: 'Descargar',
  }).click();

  const file = await download;
  expect(file.suggestedFilename()).toMatch(/\.pdf$/);
});

test('genera la versión ejecutiva del PDF', async ({ page }) => {
  await login(page);
  await page.goto(scanUrl);

  await page.getByRole('button', { name: 'reporte', exact: true }).click();
  await page.getByRole('radio', { name: 'Ejecutivo' }).check();
  await page.getByRole('button', { name: /Generar reporte|Regenerar/ }).click();

  const section = page.locator('section, div').filter({ hasText: 'Ejecutivo' }).last();
  await expect(section).toBeVisible({ timeout: 60_000 });

  const download = page.waitForEvent('download');
  await page
    .getByRole('listitem')
    .filter({ hasText: 'PDF' })
    .last()
    .getByRole('button', { name: 'Descargar' })
    .click();

  const file = await download;
  expect(file.suggestedFilename()).toMatch(/-executive\.pdf$/);
});

test('compara con la auditoría anterior', async ({ page }) => {
  await login(page);
  await page.goto(siteUrl);

  // Segunda auditoría del mismo sitio.
  await page.getByRole('button', { name: 'Ejecutar auditoría' }).click();
  await page.waitForURL('**/audits?id=*', { timeout: 30_000 });
  await waitForScan(page);

  await page.getByRole('button', { name: 'comparacion', exact: true }).click();
  await expect(
    page.getByText('Cambios respecto a la auditoría anterior'),
  ).toBeVisible();
  // `exact` evita chocar con el estado vacío «Sin cambios en los hallazgos».
  await expect(page.getByText('Sin cambios', { exact: true })).toBeVisible();
});

test('el histórico del sitio lista ambas auditorías', async ({ page }) => {
  await login(page);
  await page.goto(siteUrl);

  await expect(page.getByText('Histórico de auditorías')).toBeVisible();
  const rows = page.locator('main table tbody tr');
  expect(await rows.count()).toBeGreaterThanOrEqual(2);
});
