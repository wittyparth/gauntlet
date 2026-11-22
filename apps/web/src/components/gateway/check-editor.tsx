"use client";

import { CheckTree } from "@/components/scenarios/check-tree";
import { Textarea } from "@/components/ui/textarea";

import { parseCheck } from "./check-validation";

/** The `when` check as JSON, with a live read-only tree beside it and inline errors. */
export function CheckEditor({ value, onChange, serverError }: { value: string; onChange: (v: string) => void; serverError?: string | null }) {
  const parsed = parseCheck(value);
  const error = !parsed.ok ? parsed.message : (serverError ?? null);
  return (
    <div className="grid gap-3 md:grid-cols-2" data-testid="check-editor">
      <div className="flex flex-col gap-1">
        <Textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          spellCheck={false}
          rows={10}
          className="font-mono text-xs"
          aria-label="when (JSON)"
          aria-invalid={Boolean(error)}
          aria-describedby="check-error"
        />
        {error ? (
          <p id="check-error" role="alert" className="text-destructive text-xs" data-testid="check-error">
            {error}
          </p>
        ) : null}
      </div>
      <div className="rounded-md border p-2" aria-label="Check preview">
        {parsed.ok ? <CheckTree check={parsed.value} /> : <p className="text-muted-foreground text-xs">Fix the JSON to see the preview.</p>}
      </div>
    </div>
  );
}
