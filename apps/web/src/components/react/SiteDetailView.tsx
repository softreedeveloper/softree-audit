/** Detalle de un sitio: datos, autorización y configuración de scope. */

import { useCallback, useEffect, useState } from 'react';

import { scans as scansApi, sites as api } from '../../lib/api';
import type { ScanType, ScopeLimits, SiteDetail } from '../../lib/types';
import { EmptyState, ErrorState, LoadingState, SuccessBanner } from './UiStates';
import SiteHistoryView from './SiteHistoryView';
import { Badge, Card, Field, FormError, describeError } from './ui';

type Status = 'loading' | 'ready' | 'error' | 'missing';

function toLines(values: string[]): string {
  return values.join('\n');
}

function fromLines(value: string): string[] {
  return value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
}

export default function SiteDetailView({ siteId }: { siteId: string }) {
  const [status, setStatus] = useState<Status>('loading');
  const [site, setSite] = useState<SiteDetail | null>(null);
  const [limits, setLimits] = useState<ScopeLimits | null>(null);
  const [loadError, setLoadError] = useState('');

  const [siteForm, setSiteForm] = useState({
    name: '',
    base_url: '',
    authorized_by: '',
    authorization_date: '',
    authorization_notes: '',
    is_active: true,
  });
  const [siteSaving, setSiteSaving] = useState(false);
  const [siteError, setSiteError] = useState('');
  const [siteSaved, setSiteSaved] = useState(false);

  const [scopeForm, setScopeForm] = useState({
    allowed_domains: '',
    allowed_paths: '',
    excluded_paths: '',
    max_pages: 200,
    max_depth: 3,
    timeout_seconds: 20,
    request_delay_ms: 200,
    concurrency: 4,
    respect_robots: true,
    zap_spider_enabled: true,
    check_external_links: false,
  });
  const [scopeSaving, setScopeSaving] = useState(false);
  const [scopeError, setScopeError] = useState('');
  const [scopeSaved, setScopeSaved] = useState(false);

  const [scanType, setScanType] = useState<ScanType>('full');
  const [launching, setLaunching] = useState(false);
  const [launchError, setLaunchError] = useState('');

  const apply = useCallback((detail: SiteDetail) => {
    setSite(detail);
    setSiteForm({
      name: detail.name,
      base_url: detail.base_url,
      authorized_by: detail.authorized_by ?? '',
      authorization_date: detail.authorization_date ?? '',
      authorization_notes: detail.authorization_notes ?? '',
      is_active: detail.is_active,
    });
    setScopeForm({
      allowed_domains: toLines(detail.scope.allowed_domains),
      allowed_paths: toLines(detail.scope.allowed_paths),
      excluded_paths: toLines(detail.scope.excluded_paths),
      max_pages: detail.scope.max_pages,
      max_depth: detail.scope.max_depth,
      timeout_seconds: detail.scope.timeout_seconds,
      request_delay_ms: detail.scope.request_delay_ms,
      concurrency: detail.scope.concurrency,
      respect_robots: detail.scope.respect_robots,
      zap_spider_enabled: detail.scope.zap_spider_enabled,
      check_external_links: detail.scope.check_external_links,
    });
  }, []);

  const load = useCallback(async () => {
    setStatus('loading');
    try {
      const [detail, scopeLimits] = await Promise.all([api.get(siteId), api.scopeLimits()]);
      apply(detail);
      setLimits(scopeLimits);
      setStatus('ready');
    } catch (error) {
      if ((error as { status?: number }).status === 404) {
        setStatus('missing');
        return;
      }
      setLoadError(describeError(error));
      setStatus('error');
    }
  }, [siteId, apply]);

  useEffect(() => {
    void load();
  }, [load]);

  async function saveSite() {
    setSiteSaving(true);
    setSiteError('');
    setSiteSaved(false);
    try {
      const detail = await api.update(siteId, {
        name: siteForm.name.trim(),
        base_url: siteForm.base_url.trim(),
        authorized_by: siteForm.authorized_by.trim() || null,
        authorization_date: siteForm.authorization_date || null,
        authorization_notes: siteForm.authorization_notes.trim() || null,
        is_active: siteForm.is_active,
      });
      apply(detail);
      setSiteSaved(true);
    } catch (error) {
      setSiteError(describeError(error));
    } finally {
      setSiteSaving(false);
    }
  }

  async function saveScope() {
    setScopeSaving(true);
    setScopeError('');
    setScopeSaved(false);
    try {
      const scope = await api.updateScope(siteId, {
        allowed_domains: fromLines(scopeForm.allowed_domains),
        allowed_paths: fromLines(scopeForm.allowed_paths),
        excluded_paths: fromLines(scopeForm.excluded_paths),
        max_pages: scopeForm.max_pages,
        max_depth: scopeForm.max_depth,
        timeout_seconds: scopeForm.timeout_seconds,
        request_delay_ms: scopeForm.request_delay_ms,
        concurrency: scopeForm.concurrency,
        respect_robots: scopeForm.respect_robots,
        zap_spider_enabled: scopeForm.zap_spider_enabled,
        check_external_links: scopeForm.check_external_links,
      });
      if (site) apply({ ...site, scope });
      setScopeSaved(true);
    } catch (error) {
      setScopeError(describeError(error));
    } finally {
      setScopeSaving(false);
    }
  }

  async function launchScan() {
    setLaunching(true);
    setLaunchError('');
    try {
      const scan = await scansApi.create(siteId, scanType);
      window.location.assign(`/audits?id=${scan.id}`);
    } catch (error) {
      setLaunchError(describeError(error));
      setLaunching(false);
    }
  }

  if (status === 'loading') return <LoadingState label="Cargando el sitio…" />;
  if (status === 'missing') {
    return (
      <EmptyState
        title="El sitio no existe"
        description="Puede que se haya eliminado."
        action={
          <a className="sf-btn sf-btn-primary" href="/projects">
            Volver a proyectos
          </a>
        }
      />
    );
  }
  if (status === 'error' || !site || !limits) {
    return <ErrorState description={loadError} onRetry={() => void load()} />;
  }

  const numberFields: {
    key: keyof typeof scopeForm;
    label: string;
    max: number;
    min: number;
    hint: string;
  }[] = [
    { key: 'max_pages', label: 'Páginas máximas', min: 1, max: limits.max_pages, hint: `1 a ${limits.max_pages}` },
    { key: 'max_depth', label: 'Profundidad máxima', min: 1, max: limits.max_depth, hint: `1 a ${limits.max_depth}` },
    {
      key: 'timeout_seconds',
      label: 'Timeout (s)',
      min: 1,
      max: limits.timeout_seconds,
      hint: `1 a ${limits.timeout_seconds}`,
    },
    {
      key: 'request_delay_ms',
      label: 'Retardo entre peticiones (ms)',
      min: 0,
      max: limits.request_delay_ms,
      hint: `0 a ${limits.request_delay_ms}`,
    },
    {
      key: 'concurrency',
      label: 'Concurrencia',
      min: 1,
      max: limits.concurrency,
      hint: `1 a ${limits.concurrency}`,
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold">{site.name}</h2>
            <p className="sf-muted truncate text-sm">{site.base_url}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={site.is_authorized ? 'ok' : 'warn'}>
              {site.is_authorized ? 'Autorizado' : 'Sin autorización'}
            </Badge>
            <a className="sf-btn sf-btn-ghost" href={`/projects?id=${site.project_id}`}>
              Volver al proyecto
            </a>
          </div>
        </div>
        {!site.is_authorized ? (
          <p className="sf-muted mt-3 text-xs">
            Sin autorización registrada el sitio no puede auditarse. Complete «Autorizado por» y la
            fecha de autorización.
          </p>
        ) : null}
      </Card>

      <Card>
        <h2 className="mb-1 text-sm font-semibold">Ejecutar auditoría</h2>
        <p className="sf-muted mb-3 text-xs">
          La auditoría se ejecuta en segundo plano. Puede seguir su progreso y cancelarla en
          cualquier momento.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <select
            className="sf-input w-full max-w-full sm:w-48"
            aria-label="Tipo de auditoría"
            value={scanType}
            onChange={(event) => setScanType(event.target.value as ScanType)}
            disabled={!site.is_authorized || !site.is_active}
          >
            <option value="full">Full audit</option>
            <option value="seo">Solo SEO</option>
            <option value="security">Solo seguridad</option>
            <option value="performance">Solo rendimiento</option>
          </select>
          <button
            type="button"
            className="sf-btn sf-btn-primary"
            disabled={launching || !site.is_authorized || !site.is_active}
            onClick={() => void launchScan()}
          >
            {launching ? 'Lanzando…' : 'Ejecutar auditoría'}
          </button>
          <a className="sf-btn sf-btn-ghost" href={`/audits?site_id=${site.id}`}>
            Ver histórico ({site.scans_count})
          </a>
          <FormError>{launchError}</FormError>
        </div>
      </Card>

      <Card>
        <h2 className="mb-3 text-sm font-semibold">Datos y autorización</h2>
        <form className="grid gap-3 sm:grid-cols-2" onSubmit={(event) => {
            event.preventDefault();
            void saveSite();
          }} noValidate>
          <Field label="Nombre" htmlFor="detail-name">
            <input
              id="detail-name"
              className="sf-input"
              required
              maxLength={120}
              value={siteForm.name}
              onChange={(event) => setSiteForm({ ...siteForm, name: event.target.value })}
            />
          </Field>
          <Field
            label="URL base"
            htmlFor="detail-url"
            hint="Al cambiar de dominio, el scope se realinea automáticamente."
          >
            <input
              id="detail-url"
              className="sf-input"
              required
              value={siteForm.base_url}
              onChange={(event) => setSiteForm({ ...siteForm, base_url: event.target.value })}
            />
          </Field>
          <Field label="Autorizado por" htmlFor="detail-authorized-by">
            <input
              id="detail-authorized-by"
              className="sf-input"
              maxLength={200}
              value={siteForm.authorized_by}
              onChange={(event) => setSiteForm({ ...siteForm, authorized_by: event.target.value })}
            />
          </Field>
          <Field label="Fecha de autorización" htmlFor="detail-authorization-date">
            <input
              id="detail-authorization-date"
              className="sf-input"
              type="date"
              value={siteForm.authorization_date}
              onChange={(event) =>
                setSiteForm({ ...siteForm, authorization_date: event.target.value })
              }
            />
          </Field>
          <div className="sm:col-span-2">
            <Field label="Notas de autorización" htmlFor="detail-authorization-notes">
              <input
                id="detail-authorization-notes"
                className="sf-input"
                maxLength={2000}
                value={siteForm.authorization_notes}
                onChange={(event) =>
                  setSiteForm({ ...siteForm, authorization_notes: event.target.value })
                }
              />
            </Field>
          </div>
          <label className="flex items-center gap-2 text-sm sm:col-span-2">
            <input
              type="checkbox"
              checked={siteForm.is_active}
              onChange={(event) => setSiteForm({ ...siteForm, is_active: event.target.checked })}
            />
            Sitio activo
          </label>
          <div className="flex flex-wrap items-center gap-2 sm:col-span-2">
            <button type="submit" className="sf-btn sf-btn-primary" disabled={siteSaving}>
              {siteSaving ? 'Guardando…' : 'Guardar'}
            </button>
            <FormError>{siteError}</FormError>
          </div>
        </form>
        {siteSaved ? <div className="mt-3"><SuccessBanner>Datos del sitio actualizados.</SuccessBanner></div> : null}
      </Card>

      <Card className="!px-0 !py-0">
        <h2 className="px-4 py-3 text-sm font-semibold">Histórico de auditorías</h2>
        <div className="px-4 pb-4">
          <SiteHistoryView siteId={siteId} />
        </div>
      </Card>

      <Card>
        <h2 className="mb-1 text-sm font-semibold">Scope de crawling</h2>
        <p className="sf-muted mb-3 text-xs">
          El scope acota lo que la auditoría puede tocar. Un valor por línea en las listas; las
          rutas se comparan por prefijo y no admiten comodines.
        </p>
        <form className="grid gap-3 sm:grid-cols-3" onSubmit={(event) => {
            event.preventDefault();
            void saveScope();
          }} noValidate>
          <Field
            label="Dominios permitidos"
            htmlFor="scope-domains"
            hint={`Incluye subdominios. Máximo ${limits.domains}.`}
          >
            <textarea
              id="scope-domains"
              className="sf-input font-mono"
              rows={4}
              value={scopeForm.allowed_domains}
              onChange={(event) =>
                setScopeForm({ ...scopeForm, allowed_domains: event.target.value })
              }
            />
          </Field>
          <Field
            label="Rutas permitidas"
            htmlFor="scope-allowed"
            hint="Vacío significa todo el sitio."
          >
            <textarea
              id="scope-allowed"
              className="sf-input font-mono"
              rows={4}
              placeholder="/blog"
              value={scopeForm.allowed_paths}
              onChange={(event) =>
                setScopeForm({ ...scopeForm, allowed_paths: event.target.value })
              }
            />
          </Field>
          <Field label="Rutas excluidas" htmlFor="scope-excluded">
            <textarea
              id="scope-excluded"
              className="sf-input font-mono"
              rows={4}
              placeholder="/admin"
              value={scopeForm.excluded_paths}
              onChange={(event) =>
                setScopeForm({ ...scopeForm, excluded_paths: event.target.value })
              }
            />
          </Field>

          {numberFields.map((field) => (
            <Field key={field.key} label={field.label} htmlFor={`scope-${field.key}`} hint={field.hint}>
              <input
                id={`scope-${field.key}`}
                className="sf-input"
                type="number"
                min={field.min}
                max={field.max}
                value={String(scopeForm[field.key])}
                onChange={(event) =>
                  setScopeForm({ ...scopeForm, [field.key]: Number(event.target.value) })
                }
              />
            </Field>
          ))}

          <div className="flex flex-col gap-2 sm:col-span-3">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={scopeForm.respect_robots}
                onChange={(event) =>
                  setScopeForm({ ...scopeForm, respect_robots: event.target.checked })
                }
              />
              Respetar robots.txt
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={scopeForm.zap_spider_enabled}
                onChange={(event) =>
                  setScopeForm({ ...scopeForm, zap_spider_enabled: event.target.checked })
                }
              />
              Permitir el spider de OWASP ZAP
            </label>
            <label className="flex items-start gap-2 text-sm">
              <input
                className="mt-1"
                type="checkbox"
                checked={scopeForm.check_external_links}
                onChange={(event) =>
                  setScopeForm({ ...scopeForm, check_external_links: event.target.checked })
                }
              />
              <span>
                Comprobar enlaces externos
                <span className="sf-muted block text-xs">
                  Envía una petición a los dominios enlazados para saber si responden. Queda fuera
                  del alcance del sitio auditado, por eso viene desactivado.
                </span>
              </span>
            </label>
          </div>

          <div className="flex flex-wrap items-center gap-2 sm:col-span-3">
            <button type="submit" className="sf-btn sf-btn-primary" disabled={scopeSaving}>
              {scopeSaving ? 'Guardando…' : 'Guardar scope'}
            </button>
            <FormError>{scopeError}</FormError>
          </div>
        </form>
        {scopeSaved ? <div className="mt-3"><SuccessBanner>Scope actualizado.</SuccessBanner></div> : null}
      </Card>
    </div>
  );
}
