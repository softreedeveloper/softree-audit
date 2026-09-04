import { expect, test } from '@playwright/test';

import { CREDENTIALS, login } from './fixtures';

/** Comprobaciones de seguridad sobre la aplicación en ejecución. */

test('sin sesión, las páginas muestran el estado no autorizado', async ({ page }) => {
  await page.context().clearCookies();
  await page.goto('/dashboard');
  await expect(page.getByRole('heading', { name: 'Sesión no válida' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Ir a iniciar sesión' })).toBeVisible();
});

test('la API rechaza las peticiones sin token', async ({ request }) => {
  for (const path of ['/api/v1/projects', '/api/v1/scans', '/api/v1/findings', '/api/v1/dashboard']) {
    const response = await request.get(path);
    expect(response.status(), path).toBe(401);
  }
});

test('las credenciales incorrectas no revelan si el usuario existe', async ({ request }) => {
  const unknown = await request.post('/api/v1/auth/login', {
    data: { email: 'nadie@softree.test', password: 'incorrecta-larga' },
  });
  const wrong = await request.post('/api/v1/auth/login', {
    data: { email: CREDENTIALS.email, password: 'incorrecta-larga' },
  });

  expect(unknown.status()).toBe(401);
  expect(wrong.status()).toBe(401);
  expect(await unknown.json()).toEqual(await wrong.json());
});

test('las respuestas llevan cabeceras de seguridad', async ({ request }) => {
  const response = await request.get('/api/v1/health');
  const headers = response.headers();

  expect(headers['x-content-type-options']).toBe('nosniff');
  expect(headers['x-frame-options']).toBe('DENY');
  expect(headers['referrer-policy']).toBe('no-referrer');
  expect(headers['content-security-policy']).toContain("default-src 'none'");
});

test('la cookie de sesión es HttpOnly y de alcance limitado', async ({ request }) => {
  const response = await request.post('/api/v1/auth/login', {
    data: CREDENTIALS,
  });
  expect(response.status()).toBe(200);

  const setCookie = response.headers()['set-cookie'] ?? '';
  expect(setCookie).toContain('softree_refresh');
  expect(setCookie).toContain('HttpOnly');
  expect(setCookie.toLowerCase()).toContain('path=/api/v1/auth');
});

test('el token de refresco no sirve como token de acceso', async ({ request }) => {
  const login = await request.post('/api/v1/auth/login', { data: CREDENTIALS });
  const cookies = login.headers()['set-cookie'] ?? '';
  const refresh = /softree_refresh=([^;]+)/.exec(cookies)?.[1] ?? '';
  expect(refresh).not.toBe('');

  const response = await request.get('/api/v1/auth/me', {
    headers: { Authorization: `Bearer ${refresh}` },
  });
  expect(response.status()).toBe(401);
});

test('un sitio sin autorización no puede auditarse', async ({ request }) => {
  // Se usa la API directamente: pedir un refresco desde la página abierta
  // competiría con la propia sesión del navegador.
  const auth = await request.post('/api/v1/auth/login', { data: CREDENTIALS });
  const token = (await auth.json()).access_token;
  expect(token).toBeTruthy();

  const headers = { Authorization: `Bearer ${token}` };
  const project = await request.post('/api/v1/projects', {
    headers,
    data: { name: `Sin autorizar ${Date.now()}` },
  });
  const site = await request.post('/api/v1/sites', {
    headers,
    data: {
      project_id: (await project.json()).id,
      name: 'Sin autorización',
      base_url: 'https://example.com',
      is_active: true,
    },
  });

  const scan = await request.post('/api/v1/scans', {
    headers,
    data: { site_id: (await site.json()).id },
  });

  expect(scan.status()).toBe(409);
  expect((await scan.json()).error.code).toBe('site_not_authorized');
});

test('la documentación interactiva usa una CSP propia', async ({ request }) => {
  const response = await request.get('/api/v1/docs');
  const csp = response.headers()['content-security-policy'] ?? '';
  expect(csp).toContain("frame-ancestors 'none'");
  expect(csp).toContain("base-uri 'none'");
});

test('la configuración muestra el estado de las integraciones, no sus credenciales', async ({
  page,
}) => {
  await login(page);
  await page.goto('/settings');

  await expect(page.getByRole('heading', { name: 'Integraciones' })).toBeVisible();

  // De cada integración solo se publica el nombre de sus variables y si están
  // definidas. El valor nunca sale del servidor: lo comprueba
  // tests/integration/test_settings.py.
  const body = await page.locator('main').innerText();
  expect(body).toContain('PAGESPEED_API_KEY');
  expect(body).toContain('GOOGLE_CLIENT_SECRET');
  expect(body).toMatch(/Configurada|Sin configurar/);
});
