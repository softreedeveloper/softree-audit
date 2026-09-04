/** Tipos compartidos con la API.
 *
 * A partir del Slice 2 se generan desde OpenAPI con `make openapi`
 * (`src/lib/api-types.ts`). Estos tipos cubren lo que el Slice 1 necesita.
 */

export interface User {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user?: User | null;
}

export interface ApiErrorPayload {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}

export interface HealthResponse {
  status: string;
  environment: string;
  app_version: string;
  scan_engine_version: string;
  report_version: string;
  database: string;
  redis: string;
  ssrf_allow_private_networks: boolean;
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
  total: number | null;
}

export interface Project {
  id: string;
  name: string;
  client_name: string | null;
  notes: string | null;
  sites_count: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectInput {
  name: string;
  client_name?: string | null;
  notes?: string | null;
}

export interface Scope {
  id: string;
  site_id: string;
  allowed_domains: string[];
  allowed_paths: string[];
  excluded_paths: string[];
  max_pages: number;
  max_depth: number;
  timeout_seconds: number;
  request_delay_ms: number;
  concurrency: number;
  respect_robots: boolean;
  zap_spider_enabled: boolean;
  check_external_links: boolean;
  created_at: string;
  updated_at: string;
}

export type ScopeInput = Omit<Scope, 'id' | 'site_id' | 'created_at' | 'updated_at'>;

export interface ScopeLimits {
  max_pages: number;
  max_depth: number;
  timeout_seconds: number;
  request_delay_ms: number;
  concurrency: number;
  domains: number;
  paths: number;
}

export interface Site {
  id: string;
  project_id: string;
  name: string;
  base_url: string;
  authorized_by: string | null;
  authorization_date: string | null;
  authorization_notes: string | null;
  is_active: boolean;
  is_authorized: boolean;
  scans_count: number;
  created_at: string;
  updated_at: string;
}

export interface SiteDetail extends Site {
  scope: Scope;
}

export interface SiteInput {
  project_id?: string;
  name: string;
  base_url: string;
  authorized_by?: string | null;
  authorization_date?: string | null;
  authorization_notes?: string | null;
  is_active: boolean;
}

export type ScanType = 'full' | 'security' | 'seo' | 'performance';

export type ScanStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'partial';

export type ModuleStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped';

export interface ScanModule {
  module: string;
  status: ModuleStatus;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  error: string | null;
  detail: Record<string, unknown> | null;
}

export interface Scan {
  id: string;
  site_id: string;
  scan_type: ScanType;
  status: ScanStatus;
  progress: number;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  error: string | null;
  engine_version: string;
  app_version: string;
  site_name: string;
  site_base_url: string;
  pages_count: number;
}

export interface ScanDetail extends Scan {
  modules: ScanModule[];
  scope_snapshot: Record<string, unknown>;
}

export interface CrawledPage {
  id: string;
  url: string;
  depth: number;
  discovered_from: string | null;
  status_code: number | null;
  content_type: string | null;
  response_time_ms: number | null;
  content_length: number | null;
  title: string | null;
  meta_description: string | null;
  canonical: string | null;
  meta_robots: string | null;
  h1: string[];
  h2: string[];
  internal_links: number;
  external_links: number;
  images_total: number;
  images_missing_alt: number;
  scripts_total: number;
  forms_total: number;
  redirect_chain: { from: string; to: string; status: number }[];
  structured_data: Record<string, unknown>;
  is_indexable: boolean | null;
  error: string | null;
}

/** Estados en los que la auditoría ya no cambia. */
export const TERMINAL_STATUSES: ScanStatus[] = [
  'completed',
  'failed',
  'cancelled',
  'partial',
];

export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info';
export type FindingStatus = 'open' | 'fixed' | 'accepted' | 'false_positive';
export type FindingSource = 'zap' | 'seo' | 'crawler' | 'pagespeed' | 'search_console';
export type FindingCategory =
  | 'security'
  | 'seo'
  | 'performance'
  | 'accessibility'
  | 'best_practices';

export interface Finding {
  id: string;
  scan_id: string;
  source: FindingSource;
  category: FindingCategory;
  rule_id: string | null;
  title: string;
  severity: Severity;
  confidence: 'high' | 'medium' | 'low';
  url: string | null;
  parameter: string | null;
  evidence: string | null;
  description: string;
  impact: string | null;
  remediation: string | null;
  client_explanation: string | null;
  cwe: string | null;
  owasp: string | null;
  references: unknown[];
  occurrences: number;
  status: FindingStatus;
  created_at: string;
  updated_at: string;
}

export interface SeverityCounts {
  critical: number;
  high: number;
  medium: number;
  low: number;
  info: number;
}

export interface SeoResult {
  scan_id: string;
  pages_crawled: number;
  urls_discovered: number;
  missing_title: number;
  duplicate_title: number;
  missing_description: number;
  duplicate_description: number;
  missing_h1: number;
  multiple_h1: number;
  images_missing_alt: number;
  broken_internal_links: number;
  broken_external_links: number;
  missing_canonical: number;
  noindex_pages: number;
  redirect_chains: number;
  robots_txt_found: boolean;
  sitemap_found: boolean;
  sitemap_urls: number;
  structured_data_summary: Record<string, unknown>;
  created_at: string;
}

export const SEVERITY_ORDER: Severity[] = ['critical', 'high', 'medium', 'low', 'info'];

export const SEVERITY_LABEL: Record<Severity, string> = {
  critical: 'Crítica',
  high: 'Alta',
  medium: 'Media',
  low: 'Baja',
  info: 'Informativa',
};

export const STATUS_LABEL_FINDING: Record<FindingStatus, string> = {
  open: 'Abierto',
  fixed: 'Corregido',
  accepted: 'Aceptado',
  false_positive: 'Falso positivo',
};

export interface SecuritySummary {
  scan_id: string;
  scan_status: string;
  finished_at: string | null;
  module_status: string;
  module_detail: {
    zap_version?: string | null;
    urls_submitted?: number;
    spider_ran?: boolean;
    spider_urls?: number;
    alerts_received?: number;
    findings?: number;
    passive_scan_completed?: boolean;
    active_scan?: boolean;
  } | null;
  findings_by_severity: SeverityCounts;
  top_findings: {
    rule_id: string | null;
    title: string;
    severity: Severity;
    confidence: string;
    occurrences: number;
    cwe: string | null;
    owasp: string | null;
  }[];
}

export interface PerformanceResult {
  url: string;
  strategy: 'mobile' | 'desktop';
  performance_score: number | null;
  accessibility_score: number | null;
  best_practices_score: number | null;
  seo_score: number | null;
  lcp_ms: number | null;
  cls: string | null;
  /** `null` significa «sin datos de campo», nunca cero. */
  inp_ms: number | null;
  fcp_ms: number | null;
  tbt_ms: number | null;
  speed_index_ms: number | null;
  lighthouse_version: string | null;
  has_field_data: boolean;
  created_at: string;
}

export interface GoogleScore {
  category: string;
  value: string | null;
  detail: { by_strategy?: Record<string, number>; primary?: string };
}

export interface PerformanceSummary {
  scan_id: string;
  scan_status: string;
  finished_at: string | null;
  module_status: string;
  module_detail: Record<string, unknown> | null;
  results: PerformanceResult[];
  google_scores: GoogleScore[];
  findings_by_severity: SeverityCounts;
}

export interface GoogleStatus {
  project_id: string;
  status: 'not_connected' | 'connected' | 'revoked' | 'error';
  configured: boolean;
  google_account_email: string | null;
  property_url: string | null;
  last_sync_at: string | null;
  last_error: string | null;
}

export interface GoogleProperty {
  site_url: string;
  permission_level: string;
}

export interface SearchConsoleMetric {
  period: '7d' | '28d' | '90d';
  dimension: 'date' | 'query' | 'page' | 'country' | 'device';
  dimension_value: string;
  clicks: number;
  impressions: number;
  ctr: number;
  position: number;
}

export interface ScanSearchConsole {
  scan_id: string;
  module_status: string;
  module_detail: Record<string, unknown> | null;
  property_url: string | null;
  totals: Record<string, { clicks: number; impressions: number; ctr: number; position: number | null; days: number }>;
  metrics: SearchConsoleMetric[];
}

export interface ScoreEntry {
  system: 'softree' | 'google';
  category: string;
  value: string | null;
  weight: string | null;
  detail: Record<string, unknown>;
  engine_version: string;
}

export interface ScanScores {
  scan_id: string;
  softree: ScoreEntry[];
  google: ScoreEntry[];
  softree_overall: string | null;
  band: string | null;
  findings_by_severity: SeverityCounts;
  disclaimer: string;
}

export interface ScoreTrendPoint {
  finished_at: string;
  site_name: string;
  score: number;
}

export interface DashboardData {
  projects: number;
  sites: number;
  authorized_sites: number;
  scans: number;
  scans_in_progress: number;
  average_score: number | null;
  scored_sites: number;
  open_findings_by_severity: Record<Severity, number>;
  /** `null` en una categoría significa que ningún sitio la midió, no cero. */
  score_by_category: Record<string, number | null>;
  score_trend: ScoreTrendPoint[];
  recent_scans: {
    scan_id: string;
    site_name: string;
    site_base_url: string;
    status: ScanStatus;
    scan_type: string;
    queued_at: string;
    finished_at: string | null;
  }[];
}

export interface HistoryEntry {
  scan_id: string;
  scan_type: string;
  status: ScanStatus;
  queued_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  engine_version: string;
  softree_overall: number | null;
  open_findings: number;
}

export type ChangeKind = 'new' | 'fixed' | 'unchanged' | 'regressed';

export interface Comparison {
  current: { scan_id: string; status: string; finished_at: string | null; engine_version: string };
  previous: { scan_id: string; status: string; finished_at: string | null; engine_version: string };
  counts: Record<ChangeKind, number>;
  compared_sources: string[];
  sources_only_in_current: string[];
  sources_only_in_previous: string[];
  changes: {
    kind: ChangeKind;
    fingerprint: string;
    rule_id: string | null;
    title: string;
    severity: Severity;
    category: string;
    url: string | null;
    previous_severity: string | null;
    occurrences: number;
    previous_occurrences: number | null;
  }[];
  metrics: {
    key: string;
    label: string;
    previous: number | null;
    current: number | null;
    delta: number | null;
    direction: 'mejora' | 'empeora' | 'igual' | 'desconocido';
    unit: string;
    higher_is_better: boolean;
  }[];
}

export type ReportFormat = 'pdf' | 'html' | 'json';

export type ReportAudience = 'executive' | 'technical' | 'combined';

export interface ReportEntry {
  id: string;
  scan_id: string;
  format: ReportFormat;
  audience: ReportAudience;
  report_version: string;
  size_bytes: number | null;
  checksum_sha256: string | null;
  generated_at: string;
}

export interface ScoringWeights {
  security: number;
  performance: number;
  seo: number;
  accessibility: number;
  best_practices: number;
}

export interface IntegrationStatus {
  key: string;
  name: string;
  configured: boolean;
  detail: string;
  variables: string[];
  callback_url: string | null;
}

export interface ScopeDefaults {
  max_pages: number;
  max_depth: number;
  timeout_seconds: number;
  request_delay_ms: number;
  concurrency: number;
}

export interface InstanceSettings {
  environment: string;
  app_version: string;
  scan_engine_version: string;
  report_version: string;
  user_email: string;
  user_full_name: string;
  scoring: ScoringWeights;
  integrations: IntegrationStatus[];
  scope_defaults: ScopeDefaults;
  ssrf_allow_private_networks: boolean;
  allowed_ports: number[];
  access_token_ttl_minutes: number;
  refresh_token_ttl_days: number;
}
