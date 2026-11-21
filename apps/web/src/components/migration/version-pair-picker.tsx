"use client";

import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { AgentVersion } from "@/lib/api/models";

type Suite = { id: string; name: string };

export type Pair = { base: string; candidate: string; suite: string };

/** Two versions and a suite; the page reads them from the url. */
export function VersionPairPicker({
  versions,
  suites,
  value,
  onChange,
  onGo,
}: {
  versions: AgentVersion[];
  suites: Suite[];
  value: Pair;
  onChange: (next: Pair) => void;
  onGo: () => void;
}) {
  const vItems = versions.map((v) => ({ value: v.id, label: v.label }));
  const sItems = suites.map((s) => ({ value: s.id, label: s.name }));
  const ready = Boolean(value.base && value.candidate && value.suite && value.base !== value.candidate);
  return (
    <div className="flex flex-wrap items-end gap-3" data-testid="pair-picker">
      <label className="flex flex-col gap-1 text-xs">
        Baseline version
        <Select items={vItems} value={value.base || null} onValueChange={(v) => v && onChange({ ...value, base: v })}>
          <SelectTrigger aria-label="Baseline version" className="w-40"><SelectValue placeholder="Baseline" /></SelectTrigger>
          <SelectContent>{versions.map((v) => <SelectItem key={v.id} value={v.id}>{v.label}</SelectItem>)}</SelectContent>
        </Select>
      </label>
      <label className="flex flex-col gap-1 text-xs">
        Candidate version
        <Select items={vItems} value={value.candidate || null} onValueChange={(v) => v && onChange({ ...value, candidate: v })}>
          <SelectTrigger aria-label="Candidate version" className="w-40"><SelectValue placeholder="Candidate" /></SelectTrigger>
          <SelectContent>{versions.map((v) => <SelectItem key={v.id} value={v.id}>{v.label}</SelectItem>)}</SelectContent>
        </Select>
      </label>
      <label className="flex flex-col gap-1 text-xs">
        Suite
        <Select items={sItems} value={value.suite || null} onValueChange={(v) => v && onChange({ ...value, suite: v })}>
          <SelectTrigger aria-label="Suite" className="w-48"><SelectValue placeholder="Suite" /></SelectTrigger>
          <SelectContent>{suites.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}</SelectContent>
        </Select>
      </label>
      <Button disabled={!ready} onClick={onGo}>Compare versions</Button>
    </div>
  );
}
