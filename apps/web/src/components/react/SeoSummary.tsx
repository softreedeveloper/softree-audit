/** Resumen SEO de una auditoría, a partir de sus agregados. */

import type { SeoResult } from '../../lib/types';
import { Card } from './ui';

interface Indicator {
  label: string;
  value: number;
  /** Un valor mayor que cero es una incidencia. */
  isIssue?: boolean;
}

export default function SeoSummary({ result }: { result: SeoResult }) {
  const indicators: Indicator[] = [
    { label: 'Páginas rastreadas', value: result.pages_crawled },
    { label: 'URL descubiertas', value: result.urls_discovered },
    { label: 'Sin title', value: result.missing_title, isIssue: true },
    { label: 'Title duplicado', value: result.duplicate_title, isIssue: true },
    { label: 'Sin description', value: result.missing_description, isIssue: true },
    { label: 'Description duplicada', value: result.duplicate_description, isIssue: true },
    { label: 'Sin H1', value: result.missing_h1, isIssue: true },
    { label: 'Varios H1', value: result.multiple_h1, isIssue: true },
    { label: 'Imágenes sin alt', value: result.images_missing_alt, isIssue: true },
    { label: 'Enlaces internos rotos', value: result.broken_internal_links, isIssue: true },
    { label: 'Enlaces externos rotos', value: result.broken_external_links, isIssue: true },
    { label: 'Sin canonical', value: result.missing_canonical, isIssue: true },
    { label: 'Páginas noindex', value: result.noindex_pages, isIssue: true },
    { label: 'Cadenas de redirección', value: result.redirect_chains, isIssue: true },
  ];

  const structured = result.structured_data_summary as Record<string, number | string[]>;

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <h2 className="mb-3 text-sm font-semibold">Indicadores SEO</h2>
        <dl className="grid gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {indicators.map((indicator) => (
            <div key={indicator.label}>
              <dt className="sf-muted text-xs uppercase tracking-wide">{indicator.label}</dt>
              <dd
                className={`text-lg font-semibold ${
                  indicator.isIssue && indicator.value > 0 ? 'text-amber-600' : ''
                }`}
              >
                {indicator.value}
              </dd>
            </div>
          ))}
        </dl>
      </Card>

      <div className="grid gap-3 sm:grid-cols-2">
        <Card>
          <h2 className="mb-2 text-sm font-semibold">Archivos del sitio</h2>
          <ul className="flex flex-col gap-1 text-sm">
            <li>
              robots.txt: {result.robots_txt_found ? '✓ presente' : <Missing />}
            </li>
            <li>
              sitemap.xml:{' '}
              {result.sitemap_found ? `✓ presente (${result.sitemap_urls} URL)` : <Missing />}
            </li>
          </ul>
        </Card>

        <Card>
          <h2 className="mb-2 text-sm font-semibold">Datos estructurados</h2>
          <ul className="flex flex-col gap-1 text-sm">
            <li>Páginas con JSON-LD: {String(structured.pages_with_json_ld ?? 0)}</li>
            <li>Páginas con OpenGraph: {String(structured.pages_with_open_graph ?? 0)}</li>
            <li>Páginas con Twitter Cards: {String(structured.pages_with_twitter_cards ?? 0)}</li>
            <li>
              Bloques JSON-LD inválidos: {String(structured.invalid_json_ld_blocks ?? 0)}
            </li>
            <li className="sf-muted text-xs">
              Tipos detectados:{' '}
              {Array.isArray(structured.schema_types) && structured.schema_types.length > 0
                ? structured.schema_types.join(', ')
                : 'ninguno'}
            </li>
          </ul>
        </Card>
      </div>
    </div>
  );
}

function Missing() {
  return <span className="text-amber-600">no encontrado</span>;
}
