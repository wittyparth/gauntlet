"use client";

import { Fade } from "@animate-ui/react/primitives/effects/fade";
import { useEffect, useRef, useState } from "react";

import { Flag } from "@/components/animate-ui/icons/flag";
import { LoaderCircle } from "@/components/animate-ui/icons/loader-circle";
import { Play } from "@/components/animate-ui/icons/play";
import { LiveNumber } from "@/components/shared/live-number";
import { useToast } from "@/components/shared/use-toast";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useReportAttempt, useSendMessage, type Attempt } from "@/lib/arena/hooks";

export type Line = { role: "user" | "agent"; text: string };
const MAX_CHARS = 500;

/** One attempt: the conversation, the status line, the report button. No third-party chat widget. */
export function ChatPanel({ attempt, onClosed }: { attempt: Attempt; onClosed: () => void }) {
  const toast = useToast();
  const send = useSendMessage(attempt.id);
  const report = useReportAttempt();
  const [lines, setLines] = useState<Line[]>([]);
  const [text, setText] = useState("");
  const [status, setStatus] = useState(attempt.status);
  const [turns, setTurns] = useState(attempt.turns);
  const [why, setWhy] = useState<string | null>(null);
  const [reported, setReported] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const open = status === "open";

  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "end" });
  }, [lines.length]);

  async function submit() {
    const t = text.trim();
    if (!t || !open) return;
    setText("");
    setLines((l) => [...l, { role: "user", text: t }]);
    try {
      const r = await send.mutateAsync(t);
      setLines((l) => [...l, { role: "agent", text: r.reply }]);
      setStatus(r.status);
      setTurns(r.turns);
      setWhy(r.closed_reason ?? null);
    } catch (e) {
      toast.error(e, "Message not sent");
    }
  }

  return (
    <section className="flex flex-col gap-3" aria-label="Conversation" data-testid="chat-panel">
      <div className="flex flex-wrap items-center gap-2 text-xs" aria-live="polite">
        <Badge variant={status === "solved" ? "default" : "outline"} data-testid="attempt-status">{status}</Badge>
        <span className="text-muted-foreground">
          Turn <LiveNumber value={turns} /> of {attempt.max_turns}
        </span>
        <Button
          variant="ghost"
          size="sm"
          className="ml-auto"
          disabled={reported || report.isPending}
          onClick={() =>
            report.mutate(attempt.id, {
              onSuccess: () => {
                setReported(true);
                toast.success("Reported", "This attempt is flagged and leaves the leaderboard.");
              },
              onError: (e) => toast.error(e, "Could not report"),
            })
          }
        >
          <Flag size={14} animateOnHover /> {reported ? "Reported" : "Report"}
        </Button>
      </div>

      <div role="log" aria-live="polite" className="bg-muted/30 flex min-h-48 max-h-96 flex-col gap-2 overflow-y-auto rounded-lg border p-3" data-testid="chat-log">
        {lines.length === 0 ? <p className="text-muted-foreground text-sm">Say hello to Pip, or try something clever.</p> : null}
        {lines.map((l, i) => (
          <Fade key={i}>
            <div
              data-testid={`line-${l.role}`}
              className={l.role === "user" ? "bg-primary text-primary-foreground ml-auto w-fit max-w-[85%] rounded-lg px-3 py-1.5" : "bg-card w-fit max-w-[85%] rounded-lg border px-3 py-1.5"}
            >
              <span className="sr-only">{l.role === "user" ? "You: " : "Pip: "}</span>
              {l.text}
            </div>
          </Fade>
        ))}
        <div ref={end} />
      </div>

      {status === "solved" ? (
        <Alert data-testid="solved-alert">
          <AlertTitle>Solved in {turns} {turns === 1 ? "turn" : "turns"}</AlertTitle>
          <AlertDescription>Your handle is on the leaderboard for this level. Try the next one.</AlertDescription>
        </Alert>
      ) : null}
      {status !== "open" && status !== "solved" ? (
        <Alert data-testid="closed-alert">
          <AlertTitle>This attempt is over</AlertTitle>
          <AlertDescription>{why === "budget" ? "The arena hit its daily budget." : "The turn limit was reached or the attempt expired."} Start a new one.</AlertDescription>
        </Alert>
      ) : null}

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <Input
          aria-label="Message to Pip"
          value={text}
          maxLength={MAX_CHARS}
          disabled={!open}
          onChange={(e) => setText(e.target.value)}
          placeholder={open ? "Type a message" : "This attempt is closed"}
          autoComplete="off"
        />
        <Button type="submit" disabled={!open || !text.trim() || send.isPending}>
          {send.isPending ? <LoaderCircle size={14} animate loop /> : <Play size={14} animateOnHover />}
          Send
        </Button>
      </form>
      {!open ? (
        <Button variant="outline" className="w-fit" onClick={onClosed}>
          New attempt
        </Button>
      ) : null}
    </section>
  );
}
