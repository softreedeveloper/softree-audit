/** Histórico de auditorías de un sitio (§31). */

import { useCallback, useEffect, useState } from 'react';

import { sites as api } from '../../lib/api';
import type { HistoryEntry } from '../../lib/types';
import { EmptyState, ErrorState, LoadingState } from './UiStates';
import { STATUS_LABEL, STATUS_TONE, formatDuration } from './ScanProgress';
import { Badge, Card, describeError } from './ui';

export default function SiteHistoryView({ siteId }: { siteId: string }) {
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [items, setItems] = useState<HistoryEntry[]>([]);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setState('loading');
    try {
      setItems(await api.history(siteId));
      setState('ready');
    } catch (caught) {
      setError(describeError(caught));
      setState('error');
    }
  }, [siteId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (state === 'loading') return <LoadingState label="Cargando el histórico…" />;
  if (state === 'error') return <ErrorState description={error} onRetry={() => void load()} />;
  if (items.length === 0) {
    return (
      <EmptyState
        title="Sin auditorías"
        description="Este sitio todavía no se ha auditado."
      />
    );
  }

  return (
    <Card className="!px-0 !py-0">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="sf-muted text-xs uppercase">
            <tr className="border-y" style={{ borderColor: 'var(--border)' }}>
              <th className="px-4 py-2 font-medium">Fecha</th>
              <th className="px-2 py-2 font-medium">Tipo</th>
              <th className="px-2 py-2 font-medium">Estado</th>
              <th className="px-2 py-2 font-medium">Softree Score</th>
              <th className="px-2 py-2 font-medium">Hallazgos</th>
              <th className="px-2 py-2 font-medium">Duración</th>
              <th className="px-4 py-2 font-medium"></th>
            </tr>
          </thead>
          <tbody>
            {items.map((entry) => (
              <tr key={entry.scan_id} className="border-b" style={{ borderColor: 'var(--border)' }}>
                <td className="px-4 py-2">{new Date(entry.queued_at).toLocaleString()}</td>
                <td className="px-2 py-2">{entry.scan_type}</td>
                <td className="px-2 py-2">
                  <Badge tone={STATUS_TONE[entry.status]}>{STATUS_LABEL[entry.status]}</Badge>
                </td>
                <td className="px-2 py-2 font-semibold">
                  {entry.softree_overall === null ? '—' : entry.softree_overall.toFixed(1)}
                </td>
                <td className="px-2 py-2">{entry.open_findings}</td>
                <td className="px-2 py-2">{formatDuration(entry.duration_ms)}</td>
                <td className="px-4 py-2">
                  <a className="hover:underline" href={`/audits?id=${entry.scan_id}`}>
                    Abrir
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
