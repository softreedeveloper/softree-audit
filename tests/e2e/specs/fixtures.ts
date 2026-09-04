import { expect, type Page } from '@playwright/test';

/**
 * Credenciales del usuario con el que corren las pruebas.
 *
 * No se versiona ningún valor por defecto: una contraseña real en el
 * repositorio es una credencial filtrada, aunque sea de un entorno local.
 */
function required(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(
      `Falta la variable ${name}. Exporte E2E_EMAIL y E2E_PASSWORD con las ` +
        'credenciales del usuario creado con `make user`.',
    );
  }
  return value;
}

export const CREDENTIALS = {
  email: required('E2E_EMAIL'),
  password: required('E2E_PASSWORD'),
};

/** URL del sitio de pruebas, tal como la ve el backend dentro de Docker. */
export const TEST_TARGET_URL = process.env.E2E_TARGET ?? 'http://test-target';

export async function login(page: Page): Promise<void> {
  await page.goto('/login');
  // Si ya hay sesión, el formulario redirige solo al dashboard.
  const emailField = page.locator('#email');
  if (await emailField.isVisible({ timeout: 5_000 }).catch(() => false)) {
    await emailField.fill(CREDENTIALS.email);
    await page.locator('#password').fill(CREDENTIALS.password);
    await page.getByRole('button', { name: 'Iniciar sesión' }).click();
  }
  await page.waitForURL('**/dashboard', { timeout: 20_000 });
}

export function uniqueName(prefix: string): string {
  return `${prefix} ${Date.now().toString(36)}`;
}

/** Espera a que la auditoría alcance un estado terminal. */
export async function waitForScan(page: Page): Promise<string> {
  const badge = page.locator('main').getByText(
    /Completada|Parcial|Fallida|Cancelada/,
  ).first();
  await expect(badge).toBeVisible({ timeout: 150_000 });
  return (await badge.innerText()).trim();
}
