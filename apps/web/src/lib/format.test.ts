import { describe, expect, it } from "vitest";

import {
  dollarsToMicros,
  formatDuration,
  formatPercent,
  formatUsd,
  shortId,
  timeAgo,
} from "./format";

describe("format", () => {
  it("formats money from micro-dollars", () => {
    expect(formatUsd(12300)).toBe("$0.0123");
    expect(formatUsd(2_500_000)).toBe("$2.50");
    expect(formatUsd(0)).toBe("$0.0000");
  });
  it("converts dollars to integer micros", () => {
    expect(dollarsToMicros(2)).toBe(2_000_000);
    expect(Number.isInteger(dollarsToMicros(0.1 + 0.2))).toBe(true);
  });
  it("shortens ids but keeps the prefix and last four", () => {
    expect(shortId("ep_01HXYZABCDEFG")).toBe("ep_…DEFG");
    expect(shortId("ep_demo_5")).toBe("ep_demo_5");
  });
  it("formats durations and percents", () => {
    expect(formatDuration(450)).toBe("450ms");
    expect(formatDuration(48_000)).toBe("48s");
    expect(formatDuration(125_000)).toBe("2m 5s");
    expect(formatPercent(0.8333)).toBe("83%");
  });
  it("formats relative time", () => {
    const now = Date.parse("2026-01-01T12:00:00Z");
    expect(timeAgo("2026-01-01T11:58:00Z", now)).toBe("2m ago");
    expect(timeAgo("2026-01-01T09:00:00Z", now)).toBe("3h ago");
  });
});
