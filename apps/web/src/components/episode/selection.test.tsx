import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { parseHash, useEventSelection } from "./selection";

beforeEach(() => window.history.replaceState(null, "", "/"));

describe("selection", () => {
  it("parses event hashes", () => {
    expect(parseHash("#e-12")).toBe(12);
    expect(parseHash("#x")).toBeNull();
    expect(parseHash("")).toBeNull();
  });

  it("select sets the hash and the state, with a quote", () => {
    const { result } = renderHook(() => useEventSelection([0, 1, 2, 3]));
    act(() => result.current.select(2, "hello"));
    expect(window.location.hash).toBe("#e-2");
    expect(result.current.selectedSeq).toBe(2);
    expect(result.current.quote).toBe("hello");
  });

  it("restores the initial hash selection", () => {
    window.history.replaceState(null, "", "/#e-3");
    const { result } = renderHook(() => useEventSelection([0, 1, 2, 3]));
    expect(result.current.selectedSeq).toBe(3);
  });

  it("restores once the events arrive", () => {
    window.history.replaceState(null, "", "/#e-3");
    const { result, rerender } = renderHook(({ seqs }) => useEventSelection(seqs), {
      initialProps: { seqs: [] as number[] },
    });
    expect(result.current.selectedSeq).toBeNull();
    rerender({ seqs: [0, 1, 2, 3] });
    expect(result.current.selectedSeq).toBe(3);
  });

  it("ignores unknown seqs", () => {
    window.history.replaceState(null, "", "/#e-999");
    const { result } = renderHook(() => useEventSelection([0, 1]));
    expect(result.current.selectedSeq).toBeNull();
    act(() => result.current.select(50));
    expect(result.current.selectedSeq).toBeNull();
    expect(window.location.hash).toBe("#e-999");
  });

  it("asks the page to make the row visible before selecting", () => {
    const shown: number[] = [];
    const { result } = renderHook(() => useEventSelection([0, 1], { ensureVisible: (s) => shown.push(s) }));
    act(() => result.current.select(1));
    expect(shown).toEqual([1]);
  });
});
