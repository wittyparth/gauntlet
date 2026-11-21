"use client";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { useAllVersions } from "@/lib/api/hooks/security";

type Item = ReturnType<typeof useAllVersions>["items"][number];

export const versionLabel = (i: Item) => `${i.agentName} ${i.version.label}`;

export function VersionPicker({
  items,
  value,
  onChange,
  label = "Agent version",
}: {
  items: Item[];
  value: string;
  onChange: (versionId: string) => void;
  label?: string;
}) {
  return (
    <Select
      items={items.map((i) => ({ value: i.version.id, label: versionLabel(i) }))}
      value={value}
      onValueChange={(v) => v && onChange(v)}
    >
      <SelectTrigger size="sm" aria-label={label} className="w-56">
        <SelectValue placeholder="Choose a version" />
      </SelectTrigger>
      <SelectContent>
        {items.map((i) => (
          <SelectItem key={i.version.id} value={i.version.id}>
            {versionLabel(i)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
