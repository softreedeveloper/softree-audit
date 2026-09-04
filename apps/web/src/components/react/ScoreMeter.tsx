/** Barra del Softree Score con su escala.
 *
 * Las marcas 0, 50, 75 y 100 son las fronteras de banda del modelo de
 * puntuación: sin ellas un 87 no dice si está cerca o lejos de «excelente».
 */

export default function ScoreMeter({ value }: { value: number }) {
  const clamped = Math.min(100, Math.max(0, value));

  return (
    <div className="w-full">
      <div
        className="h-1.5 w-full overflow-hidden rounded-full"
        style={{ backgroundColor: 'var(--border)' }}
        role="progressbar"
        aria-valuenow={Math.round(clamped)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Softree Score"
      >
        <div
          className="h-full rounded-full"
          style={{ width: `${clamped}%`, backgroundColor: 'var(--accent)' }}
        />
      </div>
      <div className="mt-1.5 flex justify-between text-[11px]" style={{ color: 'var(--text-faint)' }}>
        <span>0</span>
        <span>50</span>
        <span>75</span>
        <span>100</span>
      </div>
    </div>
  );
}
