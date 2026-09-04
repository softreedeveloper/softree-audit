/** Conmutador de tema. La preferencia se guarda por navegador. */

export type Theme = 'light' | 'dark' | 'system';

const STORAGE_KEY = 'softree-audit-theme';

export function readTheme(): Theme {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'light' || stored === 'dark' || stored === 'system') {
      return stored;
    }
  } catch {
    // Almacenamiento no disponible: se usa la preferencia del sistema.
  }
  return 'system';
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  if (theme === 'system') {
    root.removeAttribute('data-theme');
  } else {
    root.setAttribute('data-theme', theme);
  }
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Sin almacenamiento la preferencia solo dura la sesión actual.
  }
}
