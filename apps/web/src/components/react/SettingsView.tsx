/** Configuración efectiva de la instancia.
 *
 * Solo lectura: los valores viven en el archivo `.env` del despliegue, no en
 * base de datos (§40). Aquí se muestran para poder comprobarlos sin entrar al
 * servidor, y nunca se expone ningún secreto: solo si está presente.
 */

import { useCallback, useEffect, useState } from 'react';

import { instance } from '../../lib/api';
import type { InstanceSettings } from '../../lib/types';
import { ErrorState, LoadingState } from './UiStates';
import ThemeToggle from './ThemeToggle';
import { Badge, Card, describeError } from './ui';

const CATEGORY_LABEL: Record<string, string> = {
  security: 'Seguridad',
  performance: 'Rendimiento',
  seo: 'SEO',
  accessibility: 'Accesibilidad',
  best_practices: 'Buenas prácticas',
};

export default function SettingsView() {
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [data, setData] = useState<InstanceSettings | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setState('loading');
    try {
      setData(await instance.settings());
      setState('ready');
    } catch (caught) {
      setError(describeError(caught));
      setState('error');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (state === 'loading') return <LoadingState label="Cargando la configuración…" />;
  if (state === 'error' || !data) {
    return <ErrorState description={error} onRetry={() => void load()} />;
  }

  const weights = Object.entries(data.scoring) as [keyof typeof data.scoring, number][];
  const total = weights.reduce((sum, [, value]) => sum + value, 0);

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <h2 className="mb-3 text-sm font-semibold">Cuenta</h2>
        <dl className="grid gap-3 sm:grid-cols-3">
          <Item label="Usuario" value={data.user_full_name} />
          <Item label="Email" value={data.user_email} />
          <Item label="Entorno" value={data.environment} />
        </dl>
        <div className="mt-4 flex items-center gap-3 border-t pt-3" style={{ borderColor: 'var(--border)' }}>
          <span className="sf-muted text-xs uppercase tracking-wide">Tema</span>
          <ThemeToggle />
        </div>
      </Card>

      <Card>
        <h2 className="mb-1 text-sm font-semibold">Pesos del Softree Score</h2>
        <p className="sf-muted mb-3 text-xs">
          Se leen de <code className="font-mono">SCORING_WEIGHTS</code> al arrancar. Una categoría
          sin datos no cuenta como cero: su peso se reparte entre las demás, y el peso aplicado se
          guarda con cada auditoría para que un cambio no altere el histórico.
        </p>
        <dl className="grid gap-3 sm:grid-cols-5">
          {weights.map(([key, value]) => (
            <Item
              key={key}
              label={CATEGORY_LABEL[key] ?? key}
              value={`${(value * 100).toFixed(0)} %`}
            />
          ))}
        </dl>
        {Math.abs(total - 1) > 0.001 ? (
          <p className="mt-3 text-xs text-amber-600">
            Los pesos suman {(total * 100).toFixed(0)} %. Se renormalizan al calcular el score.
          </p>
        ) : null}
      </Card>

      <Card>
        <h2 className="mb-3 text-sm font-semibold">Integraciones</h2>
        <ul className="flex flex-col gap-3">
          {data.integrations.map((integration) => (
            <li
              key={integration.key}
              className="flex flex-wrap items-start justify-between gap-3 border-b pb-3 last:border-0 last:pb-0"
              style={{ borderColor: 'var(--border)' }}
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{integration.name}</p>
                <p className="sf-muted text-xs">{integration.detail}</p>
                <p className="sf-muted mt-1 font-mono text-xs">
                  {integration.variables.join(' · ')}
                </p>
              </div>
              <Badge tone={integration.configured ? 'ok' : 'warn'}>
                {integration.configured ? 'Configurada' : 'Sin configurar'}
              </Badge>
            </li>
          ))}
        </ul>
      </Card>

      <Card>
        <h2 className="mb-1 text-sm font-semibold">Límites y seguridad</h2>
        <p className="sf-muted mb-3 text-xs">
          Ningún scope puede superar estos máximos, aunque se pidan valores mayores.
        </p>
        <dl className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <Item label="Páginas máximas" value={String(data.scope_defaults.max_pages)} />
          <Item label="Profundidad máxima" value={String(data.scope_defaults.max_depth)} />
          <Item label="Timeout (s)" value={String(data.scope_defaults.timeout_seconds)} />
          <Item label="Concurrencia" value={String(data.scope_defaults.concurrency)} />
          <Item label="Puertos permitidos" value={data.allowed_ports.join(', ')} />
        </dl>

        <div className="mt-4 grid gap-3 border-t pt-3 sm:grid-cols-3" style={{ borderColor: 'var(--border)' }}>
          <Item label="Access token" value={`${data.access_token_ttl_minutes} min`} />
          <Item label="Refresh token" value={`${data.refresh_token_ttl_days} días`} />
          <div>
            <dt className="sf-muted text-xs uppercase tracking-wide">Redes privadas</dt>
            <dd
              className={`text-lg font-semibold ${
                data.ssrf_allow_private_networks ? 'text-amber-600' : ''
              }`}
            >
              {data.ssrf_allow_private_networks ? 'Permitidas' : 'Bloqueadas'}
            </dd>
          </div>
        </div>

        {data.ssrf_allow_private_networks ? (
          <p className="mt-3 text-xs text-amber-600">
            El acceso a redes privadas está habilitado. Es una opción exclusiva de desarrollo,
            para poder auditar el sitio de pruebas local, y debe estar desactivada en producción.
          </p>
        ) : null}
      </Card>

      <Card>
        <h2 className="mb-3 text-sm font-semibold">Versiones</h2>
        <p className="sf-muted mb-3 text-xs">
          Cada auditoría y cada reporte guardan la versión con la que se produjeron, para poder
          comparar resultados entre versiones del motor.
        </p>
        <dl className="grid gap-3 sm:grid-cols-3">
          <Item label="Softree Audit" value={data.app_version} mono />
          <Item label="Motor de scan" value={data.scan_engine_version} mono />
          <Item label="Reporte" value={data.report_version} mono />
        </dl>
      </Card>
    </div>
  );
}

function Item({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="sf-muted text-xs uppercase tracking-wide">{label}</dt>
      <dd className={`text-lg font-semibold ${mono ? 'font-mono text-base' : ''}`}>{value}</dd>
    </div>
  );
}
