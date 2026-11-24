"use client";

import { useEffect, useState } from "react";

import { LoaderCircle } from "@/components/animate-ui/icons/loader-circle";
import { Rocket } from "@/components/animate-ui/icons/rocket";
import { useToast } from "@/components/shared/use-toast";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ErrorState } from "@/components/shared/error-state";
import { useArenaLevels, useCreateHandle, useStartAttempt, type Attempt } from "@/lib/arena/hooks";

import { ChatPanel } from "./chat-panel";
import { Leaderboard } from "./leaderboard";

const HANDLE_KEY = "gauntlet_arena_handle";

export function ArenaPage() {
  const toast = useToast();
  const levels = useArenaLevels();
  const createHandle = useCreateHandle();
  const start = useStartAttempt();
  const [handle, setHandle] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [level, setLevel] = useState(1);
  const [attempt, setAttempt] = useState<Attempt | null>(null);

  useEffect(() => {
    const saved = window.localStorage.getItem(HANDLE_KEY);
    if (saved) setHandle(saved);
  }, []);

  if (levels.isLoading) return <Skeleton className="h-64 w-full" />;
  if (levels.isError) return <ErrorState error={levels.error} onRetry={() => void levels.refetch()} />;
  const data = levels.data!;
  const current = data.levels.find((l) => l.level === level) ?? data.levels[0];

  async function claim() {
    try {
      const out = await createHandle.mutateAsync(draft.trim());
      window.localStorage.setItem(HANDLE_KEY, out.handle);
      setHandle(out.handle);
    } catch (e) {
      toast.error(e, "That handle did not work");
    }
  }

  async function begin() {
    if (!handle) return;
    try {
      setAttempt(await start.mutateAsync({ handle, level }));
    } catch (e) {
      toast.error(e, "Could not start an attempt");
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {!data.open ? (
        <Alert role="status" data-testid="arena-closed">
          <AlertTitle>The arena is closed</AlertTitle>
          <AlertDescription>
            {data.closed_reason === "disabled" ? "It has not been switched on." : `Reason: ${data.closed_reason}.`} You can still read the levels.
          </AlertDescription>
        </Alert>
      ) : null}

      <Tabs value={String(level)} onValueChange={(v) => setLevel(Number(v))}>
        <TabsList aria-label="Level">
          {data.levels.map((l) => (
            <TabsTrigger key={l.level} value={String(l.level)} disabled={!!attempt && attempt.status === "open"}>
              Level {l.level}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="flex flex-col gap-4">
          <Card data-testid="level-status">
            <CardHeader>
              <CardTitle>Level {current.level}: {current.title}</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 text-sm">
              <p>{current.description}</p>
              <ul className="flex flex-wrap gap-1.5" aria-label="Defenses">
                {current.defenses.map((d) => (
                  <li key={d}><Badge variant="outline">{d}</Badge></li>
                ))}
              </ul>
              {current.classifier ? (
                <p className="text-muted-foreground text-xs" data-testid="classifier-note">
                  Injection classifier: {current.classifier === "fake" ? "a deterministic stand-in (keyword scoring), not the trained model" : "the trained model"}.
                </p>
              ) : null}
            </CardContent>
          </Card>

          {!handle ? (
            <form
              className="flex flex-col gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                void claim();
              }}
            >
              <Label htmlFor="arena-handle">Pick a handle</Label>
              <div className="flex gap-2">
                <Input id="arena-handle" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="3 to 20 letters, digits, _ or -" autoComplete="off" />
                <Button type="submit" disabled={!data.open || draft.trim().length < 3 || createHandle.isPending}>Use handle</Button>
              </div>
              <p className="text-muted-foreground text-xs">Handles are public on the leaderboard. No accounts, no emails.</p>
            </form>
          ) : attempt && attempt.level === level ? (
            <ChatPanel key={attempt.id} attempt={attempt} onClosed={() => setAttempt(null)} />
          ) : (
            <div className="flex items-center gap-3">
              <Button onClick={() => void begin()} disabled={!data.open || start.isPending}>
                {start.isPending ? <LoaderCircle size={14} animate loop /> : <Rocket size={14} animateOnHover />}
                Start level {level} as <span className="font-mono">{handle}</span>
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  window.localStorage.removeItem(HANDLE_KEY);
                  setHandle(null);
                  setAttempt(null);
                }}
              >
                Change handle
              </Button>
            </div>
          )}
        </div>

        <aside aria-label="Leaderboard" className="flex flex-col gap-2">
          <h2 className="text-sm font-medium">Leaderboard, level {level}</h2>
          <Leaderboard level={level} />
        </aside>
      </div>
    </div>
  );
}
