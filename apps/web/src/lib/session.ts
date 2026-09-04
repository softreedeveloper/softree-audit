/** Estado de sesión compartido entre islas de React.
 *
 * Astro monta cada isla por separado, así que el estado vive fuera de React y
 * las islas se suscriben. El access token nunca se persiste en el navegador.
 */

import { ensureSession, fetchMe, login as apiLogin, logout as apiLogout } from './api';
import type { User } from './types';

export type SessionStatus = 'loading' | 'authenticated' | 'anonymous';

export interface SessionState {
  status: SessionStatus;
  user: User | null;
}

type Listener = (state: SessionState) => void;

let state: SessionState = { status: 'loading', user: null };
const listeners = new Set<Listener>();
let bootstrapPromise: Promise<void> | null = null;

function emit(next: SessionState): void {
  state = next;
  for (const listener of listeners) {
    listener(state);
  }
}

export function getSession(): SessionState {
  return state;
}

export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  listener(state);
  return () => listeners.delete(listener);
}

/** Restaura la sesión al cargar la página usando la cookie de refresh. */
export function bootstrapSession(): Promise<void> {
  if (bootstrapPromise) {
    return bootstrapPromise;
  }
  bootstrapPromise = (async () => {
    const refreshed = await ensureSession();
    if (!refreshed) {
      emit({ status: 'anonymous', user: null });
      return;
    }
    try {
      const user = await fetchMe();
      emit({ status: 'authenticated', user });
    } catch {
      emit({ status: 'anonymous', user: null });
    }
  })();
  return bootstrapPromise;
}

export async function signIn(email: string, password: string): Promise<User> {
  const data = await apiLogin(email, password);
  const user = data.user ?? (await fetchMe());
  emit({ status: 'authenticated', user });
  return user;
}

export async function signOut(): Promise<void> {
  await apiLogout();
  bootstrapPromise = null;
  emit({ status: 'anonymous', user: null });
}
