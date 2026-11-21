import { request, type FullConfig } from "@playwright/test";
import { mkdirSync } from "node:fs";

import { seedSecurity } from "./seed-security";

/** Logs in once with the dev key, seeds the dev data and saves the cookie for every spec. */
export default async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0].use.baseURL ?? "http://localhost:3000";
  const key = process.env.GAUNTLET_E2E_API_KEY ?? "gk_dev_local_only";
  mkdirSync("e2e/.auth", { recursive: true });
  const ctx = await request.newContext({ baseURL });
  const res = await ctx.post("/api/session", { data: { api_key: key } });
  if (!res.ok()) throw new Error(`e2e login failed: ${res.status()} ${await res.text()}`);
  // Idempotent: makes sure the demo run (ecommerce smoke suite) and agent profile exist.
  const seed = await ctx.post("/api/gauntlet/v1/dev/seed", { data: {}, timeout: 120_000 });
  if (!seed.ok()) throw new Error(`e2e seed failed: ${seed.status()} ${await seed.text()}`);
  // Findings for the security specs. Needs the compose `dva` profile (DVA_BRAIN=scripted); without
  // it the security specs say what is missing instead of this setup failing every other spec.
  try {
    await seedSecurity(ctx);
  } catch (e) {
    console.warn(`e2e: security seed skipped: ${e instanceof Error ? e.message : String(e)}`);
  }
  await ctx.storageState({ path: "e2e/.auth/state.json" });
  await ctx.dispose();
}
