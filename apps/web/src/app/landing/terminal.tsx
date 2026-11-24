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
        <div className="lp-term-ticks" aria-hidden>
          {LINES.map((_, i) => (
            <i key={i} />
          ))}
        </div>
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
  { id: "caddy", x: 40, y: 80, sub: ":443, TLS" },
  { id: "web", x: 190, y: 40, sub: "Next.js console" },
  { id: "api", x: 190, y: 120, sub: "FastAPI, /v1" },
  { id: "worker", x: 190, y: 200, sub: "runs, replays" },
  { id: "postgres", x: 350, y: 40, sub: "pgvector" },
  { id: "redis", x: 350, y: 120, sub: "queue" },
  { id: "minio", x: 350, y: 200, sub: "artifacts" },
] as const;
const EDGES: [string, string][] = [
  ["caddy", "web"],
  ["caddy", "api"],
  ["web", "api"],
  ["api", "postgres"],
  ["api", "redis"],
  ["api", "minio"],
  ["worker", "postgres"],
  ["worker", "redis"],
  ["worker", "minio"],
];

export function Stack() {
  const at = (id: string) => NODES.find((n) => n.id === id)!;
  return (
    <figure className="lp-stackfig">
      <svg viewBox="0 0 430 252" role="img" aria-label="Compose services: Caddy fronts web and api; api and worker use Postgres, Redis and MinIO.">
        {[40, 190, 350].map((x, i) => (
          <g key={x}>
            <line x1={x} x2={x} y1="14" y2="226" stroke="var(--rule-faint)" />
            <line x1={x} x2={x} y1="226" y2="232" stroke="var(--ink-dim)" />
            <text x={x} y="246" textAnchor="middle">
              {["edge", "app", "data"][i]}
            </text>
          </g>
        ))}
        <line x1="10" x2="420" y1="226" y2="226" stroke="var(--ink-dim)" />
        {EDGES.map(([a, b]) => (
          <line key={a + b} x1={at(a).x} y1={at(a).y} x2={at(b).x} y2={at(b).y} stroke="var(--r-teal)" strokeWidth="1.2" opacity="0.75" />
        ))}
        {NODES.map((n) => (
          <g key={n.id}>
            <circle cx={n.x} cy={n.y} r="5.5" fill="var(--plate)" stroke="var(--r-green)" strokeWidth="2" />
            <text x={n.x} y={n.y - 12} textAnchor="middle" className="nm">
              {n.id}
            </text>
            <text x={n.x} y={n.y + 20} textAnchor="middle">
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
