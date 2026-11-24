"use client";

import { SlidingNumber } from "@animate-ui/react/primitives/texts/sliding-number";
import { motion, useMotionValueEvent, useScroll, useTransform, type MotionValue } from "motion/react";
import { useRef, useState } from "react";

const P = 0.9;
const KS = [1, 2, 3, 4, 5, 6, 7, 8];
const N0 = 10;
const N1 = 160;
const RAMP = ["#fde725", "#b5de2b", "#6ece58", "#35b779", "#1f9e89", "#2c8fb0", "#5f7fd6", "#7a6ee0"];

const X0 = 64;
const X1 = 628;
const Y0 = 312;
const Y1 = 20;
const xOf = (k: number) => X0 + ((k - 0.5) * (X1 - X0)) / 8;
const yOf = (v: number) => Math.round((Y0 - (Y0 - Y1) * v) * 100) / 100;

/** 95% Wilson interval for a proportion p observed over n trials. */
function wilson(p: number, n: number): [number, number] {
  const z = 1.96;
  const d = 1 + (z * z) / n;
  const c = (p + (z * z) / (2 * n)) / d;
  const h = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / d;
  return [Math.max(0, c - h), Math.min(1, c + h)];
}
const nAt = (t: number) => Math.round(N0 * Math.pow(N1 / N0, t));

function Bar({ k, t, active }: { k: number; t: MotionValue<number>; active: boolean }) {
  const p = Math.pow(P, k);
  const hi = useTransform(t, (v) => yOf(wilson(p, nAt(v))[1]));
  const lo = useTransform(t, (v) => yOf(wilson(p, nAt(v))[0]));
  const h = useTransform(t, (v) => Math.round((yOf(wilson(p, nAt(v))[0]) - yOf(wilson(p, nAt(v))[1])) * 100) / 100);
  const x = xOf(k);
  const c = RAMP[k - 1];
  const w = active ? 16 : 9;
  return (
    <g>
      <motion.rect x={x - w / 2} width={w} y={hi} height={h} fill={c} opacity={active ? 0.9 : 0.5} />
      <motion.line x1={x - 14} x2={x + 14} y1={hi} y2={hi} stroke={c} strokeWidth="2" />
      <motion.line x1={x - 14} x2={x + 14} y1={lo} y2={lo} stroke={c} strokeWidth="2" />
      <circle cx={x} cy={yOf(p)} r={active ? 5.5 : 3.5} fill="var(--plate)" stroke={c} strokeWidth="2.2" />
      <text x={x} y={Y0 + 20} textAnchor="middle" style={active ? { fill: "var(--r-yellow)" } : undefined}>
        {k}
      </text>
    </g>
  );
}

export function Reliability() {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end end"] });
  const [t, setT] = useState(0);
  useMotionValueEvent(scrollYProgress, "change", (v) => setT(Math.min(1, Math.max(0, v))));

  const k = Math.min(8, 1 + Math.floor(t * 8));
  const n = nAt(t);
  const p = Math.pow(P, k);
  const [lo, hi] = wilson(p, n);
  const pct = (v: number) => Math.round(v * 100);

  return (
    <div className="lp-rel" ref={ref}>
      <div className="lp-rel-stick">
        <div className="lp-wrap lp-rel-grid">
          <div className="lp-rel-read">
            <div className="lp-fig-label">
              <b>Fig. 3</b> pass<sup>k</sup> reliability, illustrative
            </div>
            <h2 className="lp-h2" style={{ margin: "1rem 0 1.75rem", fontFamily: "var(--f-display)" }}>
              Reliable once is not reliable.
            </h2>
            <div className="lp-rel-big" aria-live="off">
              <SlidingNumber number={pct(p)} />
              <span className="u">%</span>
            </div>
            <div className="lp-rel-sub">
              <span>
                pass<sup>{k}</sup>
              </span>
              <span className="dim">95% CI</span>
              <span>
                [<SlidingNumber number={pct(lo)} />, <SlidingNumber number={pct(hi)} />]
              </span>
            </div>
            <div className="lp-rel-sub">
              <span className="dim">episodes</span>
              <SlidingNumber number={n} />
            </div>
            <p className="lp-rel-txt">
              pass<sup>k</sup> asks that the agent succeed on all k attempts at the same task. Scroll: k rises, the
              score decays, and more episodes narrow the interval. Gauntlet reports the interval, not just the point.
            </p>
          </div>
          <figure>
            <svg viewBox="0 0 660 350" role="img" aria-label="Confidence interval bars for pass at k equals 1 to 8, narrowing as episodes accumulate. Illustrative, assuming 90 percent per attempt.">
              {[0, 0.25, 0.5, 0.75, 1].map((v) => (
                <g key={v}>
                  <line className={v === 0 ? "ax" : "gr"} x1={X0} x2={X1} y1={yOf(v)} y2={yOf(v)} />
                  <line className="ax" x1={X0 - 6} x2={X0} y1={yOf(v)} y2={yOf(v)} />
                  <text x={X0 - 12} y={yOf(v) + 4} textAnchor="end">
                    {Math.round(v * 100)}
                  </text>
                </g>
              ))}
              <line className="ax" x1={X0} x2={X0} y1={Y1} y2={Y0} />
              {KS.map((kk) => (
                <Bar key={kk} k={kk} t={scrollYProgress} active={kk === k} />
              ))}
              <text x={X1} y={Y0 + 40} textAnchor="end">
                k, attempts that must all pass
              </text>
              <text x={X0 - 12} y={Y1 - 8} textAnchor="end">
                %
              </text>
            </svg>
            <figcaption className="lp-cap">
              <b>Fig. 3.</b> pass<sup>k</sup> with 95% Wilson intervals for an agent that passes{" "}
              <span className="mono">90%</span> of single attempts. <b>Illustrative:</b> that rate is assumed, not
              measured. The product computes the real curve per agent (the demo agent&apos;s scorecard reads pass
              <sup>1</sup> <span className="mono">90%</span>, interval <span className="mono">70 to 100%</span>, n ={" "}
              <span className="mono">10</span>).
            </figcaption>
          </figure>
        </div>
      </div>
    </div>
  );
}
