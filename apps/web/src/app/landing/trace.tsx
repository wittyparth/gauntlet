type Step = { label: string; held: boolean; blocked?: boolean };

const W = 300;
const HI = 26;
const LO = 82;
const AXIS = 106;

/** One panel's plot: attacker objective (held / not held) against steps. Same grammar in every panel. */
export function Trace({ steps, title }: { steps: Step[]; title: string }) {
  const gap = W / steps.length;
  const xs = steps.map((_, i) => gap * (i + 0.5));
  const ys = steps.map((s) => (s.held ? HI : LO));
  const path = xs.map((x, i) => `${i ? "L" : "M"}${x},${ys[i]}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} 128`} role="img" aria-label={title}>
      <line x1="0" x2={W} y1={HI} y2={HI} stroke="var(--rule-faint)" />
      <line x1="0" x2={W} y1={LO} y2={LO} stroke="var(--rule-faint)" />
      <line x1="0" x2={W} y1={AXIS} y2={AXIS} stroke="var(--ink-dim)" />
      {xs.map((x, i) => (
        <line key={i} x1={x} x2={x} y1={AXIS} y2={AXIS + 5} stroke="var(--ink-dim)" />
      ))}
      <text x="0" y={HI - 6}>objective held</text>
      <text x="0" y={LO - 13}>not held</text>
      <path d={path} fill="none" stroke="var(--r-teal)" strokeWidth="1.5" />
      {steps.map((s, i) => {
        const x = xs[i];
        const y = ys[i];
        if (s.held)
          return (
            <g key={i} stroke="var(--fail)" strokeWidth="2.2">
              <line x1={x - 6} x2={x + 6} y1={y - 6} y2={y + 6} />
              <line x1={x - 6} x2={x + 6} y1={y + 6} y2={y - 6} />
            </g>
          );
        if (s.blocked)
          return (
            <g key={i}>
              <line x1={x} x2={x} y1={HI - 10} y2={AXIS} stroke="var(--r-yellow)" strokeWidth="2.2" />
              <circle cx={x} cy={y} r="5" fill="var(--plate)" stroke="var(--r-green)" strokeWidth="2" />
            </g>
          );
        return <circle key={i} cx={x} cy={y} r="5" fill="var(--plate)" stroke="var(--r-green)" strokeWidth="2" />;
      })}
      {steps.map((s, i) => (
        <text key={i} x={xs[i]} y={AXIS + 18} textAnchor="middle">
          {s.label}
        </text>
      ))}
    </svg>
  );
}
