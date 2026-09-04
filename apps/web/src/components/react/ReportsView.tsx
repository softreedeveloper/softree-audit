/** Generación y descarga de reportes de una auditoría. */

import { useCallback, useEffect, useState } from 'react';

import { reports as api } from '../../lib/api';
import type { ReportEntry, ReportFormat } from '../../lib/types';
import { EmptyState, ErrorState, LoadingState } from './UiStates';
import { Card, FormError, describeError } from './ui';

const FORMATS: [ReportFormat, string][] = [
  ['pdf', 'PDF'],
  ['html', 'HTML'],
  ['json', 'JSON'],
];

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
      setItems(await api.generate(scanId, ['pdf', 'html', 'json']));
    } catch (caught) {
      setActionError(describeError(caught));
    } finally {
      setBusy(false);
    }
  }

  async function download(format: ReportFormat) {
    setActionError('');
    try {
      await api.download(scanId, format);
    } catch (caught) {
      setActionError(describeError(caught));
    }
  }

  if (state === 'loading') return <LoadingState label="Cargando reportes…" />;
  if (state === 'error') return <ErrorState description={error} onRetry={() => void load()} />;

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
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
            {busy ? 'Generando…' : items.length > 0 ? 'Regenerar' : 'Generar reporte'}
          </button>
        </div>
        <FormError>{actionError}</FormError>
      </Card>

      {items.length === 0 ? (
        <EmptyState
          title="Todavía no hay reportes"
          description="Genere el reporte para poder descargarlo y entregarlo al cliente."
        />
      ) : (
        <Card className="!px-0 !py-0">
          <ul className="divide-y" style={{ borderColor: 'var(--border)' }}>
            {FORMATS.map(([format, label]) => {
              const report = items.find((item) => item.format === format);
              if (!report) return null;
              return (
                <li key={format} className="flex flex-wrap items-center gap-3 px-4 py-3">
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
                    onClick={() => void download(format)}
                  >
                    Descargar
                  </button>
                </li>
              );
            })}
          </ul>
          <p className="sf-muted px-4 py-3 text-xs">
            Cada reporte guarda su suma de verificación y la versión del motor, de modo que un PDF
            entregado pueda reasociarse a los datos exactos que lo originaron.
          </p>
        </Card>
      )}
    </div>
  );
}
