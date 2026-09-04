import { useEffect, useState } from 'react';

import { applyTheme, readTheme, type Theme } from '../../lib/theme';

const OPTIONS: { value: Theme; label: string; icon: string }[] = [
  { value: 'light', label: 'Claro', icon: '☀' },
  { value: 'dark', label: 'Oscuro', icon: '☾' },
  { value: 'system', label: 'Sistema', icon: '◑' },
];

export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>('system');

  useEffect(() => {
    setTheme(readTheme());
  }, []);

  function select(next: Theme) {
    setTheme(next);
    applyTheme(next);
  }

  return (
    <div
      className="inline-flex rounded-lg border p-0.5"
      style={{ borderColor: 'var(--border)' }}
      role="group"
      aria-label="Tema de la interfaz"
    >
      {OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => select(option.value)}
          aria-pressed={theme === option.value}
          title={option.label}
          className="rounded-md px-2 py-1 text-xs"
          style={
            theme === option.value
              ? { backgroundColor: 'var(--surface-muted)', color: 'var(--text)' }
              : { color: 'var(--text-muted)' }
          }
        >
          <span aria-hidden="true">{option.icon}</span>
          <span className="sr-only">{option.label}</span>
        </button>
      ))}
    </div>
  );
}
