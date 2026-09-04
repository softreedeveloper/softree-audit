/** Resultado de rendimiento (Google PageSpeed Insights).
 *
 * La puntuación de Google se presenta etiquetada como tal. El Softree Score es
 * un indicador propio distinto y nunca debe confundirse con este (§27).
 */

import type { PerformanceResult, PerformanceSummary } from '../../lib/types';
import { Card } from './ui';

type Band = 'good' | 'needs_improvement' | 'poor';

const BAND_STYLE: Record<Band, string> = {
  good: 'text-brand-600',
  needs_improvement: 'text-amber-600',
  poor: 'text-red-600',
};

/** Umbrales públicos de Google (web.dev/vitals). */
function metricBand(value: number | null, good: number, needsImprovement: number): Band | null {
  if (value === null) return null;
  if (value <= good) return 'good';
  if (value <= needsImprovement) return 'needs_improvement';
  return 'poor';
}

function scoreBand(score: number | null): Band | null {
  if (score === null) return null;
  if (score >= 90) return 'good';
  if (score >= 50) return 'needs_improvement';
  return 'poor';
}

const SKIP_REASON: Record<string, string> = {
  quota_exceeded:
    'La cuota de la API de PageSpeed Insights está agotada. Configure PAGESPEED_API_KEY o inténtelo más tarde.',
  target_not_reachable:
    'Google no pudo analizar el sitio: la URL debe ser accesible públicamente desde Internet.',
  api_unreachable: 'No fue posible contactar con la API de PageSpeed Insights.',
  cancelled: 'La auditoría se canceló antes de terminar este módulo.',
  sin_resultados: 'No se obtuvo ningún resultado de PageSpeed Insights.',
};

export default function PerformanceSummaryView({ summary }: { summary: PerformanceSummary }) {
  const detail = (summary.module_detail ?? {}) as Record<string, unknown>;

  if (summary.results.length === 0) {
    const reason = typeof detail.reason === 'string' ? detail.reason : null;
    return (
      <Card>
        <h2 className="mb-1 text-sm font-semibold">Rendimiento</h2>
        <p className="text-sm">
          Estado del módulo: <strong>{summary.module_status}</strong>
        </p>
        <p className="sf-muted mt-2 text-sm">
          {reason ? (SKIP_REASON[reason] ?? reason) : 'Sin medidas de rendimiento para esta auditoría.'}
        </p>
      </Card>
    );
  }

  const version = summary.results.find((row) => row.lighthouse_version)?.lighthouse_version;
  const hasFieldData = summary.results.some((row) => row.has_field_data);

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold">Google Lighthouse</h2>
          <span className="sf-muted text-xs">
            Puntuaciones oficiales de Google{version ? ` · Lighthouse ${version}` : ''}
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="sf-muted text-xs uppercase">
              <tr className="border-y" style={{ borderColor: 'var(--border)' }}>
                <th className="px-2 py-2 font-medium">Categoría</th>
                {summary.results.map((row) => (
                  <th key={row.strategy} className="px-2 py-2 font-medium capitalize">
                    {row.strategy}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(
                [
                  ['Rendimiento', 'performance_score'],
                  ['Accesibilidad', 'accessibility_score'],
                  ['Buenas prácticas', 'best_practices_score'],
                  ['SEO', 'seo_score'],
                ] as const
              ).map(([label, key]) => (
                <tr key={key} className="border-b" style={{ borderColor: 'var(--border)' }}>
                  <td className="px-2 py-2">{label}</td>
                  {summary.results.map((row) => {
                    const value = row[key];
                    const band = scoreBand(value);
                    return (
                      <td key={row.strategy} className="px-2 py-2">
                        <span className={band ? BAND_STYLE[band] : 'sf-muted'}>
                          {value ?? '—'}
                        </span>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="sf-muted mt-3 text-xs">
          Estas puntuaciones proceden de la API pública de Google PageSpeed Insights. El Softree
          Score es un indicador propio y no constituye una calificación oficial de Google.
        </p>
      </Card>

      <Card>
        <h2 className="mb-3 text-sm font-semibold">Core Web Vitals</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          {summary.results.map((row) => (
            <Metrics key={row.strategy} result={row} />
          ))}
        </div>
        {!hasFieldData ? (
          <p className="sf-muted mt-3 text-xs">
            El sitio no tiene datos de campo en el informe de experiencia de usuario de Chrome, así
            que INP no está disponible. No es un cero: es una métrica sin datos.
          </p>
        ) : null}
      </Card>
    </div>
  );
}

function Metrics({ result }: { result: PerformanceResult }) {
  const cls = result.cls === null ? null : Number(result.cls);

  const rows: [string, string, Band | null][] = [
    [
      'LCP',
      result.lcp_ms === null ? '—' : `${(result.lcp_ms / 1000).toFixed(1)} s`,
      metricBand(result.lcp_ms, 2500, 4000),
    ],
    ['CLS', cls === null ? '—' : cls.toFixed(3), metricBand(cls, 0.1, 0.25)],
    [
      'INP',
      result.inp_ms === null ? 'sin datos de campo' : `${result.inp_ms} ms`,
      metricBand(result.inp_ms, 200, 500),
    ],
    [
      'FCP',
      result.fcp_ms === null ? '—' : `${(result.fcp_ms / 1000).toFixed(1)} s`,
      metricBand(result.fcp_ms, 1800, 3000),
    ],
    [
      'TBT',
      result.tbt_ms === null ? '—' : `${result.tbt_ms} ms`,
      metricBand(result.tbt_ms, 200, 600),
    ],
    [
      'Speed Index',
      result.speed_index_ms === null ? '—' : `${(result.speed_index_ms / 1000).toFixed(1)} s`,
      metricBand(result.speed_index_ms, 3400, 5800),
    ],
  ];

  return (
    <div>
      <h3 className="sf-muted mb-2 text-xs font-medium uppercase tracking-wide">
        {result.strategy}
      </h3>
      <dl className="grid grid-cols-2 gap-2 text-sm">
        {rows.map(([label, value, band]) => (
          <div key={label} className="flex items-baseline justify-between gap-2">
            <dt className="sf-muted">{label}</dt>
            <dd className={band ? BAND_STYLE[band] : 'sf-muted'}>{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
