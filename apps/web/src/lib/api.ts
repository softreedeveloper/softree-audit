/** Cliente HTTP de la API.
 *
 * El access token se mantiene solo en memoria; el refresh token vive en una
 * cookie HttpOnly que el navegador envía a `/api/v1/auth` (ADR-008).
 * Ante un 401 se intenta un refresh silencioso una única vez.
 */

import type {
  ApiErrorPayload,
  Comparison,
  CrawledPage,
  DashboardData,
  Finding,
  FindingStatus,
  GoogleProperty,
  GoogleStatus,
  HistoryEntry,
  InstanceSettings,
  Page as PageResponse,
  PerformanceSummary,
  Project,
  ProjectInput,
  ReportEntry,
  ReportFormat,
  Scan,
  ScanDetail,
  ScanType,
  Scope,
  ScopeInput,
  ScopeLimits,
  ScanScores,
  ScanSearchConsole,
  SecuritySummary,
  SeverityCounts,
  Site,
  SiteDetail,
  SiteInput,
  TokenResponse,
  User,
} from './types';

const API_BASE = import.meta.env.PUBLIC_API_BASE_URL ?? '/api/v1';

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details: unknown = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  get isRateLimited(): boolean {
    return this.status === 429;
  }
}

let accessToken: string | null = null;
let refreshInFlight: Promise<boolean> | null = null;
let bootstrapInFlight: Promise<boolean> | null = null;
/** Aumenta con cada token nuevo. Sirve para no pedir dos refrescos a la vez. */
let tokenGeneration = 0;

export function setAccessToken(token: string | null): void {
  accessToken = token;
  tokenGeneration += 1;
}

export function getAccessToken(): string | null {
  return accessToken;
}

