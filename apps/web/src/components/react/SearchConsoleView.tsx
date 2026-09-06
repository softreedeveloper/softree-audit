/** Métricas de Search Console de una auditoría. */

import { useCallback, useEffect, useState } from 'react';

import { google } from '../../lib/api';
import type { ScanSearchConsole } from '../../lib/types';
import { EmptyState, ErrorState, LoadingState, NotConnectedState } from './UiStates';
import { Card, describeError } from './ui';

const PERIODS = [
  ['7d', '7 días'],
  ['28d', '28 días'],
  ['90d', '3 meses'],
] as const;

const DIMENSIONS = [
  ['query', 'Consultas'],
  ['page', 'Páginas'],
  ['country', 'Países'],
  ['device', 'Dispositivos'],
  ['date', 'Fechas'],
] as const;

const SKIP_REASON: Record<string, string> = {
  no_conectado: 'El proyecto no tiene conectada una cuenta de Google Search Console.',
  sin_propiedad_seleccionada:
    'La cuenta está conectada pero no se ha elegido la propiedad del proyecto.',
  quota_exceeded: 'Se superó el límite de consultas de Search Console.',
  invalid_grant: 'El acceso a Google fue revocado. Vuelva a conectar la cuenta.',
  cancelled: 'La auditoría se canceló antes de terminar este módulo.',
};

export default function SearchConsoleView({ scanId }: { scanId: string }) {
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [data, setData] = useState<ScanSearchConsole | null>(null);
  const [error, setError] = useState('');
  const [period, setPeriod] = useState<string>('28d');
  const [dimension, setDimension] = useState<string>('query');

  const load = useCallback(async () => {
    setState('loading');
    try {
      setData(await google.scanMetrics(scanId, period, dimension));
      setState('ready');
    } catch (caught) {
      setError(describeError(caught));
      setState('error');
    }
  }, [scanId, period, dimension]);

  useEffect(() => {
    void load();
  }, [load]);

  if (state === 'loading') return <LoadingState label="Cargando Search Console…" />;
  if (state === 'error' || !data) {
    return <ErrorState description={error} onRetry={() => void load()} />;
  }

  const detail = (data.module_detail ?? {}) as Record<string, unknown>;
  const reason = typeof detail.reason === 'string' ? detail.reason : null;

  if (data.module_status !== 'completed') {
    if (reason === 'no_conectado' || data.module_status === 'no_ejecutado') {
      return <NotConnectedState service="Search Console" href="/integrations" />;
    }
    return (
      <Card>
        <h2 className="mb-1 text-sm font-semibold">Search Console</h2>
        <p className="text-sm">
          Estado del módulo: <strong>{data.module_status}</strong>
        </p>
        <p className="sf-muted mt-2 text-sm">
          {reason ? (SKIP_REASON[reason] ?? reason) : 'Sin datos de Search Console.'}
        </p>
      </Card>
    );
  }

  const totals = data.totals[period];

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h2 className="text-sm font-semibold">Search Console</h2>
            <p className="sf-muted break-words text-xs">
              {data.property_url ?? 'Propiedad no indicada'}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <select
              className="sf-input max-w-36 flex-1"
              aria-label="Periodo"
              value={period}
              onChange={(event) => setPeriod(event.target.value)}
            >
              {PERIODS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            <select
              className="sf-input max-w-40 flex-1"
              aria-label="Dimensión"
              value={dimension}
              onChange={(event) => setDimension(event.target.value)}
            >
              {DIMENSIONS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {totals ? (
          <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Total label="Clics" value={totals.clicks.toLocaleString()} />
            <Total label="Impresiones" value={totals.impressions.toLocaleString()} />
            <Total label="CTR" value={`${(totals.ctr * 100).toFixed(2)} %`} />
            <Total
              label="Posición media"
              value={totals.position === null ? '—' : totals.position.toFixed(1)}
            />
          </dl>
        ) : null}
        <p className="sf-muted mt-3 text-xs">
          Search Console consolida los datos con unos días de retraso, así que el periodo
          analizado termina tres días antes de la fecha de la auditoría.
        </p>
      </Card>

      {data.metrics.length === 0 ? (
        <EmptyState
          title="Sin datos para esta combinación"
          description="Pruebe con otro periodo o con otra dimensión."
        />
      ) : (
        <Card className="!px-0 !py-0">
          <div className="sf-table-wrap">
            <table className="w-full min-w-[600px] text-left text-sm">
              <thead className="sf-muted text-xs uppercase whitespace-nowrap">
                <tr className="border-y" style={{ borderColor: 'var(--border)' }}>
                  <th className="px-4 py-2 font-medium">
                    {DIMENSIONS.find(([value]) => value === dimension)?.[1] ?? dimension}
                  </th>
                  <th className="px-2 py-2 font-medium">Clics</th>
                  <th className="px-2 py-2 font-medium">Impresiones</th>
                  <th className="px-2 py-2 font-medium">CTR</th>
                  <th className="px-4 py-2 font-medium">Posición</th>
                </tr>
              </thead>
              <tbody>
                {data.metrics.map((metric) => (
                  <tr
                    key={`${metric.dimension}-${metric.dimension_value}`}
                    className="border-b"
                    style={{ borderColor: 'var(--border)' }}
                  >
                    <td className="max-w-md truncate px-4 py-2" title={metric.dimension_value}>
                      {metric.dimension_value}
                    </td>
                    <td className="px-2 py-2">{metric.clicks}</td>
                    <td className="px-2 py-2">{metric.impressions}</td>
                    <td className="px-2 py-2">{(metric.ctr * 100).toFixed(2)} %</td>
                    <td className="px-4 py-2">{metric.position.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

function Total({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="sf-muted text-xs uppercase tracking-wide">{label}</dt>
      <dd className="text-lg font-semibold">{value}</dd>
    </div>
  );
}
