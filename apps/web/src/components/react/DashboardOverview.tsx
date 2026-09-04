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
import ScoreMeter from './ScoreMeter';
import Sparkline from './Sparkline';
import { STATUS_LABEL, STATUS_TONE } from './ScanProgress';
import { Badge, Card, describeError } from './ui';

const SEVERITY_TONE: Record<string, string> = {
  critical: 'var(--tone-danger)',
  high: 'var(--tone-danger)',
  medium: 'var(--tone-accessibility)',
  low: 'var(--text)',
  info: 'var(--text)',
};

const CATEGORIES: { key: string; label: string; tone: string }[] = [
  { key: 'seo', label: 'SEO', tone: 'var(--tone-seo)' },
  { key: 'performance', label: 'Rendimiento', tone: 'var(--tone-performance)' },
  { key: 'security', label: 'Seguridad', tone: 'var(--tone-security)' },
  { key: 'accessibility', label: 'Accesibilidad', tone: 'var(--tone-accessibility)' },
];

/** Banda del score, con el mismo criterio que el motor de puntuación. */
function band(score: number): { label: string; hint: string } {
  if (score >= 90) return { label: 'Excelente', hint: 'Mantener el nivel.' };
  if (score >= 75) return { label: 'Buen estado', hint: 'Sigue mejorando hasta excelente.' };
  if (score >= 50) return { label: 'Mejorable', hint: 'Hay margen claro de mejora.' };
  return { label: 'Deficiente', hint: 'Requiere atención inmediata.' };
}

function greeting(date: Date): string {
  const hour = date.getHours();
  if (hour < 12) return 'Buenos días';
  if (hour < 20) return 'Buenas tardes';
  return 'Buenas noches';
}

function relative(iso: string | null): string {
  if (!iso) return '—';
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return 'hace un momento';
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `hace ${hours} h`;
  return new Date(iso).toLocaleDateString();
}

