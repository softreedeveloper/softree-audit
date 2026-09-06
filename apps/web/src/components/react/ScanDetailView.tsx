/** Detalle de una auditoría: progreso, resumen y páginas rastreadas. */

import { useCallback, useEffect, useRef, useState } from 'react';

import {
  findings as findingsApi,
  request,
  performance as performanceApi,
  scans as api,
  security as securityApi,
} from '../../lib/api';
import {
  TERMINAL_STATUSES,
  type CrawledPage,
  type PerformanceSummary,
  type ScanDetail,
  type ScanScores,
  type SecuritySummary,
  type SeoResult,
  type SeverityCounts,
} from '../../lib/types';
import { EmptyState, ErrorState, LoadingState, PartialState } from './UiStates';
import FindingsList from './FindingsList';
import ComparisonView from './ComparisonView';
import ReportsView from './ReportsView';
import ScanProgress, { STATUS_LABEL, STATUS_TONE, formatDuration } from './ScanProgress';
import ScoreCard from './ScoreCard';
import PerformanceSummaryView from './PerformanceSummaryView';
import SearchConsoleView from './SearchConsoleView';
import SecuritySummaryView from './SecuritySummaryView';
import SeoSummary from './SeoSummary';
import { Badge, Card, FormError, describeError } from './ui';

const POLL_INTERVAL_MS = 2000;

