/** Comparación con la auditoría anterior (§32). */

import { useCallback, useEffect, useState } from 'react';

import { scans as api } from '../../lib/api';
import type { ChangeKind, Comparison } from '../../lib/types';
import { EmptyState, ErrorState, LoadingState } from './UiStates';
import { SeverityBadge } from './FindingsList';
import { Card, describeError } from './ui';

const KIND_LABEL: Record<ChangeKind, string> = {
  regressed: 'Empeoró',
  new: 'Nuevo',
  fixed: 'Corregido',
  unchanged: 'Sin cambios',
};

const KIND_COLOR: Record<ChangeKind, string> = {
  regressed: 'text-red-600',
  new: 'text-amber-600',
  fixed: 'text-brand-600',
  unchanged: '',
};

const DIRECTION_COLOR: Record<string, string> = {
  mejora: 'text-brand-600',
  empeora: 'text-red-600',
  igual: '',
  desconocido: '',
};

function formatValue(value: number | null, unit: string): string {
  if (value === null) return '—';
  if (unit === 'ms') return `${(value / 1000).toFixed(1)} s`;
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

export default function ComparisonView({ scanId }: { scanId: string }) {
  const [state, setState] = useState<'loading' | 'ready' | 'error' | 'none'>('loading');
  const [data, setData] = useState<Comparison | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setState('loading');
    try {
      setData(await api.comparison(scanId));
      setState('ready');
    } catch (caught) {
      if ((caught as { code?: string }).code === 'no_previous_scan') {
        setState('none');
        return;
      }
      setError(describeError(caught));
      setState('error');
    }
  }, [scanId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (state === 'loading') return <LoadingState label="Comparando auditorías…" />;
  if (state === 'none') {
    return (
      <EmptyState
        title="Primera auditoría del sitio"
        description="No hay una auditoría anterior con la que comparar. La comparación estará disponible a partir de la siguiente."
      />
    );
  }
  if (state === 'error' || !data) {
    return <ErrorState description={error} onRetry={() => void load()} />;
  }

  const changed = data.changes.filter((change) => change.kind !== 'unchanged');

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold">Cambios respecto a la auditoría anterior</h2>
          <span className="sf-muted text-xs">
            {data.previous.finished_at
              ? `Anterior: ${new Date(data.previous.finished_at).toLocaleString()}`
              : 'Anterior sin fecha de fin'}
          </span>
        </div>
        <dl className="grid gap-3 sm:grid-cols-4">
          {(['regressed', 'new', 'fixed', 'unchanged'] as const).map((kind) => (
            <div key={kind}>
              <dt className="sf-muted text-xs uppercase tracking-wide">{KIND_LABEL[kind]}</dt>
              <dd className={`text-lg font-semibold ${data.counts[kind] > 0 ? KIND_COLOR[kind] : ''}`}>
                {data.counts[kind]}
              </dd>
            </div>
          ))}
        </dl>
        {data.sources_only_in_previous.length > 0 || data.sources_only_in_current.length > 0 ? (
          <p className="sf-muted mt-3 text-xs">
            Solo se comparan los módulos que se ejecutaron en las dos auditorías (
            {data.compared_sources.join(', ') || 'ninguno'}).
            {data.sources_only_in_previous.length > 0
              ? ` No se comparan ${data.sources_only_in_previous.join(', ')}: no se ejecutaron esta vez, así que sus hallazgos no cuentan como corregidos.`
              : ''}
            {data.sources_only_in_current.length > 0
              ? ` Tampoco ${data.sources_only_in_current.join(', ')}: no se ejecutaron en la auditoría anterior.`
              : ''}
          </p>
        ) : null}

        {data.current.engine_version !== data.previous.engine_version ? (
          <p className="sf-muted mt-3 text-xs">
            Las dos auditorías se hicieron con versiones distintas del motor (
            {data.previous.engine_version} y {data.current.engine_version}), así que parte de las
            diferencias puede deberse al cambio de versión.
          </p>
        ) : null}
      </Card>

      {data.metrics.length > 0 ? (
        <Card className="!px-0 !py-0">
          <h2 className="px-4 py-3 text-sm font-semibold">Métricas</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="sf-muted text-xs uppercase">
                <tr className="border-y" style={{ borderColor: 'var(--border)' }}>
                  <th className="px-4 py-2 font-medium">Métrica</th>
                  <th className="px-2 py-2 font-medium">Antes</th>
                  <th className="px-2 py-2 font-medium">Ahora</th>
                  <th className="px-4 py-2 font-medium">Cambio</th>
                </tr>
              </thead>
              <tbody>
                {data.metrics.map((metric) => (
                  <tr key={metric.key} className="border-b" style={{ borderColor: 'var(--border)' }}>
                    <td className="px-4 py-2">{metric.label}</td>
                    <td className="sf-muted px-2 py-2">
                      {formatValue(metric.previous, metric.unit)}
                    </td>
                    <td className="px-2 py-2">{formatValue(metric.current, metric.unit)}</td>
                    <td className={`px-4 py-2 ${DIRECTION_COLOR[metric.direction] ?? ''}`}>
                      {metric.delta === null
                        ? '—'
                        : `${metric.delta > 0 ? '+' : ''}${formatValue(metric.delta, metric.unit)}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : null}

      {changed.length === 0 ? (
        <EmptyState
          title="Sin cambios en los hallazgos"
          description="Los mismos hallazgos que en la auditoría anterior."
        />
      ) : (
        <Card className="!px-0 !py-0">
          <h2 className="px-4 py-3 text-sm font-semibold">Hallazgos ({changed.length})</h2>
          <ul className="divide-y" style={{ borderColor: 'var(--border)' }}>
            {changed.map((change) => (
              <li key={change.fingerprint} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <span className={`w-24 shrink-0 text-xs font-medium ${KIND_COLOR[change.kind]}`}>
                  {KIND_LABEL[change.kind]}
                </span>
                <SeverityBadge severity={change.severity} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm">
                    {change.rule_id ? `${change.rule_id} · ` : ''}
                    {change.title}
                  </p>
                  {change.url ? <p className="sf-muted truncate text-xs">{change.url}</p> : null}
                </div>
                {change.kind === 'regressed' ? (
                  <span className="sf-muted text-xs">
                    {change.previous_severity !== change.severity
                      ? `${change.previous_severity} → ${change.severity}`
                      : `${change.previous_occurrences} → ${change.occurrences} casos`}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
