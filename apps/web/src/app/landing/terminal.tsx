"use client";

import { CopyButton, CopyButtonIcon } from "@animate-ui/react/primitives/buttons/copy";
import { useInView, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";

import { CircleCheck } from "@/components/animate-ui/icons/circle-check";
import { Copy } from "@/components/animate-ui/icons/copy";

const LINES = [
  { c: true, t: "# any Ubuntu or Debian VPS, 4 GB RAM or more" },
  { c: false, t: "git clone <repo-url> /opt/gauntlet && cd /opt/gauntlet" },
  { c: false, t: "sudo ./deploy/bootstrap.sh --domain gauntlet.example.com" },
  { c: true, t: "# prints the admin key once; open the site and paste it" },
];
const TOTAL = LINES.reduce((n, l) => n + l.t.length, 0);
const COPY = LINES.filter((l) => !l.c)
  .map((l) => l.t)
  .join("\n");

export function Terminal() {
  const ref = useRef<HTMLElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.5 });
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(TOTAL);

  useEffect(() => {
    if (reduce || !inView) return;
    let n = 0;
    setShown(0);
    const id = window.setInterval(() => {
      n += 2;
      setShown(Math.min(n, TOTAL));
      if (n >= TOTAL) window.clearInterval(id);
    }, 22);
    return () => window.clearInterval(id);
  }, [inView, reduce]);

  const starts = LINES.map((_, i) => LINES.slice(0, i).reduce((n, l) => n + l.t.length, 0));
  return (
    <figure ref={ref} className="lp-termfig">
      <div className="lp-term-plate">
        <pre className="lp-term" aria-label="Self-host commands">
          {LINES.map((l, i) => {
            const take = Math.max(0, Math.min(l.t.length, shown - starts[i]));
            const typing = take > 0 && take < l.t.length;
            const done = shown >= TOTAL && i === LINES.length - 1;
            return (
              <span key={i} className={l.c ? "c" : undefined}>
                {l.t.slice(0, take)}
                {(typing || done) && <span className="lp-caret" aria-hidden />}
                {"\n"}
              </span>
            );
          })}
        </pre>
        <CopyButton content={COPY} className="lp-copy" aria-label="Copy the commands">
          <CopyButtonIcon icon={<Copy size={16} aria-hidden />} copiedIcon={<CircleCheck size={16} aria-hidden />} />
        </CopyButton>
      </div>
      <figcaption className="lp-cap">
        <b>Fig. 4.</b> Self-host quick start. The script installs Docker if missing, generates secrets, builds, migrates
        and loads the demo data.
      </figcaption>
    </figure>
  );
}

const NODES = [
  { id: "caddy", x: 40, y: 130, sub: ":443, TLS" },
  { id: "web", x: 230, y: 50, sub: "Next.js console" },
  { id: "api", x: 230, y: 130, sub: "FastAPI, /v1" },
  { id: "worker", x: 230, y: 210, sub: "runs, replays" },
  { id: "postgres", x: 450, y: 50, sub: "pgvector" },
  { id: "redis", x: 450, y: 130, sub: "queue" },
  { id: "seaweedfs", x: 450, y: 210, sub: "artifacts" },
] as const;

/** Orthogonal routes only: each bus runs in a gutter between columns, so no wire crosses a label. */
const WIRES = [
  "M40 130 H130", // caddy to bus 1
  "M130 50 V130 M130 50 H230 M130 130 H230", // bus 1 to web (pages) and api (/v1)
  "M230 50 V130", // web to api
  "M230 130 H450 M230 210 H450", // api and worker to the data column
  "M380 50 V210 M380 50 H450 M380 210 H450", // data bus
];

export function Stack() {
  return (
    <figure className="lp-stackfig">
      <svg viewBox="0 0 560 276" role="img" aria-label="Compose services: Caddy fronts web and api; api and worker use Postgres, Redis and SeaweedFS.">
        <line x1="10" x2="550" y1="248" y2="248" stroke="var(--ink-dim)" />
        {[40, 230, 450].map((x, i) => (
          <g key={x}>
            <line x1={x} x2={x} y1="248" y2="254" stroke="var(--ink-dim)" />
            <text x={x} y="270" textAnchor="middle" className="ax">
              {["edge", "app", "data"][i]}
            </text>
          </g>
        ))}
        {WIRES.map((d) => (
          <path key={d} d={d} fill="none" stroke="var(--r-teal)" strokeWidth="1.4" />
        ))}
        {NODES.map((n) => (
          <g key={n.id}>
            <circle cx={n.x} cy={n.y} r="5.5" fill="var(--plate)" stroke="var(--r-green)" strokeWidth="2" />
            <text x={n.x + 4} y={n.y - 12} className="nm">
              {n.id}
            </text>
            <text x={n.x + 4} y={n.y + 22}>
              {n.sub}
            </text>
          </g>
        ))}
      </svg>
      <figcaption className="lp-cap">
        <b>Fig. 5.</b> What runs where: seven services in one Docker Compose file. Caddy sends <code>/v1/*</code> to the
        API and everything else to the console; the worker scales with <code>--scale worker=2</code>.
      </figcaption>
    </figure>
  );
}
