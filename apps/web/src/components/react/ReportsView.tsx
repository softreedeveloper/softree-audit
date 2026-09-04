/** Generación y descarga de reportes de una auditoría.
 *
 * La audiencia decide qué contiene el documento, no qué se midió: los tres
 * salen de la misma auditoría y muestran las mismas puntuaciones.
 */

import { useCallback, useEffect, useState } from 'react';

import { reports as api } from '../../lib/api';
import type { ReportAudience, ReportEntry, ReportFormat } from '../../lib/types';
import { EmptyState, ErrorState, LoadingState } from './UiStates';
import { Badge, Card, FormError, describeError } from './ui';

const FORMATS: [ReportFormat, string][] = [
  ['pdf', 'PDF'],
  ['html', 'HTML'],
  ['json', 'JSON'],
];

const AUDIENCES: { key: ReportAudience; label: string; detail: string }[] = [
  {
    key: 'combined',
    label: 'Completo',
    detail: 'Todo: explicación para el cliente y detalle técnico con evidencia.',
  },
  {
    key: 'executive',
    label: 'Ejecutivo',
    detail: 'Puntuaciones, hallazgos graves en lenguaje claro y recomendaciones. Sin evidencia.',
  },
  {
    key: 'technical',
    label: 'Técnico',
    detail: 'Detalle por módulo con evidencia, CWE y OWASP. Sin las paráfrasis para el cliente.',
  },
];

const AUDIENCE_LABEL: Record<ReportAudience, string> = {
  combined: 'Completo',
  executive: 'Ejecutivo',
  technical: 'Técnico',
};

function formatSize(bytes: number | null): string {
  if (bytes === null) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function ReportsView({ scanId }: { scanId: string }) {
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [items, setItems] = useState<ReportEntry[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');
  const [audience, setAudience] = useState<ReportAudience>('combined');

  const load = useCallback(async () => {
    setState('loading');
    try {
      setItems(await api.list(scanId));
      setState('ready');
    } catch (caught) {
      setError(describeError(caught));
      setState('error');
    }
  }, [scanId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function generate() {
    setBusy(true);
    setActionError('');
    try {
      await api.generate(scanId, ['pdf', 'html', 'json'], audience);
      // Se recarga la lista completa: pueden existir otras audiencias ya generadas.
      setItems(await api.list(scanId));
    } catch (caught) {
      setActionError(describeError(caught));
    } finally {
      setBusy(false);
    }
  }

  async function download(format: ReportFormat, target: ReportAudience) {
    setActionError('');
    try {
      await api.download(scanId, format, target);
    } catch (caught) {
      setActionError(describeError(caught));
    }
  }

  if (state === 'loading') return <LoadingState label="Cargando reportes…" />;
  if (state === 'error') return <ErrorState description={error} onRetry={() => void load()} />;

  const selected = AUDIENCES.find((item) => item.key === audience);
  const existing = items.some((item) => item.audience === audience);
  const generated = AUDIENCES.map((item) => item.key).filter((key) =>
    items.some((item) => item.audience === key),
  );

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold">Reportes</h2>
            <p className="sf-muted text-xs">
              Los tres formatos se generan del mismo modelo de datos, así que no pueden divergir.
            </p>
          </div>
          <button
            type="button"
            className="sf-btn sf-btn-primary"
            disabled={busy}
            onClick={() => void generate()}
          >
            {busy ? 'Generando…' : existing ? 'Regenerar' : 'Generar reporte'}
          </button>
        </div>

        <fieldset className="mt-4">
          <legend className="sf-muted mb-2 text-xs uppercase tracking-wide">
            Versión del documento
          </legend>
          <div className="flex flex-wrap gap-2">
            {AUDIENCES.map((item) => (
              <label
                key={item.key}
                className={`sf-btn ${audience === item.key ? 'sf-btn-primary' : 'sf-btn-ghost'}`}
              >
                <input
                  type="radio"
                  name="audience"
                  className="sr-only"
                  value={item.key}
                  checked={audience === item.key}
                  onChange={() => setAudience(item.key)}
                />
                {item.label}
              </label>
            ))}
          </div>
          {selected ? <p className="sf-muted mt-2 text-xs">{selected.detail}</p> : null}
        </fieldset>

        <FormError>{actionError}</FormError>
      </Card>

      {items.length === 0 ? (
        <EmptyState
          title="Todavía no hay reportes"
          description="Genere el reporte para poder descargarlo y entregarlo al cliente."
        />
      ) : (
        <div className="flex flex-col gap-4">
          {generated.map((key) => (
            <Card key={key} className="!px-0 !py-0">
              <div className="flex items-center gap-2 px-4 pt-3">
                <h3 className="text-sm font-semibold">{AUDIENCE_LABEL[key]}</h3>
                {key === audience ? <Badge tone="ok">Seleccionado</Badge> : null}
              </div>
              <ul className="mt-2 divide-y" style={{ borderColor: 'var(--border)' }}>
                {FORMATS.map(([format, label]) => {
                  const report = items.find(
                    (item) => item.format === format && item.audience === key,
                  );
                  if (!report) return null;
                  return (
                    <li
                      key={`${key}-${format}`}
                      className="flex flex-wrap items-center gap-3 px-4 py-3"
                    >
                      <span className="w-16 font-medium">{label}</span>
                      <span className="sf-muted text-xs">{formatSize(report.size_bytes)}</span>
                      <span className="sf-muted text-xs">
                        {new Date(report.generated_at).toLocaleString()}
                      </span>
                      <span className="sf-muted flex-1 truncate font-mono text-xs">
                        sha256:{(report.checksum_sha256 ?? '').slice(0, 16)}
                      </span>
                      <button
                        type="button"
                        className="sf-btn sf-btn-ghost"
                        onClick={() => void download(format, key)}
                      >
                        Descargar
                      </button>
                    </li>
                  );
                })}
              </ul>
            </Card>
          ))}
          <p className="sf-muted px-1 text-xs">
            Cada reporte guarda su suma de verificación y la versión del motor, de modo que un PDF
            entregado pueda reasociarse a los datos exactos que lo originaron.
          </p>
        </div>
      )}
    </div>
  );
}
