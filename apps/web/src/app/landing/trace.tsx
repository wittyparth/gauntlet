type Step = { label: string; held: boolean; blocked?: boolean };
type Note = { text: string; step: number; tone: "fail" | "ok" };

const W = 300;
const GUT = 70;
const HI = 30;
const LO = 86;
const AXIS = 108;

/** One panel's plot: attacker objective (held / not held) against steps. Same grammar in every panel. */
export function Trace({ steps, title, note }: { steps: Step[]; title: string; note: Note }) {
  const gap = (W - GUT) / steps.length;
  const xs = steps.map((_, i) => GUT + gap * (i + 0.5));
  const ys = steps.map((s) => (s.held ? HI : LO));
  const path = xs.map((x, i) => `${i ? "L" : "M"}${x},${ys[i]}`).join(" ");
  const nx = xs[note.step];
  return (
    <svg viewBox={`0 0 ${W} 132`} role="img" aria-label={title}>
      <line x1={GUT - 8} x2={W} y1={HI} y2={HI} stroke="var(--rule)" />
      <line x1={GUT - 8} x2={W} y1={LO} y2={LO} stroke="var(--rule-faint)" />
      <line x1={GUT - 8} x2={W} y1={AXIS} y2={AXIS} stroke="var(--ink-dim)" />
      <line x1={GUT - 8} x2={GUT - 8} y1={HI - 6} y2={AXIS} stroke="var(--ink-dim)" />
      <text x={GUT - 14} y={HI + 3} textAnchor="end">
        held
      </text>
      <text x={GUT - 14} y={LO + 3} textAnchor="end">
        not held
      </text>
      {xs.map((x, i) => (
        <line key={i} x1={x} x2={x} y1={AXIS} y2={AXIS + 5} stroke="var(--ink-dim)" />
      ))}
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
        return (
          <g key={i}>
            {s.blocked && <line x1={x} x2={x} y1={HI} y2={AXIS} stroke="var(--r-yellow)" strokeWidth="2.2" />}
            <circle cx={x} cy={y} r="5" fill="var(--plate)" stroke="var(--r-green)" strokeWidth="2" />
          </g>
        );
      })}
      <text x={Math.min(nx + 6, W)} y={HI - 10} textAnchor="end" className={note.tone === "fail" ? "an fail" : "an"}>
        {note.text}
      </text>
      {steps.map((s, i) => (
        <text key={i} x={xs[i]} y={AXIS + 20} textAnchor="middle">
          {s.label}
        </text>
      ))}
    </svg>
  );
}
