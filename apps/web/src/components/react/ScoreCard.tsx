/** Softree Score y Google Score, siempre etiquetados y separados (§27). */

import type { ScanScores } from '../../lib/types';
import { Card } from './ui';

const BAND_LABEL: Record<string, string> = {
  excelente: 'Excelente',
  bueno: 'Bueno',
  mejorable: 'Mejorable',
  deficiente: 'Deficiente',
  critico: 'Crítico',
};

const BAND_COLOR: Record<string, string> = {
  excelente: 'var(--color-brand-600)',
  bueno: 'var(--color-brand-400)',
  mejorable: '#d97706',
  deficiente: '#ea580c',
  critico: '#dc2626',
};

const CATEGORY_LABEL: Record<string, string> = {
  overall: 'Global',
  security: 'Seguridad',
  performance: 'Rendimiento',
  seo: 'SEO',
  accessibility: 'Accesibilidad',
  best_practices: 'Buenas prácticas',
};

function toNumber(value: string | null): number | null {
  return value === null ? null : Number(value);
}

export default function ScoreCard({ scores }: { scores: ScanScores }) {
  const overall = toNumber(scores.softree_overall);
  const categories = scores.softree.filter((entry) => entry.category !== 'overall');

  if (overall === null && categories.length === 0 && scores.google.length === 0) {
    return null;
  }

  const color =
    (scores.band ? BAND_COLOR[scores.band] : undefined) ?? 'var(--text-muted)';

  return (
    <Card>
      <div className="flex flex-wrap items-start gap-4 sm:gap-6">
        <div className="flex items-center gap-4">
          <Dial value={overall} color={color} />
          <div>
            <p className="sf-muted text-xs uppercase tracking-wide">Softree Score</p>
            <p className="text-2xl font-semibold" style={{ color }}>
              {overall === null ? '—' : overall.toFixed(1)}
            </p>
            {scores.band ? (
              <p className="sf-muted text-sm">{BAND_LABEL[scores.band] ?? scores.band}</p>
            ) : null}
          </div>
        </div>

        <dl className="grid w-full min-w-0 flex-1 grid-cols-2 gap-3 lg:grid-cols-3">
          {categories.map((entry) => {
            const value = toNumber(entry.value);
            return (
              <div key={entry.category}>
                <dt className="sf-muted text-xs uppercase tracking-wide">
                  {CATEGORY_LABEL[entry.category] ?? entry.category}
                  {entry.weight ? (
                    <span className="ml-1 normal-case">
                      ({(Number(entry.weight) * 100).toFixed(0)} %)
                    </span>
                  ) : null}
                </dt>
                <dd className="text-lg font-semibold">
                  {value === null ? '—' : value.toFixed(1)}
                </dd>
              </div>
            );
          })}
        </dl>
      </div>

      {scores.google.length > 0 ? (
        <div className="mt-4 border-t pt-3" style={{ borderColor: 'var(--border)' }}>
          <p className="sf-muted mb-2 text-xs uppercase tracking-wide">
            Google Lighthouse (puntuación oficial de Google)
          </p>
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {scores.google.map((entry) => (
              <div key={entry.category}>
                <dt className="sf-muted text-xs">
                  {CATEGORY_LABEL[entry.category] ?? entry.category}
                </dt>
                <dd className="font-semibold">
                  {entry.value === null ? '—' : Number(entry.value).toFixed(0)}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      ) : null}

      <p className="sf-muted mt-3 text-xs">{scores.disclaimer}</p>
    </Card>
  );
}

function Dial({ value, color }: { value: number | null; color: string }) {
  const radius = 30;
  const circumference = 2 * Math.PI * radius;
  const filled = value === null ? 0 : (value / 100) * circumference;

  return (
    <svg width="76" height="76" viewBox="0 0 76 76" role="img" aria-label="Softree Score">
      <circle
        cx="38"
        cy="38"
        r={radius}
        fill="none"
        stroke="var(--surface-muted)"
        strokeWidth="8"
      />
      <circle
        cx="38"
        cy="38"
        r={radius}
        fill="none"
        stroke={color}
        strokeWidth="8"
        strokeLinecap="round"
        strokeDasharray={`${filled} ${circumference - filled}`}
        transform="rotate(-90 38 38)"
      />
    </svg>
  );
}
