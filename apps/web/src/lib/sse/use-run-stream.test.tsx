import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { toInvalidations } from "./adapter";
import { useRunStream } from "./use-run-stream";

class FakeSource {
  static last: FakeSource | null = null;
  readyState = 0;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  listeners = new Map<string, Set<(e: Event) => void>>();
  constructor(public url: string) {
    FakeSource.last = this;
  }
  addEventListener(n: string, fn: (e: Event) => void) {
    if (!this.listeners.has(n)) this.listeners.set(n, new Set());
    this.listeners.get(n)!.add(fn);
  }
  removeEventListener(n: string, fn: (e: Event) => void) {
    this.listeners.get(n)?.delete(fn);
  }
  close() {
    this.closed = true;
    this.readyState = 2;
  }
  emit(name: string, data = "{}") {
    this.listeners.get(name)?.forEach((fn) => fn(new MessageEvent(name, { data })));
  }
}

function setup(opts: Parameters<typeof useRunStream>[1] = {}) {
  const qc = new QueryClient();
  const spy = vi.spyOn(qc, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  const hook = renderHook(
    (p: Parameters<typeof useRunStream>[1]) =>
      useRunStream("run_1", { ...p, createSource: (u) => new FakeSource(u) as unknown as EventSource }),
    { wrapper, initialProps: opts },
  );
  return { qc, spy, hook, src: () => FakeSource.last! };
}

const keysOf = (spy: { mock: { calls: unknown[][] } }) =>
  spy.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown }).queryKey));

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("toInvalidations", () => {
  it("maps event names to query keys", () => {
    expect(toInvalidations("run_update", "r", "{}", {})).toEqual([["runs", "r"]]);
    expect(toInvalidations("episode_update", "r", "{}", {})).toEqual([
      ["runs", "r", "episodes"],
      ["runs", "r"],
    ]);
    expect(toInvalidations("event", "r", "{}", {})).toEqual([]);
    expect(toInvalidations("event", "r", "{}", { focusedEpisodeId: "ep_1" })).toEqual([
      ["episodes", "ep_1"],
    ]);
  });
});

describe("useRunStream", () => {
  it("coalesces a burst of 50 events into one refetch per key", () => {
    const { spy, src } = setup();
    act(() => src().onopen?.());
    act(() => {
      for (let i = 0; i < 50; i++) src().emit("episode_update");
    });
    act(() => void vi.advanceTimersByTime(500));
    const keys = keysOf(spy);
    expect(keys.filter((k) => k === '["runs","run_1","episodes"]')).toHaveLength(1);
    expect(keys.filter((k) => k === '["runs","run_1"]')).toHaveLength(1);
  });

  it("refetches the focused episode on event and verdict", () => {
    const { spy, src } = setup({ focusedEpisodeId: "ep_9" });
    act(() => src().onopen?.());
    act(() => src().emit("verdict"));
    act(() => void vi.advanceTimersByTime(500));
    expect(keysOf(spy)).toEqual(['["episodes","ep_9"]']);
  });

  it("invalidates everything once on reconnect", () => {
    const { spy, src } = setup();
    act(() => src().onopen?.());
    act(() => src().onerror?.());
    act(() => src().onopen?.());
    act(() => void vi.advanceTimersByTime(500));
    expect(keysOf(spy).sort()).toEqual(['["runs","run_1","episodes"]', '["runs","run_1"]']);
  });

  it("closes after 3 failures and reports closed", () => {
    const { hook, src } = setup();
    act(() => src().onerror?.());
    expect(hook.result.current.status).toBe("reconnecting");
    act(() => src().onerror?.());
    act(() => src().onerror?.());
    expect(hook.result.current.status).toBe("closed");
    expect(src().closed).toBe(true);
  });

  it("closes the source when disabled (terminal run) and on unmount", () => {
    const { hook, src } = setup({ enabled: true });
    const first = src();
    hook.rerender({ enabled: false });
    expect(first.closed).toBe(true);
    expect(hook.result.current.status).toBe("closed");
  });
});