async function parseError(response: Response): Promise<ApiError> {
  let code = 'http_error';
  let message = `Error ${response.status}`;
  let details: unknown = null;
  try {
    const payload = (await response.json()) as Partial<ApiErrorPayload>;
    if (payload.error) {
      code = payload.error.code ?? code;
      message = payload.error.message ?? message;
      details = payload.error.details ?? null;
    }
  } catch {
    // Respuesta sin cuerpo JSON: se conserva el mensaje genérico.
  }
  return new ApiError(response.status, code, message, details);
}

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  /** Interno: evita reintentar el refresh en bucle. */
  skipRefresh?: boolean;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, skipRefresh, headers, ...rest } = options;

  // Ninguna llamada sale antes de que la sesión esté resuelta. Sin esta espera,
  // una vista que pide datos al montarse recibiría 401 y dispararía un segundo
  // refresh en paralelo con el inicial; como el refresh token rota, el servidor
  // lo interpretaría como reuso y revocaría la sesión entera.
  if (!skipRefresh) {
    await ensureSession();
  }

  const generation = tokenGeneration;
  const finalHeaders = new Headers(headers);
  if (body !== undefined) {
    finalHeaders.set('Content-Type', 'application/json');
  }
  if (accessToken) {
    finalHeaders.set('Authorization', `Bearer ${accessToken}`);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: finalHeaders,
    credentials: 'same-origin',
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status === 401 && !skipRefresh) {
    // Si otro flujo ya renovó el token mientras esta petición viajaba, basta
    // con reintentar: pedir otro refresh usaría una credencial ya rotada.
    const refreshed =
      tokenGeneration !== generation ? true : await refreshSession();
    if (refreshed) {
      return request<T>(path, { ...options, skipRefresh: true });
    }
  }

  if (!response.ok) {
    throw await parseError(response);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/** Renueva el access token. Coalesce las llamadas concurrentes.
 *
 * El refresh token rota en cada uso, así que dos renovaciones simultáneas
 * harían que la segunda presentara una credencial ya revocada y el servidor
 * cerrara la sesión por reuso. Nunca debe haber más de una en vuelo.
 */
export function refreshSession(): Promise<boolean> {
  if (refreshInFlight) {
    return refreshInFlight;
  }
  refreshInFlight = (async () => {
    try {
      const data = await request<TokenResponse>('/auth/refresh', {
        method: 'POST',
        skipRefresh: true,
      });
      setAccessToken(data.access_token);
      return true;
    } catch {
      setAccessToken(null);
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

/** Restaura la sesión una sola vez por carga de página. */
export function ensureSession(): Promise<boolean> {
  if (accessToken) {
    return Promise.resolve(true);
  }
  if (!bootstrapInFlight) {
    bootstrapInFlight = refreshSession();
  }
  return bootstrapInFlight;
}

/** Olvida la sesión restaurada. Se usa al cerrar sesión. */
export function resetSession(): void {
  setAccessToken(null);
  bootstrapInFlight = null;
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  const data = await request<TokenResponse>('/auth/login', {
    method: 'POST',
    body: { email, password },
    skipRefresh: true,
  });
  setAccessToken(data.access_token);
  bootstrapInFlight = Promise.resolve(true);
  return data;
}

export async function logout(): Promise<void> {
  try {
    await request<void>('/auth/logout', { method: 'POST', skipRefresh: true });
  } finally {
    resetSession();
  }
}

export function fetchMe(): Promise<User> {
  return request<User>('/auth/me');
}

// ── Recursos ────────────────────────────────────────────────────────────────

export const projects = {
  list: (limit = 100): Promise<PageResponse<Project>> =>
    request<PageResponse<Project>>(`/projects?limit=${limit}`),
  get: (id: string): Promise<Project> => request<Project>(`/projects/${id}`),
  create: (body: ProjectInput): Promise<Project> =>
    request<Project>('/projects', { method: 'POST', body }),
  update: (id: string, body: ProjectInput): Promise<Project> =>
    request<Project>(`/projects/${id}`, { method: 'PUT', body }),
  remove: (id: string, force = false): Promise<void> =>
    request<void>(`/projects/${id}${force ? '?force=true' : ''}`, { method: 'DELETE' }),
};

export const sites = {
  list: (projectId?: string, limit = 100): Promise<PageResponse<Site>> => {
    const query = new URLSearchParams({ limit: String(limit) });
    if (projectId) query.set('project_id', projectId);
    return request<PageResponse<Site>>(`/sites?${query.toString()}`);
  },
  get: (id: string): Promise<SiteDetail> => request<SiteDetail>(`/sites/${id}`),
  create: (body: SiteInput): Promise<SiteDetail> =>
    request<SiteDetail>('/sites', { method: 'POST', body }),
  update: (id: string, body: SiteInput): Promise<SiteDetail> =>
    request<SiteDetail>(`/sites/${id}`, { method: 'PUT', body }),
  remove: (id: string, force = false): Promise<void> =>
    request<void>(`/sites/${id}${force ? '?force=true' : ''}`, { method: 'DELETE' }),
  scope: (id: string): Promise<Scope> => request<Scope>(`/sites/${id}/scope`),
  updateScope: (id: string, body: ScopeInput): Promise<Scope> =>
    request<Scope>(`/sites/${id}/scope`, { method: 'PUT', body }),
  scopeLimits: (): Promise<ScopeLimits> => request<ScopeLimits>('/sites/scope-limits'),
  history: (id: string): Promise<HistoryEntry[]> =>
    request<HistoryEntry[]>(`/sites/${id}/history`),
};

export const scans = {
  list: (params: { siteId?: string; status?: string; limit?: number } = {}) => {
    const query = new URLSearchParams({ limit: String(params.limit ?? 50) });
    if (params.siteId) query.set('site_id', params.siteId);
    if (params.status) query.set('status', params.status);
    return request<PageResponse<Scan>>(`/scans?${query.toString()}`);
  },
  get: (id: string): Promise<ScanDetail> => request<ScanDetail>(`/scans/${id}`),
  create: (siteId: string, scanType: ScanType): Promise<ScanDetail> =>
    request<ScanDetail>('/scans', { method: 'POST', body: { site_id: siteId, scan_type: scanType } }),
  cancel: (id: string): Promise<ScanDetail> =>
    request<ScanDetail>(`/scans/${id}/cancel`, { method: 'POST' }),
  pages: (id: string, limit = 100): Promise<PageResponse<CrawledPage>> =>
    request<PageResponse<CrawledPage>>(`/scans/${id}/pages?limit=${limit}`),
  scores: (id: string): Promise<ScanScores> => request<ScanScores>(`/scans/${id}/scores`),
  comparison: (id: string, against = 'previous'): Promise<Comparison> =>
    request<Comparison>(`/scans/${id}/comparison?against=${against}`),
};

export const security = {
  forSite: (siteId: string): Promise<SecuritySummary> =>
    request<SecuritySummary>(`/sites/${siteId}/security`),
};

export const performance = {
  forSite: (siteId: string): Promise<PerformanceSummary> =>
    request<PerformanceSummary>(`/sites/${siteId}/performance`),
};

export const findings = {
  list: (
    params: {
      scanId?: string;
      siteId?: string;
      severity?: string;
      source?: string;
      status?: string;
      limit?: number;
    } = {},
  ) => {
    const query = new URLSearchParams({ limit: String(params.limit ?? 100) });
    if (params.scanId) query.set('scan_id', params.scanId);
    if (params.siteId) query.set('site_id', params.siteId);
    if (params.severity) query.set('severity', params.severity);
    if (params.source) query.set('source', params.source);
    if (params.status) query.set('status', params.status);
    return request<PageResponse<Finding>>(`/findings?${query.toString()}`);
  },
  setStatus: (id: string, status: FindingStatus): Promise<Finding> =>
    request<Finding>(`/findings/${id}`, { method: 'PATCH', body: { status } }),
  severityCounts: (scanId: string): Promise<SeverityCounts> =>
    request<SeverityCounts>(`/scans/${scanId}/severity-counts`),
};

export const google = {
  status: (projectId: string): Promise<GoogleStatus> =>
    request<GoogleStatus>(`/integrations/google/status?project_id=${projectId}`),
  connect: (projectId: string): Promise<{ authorization_url: string; state: string }> =>
    request<{ authorization_url: string; state: string }>('/integrations/google/connect', {
      method: 'POST',
      body: { project_id: projectId },
    }),
  properties: (projectId: string): Promise<GoogleProperty[]> =>
    request<GoogleProperty[]>(`/integrations/google/properties?project_id=${projectId}`),
  selectProperty: (projectId: string, propertyUrl: string): Promise<GoogleStatus> =>
    request<GoogleStatus>('/integrations/google/property', {
      method: 'PUT',
      body: { project_id: projectId, property_url: propertyUrl },
    }),
  disconnect: (projectId: string): Promise<void> =>
    request<void>(`/integrations/google/connection?project_id=${projectId}`, {
      method: 'DELETE',
    }),
  scanMetrics: (scanId: string, period: string, dimension: string): Promise<ScanSearchConsole> =>
    request<ScanSearchConsole>(
      `/scans/${scanId}/search-console?period=${period}&dimension=${dimension}`,
    ),
};

export const dashboard = {
  load: (): Promise<DashboardData> => request<DashboardData>('/dashboard'),
};

export const reports = {
  list: (scanId: string): Promise<ReportEntry[]> =>
    request<ReportEntry[]>(`/reports/${scanId}`),
  generate: (scanId: string, formats: ReportFormat[]): Promise<ReportEntry[]> =>
    request<ReportEntry[]>(`/reports/${scanId}/generate`, {
      method: 'POST',
      body: { formats },
    }),
  downloadUrl: (scanId: string, format: ReportFormat): string =>
    `/api/v1/reports/${scanId}/download?format=${format}`,
  /** Descarga autenticada: la API exige Bearer, así que no vale un enlace directo. */
  download: async (scanId: string, format: ReportFormat): Promise<void> => {
    const response = await fetch(reports.downloadUrl(scanId, format), {
      headers: getAccessToken() ? { Authorization: `Bearer ${getAccessToken()}` } : {},
      credentials: 'same-origin',
    });
    if (!response.ok) {
      throw new ApiError(response.status, 'download_failed', 'No fue posible descargar el reporte.');
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `softree-audit-${scanId}.${format}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },
};

export const instance = {
  settings: (): Promise<InstanceSettings> => request<InstanceSettings>('/settings'),
};
