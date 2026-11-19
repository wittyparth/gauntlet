import { qk } from "@/lib/query-keys";

export type QueryKey = readonly unknown[];

export type StreamOptions = {
  focusedEpisodeId?: string | null;
};

/** The SSE event names the API emits (contracts section 9). */
export const STREAM_EVENTS = ["run_update", "episode_update", "event", "verdict"] as const;

/**
 * Which queries to refetch for one SSE message. REST is the source of truth and SSE only rings
 * the doorbell, so only the event name is used; payloads are ignored until their shapes are locked.
 */
export function toInvalidations(
  name: string,
  runId: string,
  _data: string,
  opts: StreamOptions,
): QueryKey[] {
  switch (name) {
    case "run_update":
      return [qk.run(runId)];
    case "episode_update":
      return [qk.runEpisodes(runId), qk.run(runId)];
    case "event":
    case "verdict":
      return opts.focusedEpisodeId ? [qk.episode(opts.focusedEpisodeId)] : [];
    default:
      return [];
  }
}

export function allKeys(runId: string, opts: StreamOptions): QueryKey[] {
  return [
    qk.run(runId),
    qk.runEpisodes(runId),
    ...(opts.focusedEpisodeId ? [qk.episode(opts.focusedEpisodeId)] : []),
  ];
}
