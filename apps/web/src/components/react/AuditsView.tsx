/** Listado de auditorías con actualización por polling. */

import { useCallback, useEffect, useRef, useState } from 'react';

import { scans as api } from '../../lib/api';
import { TERMINAL_STATUSES, type Scan } from '../../lib/types';
import { EmptyState, ErrorState, LoadingState } from './UiStates';
import { STATUS_LABEL, STATUS_TONE, formatDuration } from './ScanProgress';
import { Badge, Card, describeError } from './ui';

const POLL_INTERVAL_MS = 2000;

export default function AuditsView({ siteId }: { siteId?: string }) {
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [items, setItems] = useState<Scan[]>([]);
  const [error, setError] = useState('');
  const timer = useRef<number | null>(null);

  const load = useCallback(
    async (initial = false) => {
      if (initial) setStatus('loading');
      try {
        const page = await api.list({ siteId });
        setItems(page.items);
        setStatus('ready');
      } catch (caught) {
        setError(describeError(caught));
        setStatus('error');
      }
    },
    [siteId],
  );

  useEffect(() => {
    void load(true);
  }, [load]);

  // Solo se sondea mientras haya auditorías en marcha.
  useEffect(() => {
    const active = items.some((scan) => !TERMINAL_STATUSES.includes(scan.status));
    if (!active) {
      if (timer.current) window.clearInterval(timer.current);
      timer.current = null;
      return;
    }
    timer.current = window.setInterval(() => void load(), POLL_INTERVAL_MS);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
      timer.current = null;
    };
  }, [items, load]);

  if (status === 'loading') return <LoadingState label="Cargando auditorías…" />;
  if (status === 'error') return <ErrorState description={error} onRetry={() => void load(true)} />;

  if (items.length === 0) {
    return (
      <EmptyState
        title="Todavía no hay auditorías"
        description="Lance la primera desde el detalle de un sitio autorizado."
        action={
          <a className="sf-btn sf-btn-primary" href="/projects">
            Ir a proyectos
          </a>
        }
      />
    );
  }

  return (
    <Card className="!px-0 !py-0">
      <ul className="divide-y" style={{ borderColor: 'var(--border)' }}>
        {items.map((scan) => (
          <li key={scan.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
            <div className="min-w-0 flex-1">
              <a className="font-medium hover:underline" href={`/audits?id=${scan.id}`}>
                {scan.site_name}
              </a>
              <p className="sf-muted truncate text-xs">
                {scan.site_base_url} · {scan.scan_type} ·{' '}
                {new Date(scan.queued_at).toLocaleString()}
              </p>
            </div>
            <span className="sf-muted text-xs">{scan.pages_count} páginas</span>
            <span className="sf-muted text-xs">{formatDuration(scan.duration_ms)}</span>
            {!TERMINAL_STATUSES.includes(scan.status) ? (
              <span className="sf-muted text-xs">{scan.progress}%</span>
            ) : null}
            <Badge tone={STATUS_TONE[scan.status]}>{STATUS_LABEL[scan.status]}</Badge>
            <a className="sf-btn sf-btn-ghost" href={`/audits?id=${scan.id}`}>
              Ver
            </a>
          </li>
        ))}
      </ul>
    </Card>
  );
}
