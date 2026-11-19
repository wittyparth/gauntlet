"use client";

import type { ReactNode } from "react";

import { Progress } from "@/components/ui/progress";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

export type Step = { value: string; label: string; content: ReactNode };

/** Wizard steps: Base UI Tabs, controlled; steps beyond `reached` are disabled. */
export function Stepper({
  steps,
  current,
  reached,
  onChange,
}: {
  steps: Step[];
  current: number;
  reached: number;
  onChange: (index: number) => void;
}) {
  const active = steps[current];
  return (
    <Tabs
      value={active?.value}
      onValueChange={(v) => {
        const i = steps.findIndex((s) => s.value === v);
        if (i >= 0 && i <= reached) onChange(i);
      }}
      className="gap-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <TabsList aria-label="Setup steps">
          {steps.map((s, i) => (
            <TabsTrigger key={s.value} value={s.value} disabled={i > reached}>
              {i + 1} {s.label}
            </TabsTrigger>
          ))}
        </TabsList>
        <div className="flex items-center gap-2">
          <Progress value={((current + 1) / steps.length) * 100} className="w-40" />
          <span className="text-muted-foreground text-xs">
            step {current + 1} of {steps.length}
          </span>
        </div>
      </div>
      {steps.map((s) => (
        <TabsContent key={s.value} value={s.value}>
          {s.content}
        </TabsContent>
      ))}
    </Tabs>
  );
}
