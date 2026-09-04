/** Resumen de la plataforma (§28).
 *
 * Agrega el estado **actual** de cada sitio: sumar todo el histórico
 * multiplicaría los hallazgos por el número de auditorías.
 */

import { useCallback, useEffect, useState } from 'react';

import { dashboard as api, request } from '../../lib/api';
import {
  SEVERITY_LABEL,
  SEVERITY_ORDER,
  type DashboardData,
  type HealthResponse,
} from '../../lib/types';
import { EmptyState, ErrorState, LoadingState } from './UiStates';
import { STATUS_LABEL, STATUS_TONE } from './ScanProgress';
import { Badge, Card, describeError } from './ui';

const SEVERITY_TONE: Record<string, string> = {
  critical: 'text-red-600',
  high: 'text-red-600',
  medium: 'text-amber-600',
  low: '',
  info: '',
};

export default function DashboardOverview() {
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [data, setData] = useState<DashboardData | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setState('loading');
    try {
      const [summary, status] = await Promise.all([
        api.load(),
        request<HealthResponse>('/health'),
      ]);
      setData(summary);
      setHealth(status);
      setState('ready');
    } catch (caught) {
      setError(describeError(caught));
      setState('error');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (state === 'loading') return <LoadingState label="Cargando el resumen…" />;
  if (state === 'error' || !data) {
    return <ErrorState description={error} onRetry={() => void load()} />;
  }

  return (
    <div className="flex flex-col gap-4">
      {health?.ssrf_allow_private_networks ? (
        <div className="sf-card border-amber-400 px-4 py-3 text-sm" role="alert">
          <strong className="text-amber-600">Atención:</strong> el acceso a redes privadas está
          habilitado. Es una opción exclusiva de desarrollo y debe estar desactivada en producción.
        </div>
      ) : null}

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Softree Score medio" value={data.average_score?.toFixed(1) ?? '—'} hint={
          data.scored_sites > 0 ? `${data.scored_sites} sitio(s) con puntuación` : 'Sin auditorías'
        } />
        <Metric label="Proyectos" value={String(data.projects)} />
        <Metric
          label="Sitios"
          value={String(data.sites)}
          hint={`${data.authorized_sites} autorizado(s)`}
        />
        <Metric
          label="Auditorías"
          value={String(data.scans)}
          hint={data.scans_in_progress > 0 ? `${data.scans_in_progress} en curso` : undefined}
        />
      </section>

      <Card>
        <h2 className="mb-3 text-sm font-semibold">Hallazgos abiertos</h2>
        <p className="sf-muted mb-3 text-xs">
          Estado actual de cada sitio, según su última auditoría terminada.
        </p>
        <dl className="grid gap-3 sm:grid-cols-5">
          {SEVERITY_ORDER.map((severity) => {
            const value = data.open_findings_by_severity[severity] ?? 0;
            return (
              <div key={severity}>
                <dt className="sf-muted text-xs uppercase tracking-wide">
                  {SEVERITY_LABEL[severity]}
                </dt>
                <dd className={`text-lg font-semibold ${value > 0 ? SEVERITY_TONE[severity] : ''}`}>
                  {value}
                </dd>
              </div>
            );
          })}
        </dl>
      </Card>

      {data.recent_scans.length === 0 ? (
        <EmptyState
          title="Todavía no hay auditorías"
          description="Cree un proyecto, registre un sitio autorizado y lance su primera auditoría."
          action={
            <a className="sf-btn sf-btn-primary" href="/projects">
              Ir a proyectos
            </a>
          }
        />
      ) : (
        <Card className="!px-0 !py-0">
          <h2 className="px-4 py-3 text-sm font-semibold">Últimas auditorías</h2>
          <ul className="divide-y" style={{ borderColor: 'var(--border)' }}>
            {data.recent_scans.map((scan) => (
              <li key={scan.scan_id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <a className="font-medium hover:underline" href={`/audits?id=${scan.scan_id}`}>
                    {scan.site_name}
                  </a>
                  <p className="sf-muted truncate text-xs">
                    {scan.site_base_url} · {scan.scan_type} ·{' '}
                    {new Date(scan.queued_at).toLocaleString()}
                  </p>
                </div>
                <Badge tone={STATUS_TONE[scan.status]}>{STATUS_LABEL[scan.status]}</Badge>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {health ? (
        <Card>
          <h2 className="mb-2 text-sm font-semibold">Estado del servicio</h2>
          <dl className="grid gap-3 sm:grid-cols-4 text-sm">
            <div>
              <dt className="sf-muted text-xs uppercase tracking-wide">Estado</dt>
              <dd className="capitalize">{health.status === 'ok' ? 'Operativo' : 'Degradado'}</dd>
            </div>
            <div>
              <dt className="sf-muted text-xs uppercase tracking-wide">Entorno</dt>
              <dd>{health.environment}</dd>
            </div>
            <div>
              <dt className="sf-muted text-xs uppercase tracking-wide">Softree Audit</dt>
              <dd className="font-mono">{health.app_version}</dd>
            </div>
            <div>
              <dt className="sf-muted text-xs uppercase tracking-wide">Scan Engine</dt>
              <dd className="font-mono">{health.scan_engine_version}</dd>
            </div>
          </dl>
        </Card>
      ) : null}
    </div>
  );
}

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="sf-card px-4 py-3">
      <p className="sf-muted text-xs uppercase tracking-wide">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
      {hint ? <p className="sf-muted text-xs">{hint}</p> : null}
    </div>
  );
}
