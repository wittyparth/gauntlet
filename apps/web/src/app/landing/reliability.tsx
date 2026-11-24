"use client";

import { SlidingNumber } from "@animate-ui/react/primitives/texts/sliding-number";
import { motion, useMotionValueEvent, useScroll } from "motion/react";
import { useRef, useState } from "react";

const P = 0.9;
const KS = [1, 2, 3, 4, 5, 6, 7, 8];
const RAMP = ["#fde725", "#b5de2b", "#6ece58", "#35b779", "#1f9e89", "#2c8fb0", "#5f7fd6", "#7a6ee0"];

const X0 = 64;
const X1 = 628;
const Y0 = 312;
const Y1 = 20;
const r2 = (v: number) => Math.round(v * 100) / 100;
const xOf = (k: number) => X0 + ((k - 0.5) * (X1 - X0)) / 8;
const yOf = (v: number) => r2(Y0 - (Y0 - Y1) * v);

/** Wilson score interval, the product's fallback when a bootstrap collapses to a point. */
function wilson(s: number, n: number): [number, number] {
  const z = 1.959963984540054;
  const p = s / n;
  const d = 1 + (z * z) / n;
  const c = (p + (z * z) / (2 * n)) / d;
  const h = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / d;
  return [Math.max(0, c - h), Math.min(1, c + h)];
}

/**
 * 95% interval as the product computes it (gauntlet_core.stats.passk): a percentile bootstrap over
 * scenarios, widened to contain the point, with a Wilson fallback when it has zero width. The
 * bootstrap distribution of s successes in n scenarios is Binomial(n, s/n); its quantiles are exact here.
 */
function interval(pk: number, n: number): [number, number] {
  const s = Math.round(pk * n);
  const q = s / n;
  if (s === 0 || s === n) return wilson(s, n);
  const lf = [0];
  for (let i = 1; i <= n; i++) lf.push(lf[i - 1] + Math.log(i));
  let cdf = 0;
  let lo = -1;
  let hi = n;
  for (let x = 0; x <= n; x++) {
    cdf += Math.exp(lf[n] - lf[x] - lf[n - x] + x * Math.log(q) + (n - x) * Math.log(1 - q));
    if (lo < 0 && cdf >= 0.025) lo = x;
    if (cdf >= 0.975) {
      hi = x;
      break;
    }
  }
  return [Math.min(lo, s) / n, Math.max(hi, s) / n];
}
/** Episodes accumulated by step k: 10 at k=1 up to 160 at k=8. A function of k alone. */
const episodesAt = (k: number) => Math.round(10 * Math.pow(16, (k - 1) / 7));
const spring = { type: "spring", stiffness: 140, damping: 22 } as const;

function Bar({ k, active, n }: { k: number; active: boolean; n: number }) {
  const p = Math.pow(P, k);
  const [lo, hi] = interval(p, n);
  const yHi = yOf(hi);
  const yLo = yOf(lo);
  const x = xOf(k);
  const c = RAMP[k - 1];
  const w = active ? 16 : 9;
  return (
    <g>
      <motion.rect initial={false} animate={{ y: yHi, height: r2(yLo - yHi), width: w, x: x - w / 2 }} transition={spring} fill={c} opacity={active ? 0.9 : 0.5} />
      <motion.line initial={false} animate={{ y1: yHi, y2: yHi }} transition={spring} x1={x - 14} x2={x + 14} stroke={c} strokeWidth="2" />
      <motion.line initial={false} animate={{ y1: yLo, y2: yLo }} transition={spring} x1={x - 14} x2={x + 14} stroke={c} strokeWidth="2" />
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
  const [k, setK] = useState(1);
  useMotionValueEvent(scrollYProgress, "change", (v) => setK(Math.min(8, Math.max(1, 1 + Math.floor(v * 8)))));

  const n = episodesAt(k);
  const p = Math.pow(P, k);
  const [lo, hi] = interval(p, n);
  const pct = (v: number) => Math.round(v * 100);

  return (
    <div className="lp-rel" ref={ref}>
      <div className="lp-rel-stick">
        <div className="lp-wrap lp-rel-grid">
          <div>
            <h2 className="lp-h2">Reliable once is not reliable.</h2>
            <p className="lp-rel-txt">
              pass<sup>k</sup> asks that the agent succeed on all k attempts at the same task. Scroll: k rises, the
              score decays, and the episodes behind it accumulate until the interval is narrow enough to trust.
              Gauntlet reports the interval, not just the point.
            </p>
          </div>
          <figure>
            <div className="lp-rel-annot mono" aria-live="off">
              <span>
                k = <SlidingNumber number={k} />
              </span>
              <span>
                pass<sup>{k}</sup> = <SlidingNumber number={pct(p)} />%
              </span>
              <span>
                95% CI [<SlidingNumber number={pct(lo)} />, <SlidingNumber number={pct(hi)} />]
              </span>
              <span>
                n = <SlidingNumber number={n} />
              </span>
            </div>
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
                <Bar key={kk} k={kk} n={n} active={kk === k} />
              ))}
              <text x={X1} y={Y0 + 40} textAnchor="end">
                k, attempts that must all pass
              </text>
              <text x={X0 - 12} y={Y1 - 8} textAnchor="end">
                %
              </text>
            </svg>
            <figcaption className="lp-cap">
              <b>Fig. 3.</b> pass<sup>k</sup> with 95% bootstrap intervals, the product&apos;s method, for an agent that passes{" "}
              <span className="mono">90%</span> of single attempts: by k = 8 it passes all eight about{" "}
              <span className="mono">43%</span> of the time. <b>Illustrative:</b> the 90% is assumed, not measured. The
              product computes the real curve per agent (the demo agent&apos;s scorecard reads pass<sup>1</sup>{" "}
              <span className="mono">90%</span>, interval <span className="mono">70 to 100%</span>, n ={" "}
              <span className="mono">10</span>).
            </figcaption>
          </figure>
        </div>
      </div>
    </div>
  );
}
