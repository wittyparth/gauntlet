"use client";

import { createContext, useContext } from "react";

import type { StreamStatus } from "@/lib/sse/use-run-stream";

export type RunLive = { status: StreamStatus; pollMs: number | false; live: boolean };

export const RunLiveContext = createContext<RunLive>({ status: "closed", pollMs: false, live: false });
export const useRunLive = () => useContext(RunLiveContext);
