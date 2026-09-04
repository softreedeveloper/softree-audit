/** Página de sitios. Requiere `?id=` con el sitio a configurar. */

import { useEffect, useState } from 'react';

import AppShell from '../AppShell';
import SiteDetailView from '../SiteDetailView';
import { EmptyState } from '../UiStates';

export default function SitesPage() {
  const [siteId, setSiteId] = useState<string | null>(null);
  const [resolved, setResolved] = useState(false);

  useEffect(() => {
    setSiteId(new URLSearchParams(window.location.search).get('id'));
    setResolved(true);
  }, []);

  return (
    <AppShell title="Site" subtitle="Configuración del sitio y su scope" current="/projects">
      {resolved ? (
        siteId ? (
          <SiteDetailView siteId={siteId} />
        ) : (
          <EmptyState
            title="No se indicó ningún sitio"
            description="Abra un sitio desde su proyecto."
            action={
              <a className="sf-btn sf-btn-primary" href="/projects">
                Ir a proyectos
              </a>
            }
          />
        )
      ) : null}
    </AppShell>
  );
}
