/** Primitivas de interfaz compartidas. */

import type { ReactNode } from 'react';

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`sf-card px-4 py-4 ${className}`}>{children}</section>;
}

export function Field({
  label,
  hint,
  error,
  htmlFor,
  children,
}: {
  label: string;
  hint?: ReactNode;
  error?: string | null;
  htmlFor: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-sm font-medium" htmlFor={htmlFor}>
        {label}
      </label>
      {children}
      {hint ? <p className="sf-muted text-xs">{hint}</p> : null}
      {error ? (
        <p className="text-xs text-red-600" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function Badge({
  tone,
  children,
}: {
  tone: 'ok' | 'warn' | 'muted';
  children: ReactNode;
}) {
  const styles: Record<typeof tone, string> = {
    ok: 'text-brand-700 border-brand-300',
    warn: 'text-amber-700 border-amber-300',
    muted: '',
  };
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs ${styles[tone]}`}
      style={tone === 'muted' ? { borderColor: 'var(--border)', color: 'var(--text-muted)' } : {}}
    >
      {children}
    </span>
  );
}

/** Confirmación en línea.
 *
 * No se usa `window.confirm`: bloquea el hilo del navegador y rompe cualquier
 * automatización posterior (pruebas E2E del Slice 11).
 */
export function ConfirmInline({
  message,
  confirmLabel = 'Eliminar',
  busy = false,
  onConfirm,
  onCancel,
}: {
  message: ReactNode;
  confirmLabel?: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm" role="alertdialog" aria-live="polite">
      <span>{message}</span>
      <button type="button" className="sf-btn sf-btn-primary" disabled={busy} onClick={onConfirm}>
        {busy ? 'Eliminando…' : confirmLabel}
      </button>
      <button type="button" className="sf-btn sf-btn-ghost" disabled={busy} onClick={onCancel}>
        Cancelar
      </button>
    </div>
  );
}

export function FormError({ children }: { children: ReactNode }) {
  if (!children) return null;
  return (
    <p className="text-sm text-red-600" role="alert">
      {children}
    </p>
  );
}

/** Convierte un error de la API en un mensaje legible.
 *
 * Los 422 traen el detalle por campo; se muestran tal cual llegan para no
 * ocultar la causa real al usuario.
 */
export function describeError(error: unknown): string {
  if (error && typeof error === 'object' && 'code' in error && 'message' in error) {
    const api = error as { message: string; details?: unknown };
    if (Array.isArray(api.details)) {
      const fields = api.details
        .map((detail) => {
          const item = detail as { field?: string; message?: string };
          return item.field ? `${item.field}: ${item.message}` : item.message;
        })
        .filter(Boolean);
      if (fields.length) return fields.join(' · ');
    }
    return api.message;
  }
  return 'No fue posible contactar con el servidor.';
}
