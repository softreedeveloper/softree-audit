/** Contenedor de la aplicación autenticada: barra lateral, encabezado y
 *  control de sesión. Muestra Loading y Unauthorized sin dejar la vista vacía.
 *
 *  En pantallas estrechas la barra lateral se convierte en un cajón que se
 *  abre desde el encabezado: sin él la navegación quedaba inalcanzable en
 *  móvil, que es donde más se consulta el estado de una auditoría en curso.
 */

import { useEffect, useState, type ReactNode } from 'react';

import { request } from '../../lib/api';
import {
  bootstrapSession,
  getSession,
  signOut,
  subscribe,
  type SessionState,
} from '../../lib/session';
import type { HealthResponse } from '../../lib/types';
import { LoadingState, UnauthorizedState } from './UiStates';
import ThemeToggle from './ThemeToggle';

interface NavItem {
  label: string;
  href: string;
  icon: ReactNode;
}

interface NavGroup {
  title: string;
  items: NavItem[];
}

/* Iconos en línea: son cuatro trazos y evitan cargar una tipografía de iconos
   solo para la barra lateral. */
const icon = (path: ReactNode) => (
  <svg
    viewBox="0 0 16 16"
    className="size-4 shrink-0"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.4"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    {path}
  </svg>
);

const NAV: NavGroup[] = [
  {
    title: 'Monitorizar',
    items: [
      {
        label: 'Resumen',
        href: '/dashboard',
        icon: icon(
          <>
            <rect x="2" y="2" width="5" height="5" rx="1" />
            <rect x="9" y="2" width="5" height="5" rx="1" />
            <rect x="2" y="9" width="5" height="5" rx="1" />
            <rect x="9" y="9" width="5" height="5" rx="1" />
          </>,
        ),
      },
      {
        label: 'Proyectos',
        href: '/projects',
        icon: icon(
          <>
            <path d="M2 4.5A1.5 1.5 0 0 1 3.5 3h2.2l1.2 1.5h5.6A1.5 1.5 0 0 1 14 6v6a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 12z" />
          </>,
        ),
      },
      {
        label: 'Auditorías',
        href: '/audits',
        icon: icon(
          <>
            <circle cx="7" cy="7" r="4.5" />
            <path d="m10.5 10.5 3 3" />
          </>,
        ),
      },
      {
        label: 'Hallazgos',
        href: '/findings',
        icon: icon(
          <>
            <path d="M8 2.5 14 13H2z" />
            <path d="M8 6.5v3" />
            <path d="M8 11.2v.1" />
          </>,
        ),
      },
    ],
  },
  {
    title: 'Entregar',
    items: [
      {
        label: 'Reportes',
        href: '/reports',
        icon: icon(
          <>
            <path d="M4 2h5l3 3v9H4z" />
            <path d="M9 2v3h3" />
            <path d="M6 8.5h4M6 11h3" />
          </>,
        ),
      },
      {
        label: 'Integraciones',
        href: '/integrations',
        icon: icon(
          <>
            <rect x="2" y="2" width="5.5" height="5.5" rx="1.2" />
            <rect x="8.5" y="8.5" width="5.5" height="5.5" rx="1.2" />
            <path d="M7.5 4.8h3a2 2 0 0 1 2 2v1.7" />
          </>,
        ),
      },
      {
        label: 'Configuración',
        href: '/settings',
        icon: icon(
          <>
            <circle cx="8" cy="8" r="2" />
            <path d="M8 1.5v1.7M8 12.8v1.7M14.5 8h-1.7M3.2 8H1.5M12.6 3.4l-1.2 1.2M4.6 11.4l-1.2 1.2M12.6 12.6l-1.2-1.2M4.6 4.6 3.4 3.4" />
          </>,
        ),
      },
    ],
  },
];

/** Marca de la aplicación. Se repite en la barra lateral y en el cajón. */
function Brand() {
  return (
    <a href="/dashboard" className="flex min-w-0 items-center gap-3 px-2">
      <span
        className="grid size-9 shrink-0 place-items-center rounded-xl text-base font-bold"
        style={{ backgroundColor: 'var(--accent)', color: 'var(--accent-contrast)' }}
        aria-hidden="true"
      >
        S
      </span>
      <span className="min-w-0 leading-tight">
        <span className="block text-sm font-semibold tracking-[0.18em]">SOFTREE</span>
        <span className="sf-label block">Audit platform</span>
      </span>
    </a>
  );
}

function NavLinks({ current, onNavigate }: { current: string; onNavigate?: () => void }) {
  return (
    <>
      {NAV.map((group) => (
        <div key={group.title} className="flex flex-col gap-1">
          <p className="sf-label px-3 pb-1">{group.title}</p>
          {group.items.map((item) => (
            <a
              key={item.href}
              href={item.href}
              aria-current={item.href === current ? 'page' : undefined}
              className="sf-nav-item"
              onClick={onNavigate}
            >
              {item.icon}
              <span className="min-w-0 flex-1 truncate">{item.label}</span>
            </a>
          ))}
        </div>
      ))}
    </>
  );
}

interface AppShellProps {
  title: string;
  subtitle?: string;
  current: string;
  children?: ReactNode;
}

