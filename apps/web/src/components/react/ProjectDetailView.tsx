/** Detalle de un proyecto: datos y sitios que contiene. */

import { useCallback, useEffect, useState } from 'react';

import { projects as projectsApi, sites as sitesApi } from '../../lib/api';
import type { Project, Site } from '../../lib/types';
import { EmptyState, ErrorState, LoadingState } from './UiStates';
import { Badge, Card, ConfirmInline, Field, FormError, describeError } from './ui';

type Status = 'loading' | 'ready' | 'error' | 'missing';

const EMPTY_SITE = {
  name: '',
  base_url: '',
  authorized_by: '',
  authorization_date: '',
  authorization_notes: '',
};

export default function ProjectDetailView({ projectId }: { projectId: string }) {
  const [status, setStatus] = useState<Status>('loading');
  const [project, setProject] = useState<Project | null>(null);
  const [siteList, setSiteList] = useState<Site[]>([]);
  const [loadError, setLoadError] = useState('');

  const [form, setForm] = useState(EMPTY_SITE);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const [confirming, setConfirming] = useState<Site | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');

  const load = useCallback(async () => {
    setStatus('loading');
    try {
      const [detail, page] = await Promise.all([
        projectsApi.get(projectId),
        sitesApi.list(projectId),
      ]);
      setProject(detail);
      setSiteList(page.items);
      setStatus('ready');
    } catch (error) {
      const status = (error as { status?: number }).status;
      if (status === 404) {
        setStatus('missing');
        return;
      }
      setLoadError(describeError(error));
      setStatus('error');
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onSubmit() {
    setSaving(true);
    setFormError('');
    try {
      await sitesApi.create({
        project_id: projectId,
        name: form.name.trim(),
        base_url: form.base_url.trim(),
        authorized_by: form.authorized_by.trim() || null,
        authorization_date: form.authorization_date || null,
        authorization_notes: form.authorization_notes.trim() || null,
        is_active: true,
      });
      setForm(EMPTY_SITE);
      await load();
    } catch (error) {
      setFormError(describeError(error));
    } finally {
      setSaving(false);
    }
  }

  async function onDelete(site: Site) {
    setDeleting(true);
    setDeleteError('');
    try {
      await sitesApi.remove(site.id, site.scans_count > 0);
      setConfirming(null);
      await load();
    } catch (error) {
      setDeleteError(describeError(error));
    } finally {
      setDeleting(false);
    }
  }

  if (status === 'loading') return <LoadingState label="Cargando el proyecto…" />;
  if (status === 'missing') {
    return (
      <EmptyState
        title="El proyecto no existe"
        description="Puede que se haya eliminado."
        action={
          <a className="sf-btn sf-btn-primary" href="/projects">
            Volver a proyectos
          </a>
        }
      />
    );
  }
  if (status === 'error' || !project) {
    return <ErrorState description={loadError} onRetry={() => void load()} />;
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold">{project.name}</h2>
            <p className="sf-muted text-sm">
              {project.client_name ?? 'Sin cliente asignado'} · {project.sites_count} sitio(s)
            </p>
          </div>
          <a className="sf-btn sf-btn-ghost" href="/projects">
            Volver
          </a>
        </div>
        {project.notes ? (
          <p className="mt-3 break-words text-sm whitespace-pre-line">{project.notes}</p>
        ) : null}
      </Card>

      <Card>
        <h2 className="mb-1 text-sm font-semibold">Nuevo sitio</h2>
        <p className="sf-muted mb-3 text-xs">
          Un sitio solo puede auditarse con autorización registrada. Puede añadirla ahora o más
          tarde.
        </p>
        <form className="grid gap-3 sm:grid-cols-2" onSubmit={(event) => {
            event.preventDefault();
            void onSubmit();
          }} noValidate>
          <Field label="Nombre" htmlFor="site-name">
            <input
              id="site-name"
              className="sf-input"
              required
              maxLength={120}
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
            />
          </Field>
          <Field label="URL base" htmlFor="site-url" hint="Debe empezar por http:// o https://">
            <input
              id="site-url"
              className="sf-input"
              required
              placeholder="https://ejemplo.com"
              value={form.base_url}
              onChange={(event) => setForm({ ...form, base_url: event.target.value })}
            />
          </Field>
          <Field
            label="Autorizado por"
            htmlFor="site-authorized-by"
            hint="Persona o entidad que autoriza la auditoría."
          >
            <input
              id="site-authorized-by"
              className="sf-input"
              maxLength={200}
              value={form.authorized_by}
              onChange={(event) => setForm({ ...form, authorized_by: event.target.value })}
            />
          </Field>
          <Field label="Fecha de autorización" htmlFor="site-authorization-date">
            <input
              id="site-authorization-date"
              className="sf-input"
              type="date"
              value={form.authorization_date}
              onChange={(event) => setForm({ ...form, authorization_date: event.target.value })}
            />
          </Field>
          <div className="sm:col-span-2">
            <Field label="Notas de autorización" htmlFor="site-authorization-notes">
              <input
                id="site-authorization-notes"
                className="sf-input"
                maxLength={2000}
                placeholder="Contrato, correo o referencia"
                value={form.authorization_notes}
                onChange={(event) =>
                  setForm({ ...form, authorization_notes: event.target.value })
                }
              />
            </Field>
          </div>
          <div className="flex flex-wrap items-center gap-2 sm:col-span-2">
            <button
              type="submit"
              className="sf-btn sf-btn-primary"
              disabled={saving || !form.name.trim() || !form.base_url.trim()}
            >
              {saving ? 'Guardando…' : 'Añadir sitio'}
            </button>
            <FormError>{formError}</FormError>
          </div>
        </form>
      </Card>

      {siteList.length === 0 ? (
        <EmptyState
          title="El proyecto no tiene sitios"
          description="Añada la URL del sitio que va a auditar."
        />
      ) : (
        <Card className="!px-0 !py-0">
          <ul className="divide-y" style={{ borderColor: 'var(--border)' }}>
            {siteList.map((site) => (
              <li key={site.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3">
                <div className="w-full min-w-0 sm:w-auto sm:flex-1">
                  <a className="font-medium hover:underline" href={`/sites?id=${site.id}`}>
                    {site.name}
                  </a>
                  <p className="sf-muted truncate text-xs">{site.base_url}</p>
                </div>
                <Badge tone={site.is_authorized ? 'ok' : 'warn'}>
                  {site.is_authorized ? 'Autorizado' : 'Sin autorización'}
                </Badge>
                {site.is_active ? null : <Badge tone="muted">Inactivo</Badge>}

                {confirming?.id === site.id ? (
                  <div className="flex w-full min-w-0 flex-col gap-1">
                    <ConfirmInline
                      message={
                        site.scans_count > 0
                          ? `Eliminar «${site.name}» y sus ${site.scans_count} auditoría(s)?`
                          : `Eliminar «${site.name}»?`
                      }
                      busy={deleting}
                      onConfirm={() => void onDelete(site)}
                      onCancel={() => {
                        setConfirming(null);
                        setDeleteError('');
                      }}
                    />
                    <FormError>{deleteError}</FormError>
                  </div>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    <a className="sf-btn sf-btn-ghost" href={`/sites?id=${site.id}`}>
                      Configurar
                    </a>
                    <button
                      type="button"
                      className="sf-btn sf-btn-ghost"
                      onClick={() => setConfirming(site)}
                    >
                      Eliminar
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
