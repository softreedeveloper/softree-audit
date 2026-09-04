/** Página de reportes. Requiere `?scan_id=` con la auditoría. */

import { useEffect, useState } from 'react';

import AppShell from '../AppShell';
import ReportsView from '../ReportsView';
import { EmptyState } from '../UiStates';

export default function ReportsPage() {
  const [scanId, setScanId] = useState<string | null>(null);
  const [resolved, setResolved] = useState(false);

  useEffect(() => {
    setScanId(new URLSearchParams(window.location.search).get('scan_id'));
    setResolved(true);
  }, []);

  return (
    <AppShell title="Reports" subtitle="Reportes PDF, HTML y JSON" current="/reports">
      {resolved ? (
        scanId ? (
          <ReportsView scanId={scanId} />
        ) : (
          <EmptyState
            title="Elija una auditoría"
            description="Los reportes se generan a partir de una auditoría concreta."
            action={
              <a className="sf-btn sf-btn-primary" href="/audits">
                Ir a auditorías
              </a>
            }
          />
        )
      ) : null}
    </AppShell>
  );
}
