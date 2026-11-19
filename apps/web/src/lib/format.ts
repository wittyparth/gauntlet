/** Money is integer micro-dollars. 4 decimals below $1, 2 above. */
export function formatUsd(usdMicros: number): string {
  const dollars = usdMicros / 1_000_000;
  return `$${dollars.toFixed(Math.abs(dollars) < 1 ? 4 : 2)}`;
}

export function dollarsToMicros(dollars: number): number {
  return Math.round(dollars * 1_000_000);
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(s < 10 ? 1 : 0)}s`;
  const m = Math.floor(s / 60);
  return `${m}m ${Math.round(s - m * 60)}s`;
}

export function formatPercent(fraction: number, digits = 0): string {
  return `${(fraction * 100).toFixed(digits)}%`;
}

/** `ep_01HXYZABCDEFG` becomes `ep_…DEFG`; short ids are left alone. */
export function shortId(id: string): string {
  const i = id.indexOf("_");
  if (i < 0 || id.length <= i + 9) return id;
  return `${id.slice(0, i + 1)}…${id.slice(-4)}`;
}

export function timeAgo(iso: string, now: number = Date.now()): string {
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}
