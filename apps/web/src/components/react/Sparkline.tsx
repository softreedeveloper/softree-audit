/** Línea de tendencia del Softree Score.
 *
 * SVG sin librería: son dos docenas de puntos como mucho. La escala es fija de
 * 0 a 100 porque el score lo es; una escala automática exageraría variaciones
 * de una décima y daría una idea falsa de movimiento.
 */

export default function Sparkline({
  values,
  className = '',
}: {
  values: number[];
  className?: string;
}) {
  if (values.length < 2) return null;

  const width = 600;
  const height = 90;
  const padding = 6;
  const step = (width - padding * 2) / (values.length - 1);

  const points = values.map((value, index) => {
    const clamped = Math.min(100, Math.max(0, value));
    const x = padding + index * step;
    const y = height - padding - (clamped / 100) * (height - padding * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const last = points[points.length - 1]!.split(',');

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className={`w-full ${className}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={`Tendencia del Softree Score: de ${values[0]} a ${values[values.length - 1]}`}
    >
      <polyline
        points={points.join(' ')}
        fill="none"
        stroke="var(--accent)"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
      <circle cx={last[0]} cy={last[1]} r="2.5" fill="var(--accent)" />
    </svg>
  );
}
