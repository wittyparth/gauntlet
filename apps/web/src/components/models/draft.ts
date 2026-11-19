import type { ModelCatalogEntry, ModelSettings, RoleChoice } from "@/lib/api/models";

export const ROLE_LABELS: Record<string, { label: string; hint: string }> = {
  simulator: { label: "User simulator", hint: "Plays the customer in every conversation." },
  judge_small: { label: "Judge (first pass)", hint: "Grades every episode; cheap and fast." },
  judge_strong: { label: "Judge (second opinion)", hint: "Re-grades the uncertain verdicts." },
  attacker: { label: "Attacker", hint: "Probes the agent with adversarial messages." },
  generator: { label: "Scenario generator", hint: "Writes new scenarios from an agent profile." },
};
export const ROLE_ORDER = ["simulator", "judge_small", "judge_strong", "attacker", "generator"];

/** Roles to send in the PUT: what the workspace already overrides, plus what changed. */
export function rolesToSave(
  initial: Pick<ModelSettings, "roles" | "overridden">,
  draft: Record<string, RoleChoice>,
): Record<string, RoleChoice> {
  const out: Record<string, RoleChoice> = {};
  for (const role of Object.keys(draft)) {
    const was = initial.roles[role];
    const changed = !was || was.model !== draft[role].model || was.reasoning !== draft[role].reasoning;
    if (changed || initial.overridden.includes(role)) out[role] = draft[role];
  }
  return out;
}

const usd = (n: number) => {
  const s = n.toFixed(3);
  return s.endsWith("0") ? s.slice(0, -1) : s; // $0.03, $0.075
};

export const priceLabel = (m: Pick<ModelCatalogEntry, "input_usd_per_mtok" | "output_usd_per_mtok">) =>
  `$${usd(m.input_usd_per_mtok)} / $${usd(m.output_usd_per_mtok)} per 1M`;

export const shortModel = (id: string) => id.split("/").pop() ?? id;
