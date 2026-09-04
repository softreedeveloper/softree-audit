/** Página de auditorías: listado, o detalle si llega `?id=`. */

import { useEffect, useState } from 'react';

import AppShell from '../AppShell';
import AuditsView from '../AuditsView';
import ScanDetailView from '../ScanDetailView';

export default function AuditsPage() {
  const [scanId, setScanId] = useState<string | null>(null);
  const [siteId, setSiteId] = useState<string | undefined>();
  const [resolved, setResolved] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setScanId(params.get('id'));
    setSiteId(params.get('site_id') ?? undefined);
    setResolved(true);
  }, []);

  return (
    <AppShell
      title="Audits"
      subtitle={scanId ? 'Detalle de la auditoría' : 'Auditorías ejecutadas y en curso'}
      current="/audits"
    >
      {resolved ? (
        scanId ? (
          <ScanDetailView scanId={scanId} />
        ) : (
          <AuditsView siteId={siteId} />
        )
      ) : null}
    </AppShell>
  );
}
