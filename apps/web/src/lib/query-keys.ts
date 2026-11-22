export const qk = {
  projects: ["projects"] as const,
  agents: ["agents"] as const,
  agent: (id: string) => ["agents", id] as const,
  agentVersions: (id: string) => ["agents", id, "versions"] as const,
  scenarios: ["scenarios"] as const,
  scenario: (id: string) => ["scenarios", id] as const,
  suites: ["suites"] as const,
  worlds: ["worlds"] as const,
  world: (id: string) => ["worlds", id] as const,
  secrets: ["secrets"] as const,
  runs: ["runs"] as const,
  run: (id: string) => ["runs", id] as const,
  runEpisodes: (id: string) => ["runs", id, "episodes"] as const,
  runReport: (id: string) => ["runs", id, "report"] as const,
  episode: (id: string) => ["episodes", id] as const,
  modelCatalog: ["models", "catalog"] as const,
  modelSettings: ["settings", "models"] as const,
};

export const qkSec = {
  findings: (filters: object = {}) => ["findings", filters] as const,
  finding: (id: string) => ["findings", "detail", id] as const,
  attacks: (filters: object = {}) => ["attacks", filters] as const,
  taxonomy: ["security", "taxonomy"] as const,
  posture: (agentId: string, versionId: string) => ["security", "posture", agentId, versionId] as const,
  coverage: (agentId: string, versionId: string) => ["security", "coverage", agentId, versionId] as const,
  killswitch: ["security", "killswitch"] as const,
  verifications: ["security", "verifications"] as const,
  attackScope: ["security", "attack-scope"] as const,
  audit: (filters: object = {}) => ["security", "audit", filters] as const,
  auditVerify: ["security", "audit-verify"] as const,
};

export const qkQ = {
  compare: (runId: string, baseline: string) => ["compare", runId, baseline] as const,
  diff: (episodeId: string, against: string) => ["compare", "diff", episodeId, against] as const,
  clusters: (runId: string) => ["runs", runId, "clusters"] as const,
  reviewQueue: (rubric: string) => ["review", "queue", rubric] as const,
  reviewItem: (episodeId: string, rubric: string, reveal: boolean) => ["review", "item", episodeId, rubric, reveal] as const,
  rubrics: ["rubrics"] as const,
  rubric: (id: string) => ["rubrics", id] as const,
  calibrations: (id: string) => ["rubrics", id, "calibrations"] as const,
  migration: (runId: string, baseline: string, force: boolean) => ["migration", runId, baseline, force] as const,
  pareto: (runIds: string[]) => ["migration", "pareto", runIds] as const,
  scorecard: (agentId: string, versionId: string) => ["scorecard", agentId, versionId] as const,
};

export const qkG = {
  policies: ["policies"] as const,
  policy: (id: string) => ["policies", id] as const,
  proposals: (id: string) => ["policies", id, "proposals"] as const,
  tests: (id: string) => ["policies", id, "tests"] as const,
  test: (id: string) => ["policy-tests", id] as const,
  decisions: (filters: object) => ["gateway", "decisions", filters] as const,
  stats: (window: string) => ["gateway", "stats", window] as const,
  approvals: (status: string) => ["gateway", "approvals", status] as const,
};
