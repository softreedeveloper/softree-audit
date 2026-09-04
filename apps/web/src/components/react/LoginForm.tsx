import { useEffect, useState } from 'react';

import { ApiError } from '../../lib/api';
import { bootstrapSession, getSession, signIn } from '../../lib/session';

export default function LoginForm() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(true);

  // Si ya existe una cookie de refresh válida no tiene sentido pedir credenciales.
  useEffect(() => {
    let active = true;
    void bootstrapSession().then(() => {
      if (!active) return;
      if (getSession().status === 'authenticated') {
        window.location.replace('/dashboard');
        return;
      }
      setChecking(false);
    });
    return () => {
      active = false;
    };
  }, []);

  async function onSubmit() {
    setSubmitting(true);
    setError(null);
    try {
      await signIn(email, password);
      window.location.assign('/dashboard');
    } catch (caught) {
      if (caught instanceof ApiError) {
        setError(
          caught.isRateLimited
            ? 'Demasiados intentos. Espere unos minutos antes de volver a intentar.'
            : caught.message,
        );
      } else {
        setError('No fue posible contactar con el servidor.');
      }
      setSubmitting(false);
    }
  }

  return (
    <form className="flex flex-col gap-4" onSubmit={(event) => {
            event.preventDefault();
            void onSubmit();
          }} noValidate>
      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-medium" htmlFor="email">
          Email
        </label>
        <input
          id="email"
          name="email"
          type="email"
          className="sf-input"
          autoComplete="username"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          disabled={submitting || checking}
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-medium" htmlFor="password">
          Contraseña
        </label>
        <input
          id="password"
          name="password"
          type="password"
          className="sf-input"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          disabled={submitting || checking}
        />
      </div>

      {error ? (
        <p className="text-sm text-red-600" role="alert">
          {error}
        </p>
      ) : null}

      <button
        type="submit"
        className="sf-btn sf-btn-primary w-full"
        disabled={submitting || checking || !email || !password}
      >
        {submitting ? 'Verificando…' : 'Iniciar sesión'}
      </button>

      <p className="sf-muted text-xs">
        El acceso es interno. Las cuentas las crea un administrador con{' '}
        <code className="font-mono">softree-audit create-user</code>.
      </p>
    </form>
  );
}
