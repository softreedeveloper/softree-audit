/** Conexión de cada proyecto con Google Search Console.
 *
 * La conexión pertenece a un proyecto: los datos de un cliente no se cruzan con
 * los de otro (§53).
 */

import { useCallback, useEffect, useState } from 'react';

import { google, projects as projectsApi } from '../../lib/api';
import type { GoogleProperty, GoogleStatus, Project } from '../../lib/types';
import { EmptyState, ErrorState, LoadingState } from './UiStates';
import { Badge, Card, FormError, describeError } from './ui';

const STATUS_LABEL: Record<GoogleStatus['status'], string> = {
  not_connected: 'No conectado',
  connected: 'Conectado',
  revoked: 'Acceso revocado',
  error: 'Con error',
};

const STATUS_TONE: Record<GoogleStatus['status'], 'ok' | 'warn' | 'muted'> = {
  not_connected: 'muted',
  connected: 'ok',
  revoked: 'warn',
  error: 'warn',
};

export default function IntegrationsView() {
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [items, setItems] = useState<Project[]>([]);
  const [statuses, setStatuses] = useState<Record<string, GoogleStatus>>({});
  const [error, setError] = useState('');
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState('loading');
    try {
      const page = await projectsApi.list();
      setItems(page.items);
      const entries = await Promise.all(
        page.items.map(async (project) => [project.id, await google.status(project.id)] as const),
      );
      setStatuses(Object.fromEntries(entries));
      setState('ready');
    } catch (caught) {
      setError(describeError(caught));
      setState('error');
    }
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const result = params.get('google');
    if (result === 'connected') setNotice('Cuenta de Google conectada.');
    if (result === 'error') {
      setNotice(`No se completó la conexión con Google (${params.get('reason') ?? 'desconocido'}).`);
    }
    void load();
  }, [load]);

  if (state === 'loading') return <LoadingState label="Cargando integraciones…" />;
  if (state === 'error') return <ErrorState description={error} onRetry={() => void load()} />;

  const configured = Object.values(statuses).some((status) => status.configured);

  return (
    <div className="flex flex-col gap-4">
      {notice ? (
        <Card>
          <p className="text-sm">{notice}</p>
        </Card>
      ) : null}

      {!configured ? (
        <Card>
          <h2 className="mb-1 text-sm font-semibold">Google Search Console</h2>
          <p className="sf-muted text-sm">
            La integración no está configurada en este entorno. Defina{' '}
            <code className="font-mono">GOOGLE_CLIENT_ID</code> y{' '}
            <code className="font-mono">GOOGLE_CLIENT_SECRET</code> en el archivo{' '}
            <code className="font-mono">.env</code> y reinicie la API.
          </p>
        </Card>
      ) : null}

      {items.length === 0 ? (
        <EmptyState
          title="No hay proyectos"
          description="Cree un proyecto para conectar su propiedad de Search Console."
          action={
            <a className="sf-btn sf-btn-primary" href="/projects">
              Ir a proyectos
            </a>
          }
        />
      ) : (
        items.map((project) => (
          <ProjectConnection
            key={project.id}
            project={project}
            status={statuses[project.id]}
            onChanged={() => void load()}
          />
        ))
      )}
    </div>
  );
}

function ProjectConnection({
  project,
  status,
  onChanged,
}: {
  project: Project;
  status: GoogleStatus | undefined;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');
  const [properties, setProperties] = useState<GoogleProperty[] | null>(null);

  if (!status) return null;

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setActionError('');
    try {
      await action();
      onChanged();
    } catch (caught) {
      setActionError(describeError(caught));
    } finally {
      setBusy(false);
    }
  }

  async function connect() {
    setBusy(true);
    setActionError('');
    try {
      const { authorization_url } = await google.connect(project.id);
      window.location.assign(authorization_url);
    } catch (caught) {
      setActionError(describeError(caught));
      setBusy(false);
    }
  }

  async function loadProperties() {
    setBusy(true);
    setActionError('');
    try {
      setProperties(await google.properties(project.id));
    } catch (caught) {
      setActionError(describeError(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-semibold">{project.name}</h2>
          <p className="sf-muted break-words text-xs">
            {status.google_account_email ?? 'Sin cuenta conectada'}
            {status.property_url ? ` · ${status.property_url}` : ''}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={STATUS_TONE[status.status]}>{STATUS_LABEL[status.status]}</Badge>
          {status.status === 'not_connected' ? (
            <button
              type="button"
              className="sf-btn sf-btn-primary"
              disabled={busy || !status.configured}
              onClick={() => void connect()}
            >
              Conectar Google
            </button>
          ) : (
            <>
              <button
                type="button"
                className="sf-btn sf-btn-ghost"
                disabled={busy}
                onClick={() => void loadProperties()}
              >
                Elegir propiedad
              </button>
              <button
                type="button"
                className="sf-btn sf-btn-ghost"
                disabled={busy}
                onClick={() => void run(() => google.disconnect(project.id))}
              >
                Desconectar
              </button>
            </>
          )}
        </div>
      </div>

      {status.status === 'revoked' ? (
        <p className="mt-2 text-sm text-amber-600">
          El acceso fue revocado desde la cuenta de Google. Vuelva a conectar para seguir
          recibiendo datos.
        </p>
      ) : null}

      {status.last_error ? <p className="sf-muted mt-2 text-xs">{status.last_error}</p> : null}

      {properties ? (
        <div className="mt-3">
          {properties.length === 0 ? (
            <p className="sf-muted text-sm">
              La cuenta conectada no tiene propiedades en Search Console.
            </p>
          ) : (
            <label className="flex flex-col gap-1.5 text-sm">
              <span className="font-medium">Propiedad del proyecto</span>
              <select
                className="sf-input w-full max-w-lg"
                value={status.property_url ?? ''}
                disabled={busy}
                onChange={(event) =>
                  void run(() => google.selectProperty(project.id, event.target.value))
                }
              >
                <option value="" disabled>
                  Seleccione una propiedad
                </option>
                {properties.map((property) => (
                  <option key={property.site_url} value={property.site_url}>
                    {property.site_url} ({property.permission_level})
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      ) : null}

      <FormError>{actionError}</FormError>
    </Card>
  );
}
