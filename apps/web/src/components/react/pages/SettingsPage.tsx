import AppShell from '../AppShell';
import SettingsView from '../SettingsView';

export default function SettingsPage() {
  return (
    <AppShell
      title="Settings"
      subtitle="Configuración de la instancia"
      current="/settings"
    >
      <SettingsView />
    </AppShell>
  );
}
