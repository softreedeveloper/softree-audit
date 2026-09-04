import AppShell from '../AppShell';
import IntegrationsView from '../IntegrationsView';

export default function IntegrationsPage() {
  return (
    <AppShell
      title="Integrations"
      subtitle="Google Search Console y PageSpeed Insights"
      current="/integrations"
    >
      <IntegrationsView />
    </AppShell>
  );
}
