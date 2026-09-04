/** Página de una sección todavía no implementada.
 *
 * Mantiene la navegación y los estados de sesión funcionando, y declara con
 * claridad en qué slice llega la funcionalidad, en lugar de mostrar una
 * pantalla en blanco o datos ficticios (§38, regla 8 de §58).
 */

import AppShell from '../AppShell';
import { PlannedState } from '../UiStates';

interface Props {
  title: string;
  subtitle: string;
  current: string;
  slice: string;
}

export default function PlaceholderPage({ title, subtitle, current, slice }: Props) {
  return (
    <AppShell title={title} subtitle={subtitle} current={current}>
      <PlannedState title={`${title} todavía no está disponible`} slice={slice} />
    </AppShell>
  );
}
