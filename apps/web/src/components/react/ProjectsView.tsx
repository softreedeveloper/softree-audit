/** Listado, alta, edición y borrado de proyectos. */

import { useCallback, useEffect, useState } from 'react';

import { projects as api } from '../../lib/api';
import type { Project } from '../../lib/types';
import { EmptyState, ErrorState, LoadingState } from './UiStates';
import { Card, ConfirmInline, Field, FormError, describeError } from './ui';

type Status = 'loading' | 'ready' | 'error';

const EMPTY = { name: '', client_name: '', notes: '' };

export default function ProjectsView() {
  const [status, setStatus] = useState<Status>('loading');
  const [items, setItems] = useState<Project[]>([]);
  const [loadError, setLoadError] = useState('');

  const [form, setForm] = useState(EMPTY);
  const [editing, setEditing] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const [confirming, setConfirming] = useState<Project | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');

  const load = useCallback(async () => {
    setStatus('loading');
    try {
      const page = await api.list();
      setItems(page.items);
      setStatus('ready');
    } catch (error) {
      setLoadError(describeError(error));
      setStatus('error');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function resetForm() {
    setForm(EMPTY);
    setEditing(null);
    setFormError('');
  }

  async function onSubmit() {
    setSaving(true);
    setFormError('');
    const payload = {
      name: form.name.trim(),
      client_name: form.client_name.trim() || null,
      notes: form.notes.trim() || null,
    };
    try {
      if (editing) {
        await api.update(editing, payload);
      } else {
        await api.create(payload);
      }
      resetForm();
      await load();
    } catch (error) {
      setFormError(describeError(error));
    } finally {
      setSaving(false);
    }
  }

  async function onDelete(project: Project, force: boolean) {
    setDeleting(true);
    setDeleteError('');
    try {
      await api.remove(project.id, force);
      setConfirming(null);
      await load();
    } catch (error) {
      setDeleteError(describeError(error));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <h2 className="mb-3 text-sm font-semibold">
          {editing ? 'Editar proyecto' : 'Nuevo proyecto'}
        </h2>
        <form className="grid gap-3 sm:grid-cols-2" onSubmit={(event) => {
            event.preventDefault();
            void onSubmit();
          }} noValidate>
          <Field label="Nombre" htmlFor="project-name">
            <input
              id="project-name"
              className="sf-input"
              required
              maxLength={120}
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
            />
          </Field>
          <Field label="Cliente" htmlFor="project-client" hint="Opcional.">
            <input
              id="project-client"
              className="sf-input"
              maxLength={160}
              value={form.client_name}
              onChange={(event) => setForm({ ...form, client_name: event.target.value })}
            />
          </Field>
          <div className="sm:col-span-2">
            <Field label="Notas" htmlFor="project-notes" hint="Opcional.">
              <textarea
                id="project-notes"
                className="sf-input"
                rows={2}
                maxLength={4000}
                value={form.notes}
                onChange={(event) => setForm({ ...form, notes: event.target.value })}
              />
            </Field>
          </div>
          <div className="flex items-center gap-2 sm:col-span-2">
            <button type="submit" className="sf-btn sf-btn-primary" disabled={saving || !form.name.trim()}>
              {saving ? 'Guardando…' : editing ? 'Guardar cambios' : 'Crear proyecto'}
            </button>
            {editing ? (
              <button type="button" className="sf-btn sf-btn-ghost" onClick={resetForm}>
                Cancelar
              </button>
            ) : null}
            <FormError>{formError}</FormError>
          </div>
        </form>
      </Card>

      {status === 'loading' ? <LoadingState label="Cargando proyectos…" /> : null}
      {status === 'error' ? (
        <ErrorState description={loadError} onRetry={() => void load()} />
      ) : null}

      {status === 'ready' && items.length === 0 ? (
        <EmptyState
          title="Todavía no hay proyectos"
          description="Cree el primer proyecto para agrupar los sitios de un cliente."
        />
      ) : null}

      {status === 'ready' && items.length > 0 ? (
        <Card className="!px-0 !py-0">
          <ul className="divide-y" style={{ borderColor: 'var(--border)' }}>
            {items.map((project) => (
              <li key={project.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <a
                    className="font-medium hover:underline"
                    href={`/projects?id=${project.id}`}
                  >
                    {project.name}
                  </a>
                  <p className="sf-muted text-xs">
                    {project.client_name ? `${project.client_name} · ` : ''}
                    {project.sites_count} sitio(s)
                  </p>
                </div>

                {confirming?.id === project.id ? (
                  <div className="flex flex-col gap-1">
                    <ConfirmInline
                      message={
                        project.sites_count > 0
                          ? `Eliminar «${project.name}» y sus ${project.sites_count} sitio(s) con todo su histórico?`
                          : `Eliminar «${project.name}»?`
                      }
                      busy={deleting}
                      onConfirm={() => void onDelete(project, project.sites_count > 0)}
                      onCancel={() => {
                        setConfirming(null);
                        setDeleteError('');
                      }}
                    />
                    <FormError>{deleteError}</FormError>
                  </div>
                ) : (
                  <div className="flex gap-2">
                    <a className="sf-btn sf-btn-ghost" href={`/projects?id=${project.id}`}>
                      Abrir
                    </a>
                    <button
                      type="button"
                      className="sf-btn sf-btn-ghost"
                      onClick={() => {
                        setEditing(project.id);
                        setFormError('');
                        setForm({
                          name: project.name,
                          client_name: project.client_name ?? '',
                          notes: project.notes ?? '',
                        });
                        window.scrollTo({ top: 0, behavior: 'smooth' });
                      }}
                    >
                      Editar
                    </button>
                    <button
                      type="button"
                      className="sf-btn sf-btn-ghost"
                      onClick={() => setConfirming(project)}
                    >
                      Eliminar
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}
