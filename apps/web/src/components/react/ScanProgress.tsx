/** Progreso de una auditoría por módulo (§30).
 *
 * Se actualiza por polling; el estado de cada módulo es independiente, de modo
 * que la falla de uno se ve sin que parezca que falló toda la auditoría.
 */

import type { ModuleStatus, ScanModule, ScanStatus } from '../../lib/types';

const MODULE_LABELS: Record<string, string> = {
  discovery: 'Discovery',
  crawler: 'Crawler',
  security: 'Security',
  seo: 'SEO',
  performance: 'Performance',
  search_console: 'Search Console',
  findings: 'Findings',
  scoring: 'Scoring',
  report: 'Report',
};

const MODULE_ICON: Record<ModuleStatus, string> = {
  completed: '✓',
  running: '●',
  pending: '○',
  failed: '✕',
  skipped: '–',
};

const MODULE_COLOR: Record<ModuleStatus, string> = {
  completed: 'text-brand-600',
  running: 'text-amber-600',
  pending: '',
  failed: 'text-red-600',
  skipped: '',
};

export const STATUS_LABEL: Record<ScanStatus, string> = {
  queued: 'En cola',
  running: 'En ejecución',
  completed: 'Completada',
  failed: 'Fallida',
  cancelled: 'Cancelada',
  partial: 'Parcial',
};

export const STATUS_TONE: Record<ScanStatus, 'ok' | 'warn' | 'muted'> = {
  queued: 'muted',
  running: 'warn',
  completed: 'ok',
  failed: 'warn',
  cancelled: 'muted',
  partial: 'warn',
};

export function formatDuration(ms: number | null): string {
  if (ms === null) return '—';
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

export default function ScanProgress({
  modules,
  progress,
  status,
}: {
  modules: ScanModule[];
  progress: number;
  status: ScanStatus;
}) {
  return (
    <div className="flex flex-col gap-3">
      <div
        className="h-1.5 w-full overflow-hidden rounded-full"
        style={{ backgroundColor: 'var(--surface-muted)' }}
        role="progressbar"
        aria-valuenow={progress}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Progreso de la auditoría"
      >
        <div
          className="h-full rounded-full transition-[width] duration-500"
          style={{
            width: `${progress}%`,
            backgroundColor: status === 'failed' ? '#dc2626' : 'var(--color-brand-500)',
          }}
        />
      </div>

      {modules.length === 0 ? (
        <p className="sf-muted text-sm">
          {status === 'queued'
            ? 'En cola. El worker la tomará en unos segundos.'
            : 'Sin módulos registrados.'}
        </p>
      ) : (
        <ul className="flex flex-col gap-1">
          {modules.map((module) => (
            <li key={module.module} className="flex items-center gap-2 text-sm">
              <span className={`w-4 text-center ${MODULE_COLOR[module.status]}`} aria-hidden="true">
                {MODULE_ICON[module.status]}
              </span>
              <span className="min-w-32">{MODULE_LABELS[module.module] ?? module.module}</span>
              <span className="sf-muted text-xs">{formatDuration(module.duration_ms)}</span>
              {module.error ? (
                <span className="text-xs text-red-600" title={module.error}>
                  {module.error.slice(0, 80)}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