export default function DashboardOverview({ userName }: { userName?: string }) {
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

  const now = new Date();
  const score = data.average_score;
  const trend = data.score_trend.map((point) => point.score);
  const delta =
    trend.length >= 2 ? Number((trend[trend.length - 1]! - trend[trend.length - 2]!).toFixed(1)) : null;
  const latest = data.recent_scans[0] ?? null;
  const urgent =
    (data.open_findings_by_severity.critical ?? 0) + (data.open_findings_by_severity.high ?? 0);

  return (
    <div className="flex flex-col gap-5">
      {health?.ssrf_allow_private_networks ? (
        <div
          className="sf-card px-4 py-3 text-sm"
          style={{ borderColor: 'var(--tone-accessibility)' }}
          role="alert"
        >
          <strong style={{ color: 'var(--tone-accessibility)' }}>Atención:</strong> el acceso a
          redes privadas está habilitado. Es una opción exclusiva de desarrollo y debe estar
          desactivada en producción.
        </div>
      ) : null}

      {/* Encabezado */}
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="sf-label">
            {now.toLocaleDateString(undefined, {
              weekday: 'long',
              day: '2-digit',
              month: 'long',
              year: 'numeric',
            })}
          </p>
          <h1 className="mt-2 text-4xl font-semibold tracking-tight">
            {greeting(now)}
            {userName ? `, ${userName}` : ''}.
          </h1>
          <p className="sf-muted mt-1.5 text-sm">
            {data.scans === 0
              ? 'Todavía no hay auditorías. Empiece registrando un sitio autorizado.'
              : urgent > 0
                ? `Hay ${urgent} hallazgo(s) de gravedad alta o crítica esperando.`
                : 'Ningún hallazgo de gravedad alta ni crítica abierto.'}
          </p>
        </div>

        <a className="sf-btn sf-btn-primary" href="/projects">
          Nueva auditoría <span aria-hidden="true">→</span>
        </a>
      </header>

      {/* Score y última auditoría */}
      <section className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
        <Card className="!p-6">
          <div className="flex items-start justify-between gap-4">
            <p className="sf-label">Estado general</p>
            {delta !== null ? (
              <p className="text-sm">
                <span
                  className="font-semibold"
                  style={{ color: delta >= 0 ? 'var(--accent)' : 'var(--tone-danger)' }}
                >
                  {delta > 0 ? '+' : ''}
                  {delta}
                </span>{' '}
                <span className="sf-muted">frente a la anterior</span>
              </p>
            ) : null}
          </div>
          <h2 className="mt-1 text-xl font-semibold">Softree Score medio</h2>

          <div className="mt-5 flex flex-wrap items-end gap-6">
            <p className="flex items-baseline gap-1">
              <span className="text-6xl font-semibold tracking-tight">
                {score !== null ? score.toFixed(0) : '—'}
              </span>
              <span className="sf-muted text-lg">/100</span>
            </p>

            <div className="min-w-[220px] flex-1">
              {score !== null ? (
                <>
                  <p className="font-medium" style={{ color: 'var(--accent)' }}>
                    {band(score).label}
                  </p>
                  <p className="sf-muted mb-3 text-sm">{band(score).hint}</p>
                  <ScoreMeter value={score} />
                </>
              ) : (
                <p className="sf-muted text-sm">
                  Sin puntuación todavía: hace falta una auditoría terminada.
                </p>
              )}
            </div>
          </div>

          {trend.length >= 2 ? (
            <div className="mt-6 border-t pt-4" style={{ borderColor: 'var(--border)' }}>
              <Sparkline values={trend} />
              <p className="sf-muted mt-2 text-xs">
                {trend.length} auditoría(s) con puntuación, de la más antigua a la más reciente.
              </p>
            </div>
          ) : null}
        </Card>

        <Card className="!p-6">
          <div className="flex items-start justify-between gap-3">
            <p className="sf-label">Última auditoría</p>
            {latest ? <Badge tone={STATUS_TONE[latest.status]}>{STATUS_LABEL[latest.status]}</Badge> : null}
          </div>

          {latest ? (
            <>
              <h2 className="mt-1 truncate text-xl font-semibold">{latest.site_name}</h2>
              <p className="sf-muted truncate text-sm">{latest.site_base_url}</p>

              <dl className="mt-6 grid grid-cols-2 gap-4">
                <div>
                  <dt className="sf-label">Terminada</dt>
                  <dd className="mt-1 text-sm">{relative(latest.finished_at)}</dd>
                </div>
                <div>
                  <dt className="sf-label">Tipo</dt>
                  <dd className="mt-1 text-sm capitalize">{latest.scan_type}</dd>
                </div>
                <div>
                  <dt className="sf-label">Sitios</dt>
                  <dd className="mt-1 text-sm">
                    {data.sites} ({data.authorized_sites} autorizados)
                  </dd>
                </div>
                <div>
                  <dt className="sf-label">En curso</dt>
                  <dd className="mt-1 text-sm">{data.scans_in_progress}</dd>
                </div>
              </dl>

              <a
                className="mt-6 inline-flex items-center gap-2 text-sm font-medium"
                style={{ color: 'var(--accent)' }}
                href={`/audits?id=${latest.scan_id}`}
              >
                Ver la auditoría <span aria-hidden="true">→</span>
              </a>
            </>
          ) : (
            <p className="sf-muted mt-4 text-sm">Todavía no se ha ejecutado ninguna auditoría.</p>
          )}
        </Card>
      </section>

      {/* Desglose por categoría */}
      <section
        className="sf-card grid gap-px overflow-hidden sm:grid-cols-2 lg:grid-cols-4"
        style={{ backgroundColor: 'var(--border)' }}
        aria-label="Puntuación por categoría"
      >
        {CATEGORIES.map((category) => {
          // Ausente y `null` significan lo mismo: nadie midió esa categoría.
          const value = data.score_by_category[category.key] ?? null;
          return (
            <div
              key={category.key}
              className="flex items-baseline gap-3 px-5 py-4"
              style={{ backgroundColor: 'var(--surface-raised)' }}
            >
              <span
                className="text-3xl font-semibold"
                style={{ color: value === null ? 'var(--text-faint)' : category.tone }}
              >
                {value === null ? '—' : value.toFixed(0)}
              </span>
              <span className="sf-muted text-sm">{category.label}</span>
            </div>
          );
        })}
      </section>

      {/* Hallazgos abiertos */}
      <Card className="!p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Hallazgos por resolver</h2>
            <p className="sf-muted text-sm">
              Estado actual de cada sitio, según su última auditoría terminada.
            </p>
          </div>
          <a
            className="inline-flex items-center gap-2 text-sm font-medium"
            style={{ color: 'var(--accent)' }}
            href="/findings"
          >
            Ver todos <span aria-hidden="true">→</span>
          </a>
        </div>

        <dl className="mt-5 grid gap-4 sm:grid-cols-5">
          {SEVERITY_ORDER.map((severity) => {
            const value = data.open_findings_by_severity[severity] ?? 0;
            return (
              <div key={severity}>
                <dt className="sf-label">{SEVERITY_LABEL[severity]}</dt>
                <dd
                  className="mt-1 text-2xl font-semibold"
                  style={{ color: value > 0 ? SEVERITY_TONE[severity] : 'var(--text-faint)' }}
                >
                  {value}
                </dd>
              </div>
            );
          })}
        </dl>
      </Card>

      {/* Auditorías recientes */}
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
          <h2 className="px-6 py-4 text-xl font-semibold">Auditorías recientes</h2>
          <ul className="divide-y" style={{ borderColor: 'var(--border)' }}>
            {data.recent_scans.map((scan) => (
              <li key={scan.scan_id} className="flex flex-wrap items-center gap-3 px-6 py-3.5">
                <div className="min-w-0 flex-1">
                  <a className="font-medium hover:underline" href={`/audits?id=${scan.scan_id}`}>
                    {scan.site_name}
                  </a>
                  <p className="sf-muted truncate text-xs">
                    {scan.site_base_url} · {scan.scan_type} · {relative(scan.queued_at)}
                  </p>
                </div>
                <Badge tone={STATUS_TONE[scan.status]}>{STATUS_LABEL[scan.status]}</Badge>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {health ? (
        <p className="sf-muted text-xs">
          {health.status === 'ok' ? 'Servicio operativo' : 'Servicio degradado'} · entorno{' '}
          {health.environment} · Softree Audit {health.app_version} · motor{' '}
          {health.scan_engine_version}
        </p>
      ) : null}
    </div>
  );
}
