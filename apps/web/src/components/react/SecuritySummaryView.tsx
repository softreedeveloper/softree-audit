/** Resumen de seguridad de una auditoría (passive scan de OWASP ZAP). */

import type { SecuritySummary } from '../../lib/types';
import { SeverityBadge } from './FindingsList';
import { Card } from './ui';

const MODULE_LABEL: Record<string, string> = {
  completed: 'Completado',
  failed: 'Falló',
  skipped: 'Omitido',
  running: 'En ejecución',
  pending: 'Pendiente',
  no_ejecutado: 'No se ejecutó',
};

const SKIP_REASON: Record<string, string> = {
  zap_no_configurado: 'OWASP ZAP no está configurado en este entorno.',
  zap_no_disponible: 'No fue posible contactar con OWASP ZAP.',
  cancelled: 'La auditoría se canceló antes de llegar a este módulo.',
};

export default function SecuritySummaryView({ summary }: { summary: SecuritySummary }) {
  const detail = summary.module_detail ?? {};
  const reason = typeof detail === 'object' && 'reason' in detail ? String(detail.reason) : null;

  if (summary.module_status !== 'completed') {
    return (
      <Card>
        <h2 className="mb-1 text-sm font-semibold">Análisis de seguridad</h2>
        <p className="text-sm">
          Estado del módulo:{' '}
          <strong>{MODULE_LABEL[summary.module_status] ?? summary.module_status}</strong>
        </p>
        <p className="sf-muted mt-2 text-sm">
          {reason ? (SKIP_REASON[reason] ?? reason) : 'Sin resultados de seguridad para esta auditoría.'}
        </p>
        <p className="sf-muted mt-2 text-xs">
          La ausencia de resultados no significa que el sitio esté limpio.
        </p>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <h2 className="mb-3 text-sm font-semibold">Análisis de seguridad</h2>
        <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Item label="URL analizadas" value={String(detail.urls_submitted ?? 0)} />
          <Item label="Alertas de ZAP" value={String(detail.alerts_received ?? 0)} />
          <Item label="Hallazgos agrupados" value={String(detail.findings ?? 0)} />
          <Item label="Versión de ZAP" value={detail.zap_version ?? '—'} />
        </dl>
        <p className="sf-muted mt-3 text-xs">
          Análisis pasivo: se examinan las respuestas del sitio sin enviarle peticiones de ataque.
          No cubre todas las clases de vulnerabilidad.
          {detail.passive_scan_completed === false
            ? ' La cola de análisis no llegó a vaciarse, así que el resultado puede estar incompleto.'
            : ''}
        </p>
      </Card>

      {summary.top_findings.length === 0 ? (
        <Card>
          <p className="text-sm">
            El análisis pasivo no encontró hallazgos abiertos en esta auditoría.
          </p>
        </Card>
      ) : (
        <Card className="!px-0 !py-0">
          <h2 className="px-4 py-3 text-sm font-semibold">Principales hallazgos</h2>
          <div className="sf-table-wrap">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="sf-muted text-xs uppercase whitespace-nowrap">
                <tr className="border-y" style={{ borderColor: 'var(--border)' }}>
                  <th className="px-4 py-2 font-medium">Severidad</th>
                  <th className="px-2 py-2 font-medium">Regla</th>
                  <th className="px-2 py-2 font-medium">Hallazgo</th>
                  <th className="px-2 py-2 font-medium">Casos</th>
                  <th className="px-2 py-2 font-medium">CWE</th>
                  <th className="px-4 py-2 font-medium">OWASP</th>
                </tr>
              </thead>
              <tbody>
                {summary.top_findings.map((finding) => (
                  <tr
                    key={`${finding.rule_id}-${finding.title}`}
                    className="border-b"
                    style={{ borderColor: 'var(--border)' }}
                  >
                    <td className="px-4 py-2">
                      <SeverityBadge severity={finding.severity} />
                    </td>
                    <td className="px-2 py-2 font-mono text-xs">{finding.rule_id ?? '—'}</td>
                    <td className="px-2 py-2">{finding.title}</td>
                    <td className="px-2 py-2">{finding.occurrences}</td>
                    <td className="px-2 py-2 font-mono text-xs">{finding.cwe ?? '—'}</td>
                    <td className="px-4 py-2 text-xs">{finding.owasp ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

function Item({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="sf-muted text-xs uppercase tracking-wide">{label}</dt>
      <dd className="break-words text-lg font-semibold">{value}</dd>
    </div>
  );
}
