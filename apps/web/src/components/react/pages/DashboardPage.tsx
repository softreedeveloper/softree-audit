import AppShell from '../AppShell';
import DashboardOverview from '../DashboardOverview';

export default function DashboardPage() {
  return (
    <AppShell title="Dashboard" subtitle="Resumen de la plataforma" current="/dashboard">
      <DashboardOverview />
    </AppShell>
  );
}
