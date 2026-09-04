/** Estados de pantalla obligatorios (§38): Loading, Empty, Error, Success,
 *  Partial, Unauthorized y Not connected. Ninguna vista debe quedar en blanco.
 */

import type { ReactNode } from 'react';

interface StateShellProps {
  icon: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  tone?: 'neutral' | 'danger' | 'warning' | 'success';
}

const toneRing: Record<NonNullable<StateShellProps['tone']>, string> = {
  neutral: 'text-brand-600',
  danger: 'text-red-600',
  warning: 'text-amber-600',
  success: 'text-brand-600',
};

function StateShell({ icon, title, description, action, tone = 'neutral' }: StateShellProps) {
  return (
    <div className="sf-card flex flex-col items-center gap-3 px-6 py-12 text-center">
      <div className={`text-2xl ${toneRing[tone]}`} aria-hidden="true">
        {icon}
      </div>
      <h2 className="text-base font-semibold">{title}</h2>
      {description ? <p className="sf-muted max-w-md text-sm">{description}</p> : null}
      {action}
    </div>
  );
}

export function LoadingState({ label = 'Cargando…' }: { label?: string }) {
  return (
    <div
      className="sf-card flex items-center justify-center gap-3 px-6 py-12"
      role="status"
      aria-live="polite"
    >
      <span
        className="size-4 animate-spin rounded-full border-2 border-brand-500 border-t-transparent"
        aria-hidden="true"
      />
      <span className="sf-muted text-sm">{label}</span>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return <StateShell icon="◍" title={title} description={description} action={action} />;
}

export function ErrorState({
  title = 'No fue posible cargar la información',
  description,
  onRetry,
}: {
  title?: string;
  description?: ReactNode;
  onRetry?: () => void;
}) {
  return (
    <StateShell
      icon="⚠"
      tone="danger"
      title={title}
      description={description}
      action={
        onRetry ? (
          <button type="button" className="sf-btn sf-btn-ghost" onClick={onRetry}>
            Reintentar
          </button>
        ) : undefined
      }
    />
  );
}

export function UnauthorizedState() {
  return (
    <StateShell
      icon="⛔"
      tone="warning"
      title="Sesión no válida"
      description="Inicie sesión para continuar."
      action={
        <a className="sf-btn sf-btn-primary" href="/login">
          Ir a iniciar sesión
        </a>
      }
    />
  );
}

export function NotConnectedState({
  service,
  href,
}: {
  service: string;
  href?: string;
}) {
  return (
    <StateShell
      icon="🔌"
      tone="warning"
      title={`${service}: no conectado`}
      description={`La auditoría se ejecuta normalmente sin ${service}. Conéctelo para incorporar sus datos.`}
      action={
        href ? (
          <a className="sf-btn sf-btn-ghost" href={href}>
            Configurar integración
          </a>
        ) : undefined
      }
    />
  );
}

export function PartialState({ description }: { description: ReactNode }) {
  return (
    <div
      className="sf-card flex items-start gap-3 px-4 py-3 text-sm"
      role="status"
      aria-live="polite"
    >
      <span className="text-amber-600" aria-hidden="true">
        ◐
      </span>
      <div>
        <p className="font-medium">Resultado parcial</p>
        <p className="sf-muted">{description}</p>
      </div>
    </div>
  );
}

export function SuccessBanner({ children }: { children: ReactNode }) {
  return (
    <div className="sf-card border-brand-300 px-4 py-3 text-sm" role="status" aria-live="polite">
      <span className="text-brand-600" aria-hidden="true">
        ✓
      </span>{' '}
      {children}
    </div>
  );
}
