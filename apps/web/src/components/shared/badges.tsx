import type { ReactNode } from "react";

import { CircleAlert } from "@/components/animate-ui/icons/circle-alert";
import { CircleCheck } from "@/components/animate-ui/icons/circle-check";
import { CircleX } from "@/components/animate-ui/icons/circle-x";
import { Clock } from "@/components/animate-ui/icons/clock";
import { Info } from "@/components/animate-ui/icons/info";
import { LoaderCircle } from "@/components/animate-ui/icons/loader-circle";
import { Pause } from "@/components/animate-ui/icons/pause";
import { TriangleAlert } from "@/components/animate-ui/icons/triangle-alert";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type Tone = "success" | "destructive" | "warning" | "info" | "progress";

const TONE: Record<Tone, string> = {
  success: "border-success/40 bg-success/10 text-success",
  destructive: "border-destructive/40 bg-destructive/10 text-destructive",
  warning: "border-warning/40 bg-warning/10 text-warning",
  info: "border-border bg-muted/50 text-muted-foreground",
  progress: "border-border bg-muted/50 text-foreground",
};

function ToneBadge({
  tone,
  icon,
  children,
  className,
  testId,
}: {
  tone: Tone;
  icon: ReactNode;
  children: ReactNode;
  className?: string;
  testId?: string;
}) {
  return (
    <Badge variant="outline" className={cn(TONE[tone], className)} data-testid={testId}>
      {icon}
      {children}
    </Badge>
  );
}

const iconProps = { size: 12 } as const;
const ICON = {
  success: <CircleCheck {...iconProps} animate />,
  destructive: <CircleX {...iconProps} animate />,
  warning: <TriangleAlert {...iconProps} animate />,
  info: <Info {...iconProps} />,
  progress: <LoaderCircle {...iconProps} animate loop />,
  queued: <Clock {...iconProps} />,
  paused: <Pause {...iconProps} />,
  alert: <CircleAlert {...iconProps} />,
};

const titleCase = (s: string) => s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

export function assertNever(x: never): never {
  throw new Error(`Unhandled value: ${String(x)}`);
}

export type OutcomeValue =
  | "passed"
  | "failed"
  | "invalid_scenario"
  | "simulator_error"
  | "target_error"
  | "platform_error"
  | "budget_exhausted";

export function OutcomeBadge({ outcome }: { outcome: string | null | undefined }) {
  if (!outcome) return null;
  const o = outcome as OutcomeValue;
  switch (o) {
    case "passed":
      return <ToneBadge tone="success" icon={ICON.success}>Passed</ToneBadge>;
    case "failed":
      return <ToneBadge tone="destructive" icon={ICON.destructive}>Failed</ToneBadge>;
    case "invalid_scenario":
    case "simulator_error":
    case "target_error":
    case "platform_error":
    case "budget_exhausted":
      return <ToneBadge tone="warning" icon={ICON.warning}>{titleCase(o)}</ToneBadge>;
    default:
      return <ToneBadge tone="info" icon={ICON.info}>{titleCase(String(o))}</ToneBadge>;
  }
}

export function VerdictBadge({ result }: { result: string }) {
  switch (result) {
    case "pass":
      return <ToneBadge tone="success" icon={ICON.success}>Pass</ToneBadge>;
    case "fail":
      return <ToneBadge tone="destructive" icon={ICON.destructive}>Fail</ToneBadge>;
    case "error":
      return <ToneBadge tone="warning" icon={ICON.warning}>Error</ToneBadge>;
    default:
      return <ToneBadge tone="info" icon={ICON.info}>{result === "na" ? "N/A" : titleCase(result)}</ToneBadge>;
  }
}

export function SeverityBadge({ severity }: { severity: string }) {
  switch (severity) {
    case "critical":
    case "high":
      return <ToneBadge tone="destructive" icon={ICON.destructive}>{titleCase(severity)}</ToneBadge>;
    case "medium":
      return <ToneBadge tone="warning" icon={ICON.warning}>Medium</ToneBadge>;
    default:
      return <ToneBadge tone="info" icon={ICON.info}>{titleCase(severity)}</ToneBadge>;
  }
}

export function RiskBadge({ risk }: { risk: string }) {
  switch (risk) {
    case "read":
      return <Badge variant="secondary" className="text-muted-foreground">read</Badge>;
    case "write":
      return <ToneBadge tone="info" icon={null} className="text-info">write</ToneBadge>;
    default:
      return <ToneBadge tone="warning" icon={ICON.warning} className="bg-transparent">{risk.replace(/_/g, " ")}</ToneBadge>;
  }
}

export function RunStatusBadge({ status }: { status: string }) {
  switch (status) {
    case "running":
      return <ToneBadge tone="progress" icon={ICON.progress}>Running</ToneBadge>;
    case "queued":
      return <ToneBadge tone="info" icon={ICON.queued}>Queued</ToneBadge>;
    case "paused":
      return <ToneBadge tone="warning" icon={ICON.paused}>Paused</ToneBadge>;
    case "done":
      return <ToneBadge tone="success" icon={ICON.success}>Finished</ToneBadge>;
    case "failed":
      return <ToneBadge tone="destructive" icon={ICON.destructive}>Failed</ToneBadge>;
    case "cancelled":
      return <ToneBadge tone="info" icon={ICON.info}>Cancelled</ToneBadge>;
    default:
      return <ToneBadge tone="info" icon={ICON.info}>{titleCase(status)}</ToneBadge>;
  }
}

export function EpisodeStatusBadge({ status }: { status: string }) {
  switch (status) {
    case "leased":
      return <ToneBadge tone="progress" icon={ICON.progress}>Running</ToneBadge>;
    case "queued":
      return <ToneBadge tone="info" icon={ICON.queued}>Queued</ToneBadge>;
    case "done":
      return <ToneBadge tone="info" icon={ICON.info}>Done</ToneBadge>;
    case "cancelled":
      return <ToneBadge tone="info" icon={ICON.info}>Cancelled</ToneBadge>;
    default:
      return <ToneBadge tone="info" icon={ICON.info}>{titleCase(status)}</ToneBadge>;
  }
}

/** Whether an outcome counts toward the pass rate (contract D5). */
export const countsTowardStats = (outcome: string | null | undefined) =>
  outcome === "passed" || outcome === "failed";
