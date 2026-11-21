"use client";

import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { RubricDoc } from "@/lib/api/hooks/rubrics";

export function RubricDetail({ rubric }: { rubric: RubricDoc }) {
  return (
    <div className="flex flex-col gap-3" data-testid="rubric-detail">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm" data-testid="rubric-question">{rubric.question}</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-2 text-sm">
          <p><span className="font-medium">Pass: </span>{rubric.pass_definition}</p>
          <p><span className="font-medium">Fail: </span>{rubric.fail_definition}</p>
          {rubric.na_definition ? <p><span className="font-medium">Not applicable: </span>{rubric.na_definition}</p> : null}
          <p className="text-muted-foreground flex flex-wrap items-center gap-2 text-xs">
            Scope <Badge variant="outline">{rubric.scope}</Badge> Threshold <span className="font-mono">{rubric.threshold}</span>
          </p>
        </CardContent>
      </Card>
      <Accordion className="rounded-md border">
        <AccordionItem value="examples">
          <AccordionTrigger className="px-3">Examples ({rubric.examples.length})</AccordionTrigger>
          <AccordionContent className="flex flex-col gap-2 px-3">
            {rubric.examples.length === 0 ? <p className="text-muted-foreground text-sm">No examples.</p> : null}
            {rubric.examples.map((e, i) => (
              <div key={i} className="rounded-md border p-2 text-sm">
                <Badge variant="secondary">{e.result}</Badge>
                <pre className="mt-1 font-mono text-xs break-words whitespace-pre-wrap">{e.transcript}</pre>
                <p className="text-muted-foreground mt-1 text-xs">{e.why}</p>
              </div>
            ))}
          </AccordionContent>
        </AccordionItem>
        <AccordionItem value="versions">
          <AccordionTrigger className="px-3">Versions</AccordionTrigger>
          <AccordionContent className="px-3 text-sm">
            This is version {rubric.version}, created {new Date(rubric.created_at).toLocaleDateString()}. A rubric is never edited in place: a change creates a new version.
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </div>
  );
}
