import type { Metadata } from "next";
import { Fragment_Mono, Host_Grotesk } from "next/font/google";
import type { ReactNode } from "react";

import "./landing.css";

const display = Host_Grotesk({ variable: "--font-lp-display", subsets: ["latin"], display: "swap" });
const mono = Fragment_Mono({ variable: "--font-lp-mono", subsets: ["latin"], weight: "400", display: "swap" });

export const metadata: Metadata = {
  title: "Gauntlet: test, attack, and guard your AI agents",
  description:
    "Find a hole, turn it into a policy, prove the fix. Gauntlet tests, red-teams and guards AI agents, and publishes its benchmarks including the misses.",
};

export default function LandingLayout({ children }: { children: ReactNode }) {
  return <div className={`lp ${display.variable} ${mono.variable}`}>{children}</div>;
}
