/** Página de proyectos.
 *
 * La salida del sitio es estática, así que el detalle no usa una ruta dinámica
 * sino el parámetro `?id=`, resuelto en el cliente.
 */

import { useEffect, useState } from 'react';

import AppShell from '../AppShell';
import ProjectDetailView from '../ProjectDetailView';
import ProjectsView from '../ProjectsView';

export default function ProjectsPage() {
  const [projectId, setProjectId] = useState<string | null>(null);
  const [resolved, setResolved] = useState(false);

  useEffect(() => {
    setProjectId(new URLSearchParams(window.location.search).get('id'));
    setResolved(true);
  }, []);

  return (
    <AppShell
      title="Proyectos"
      subtitle={projectId ? 'Detalle del proyecto' : 'Proyectos y sitios auditados'}
      current="/projects"
    >
      {resolved ? (
        projectId ? (
          <ProjectDetailView projectId={projectId} />
        ) : (
          <ProjectsView />
        )
      ) : null}
    </AppShell>
  );
}
