// @ts-check
import react from '@astrojs/react';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'astro/config';

// El frontend y la API se sirven en el mismo origen (ADR-008, D-005).
// En desarrollo eso se consigue con este proxy; en producción, con el reverse
// proxy descrito en docs/development/deployment.md.
const apiTarget = process.env.API_PROXY_TARGET ?? 'http://localhost:8000';

export default defineConfig({
  integrations: [react()],
  output: 'static',
  // La raíz lleva al dashboard; si no hay sesión, el propio shell muestra el
  // estado Unauthorized con el enlace a /login.
  redirects: { '/': '/dashboard' },
  server: { port: 4321, host: true },
  vite: {
    plugins: [tailwindcss()],
    server: {
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: false,
          secure: false,
        },
      },
    },
  },
});
