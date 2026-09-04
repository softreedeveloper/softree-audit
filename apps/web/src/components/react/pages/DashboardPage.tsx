import { useEffect, useState } from 'react';

import { getSession, subscribe, type SessionState } from '../../../lib/session';
import AppShell from '../AppShell';
import DashboardOverview from '../DashboardOverview';

export default function DashboardPage() {
  const [session, setSession] = useState<SessionState>(getSession());

  useEffect(() => subscribe(setSession), []);

  // Solo el nombre de pila: el saludo con nombre y apellidos suena a carta.
  const firstName = session.user?.full_name?.split(' ')[0];

  return (
    <AppShell title="Resumen" current="/dashboard">
      <DashboardOverview userName={firstName} />
    </AppShell>
  );
}
