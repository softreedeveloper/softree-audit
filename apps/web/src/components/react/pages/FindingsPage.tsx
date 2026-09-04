/** Vista transversal de hallazgos. */

import { useEffect, useState } from 'react';

import AppShell from '../AppShell';
import FindingsList from '../FindingsList';

export default function FindingsPage() {
  const [siteId, setSiteId] = useState<string | undefined>();
  const [scanId, setScanId] = useState<string | undefined>();
  const [resolved, setResolved] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setSiteId(params.get('site_id') ?? undefined);
    setScanId(params.get('scan_id') ?? undefined);
    setResolved(true);
  }, []);

  return (
    <AppShell
      title="Hallazgos"
      subtitle="Hallazgos de seguridad, SEO y rendimiento"
      current="/findings"
    >
      {resolved ? <FindingsList siteId={siteId} scanId={scanId} /> : null}
    </AppShell>
  );
}
