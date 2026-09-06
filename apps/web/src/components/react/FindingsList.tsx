/** Listado de hallazgos con filtros y cambio de estado. */

import { useCallback, useEffect, useState } from 'react';

import { findings as api } from '../../lib/api';
import {
  SEVERITY_LABEL,
  SEVERITY_ORDER,
  STATUS_LABEL_FINDING,
  type Finding,
  type FindingStatus,
  type Severity,
} from '../../lib/types';
import { EmptyState, ErrorState, LoadingState } from './UiStates';
import { Card, FormError, describeError } from './ui';

const SEVERITY_STYLE: Record<Severity, string> = {
  critical: 'bg-red-600 text-white',
  high: 'text-red-600 border-red-300',
  medium: 'text-amber-700 border-amber-300',
  low: 'text-brand-700 border-brand-300',
  info: '',
};

const STATUSES: FindingStatus[] = ['open', 'fixed', 'accepted', 'false_positive'];

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-xs ${SEVERITY_STYLE[severity]}`}
      style={
        severity === 'info' ? { borderColor: 'var(--border)', color: 'var(--text-muted)' } : {}
      }
    >
      {SEVERITY_LABEL[severity]}
    </span>
  );
}

export default function FindingsList({
  scanId,
  siteId,
}: {
  scanId?: string;
  siteId?: string;
}) {
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [items, setItems] = useState<Finding[]>([]);
  const [error, setError] = useState('');
  const [severityFilter, setSeverityFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('open');
  const [expanded, setExpanded] = useState<string | null>(null);
  const [updating, setUpdating] = useState<string | null>(null);
  const [updateError, setUpdateError] = useState('');

  const load = useCallback(async () => {
    setStatus('loading');
    try {
      const page = await api.list({
        scanId,
        siteId,
        severity: severityFilter || undefined,
        status: statusFilter || undefined,
      });
      setItems(page.items);
      setStatus('ready');
    } catch (caught) {
      setError(describeError(caught));
      setStatus('error');
    }
  }, [scanId, siteId, severityFilter, statusFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  async function changeStatus(finding: Finding, next: FindingStatus) {
    setUpdating(finding.id);
    setUpdateError('');
    try {
      await api.setStatus(finding.id, next);
      await load();
    } catch (caught) {
      setUpdateError(describeError(caught));
    } finally {
      setUpdating(null);
    }
  }

  const filters = (
    <div className="flex flex-wrap items-center gap-2">
      <label className="sf-muted text-xs" htmlFor="filter-severity">
        Severidad
      </label>
      <select
        id="filter-severity"
        className="sf-input max-w-40 flex-1"
        value={severityFilter}
        onChange={(event) => setSeverityFilter(event.target.value)}
      >
        <option value="">Todas</option>
        {SEVERITY_ORDER.map((severity) => (
          <option key={severity} value={severity}>
            {SEVERITY_LABEL[severity]}
          </option>
        ))}
      </select>

      <label className="sf-muted text-xs" htmlFor="filter-status">
        Estado
      </label>
      <select
        id="filter-status"
        className="sf-input max-w-40 flex-1"
        value={statusFilter}
        onChange={(event) => setStatusFilter(event.target.value)}
      >
        <option value="">Todos</option>
        {STATUSES.map((value) => (
          <option key={value} value={value}>
            {STATUS_LABEL_FINDING[value]}
          </option>
        ))}
      </select>
      <FormError>{updateError}</FormError>
    </div>
  );

  return (
    <div className="flex flex-col gap-4">
      <Card>{filters}</Card>

      {status === 'loading' ? <LoadingState label="Cargando hallazgos…" /> : null}
      {status === 'error' ? <ErrorState description={error} onRetry={() => void load()} /> : null}

      {status === 'ready' && items.length === 0 ? (
        <EmptyState
          title="Sin hallazgos con estos filtros"
          description={
            statusFilter === 'open'
              ? 'No hay hallazgos abiertos. Pruebe a cambiar los filtros para ver los ya resueltos.'
              : 'Ajuste los filtros para ver otros hallazgos.'
          }
        />
      ) : null}

      {status === 'ready' && items.length > 0 ? (
        <Card className="!px-0 !py-0">
          <ul className="divide-y" style={{ borderColor: 'var(--border)' }}>
            {items.map((finding) => (
              <li key={finding.id} className="px-4 py-3">
                <div className="flex flex-wrap items-start gap-3">
                  <SeverityBadge severity={finding.severity} />
                  <div className="min-w-0 flex-1">
                    <button
                      type="button"
                      className="text-left font-medium hover:underline"
                      onClick={() => setExpanded(expanded === finding.id ? null : finding.id)}
                      aria-expanded={expanded === finding.id}
                    >
                      {finding.rule_id ? `${finding.rule_id} · ` : ''}
                      {finding.title}
                    </button>
                    <p className="sf-muted truncate text-xs">
                      {finding.url ?? 'Ámbito del sitio'}
                      {finding.occurrences > 1 ? ` · ${finding.occurrences} casos` : ''}
                    </p>
                  </div>
                  <select
                    className="sf-input w-full max-w-40 sm:w-auto"
                    aria-label={`Estado de ${finding.title}`}
                    value={finding.status}
                    disabled={updating === finding.id}
                    onChange={(event) =>
                      void changeStatus(finding, event.target.value as FindingStatus)
                    }
                  >
                    {STATUSES.map((value) => (
                      <option key={value} value={value}>
                        {STATUS_LABEL_FINDING[value]}
                      </option>
                    ))}
                  </select>
                </div>

                {expanded === finding.id ? (
                  <div className="mt-3 flex flex-col gap-3 text-sm">
                    <Detail label="Qué ocurre">{finding.description}</Detail>
                    {finding.impact ? <Detail label="Impacto">{finding.impact}</Detail> : null}
                    {finding.remediation ? (
                      <Detail label="Cómo se corrige">{finding.remediation}</Detail>
                    ) : null}
                    {finding.client_explanation ? (
                      <Detail label="Explicación para el cliente">
                        {finding.client_explanation}
                      </Detail>
                    ) : null}
                    {finding.evidence ? (
                      <Detail label="Evidencia">
                        <pre className="max-w-full overflow-x-auto whitespace-pre-wrap break-words font-mono text-xs">
                          {finding.evidence}
                        </pre>
                      </Detail>
                    ) : null}
                    <p className="sf-muted text-xs">
                      Fuente: {finding.source} · Categoría: {finding.category} · Confianza:{' '}
                      {finding.confidence}
                    </p>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="sf-muted text-xs font-medium uppercase tracking-wide">{label}</p>
      <div className="mt-0.5">{children}</div>
    </div>
  );
}
