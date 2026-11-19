"use client";

import { SlidingNumber } from "@animate-ui/react/primitives/texts/sliding-number";

import { formatUsd } from "@/lib/format";
import { cn } from "@/lib/utils";

export function LiveNumber({
  value,
  decimalPlaces = 0,
  className,
}: {
  value: number;
  decimalPlaces?: number;
  className?: string;
}) {
  return (
    <SlidingNumber
      number={value}
      decimalPlaces={decimalPlaces}
      initiallyStable
      className={cn("tabular-nums", className)}
    />
  );
}

/** Integer micro-dollars. Rolls while `live`, plain text otherwise. */
export function Money({
  usdMicros,
  live = false,
  className,
}: {
  usdMicros: number;
  live?: boolean;
  className?: string;
}) {
  if (!live) {
    return <span className={cn("font-mono tabular-nums", className)}>{formatUsd(usdMicros)}</span>;
  }
  const dollars = usdMicros / 1_000_000;
  return (
    <span className={cn("inline-flex font-mono tabular-nums", className)}>
      $<LiveNumber value={dollars} decimalPlaces={dollars < 1 ? 4 : 2} />
    </span>
  );
}