export default function AppShell({ title, subtitle, current, children }: AppShellProps) {
  const [session, setSession] = useState<SessionState>(getSession());
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const unsubscribe = subscribe(setSession);
    void bootstrapSession();
    return unsubscribe;
  }, []);

  useEffect(() => {
    if (session.status !== 'authenticated') return;
    // El estado del servicio se consulta una vez por carga: es un indicador,
    // no un monitor en tiempo real.
    request<HealthResponse>('/health')
      .then(setHealth)
      .catch(() => setHealth(null));
  }, [session.status]);

  // Con el cajón abierto se bloquea el desplazamiento del fondo y se cierra con
  // Escape: es un diálogo, y comportarse como tal evita que quede atrapado.
  useEffect(() => {
    if (!menuOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMenuOpen(false);
    };
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [menuOpen]);

  const operational = health?.status === 'ok';
  const initials = (session.user?.full_name ?? session.user?.email ?? 'S')
    .split(/[\s@.]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('');

  const userChip = session.user ? (
    <div
      className="flex items-center gap-2 rounded-xl border px-3 py-2.5 text-sm"
      style={{ borderColor: 'var(--border)' }}
    >
      <span className="sf-dot shrink-0" aria-hidden="true" />
      <span className="min-w-0 flex-1 truncate">{session.user.full_name}</span>
    </div>
  ) : null;

  return (
    <div className="flex min-h-screen">
      <aside
        className="hidden w-64 shrink-0 flex-col border-r px-3 py-5 md:flex"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--surface-sidebar)' }}
      >
        <div className="mb-6">
          <Brand />
        </div>

        {userChip ? <div className="mb-6">{userChip}</div> : null}

        <nav className="flex flex-1 flex-col gap-6" aria-label="Navegación principal">
          <NavLinks current={current} />
        </nav>

        <div className="mt-6 border-t pt-4" style={{ borderColor: 'var(--border)' }}>
          <ThemeToggle />
        </div>
      </aside>

      {/* Cajón de navegación en pantallas estrechas. */}
      {menuOpen ? (
        <div className="fixed inset-0 z-50 md:hidden" role="dialog" aria-modal="true" aria-label="Navegación principal">
          <button
            type="button"
            className="absolute inset-0 h-full w-full bg-black/50"
            aria-label="Cerrar navegación"
            onClick={() => setMenuOpen(false)}
          />
          <div
            className="absolute inset-y-0 left-0 flex w-[min(19rem,85vw)] flex-col overflow-y-auto border-r px-3 py-5"
            style={{ borderColor: 'var(--border)', backgroundColor: 'var(--surface-sidebar)' }}
          >
            <div className="mb-6 flex items-start justify-between gap-2">
              <Brand />
              <button
                type="button"
                className="sf-icon-btn"
                aria-label="Cerrar navegación"
                onClick={() => setMenuOpen(false)}
              >
                <svg viewBox="0 0 16 16" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
                  <path d="m4 4 8 8M12 4l-8 8" />
                </svg>
              </button>
            </div>

            {userChip ? <div className="mb-6">{userChip}</div> : null}

            <nav className="flex flex-1 flex-col gap-6" aria-label="Navegación principal">
              <NavLinks current={current} onNavigate={() => setMenuOpen(false)} />
            </nav>

            <div className="mt-6 border-t pt-4" style={{ borderColor: 'var(--border)' }}>
              <ThemeToggle />
            </div>
          </div>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col" style={{ backgroundColor: 'var(--surface)' }}>
        <header
          className="flex items-center justify-between gap-2 border-b px-3 py-3 sm:px-4 sm:gap-3 md:px-8 md:py-3.5"
          style={{ borderColor: 'var(--border)' }}
        >
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <button
              type="button"
              className="sf-icon-btn md:hidden"
              aria-label="Abrir navegación"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen(true)}
            >
              <svg viewBox="0 0 16 16" className="size-4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
                <path d="M2.5 4h11M2.5 8h11M2.5 12h11" />
              </svg>
            </button>

            <nav className="flex min-w-0 items-center gap-2 text-sm" aria-label="Migas de pan">
              <span className="hidden sm:inline" style={{ color: 'var(--text-faint)' }}>
                Workspace
              </span>
              <span className="hidden sm:inline" style={{ color: 'var(--text-faint)' }} aria-hidden="true">
                /
              </span>
              <span className="truncate font-medium">{title}</span>
            </nav>
          </div>

          <div className="flex shrink-0 items-center gap-2 sm:gap-3">
            {health ? (
              <span className="hidden items-center gap-2 text-xs lg:flex">
                <span
                  className="sf-dot"
                  style={operational ? undefined : { backgroundColor: 'var(--tone-danger)' }}
                  aria-hidden="true"
                />
                <span className="sf-muted">
                  {operational ? 'Todos los servicios operativos' : 'Servicio degradado'}
                </span>
              </span>
            ) : null}

            {session.status === 'authenticated' ? (
              <>
                <button
                  type="button"
                  className="sf-btn sf-btn-ghost !px-3"
                  title="Cerrar sesión"
                  onClick={() => {
                    void signOut().then(() => window.location.assign('/login'));
                  }}
                >
                  Salir
                </button>
                <span
                  className="grid size-8 shrink-0 place-items-center rounded-full text-xs font-semibold"
                  style={{ backgroundColor: 'var(--accent)', color: 'var(--accent-contrast)' }}
                  title={session.user?.email}
                >
                  {initials}
                </span>
              </>
            ) : null}
          </div>
        </header>

        <main className="min-w-0 flex-1 px-4 py-6 md:px-8 md:py-8">
          <div className="mx-auto flex w-full min-w-0 max-w-6xl flex-col gap-5">
            {subtitle && session.status === 'authenticated' ? (
              <p className="sf-muted -mb-1 text-sm">{subtitle}</p>
            ) : null}
            {session.status === 'loading' ? <LoadingState label="Restaurando sesión…" /> : null}
            {session.status === 'anonymous' ? <UnauthorizedState /> : null}
            {session.status === 'authenticated' ? children : null}
          </div>
        </main>

        <footer className="sf-muted px-4 py-6 text-xs md:px-8">
          SOFTREE AUDIT · Uso interno. Auditar únicamente sitios propios, entregados por Softree o
          con autorización explícita del cliente.
        </footer>
      </div>
    </div>
  );
}
