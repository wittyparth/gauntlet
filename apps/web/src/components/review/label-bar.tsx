"use client";

import { useHotkeys } from "react-hotkeys-hook";

import { Button } from "@/components/ui/button";
import type { LabelResult } from "@/lib/api/hooks/review";

export const LABEL_KEYS = { pass: "p", fail: "f", na: "n" } as const;

export type LabelBarProps = {
  disabled?: boolean;
  onLabel: (result: LabelResult) => void;
  onSkip: () => void;
  onNext: () => void;
  onPrev: () => void;
  onToggleJudge: () => void;
  announcement: string;
};

/** Keyboard first: p pass, f fail, n not applicable, s skip, j next, k previous, h judge. */
export function LabelBar({ disabled, onLabel, onSkip, onNext, onPrev, onToggleJudge, announcement }: LabelBarProps) {
  const opts = { enabled: !disabled, preventDefault: true };
  useHotkeys("p", () => onLabel("pass"), opts, [onLabel, disabled]);
  useHotkeys("f", () => onLabel("fail"), opts, [onLabel, disabled]);
  useHotkeys("n", () => onLabel("na"), opts, [onLabel, disabled]);
  useHotkeys("s", onSkip, opts, [onSkip, disabled]);
  useHotkeys("j", onNext, opts, [onNext, disabled]);
  useHotkeys("k", onPrev, opts, [onPrev, disabled]);
  useHotkeys("h", onToggleJudge, { preventDefault: true }, [onToggleJudge]);
  return (
    <div className="bg-background sticky bottom-0 flex flex-col gap-1 border-t p-3" data-testid="label-bar">
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Label this trajectory">
        <Button disabled={disabled} onClick={() => onLabel("pass")}>Pass <kbd className="font-mono text-xs">p</kbd></Button>
        <Button variant="destructive" disabled={disabled} onClick={() => onLabel("fail")}>Fail <kbd className="font-mono text-xs">f</kbd></Button>
        <Button variant="outline" disabled={disabled} onClick={() => onLabel("na")}>N/A <kbd className="font-mono text-xs">n</kbd></Button>
        <Button variant="ghost" disabled={disabled} onClick={onSkip}>Skip <kbd className="font-mono text-xs">s</kbd></Button>
        <span className="text-muted-foreground ml-auto text-xs">j next, k previous, h judge prediction</span>
      </div>
      <p className="sr-only" aria-live="polite" data-testid="label-announcement">{announcement}</p>
    </div>
  );
}