export default function ScanDetailView({ scanId }: { scanId: string }) {
  const [status, setStatus] = useState<'loading' | 'ready' | 'error' | 'missing'>('loading');
  const [scan, setScan] = useState<ScanDetail | null>(null);
  const [pages, setPages] = useState<CrawledPage[]>([]);
  const [seo, setSeo] = useState<SeoResult | null>(null);
  const [security, setSecurity] = useState<SecuritySummary | null>(null);
  const [performance, setPerformance] = useState<PerformanceSummary | null>(null);
  const [counts, setCounts] = useState<SeverityCounts | null>(null);
  const [scores, setScores] = useState<ScanScores | null>(null);
  const [tab, setTab] = useState<
    | 'resumen'
    | 'seguridad'
    | 'seo'
    | 'rendimiento'
    | 'search console'
    | 'comparacion'
    | 'hallazgos'
    | 'paginas'
    | 'reporte'
  >('resumen');
  const [error, setError] = useState('');
  const [cancelError, setCancelError] = useState('');
  const [cancelling, setCancelling] = useState(false);
  const timer = useRef<number | null>(null);

  const load = useCallback(
    async (initial = false) => {
      if (initial) setStatus('loading');
      try {
        const detail = await api.get(scanId);
        setScan(detail);
        setStatus('ready');
        if (TERMINAL_STATUSES.includes(detail.status)) {
          if (detail.pages_count > 0) {
            setPages((await api.pages(scanId)).items);
          }
          setCounts(await findingsApi.severityCounts(scanId));
          setScores(await api.scores(scanId));
          try {
            const summary = await request<{ result: SeoResult | null }>(
              `/sites/${detail.site_id}/seo`,
            );
            setSeo(summary.result);
          } catch {
            // El sitio puede no tener todavía un resultado SEO; no es un error.
          }
          try {
            setSecurity(await securityApi.forSite(detail.site_id));
          } catch {
            // Igual con seguridad: su ausencia no es un fallo de la vista.
          }
          try {
            setPerformance(await performanceApi.forSite(detail.site_id));
          } catch {
            // Y con rendimiento.
          }
        }
      } catch (caught) {
        if ((caught as { status?: number }).status === 404) {
          setStatus('missing');
          return;
        }
        setError(describeError(caught));
        setStatus('error');
      }
    },
    [scanId],
  );

  useEffect(() => {
    void load(true);
  }, [load]);

  useEffect(() => {
    if (!scan || TERMINAL_STATUSES.includes(scan.status)) {
      if (timer.current) window.clearInterval(timer.current);
      timer.current = null;
      return;
    }
    timer.current = window.setInterval(() => void load(), POLL_INTERVAL_MS);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
      timer.current = null;
    };
  }, [scan, load]);

  async function cancel() {
    setCancelling(true);
    setCancelError('');
    try {
      setScan(await api.cancel(scanId));
    } catch (caught) {
      setCancelError(describeError(caught));
    } finally {
      setCancelling(false);
    }
  }

  if (status === 'loading') return <LoadingState label="Cargando la auditoría…" />;
  if (status === 'missing') {
    return (
      <EmptyState
        title="La auditoría no existe"
        description="Puede que se haya eliminado junto con su sitio."
        action={
          <a className="sf-btn sf-btn-primary" href="/audits">
            Volver a auditorías
          </a>
        }
      />
    );
  }
  if (status === 'error' || !scan) {
    return <ErrorState description={error} onRetry={() => void load(true)} />;
  }

  const running = !TERMINAL_STATUSES.includes(scan.status);

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold">{scan.site_name}</h2>
            <p className="sf-muted truncate text-sm">
              {scan.site_base_url} · {scan.scan_type} ·{' '}
              {new Date(scan.queued_at).toLocaleString()}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={STATUS_TONE[scan.status]}>{STATUS_LABEL[scan.status]}</Badge>
            {running ? (
              <button
                type="button"
                className="sf-btn sf-btn-ghost"
                disabled={cancelling}
                onClick={() => void cancel()}
              >
                {cancelling ? 'Cancelando…' : 'Cancelar'}
              </button>
            ) : null}
            <a className="sf-btn sf-btn-ghost" href="/audits">
              Volver
            </a>
          </div>
        </div>
        <FormError>{cancelError}</FormError>
      </Card>

      {scan.status === 'partial' ? (
        <PartialState description="Algunos módulos fallaron. El resto de la auditoría sí se completó." />
      ) : null}

      <Card>
        <h2 className="mb-3 text-sm font-semibold">Progreso</h2>
        <ScanProgress modules={scan.modules} progress={scan.progress} status={scan.status} />
      </Card>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Páginas rastreadas" value={String(scan.pages_count)} />
        <Metric label="Duración" value={formatDuration(scan.duration_ms)} />
        <Metric label="Motor de scan" value={scan.engine_version} />
        <Metric
          label="Páginas máximas"
          value={String(scan.scope_snapshot.max_pages ?? '—')}
        />
      </section>

      {scan.error ? (
        <Card>
          <h2 className="mb-1 text-sm font-semibold text-red-600">Error</h2>
          <p className="break-words text-sm">{scan.error}</p>
        </Card>
      ) : null}

      {scores ? <ScoreCard scores={scores} /> : null}

      {counts ? <SeverityRow counts={counts} /> : null}

      {TERMINAL_STATUSES.includes(scan.status) ? (
        <>
          <nav
            className="sf-tabs border-b"
            style={{ borderColor: 'var(--border)' }}
            aria-label="Secciones de la auditoría"
          >
            {(
              [
                'resumen',
                'seguridad',
                'seo',
                'rendimiento',
                'search console',
                'comparacion',
                'hallazgos',
                'paginas',
                'reporte',
              ] as const
            ).map((value) => (
              <button
                key={value}
                type="button"
                className="shrink-0 whitespace-nowrap rounded-t-lg px-3 py-2 text-sm capitalize"
                aria-current={tab === value ? 'page' : undefined}
                style={
                  tab === value
                    ? { backgroundColor: 'var(--surface-raised)', color: 'var(--text)' }
                    : { color: 'var(--text-muted)' }
                }
                onClick={() => setTab(value)}
              >
                {value === 'paginas' ? 'páginas' : value}
              </button>
            ))}
          </nav>

          {tab === 'seguridad' ? (
            security ? (
              <SecuritySummaryView summary={security} />
            ) : (
              <EmptyState
                title="Sin resultado de seguridad"
                description="Esta auditoría no incluyó el módulo de seguridad o no llegó a completarlo."
              />
            )
          ) : null}

          {tab === 'seo' ? (
            seo ? (
              <SeoSummary result={seo} />
            ) : (
              <EmptyState
                title="Sin resultado SEO"
                description="Esta auditoría no incluyó el módulo SEO o no llegó a completarlo."
              />
            )
          ) : null}

          {tab === 'rendimiento' ? (
            performance ? (
              <PerformanceSummaryView summary={performance} />
            ) : (
              <EmptyState
                title="Sin resultado de rendimiento"
                description="Esta auditoría no incluyó el módulo de rendimiento o no llegó a completarlo."
              />
            )
          ) : null}

          {tab === 'search console' ? <SearchConsoleView scanId={scan.id} /> : null}

          {tab === 'comparacion' ? <ComparisonView scanId={scan.id} /> : null}

          {tab === 'hallazgos' ? <FindingsList scanId={scan.id} /> : null}

          {tab === 'reporte' ? <ReportsView scanId={scan.id} /> : null}

          {tab === 'paginas' ? (
            pages.length > 0 ? (
              <PagesTable pages={pages} />
            ) : (
              <EmptyState
                title="No se rastreó ninguna página"
                description="Revise el scope del sitio y el detalle de los módulos."
              />
            )
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function SeverityRow({ counts }: { counts: SeverityCounts }) {
  const entries: [string, number, string][] = [
    ['Críticos', counts.critical, 'text-red-600'],
    ['Altos', counts.high, 'text-red-600'],
    ['Medios', counts.medium, 'text-amber-600'],
    ['Bajos', counts.low, ''],
    ['Informativos', counts.info, ''],
  ];
  return (
    <section className="grid grid-cols-2 gap-3 sm:grid-cols-5">
      {entries.map(([label, value, tone]) => (
        <div key={label} className="sf-card px-4 py-3">
          <p className="sf-muted text-xs uppercase tracking-wide">{label}</p>
          <p className={`mt-1 text-lg font-semibold ${value > 0 ? tone : ''}`}>{value}</p>
        </div>
      ))}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="sf-card px-4 py-3">
      <p className="sf-muted text-xs uppercase tracking-wide">{label}</p>
      <p className="mt-1 break-words text-lg font-semibold">{value}</p>
    </div>
  );
}

function PagesTable({ pages }: { pages: CrawledPage[] }) {
  return (
    <Card className="!px-0 !py-0">
      <h2 className="px-4 py-3 text-sm font-semibold">Páginas rastreadas ({pages.length})</h2>
      <div className="sf-table-wrap">
        <table className="w-full min-w-[880px] text-left text-sm">
          <thead className="sf-muted text-xs uppercase whitespace-nowrap">
            <tr className="border-y" style={{ borderColor: 'var(--border)' }}>
              <th className="px-4 py-2 font-medium">URL</th>
              <th className="px-2 py-2 font-medium">Código</th>
              <th className="px-2 py-2 font-medium">Prof.</th>
              <th className="px-2 py-2 font-medium">Title</th>
              <th className="px-2 py-2 font-medium">Desc.</th>
              <th className="px-2 py-2 font-medium">H1</th>
              <th className="px-2 py-2 font-medium">Img sin alt</th>
              <th className="px-2 py-2 font-medium">Indexable</th>
              <th className="px-4 py-2 font-medium">ms</th>
            </tr>
          </thead>
          <tbody>
            {pages.map((page) => (
              <tr key={page.id} className="border-b" style={{ borderColor: 'var(--border)' }}>
                <td className="max-w-xs truncate px-4 py-2 font-mono text-xs" title={page.url}>
                  {page.url}
                </td>
                <td className="px-2 py-2">
                  <StatusCode value={page.status_code} />
                </td>
                <td className="px-2 py-2">{page.depth}</td>
                <td className="max-w-xs truncate px-2 py-2" title={page.title ?? ''}>
                  {page.title ?? <Missing />}
                </td>
                <td className="px-2 py-2">{page.meta_description ? '✓' : <Missing />}</td>
                <td className="px-2 py-2">{page.h1.length === 1 ? '✓' : page.h1.length}</td>
                <td className="px-2 py-2">
                  {page.images_missing_alt > 0 ? (
                    <span className="text-amber-600">{page.images_missing_alt}</span>
                  ) : (
                    '0'
                  )}
                </td>
                <td className="px-2 py-2">{page.is_indexable === false ? <Missing /> : '✓'}</td>
                <td className="px-4 py-2">{page.response_time_ms ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function StatusCode({ value }: { value: number | null }) {
  if (value === null) return <Missing />;
  const tone =
    value >= 500 ? 'text-red-600' : value >= 400 ? 'text-amber-600' : 'text-brand-600';
  return <span className={tone}>{value}</span>;
}

function Missing() {
  return <span className="text-amber-600">falta</span>;
}
