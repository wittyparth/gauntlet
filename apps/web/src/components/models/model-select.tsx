"use client";

import { Info } from "@/components/animate-ui/icons/info";
import { Badge } from "@/components/ui/badge";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { ModelCatalogEntry } from "@/lib/api/models";

import { priceLabel } from "./draft";

/** Details of one catalog model, shown in a hover card next to the picker. */
export function ModelDetails({ model, role }: { model: ModelCatalogEntry; role?: string }) {
  return (
    <div className="flex flex-col gap-2 text-sm" data-testid="model-details">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium">{model.name}</span>
        <span className="text-muted-foreground font-mono text-xs">{priceLabel(model)}</span>
      </div>
      <p className="text-muted-foreground">{model.description}</p>
      <div className="flex flex-wrap gap-1">
        {model.good_for.map((t) => (
          <Badge key={t} variant="secondary">{t}</Badge>
        ))}
      </div>
      <p className="text-muted-foreground text-xs">
        {(model.context_length / 1000).toLocaleString("en-US")}k context, {model.provider_family}.
        {role && model.recommended_roles.includes(role) ? " Recommended for this role." : ""}
      </p>
    </div>
  );
}

/** A catalog-based model picker. `role` marks the models recommended for it. */
export function ModelSelect({
  id,
  catalog,
  value,
  onChange,
  role,
  label,
}: {
  id?: string;
  catalog: ModelCatalogEntry[];
  value: string;
  onChange: (id: string) => void;
  role?: string;
  label: string;
}) {
  const current = catalog.find((m) => m.id === value);
  return (
    <div className="flex items-center gap-2">
      <Select
        items={catalog.map((m) => ({ value: m.id, label: m.name }))}
        value={value}
        onValueChange={(v) => v && onChange(v)}
      >
        <SelectTrigger id={id} aria-label={label} className="w-72" data-testid={`model-select-${role ?? "model"}`}>
          <SelectValue placeholder="Choose a model" />
        </SelectTrigger>
        <SelectContent alignItemWithTrigger={false} className="min-w-96">
          {catalog.map((m) => (
            <SelectItem key={m.id} value={m.id}>
              <span className="flex w-full flex-col gap-0.5 py-0.5">
                <span className="flex items-center gap-2">
                  <span>{m.name}</span>
                  {role && m.recommended_roles.includes(role) ? (
                    <Badge variant="outline" className="border-success/40 text-success">Recommended</Badge>
                  ) : null}
                </span>
                <span className="text-muted-foreground flex items-center gap-2 text-xs">
                  <span className="font-mono">{priceLabel(m)}</span>
                  <span>{m.good_for.join(", ")}</span>
                </span>
              </span>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {current ? (
        <HoverCard>
          <HoverCardTrigger
            delay={100}
            render={
              <button type="button" aria-label={`About ${current.name}`} className="text-muted-foreground hover:text-foreground rounded-md p-1" />
            }
          >
            <Info size={16} animateOnHover />
          </HoverCardTrigger>
          <HoverCardContent className="w-80" side="right">
            <ModelDetails model={current} role={role} />
          </HoverCardContent>
        </HoverCard>
      ) : null}
    </div>
  );
}
