/** Contenedor de la aplicación autenticada: barra lateral, encabezado y
 *  control de sesión. Muestra Loading y Unauthorized sin dejar la vista vacía.
 */

import { useEffect, useState, type ReactNode } from 'react';

import { getSession, bootstrapSession, signOut, subscribe, type SessionState } from '../../lib/session';
import { LoadingState, UnauthorizedState } from './UiStates';
import ThemeToggle from './ThemeToggle';

interface NavItem {
  label: string;
  href: string;
  icon: string;
}

const NAV: NavItem[] = [
  { label: 'Dashboard', href: '/dashboard', icon: '▤' },
  { label: 'Projects', href: '/projects', icon: '▣' },
  { label: 'Audits', href: '/audits', icon: '◎' },
  { label: 'Findings', href: '/findings', icon: '⚑' },
  { label: 'Reports', href: '/reports', icon: '▦' },
  { label: 'Integrations', href: '/integrations', icon: '⧉' },
  { label: 'Settings', href: '/settings', icon: '⚙' },
];

interface AppShellProps {
  title: string;
  subtitle?: string;
  current: string;
  children?: ReactNode;
}

export default function AppShell({ title, subtitle, current, children }: AppShellProps) {
  const [session, setSession] = useState<SessionState>(getSession());

  useEffect(() => {
    const unsubscribe = subscribe(setSession);
    void bootstrapSession();
    return unsubscribe;
  }, []);

  return (
    <div className="flex min-h-screen">
      <aside
        className="hidden w-60 shrink-0 flex-col border-r px-3 py-4 md:flex"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--surface-raised)' }}
      >
        <a href="/dashboard" className="mb-6 flex items-center gap-2 px-2">
          <img src="/brand/softree-isotipo.png" alt="" className="size-8" aria-hidden="true" />
          <span className="text-sm leading-tight font-semibold">
            SOFTREE
            <span className="sf-muted block text-[11px] font-normal tracking-wide">AUDIT</span>
          </span>
        </a>

        <nav className="flex flex-1 flex-col gap-0.5" aria-label="Navegación principal">
          {NAV.map((item) => {
            const active = item.href === current;
            return (
              <a
                key={item.href}
                href={item.href}
                aria-current={active ? 'page' : undefined}
                className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm"
                style={
                  active
                    ? { backgroundColor: 'var(--surface-muted)', color: 'var(--text)' }
                    : { color: 'var(--text-muted)' }
                }
              >
                <span aria-hidden="true" className="w-4 text-center">
                  {item.icon}
                </span>
                {item.label}
              </a>
            );
          })}
        </nav>

        <div className="mt-4 border-t pt-3" style={{ borderColor: 'var(--border)' }}>
          <ThemeToggle />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header
          className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3 md:px-6"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--surface-raised)' }}
        >
          <div className="min-w-0">
            <h1 className="truncate text-lg font-semibold">{title}</h1>
            {subtitle ? <p className="sf-muted truncate text-sm">{subtitle}</p> : null}
          </div>

          <div className="flex items-center gap-3">
            {session.user ? (
              <span className="sf-muted hidden text-sm sm:inline">{session.user.email}</span>
            ) : null}
            {session.status === 'authenticated' ? (
              <button
                type="button"
                className="sf-btn sf-btn-ghost"
                onClick={() => {
                  void signOut().then(() => window.location.assign('/login'));
                }}
              >
                Cerrar sesión
              </button>
            ) : null}
          </div>
        </header>

        <main className="flex-1 px-4 py-6 md:px-6">
          <div className="mx-auto flex max-w-6xl flex-col gap-4">
            {session.status === 'loading' ? <LoadingState label="Restaurando sesión…" /> : null}
            {session.status === 'anonymous' ? <UnauthorizedState /> : null}
            {session.status === 'authenticated' ? children : null}
          </div>
        </main>

        <footer className="sf-muted px-4 py-4 text-xs md:px-6">
          SOFTREE AUDIT · Uso interno. Auditar únicamente sitios propios, entregados por Softree o
          con autorización explícita del cliente.
        </footer>
      </div>
    </div>
  );
}
