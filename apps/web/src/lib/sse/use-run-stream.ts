"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { allKeys, STREAM_EVENTS, toInvalidations, type QueryKey } from "./adapter";

export type StreamStatus = "connecting" | "open" | "reconnecting" | "closed";

export type RunStreamOptions = {
  enabled?: boolean;
  focusedEpisodeId?: string | null;
  throttleMs?: number;
  maxFailures?: number;
  /** Test seam. */
  createSource?: (url: string) => EventSource;
};

export function useRunStream(runId: string, opts: RunStreamOptions = {}) {
  const { enabled = true, throttleMs = 400, maxFailures = 3 } = opts;
  const createRef = useRef(opts.createSource);
  createRef.current = opts.createSource;
  const qc = useQueryClient();
  const [status, setStatus] = useState<StreamStatus>("connecting");
  const [lastEventAt, setLastEventAt] = useState<number | null>(null);
  const focusRef = useRef(opts.focusedEpisodeId ?? null);
  focusRef.current = opts.focusedEpisodeId ?? null;

  useEffect(() => {
    if (!enabled) {
      setStatus("closed");
      return;
    }
    const url = `/api/gauntlet/v1/runs/${runId}/stream`;
    const source = createRef.current ? createRef.current(url) : new EventSource(url);
    const timers = new Map<string, ReturnType<typeof setTimeout>>();
    let failures = 0;
    let hasOpened = false;
    setStatus("connecting");

    const refetch = (key: QueryKey) => {
      const id = JSON.stringify(key);
      if (timers.has(id)) return; // trailing throttle: one refetch per key per window
      timers.set(
        id,
        setTimeout(() => {
          timers.delete(id);
          void qc.invalidateQueries({ queryKey: key });
        }, throttleMs),
      );
    };

    source.onopen = () => {
      failures = 0;
      setStatus("open");
      if (hasOpened) allKeys(runId, { focusedEpisodeId: focusRef.current }).forEach(refetch);
      hasOpened = true;
    };
    source.onerror = () => {
      failures += 1;
      if (failures >= maxFailures || source.readyState === 2) {
        source.close();
        setStatus("closed");
      } else {
        setStatus("reconnecting");
      }
    };
    const handlers = STREAM_EVENTS.map((name) => {
      const fn = (e: Event) => {
        setLastEventAt(Date.now());
        const data = (e as MessageEvent).data;
        toInvalidations(name, runId, typeof data === "string" ? data : "", {
          focusedEpisodeId: focusRef.current,
        }).forEach(refetch);
      };
      source.addEventListener(name, fn);
      return [name, fn] as const;
    });

    return () => {
      handlers.forEach(([name, fn]) => source.removeEventListener(name, fn));
      source.close();
      timers.forEach(clearTimeout);
    };
  }, [runId, enabled, throttleMs, maxFailures, qc]);

  return { status, lastEventAt };
}
