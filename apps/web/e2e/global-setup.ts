import { request, type FullConfig } from "@playwright/test";
import { mkdirSync } from "node:fs";

/** Logs in once with the dev key and saves the cookie for every spec. */
export default async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0].use.baseURL ?? "http://localhost:3000";
  const key = process.env.GAUNTLET_E2E_API_KEY ?? "gk_dev_local_only";
  mkdirSync("e2e/.auth", { recursive: true });
  const ctx = await request.newContext({ baseURL });
  const res = await ctx.post("/api/session", { data: { api_key: key } });
  if (!res.ok()) throw new Error(`e2e login failed: ${res.status()} ${await res.text()}`);
  await ctx.storageState({ path: "e2e/.auth/state.json" });
  await ctx.dispose();
}
