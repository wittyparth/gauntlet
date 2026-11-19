"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { AgentVersion } from "@/lib/api/models";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[6rem_1fr] gap-2">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  );
}

export function ProfileCard({ profile }: { profile: AgentVersion["profile"] }) {
  return (
    <Card size="sm">
      <CardHeader><CardTitle><h2 className="text-sm font-medium">Profile</h2></CardTitle></CardHeader>
      <CardContent>
        <dl className="flex flex-col gap-2">
          <Row label="Purpose">{profile.purpose}</Row>
          <Row label="Audience">{profile.audience || <span className="text-muted-foreground">Not set</span>}</Row>
          <Row label="Languages">
            <div className="flex gap-1">{profile.languages.map((l) => <Badge key={l} variant="outline">{l}</Badge>)}</div>
          </Row>
        </dl>
        <div className="mt-2 flex flex-col gap-1">
          <Collapsible>
            <CollapsibleTrigger render={<Button variant="ghost" size="xs" />}>Policies</CollapsibleTrigger>
            <CollapsibleContent>
              <p className="mt-1 text-sm whitespace-pre-wrap">{profile.policies_text || "No policies written down."}</p>
            </CollapsibleContent>
          </Collapsible>
          <Collapsible>
            <CollapsibleTrigger render={<Button variant="ghost" size="xs" />}>Forbidden behaviors ({profile.forbidden_behaviors.length})</CollapsibleTrigger>
            <CollapsibleContent>
              <ul className="mt-1 list-disc pl-5 text-sm">
                {profile.forbidden_behaviors.length === 0 ? <li className="text-muted-foreground list-none">None listed.</li> : profile.forbidden_behaviors.map((f) => <li key={f}>{f}</li>)}
              </ul>
            </CollapsibleContent>
          </Collapsible>
        </div>
      </CardContent>
    </Card>
  );
}
