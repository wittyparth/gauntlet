"use client";

import { ShieldCheck } from "@/components/animate-ui/icons/shield-check";
import { RiskBadge, SeverityBadge } from "@/components/shared/badges";
import { JsonBlock } from "@/components/shared/json-block";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { useWorld } from "@/lib/api/hooks/read";
import type { ScenarioDoc } from "@/lib/api/models";

import { CheckTree } from "./check-tree";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card size="sm">
      <CardHeader><CardTitle className="text-sm">{title}</CardTitle></CardHeader>
      <CardContent className="flex flex-col gap-2">{children}</CardContent>
    </Card>
  );
}

function WorldTools({ worldId }: { worldId: string }) {
  const w = useWorld(worldId);
  return (
    <Collapsible>
      <CollapsibleTrigger render={<Button variant="ghost" size="xs" />}>
        World {worldId}{w.data ? ` · ${w.data.tools.length} tools` : ""}
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ul className="mt-1 flex flex-col gap-1">
          {w.data?.tools.map((t) => (
            <li key={t.name} className="flex items-center gap-2 text-xs">
              <span className="font-mono">{t.name}</span> <RiskBadge risk={t.risk} />
            </li>
          ))}
        </ul>
      </CollapsibleContent>
    </Collapsible>
  );
}

export function ScenarioSummary({ s }: { s: ScenarioDoc }) {
  const overrides = Object.entries(s.persona_overrides);
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
      <div className="flex flex-col gap-3">
        <Section title="Goal"><p>{s.goal}</p></Section>
        <Section title="Persona">
          <span className="font-mono text-xs">{s.persona}</span>
          {overrides.length > 0 ? (
            <p className="text-muted-foreground text-xs">overrides: {overrides.map(([k, v]) => `${k} ${JSON.stringify(v)}`).join(", ")}</p>
          ) : null}
          {s.opening_message ? <p className="text-sm">Opens with: “{s.opening_message}”</p> : <p className="text-muted-foreground text-xs">The simulator writes the opening message.</p>}
        </Section>
        <Section title="Setup">
          <Collapsible>
            <CollapsibleTrigger render={<Button variant="ghost" size="xs" />}>Hidden facts ({s.hidden_facts.length})</CollapsibleTrigger>
            <CollapsibleContent>
              <p className="text-muted-foreground mt-1 text-xs">Not shown to the agent or the judge.</p>
              <ul className="mt-1 list-disc pl-5 text-sm">{s.hidden_facts.map((f) => <li key={f}>{f}</li>)}</ul>
            </CollapsibleContent>
          </Collapsible>
          <div className="text-sm">Max turns <span className="font-mono">{s.max_turns}</span></div>
          <div className="flex flex-wrap gap-1">
            {Object.entries(s.tags).map(([k, v]) => <Badge key={k} variant="outline" className="font-mono">{k}:{v}</Badge>)}
          </div>
          {typeof s.world === "string" ? <WorldTools worldId={s.world} /> : <JsonBlock value={s.world} label="inline world" defaultOpen={false} />}
        </Section>
      </div>
      <div className="flex flex-col gap-3">
        <Section title="Success (must hold)"><CheckTree check={s.success} /></Section>
        <Section title="Forbidden">
          {s.forbidden.length === 0 ? <p className="text-muted-foreground text-sm">Nothing is forbidden.</p> : null}
          {s.forbidden.map((f) => (
            <Collapsible key={f.id}>
              <div className="flex flex-wrap items-center gap-2">
                <SeverityBadge severity={f.severity} />
                <span className="font-mono text-xs">{f.id}</span>
                <CollapsibleTrigger render={<Button variant="ghost" size="xs" />}>Show check</CollapsibleTrigger>
              </div>
              {f.description ? <p className="text-muted-foreground text-xs">{f.description}</p> : null}
              <CollapsibleContent><CheckTree check={f.check} /></CollapsibleContent>
            </Collapsible>
          ))}
        </Section>
        <Section title="Rubrics">
          <div className="flex flex-wrap gap-1">
            {s.rubrics.length === 0 ? <span className="text-muted-foreground text-sm">None.</span> : s.rubrics.map((r) => <Badge key={r} variant="secondary" className="font-mono">{r}</Badge>)}
          </div>
        </Section>
        {s.attack ? (
          <Section title="Attack">
            <div className="text-info flex items-center gap-2 text-sm"><ShieldCheck size={16} /> Security scenario</div>
            <JsonBlock value={s.attack} label="attack" />
          </Section>
        ) : null}
      </div>
    </div>
  );
}
