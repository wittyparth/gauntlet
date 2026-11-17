# Contracts

These are locked. They live as code in `packages/core/src/gauntlet_core/schema/` (written by the lead in task L1). Changing one requires a lead decision recorded in the log at the bottom. Field lists here are the required fields; `...` is never implied.

All models are Pydantic v2 `BaseModel` with `model_config = ConfigDict(extra="forbid", frozen=True)` unless noted. `Json = dict[str, Any]`.

## 1. Authoring models (what users and packs write, YAML or JSON)

```python
class Persona:
    id: str; name: str; description: str
    traits: dict[str, str | float]        # patience, literacy, emotion, verbosity, honesty, typo_rate, language ...
    behavior_rules: list[str]             # "never volunteers the order number unless asked"
    adversarial_intent: str | None        # None for benign personas

class ToolSpec:
    name: str; description: str
    input_schema: Json                    # JSON Schema
    risk: Literal["read", "write", "destructive", "financial", "external_comm"]
    handler: HandlerSpec                  # see below
    untrusted_output: bool = False        # results are tagged origin=untrusted_external
    honeytool: bool = False               # any call is proof of hijack

class HandlerSpec:                        # discriminated on `kind`
    kind: Literal["crud", "python", "llm_sim", "static"]
    # crud:   collection: str; op: Literal["get","list","create","update","delete"]; key_arg: str | None; filter_args: list[str]
    # python: entrypoint: str   ("packs.ecommerce.handlers:issue_refund")
    # llm_sim: instructions: str
    # static: result: Json

class WorldSpec:
    tools: list[ToolSpec]
    seed: dict[str, list[Json]]           # collection name -> records, each record has "id"
    clock_start: datetime
    faults: list[FaultSpec] = []
    canaries: list[CanarySpec] = []
    documents: list[DocumentSpec] = []    # knowledge base and injectable content

class FaultSpec:
    tool: str; kind: Literal["timeout","http_500","http_429","malformed_json","empty","stale","latency","schema_drift"]
    probability: float = 1.0; on_call_index: int | None = None; params: Json = {}

class CanarySpec:
    id: str; kind: Literal["api_key","email","card","ssn","record","freeform"]
    placement: Literal["system_prompt","world_record","document","tool_result"]
    location: str                         # "customers/cust_2/notes", doc id, or tool name

class DocumentSpec:
    id: str; title: str; body: str; trusted: bool = True
    injection: InjectionSpec | None = None   # Phase 2

class Scenario:
    id: str; version: int; title: str
    goal: str                             # what the simulated user wants
    persona: str                          # persona id
    persona_overrides: dict[str, str | float] = {}
    hidden_facts: list[str] = []
    opening_message: str | None = None    # None -> simulator writes it
    world: str | WorldSpec                # pack world id or inline
    world_overrides: Json = {}            # merged into seed
    success: Check                        # must hold for `passed`
    forbidden: list[NamedCheck] = []      # any holding -> `failed`, each with severity
    rubrics: list[str] = []               # judge rubric ids to apply
    max_turns: int = 12
    tags: dict[str, str] = {}             # intent, difficulty, risk, language, category
    attack: AttackRef | None = None       # Phase 2; makes this a security scenario

class NamedCheck:
    id: str; description: str; severity: Literal["low","medium","high","critical"]; check: Check

class Suite:
    id: str; name: str; scenarios: list[str]; repetitions: int = 1
    persona_mix: dict[str, float] | None = None

class AgentVersion:
    id: str; agent_id: str; label: str
    target: TargetConfig                  # discriminated: hosted | openai_compat | http | wired
    profile: AgentProfile                 # purpose, audience, policies_text, forbidden_behaviors, languages

class HostedTargetConfig:
    kind: Literal["hosted"]; model: str; system_prompt: str; temperature: float = 0.0
    tools: list[str] | None = None        # subset of world tools; None = all
class OpenAICompatTargetConfig:
    kind: Literal["openai_compat"]; base_url: str; model: str; api_key_secret: str | None; wired: bool = False
class HttpTargetConfig:
    kind: Literal["http"]; url: str; method: str = "POST"; headers: dict[str, str]
    body_template: Json; reply_path: str; conversation_id_path: str | None; stateful: bool; wired: bool = False
```

## 2. The journal

```python
EventKind = Literal[
  "episode_started", "user_message", "agent_message", "tool_call", "tool_result",
  "fault_injected", "sim_note", "check_result", "verdict", "episode_ended"]

class Origin:
    trust: Literal["system", "user", "untrusted_external"]
    source: str | None                    # tool name, document id
    markers: list[str] = []               # taint markers present in this content (03 section 6.3)

class Cost:
    usd_micros: int; input_tokens: int; output_tokens: int; model: str | None

class Event:
    seq: int                              # 0-based, dense, unique per episode
    kind: EventKind
    actor: Literal["user", "agent", "tool", "platform"]
    sim_time: datetime                    # simulated clock
    wall_ms: int                          # latency of the step that produced it
    payload: Json                         # shape fixed per kind, below
    origin: Origin | None = None
    cost: Cost | None = None
    effect_key: str | None = None         # the effect that produced it

# payload shapes
# user_message / agent_message: {"text": str}
# tool_call:   {"call_id": str, "tool": str, "args": Json, "via": "hosted"|"wired"}
# tool_result: {"call_id": str, "ok": bool, "result": Json, "patch": list[PatchOp], "error": str | None}
# fault_injected: {"call_id": str, "fault": FaultSpec}
# episode_ended: {"outcome": Outcome, "termination": Termination, "detail": str | None}

class PatchOp:
    op: Literal["add", "replace", "remove"]
    collection: str; id: str
    value: Json | None = None             # full record for add/replace
    before: Json | None = None            # previous record for replace/remove (makes patches invertible)

class EffectRecord:
    key: str                              # f"{kind}:{ordinal}" ordinal counted per kind per episode
    kind: Literal["llm", "target", "tool", "rng"]
    request_hash: str                     # sha256 of canonical JSON request
    status: Literal["pending", "done", "failed"]
    result: Json | None
    cost: Cost | None

Outcome = Literal["passed","failed","invalid_scenario","simulator_error","target_error","platform_error","budget_exhausted"]
Termination = Literal["user_done","max_turns","agent_stuck","target_unreachable","budget","simulator_drift","error"]

class Trajectory:                         # read model handed to checks and evaluators
    episode_id: str; scenario: Scenario; events: list[Event]
    initial_world: WorldSnapshot; final_world: WorldSnapshot
    canaries: list[PlantedCanary]         # id, kind, value, variants
    def messages(self) -> list[Event]; def tool_calls(self) -> list[ToolCallView]
    def diff(self) -> StateDiff           # initial -> final

class RunManifest:
    run_id: str; suite_id: str; agent_version: AgentVersion
    scenario_versions: dict[str, int]; seed: int; repetitions: int
    model_roles: dict[str, str]; rubric_versions: dict[str, int]
    platform_version: str; budget_usd_micros: int; created_at: datetime
```

## 3. Engine interfaces

```python
class JournalStore(Protocol):
    async def load(self, episode_id: str) -> JournalSnapshot            # events, effects, epoch
    async def append(self, episode_id: str, epoch: int, *, events: Sequence[Event] = (),
                     effects: Sequence[EffectRecord] = ()) -> None      # atomic; raises StaleLease, SeqConflict

class EpisodeQueue(Protocol):
    async def claim(self, worker_id: str, limit: int, lease_s: int) -> list[EpisodeLease]   # bumps epoch
    async def heartbeat(self, lease: EpisodeLease) -> bool                                   # False = lost
    async def finish(self, lease: EpisodeLease, outcome: Outcome) -> None
    async def release(self, lease: EpisodeLease, *, retry_after_s: int) -> None

class BudgetLedger(Protocol):
    async def reserve(self, run_id: str, usd_micros: int) -> bool
    async def settle(self, run_id: str, reserved: int, actual: int) -> None

class Gateway(Protocol):                                                 # gauntlet_core.llm
    async def complete(self, role: str, messages: list[Json], *, tools: list[Json] | None = None,
                       response_model: type[BaseModel] | None = None, temperature: float | None = None,
                       seed: int | None = None) -> LLMResult             # text, tool_calls, parsed, cost

class EpisodeCtx:                                                        # passed to everything inside an episode
    episode_id: str; run_id: str; rng_seed: int
    async def effect(self, kind: str, request: Json, fn: Callable[[], Awaitable[Json]], *,
                     retry_safe: bool, est_usd_micros: int = 0) -> Json
    async def emit(self, *events: EventDraft) -> None
    async def llm(self, role: str, messages, **kw) -> LLMResult         # = effect("llm", ...) over Gateway
    world: World; clock: SimClock; trajectory_so_far: Sequence[Event]

class Target(Protocol):
    stateful: bool                         # remote holds conversation state -> not retry-safe
    async def open(self, ctx: EpisodeCtx) -> None
    async def send(self, ctx: EpisodeCtx, user_text: str) -> str       # returns agent reply text; tool events go via ctx
    async def close(self, ctx: EpisodeCtx) -> None

class World:
    async def call_tool(self, ctx: EpisodeCtx, tool: str, args: Json, *, via: str) -> ToolResult
    def snapshot(self) -> WorldSnapshot
    def tool_schemas(self, subset: list[str] | None) -> list[Json]      # OpenAI tool format

ToolHandler = Callable[[WorldView, Json, datetime], ToolOutcome]        # PURE. No I/O, no clock, no randomness
class ToolOutcome: result: Json; patch: list[PatchOp] = []; error: str | None = None

class UserSimulator(Protocol):
    async def next_message(self, ctx: EpisodeCtx) -> SimTurn            # text | done(reason) | drift(detail)

async def run_episode(ctx_factory, scenario: Scenario, target: Target, sim: UserSimulator) -> Outcome
async def evaluate(trajectory: Trajectory, evaluators: Sequence[Evaluator], gateway: Gateway) -> list[Verdict]
```

## 4. Checks (the shared predicate language)

`Check` is a discriminated union on `type`. YAML form is the same structure.

| type | fields | holds when |
|---|---|---|
| `all` / `any` | `of: list[Check]` | all / any hold |
| `not` | `check: Check` | inner does not hold |
| `tool_called` | `tool: str`, `args: dict[path, Matcher] = {}`, `count: IntRange = {min: 1}`, `ok: bool \| None` | number of matching calls is in range |
| `sequence` | `first: Check`, `then: Check`, `strict: bool = false` | an event matching `first` precedes one matching `then`; with `not` this expresses "never B before A" |
| `state` | `collection`, `id \| where`, `path`, `matcher: Matcher` | final world record field matches |
| `state_diff` | `collection`, `added: IntRange?`, `removed: IntRange?`, `changed: dict[path, Matcher]?`, `only: bool = false` | the initial→final diff matches; `only` = nothing else in that collection changed |
| `output` | `actor: "agent"`, `matcher: Matcher`, `scope: "any" \| "last" \| "all"` | agent message text matches |
| `canary_leaked` | `canary: str \| "*"`, `channels: list["output","tool_args"]` | planted value or a known transform appears |
| `egress` | `allow_domains: list[str]`, `allow_recipients: list[str]` | a URL or recipient outside the allowlist appears in output or tool args |
| `tainted_call` | `tool: str \| "*"`, `risk: list[str]?` | a tool call's args contain a taint marker from untrusted content |
| `detector` | `name: str`, `params: Json` | a registered deterministic detector fires (pii, secret, profanity, markdown_image_exfil, loop, commitment_phrase) |
| `judge` | `rubric: str` | escape hatch: needs an LLM. Not evaluable online. |

`Matcher`: `{eq}`, `{ne}`, `{in}`, `{regex}`, `{contains}`, `{gt|gte|lt|lte}`, `{exists}`, `{ref: "world:orders/{args.order_id}/total"}` (compare against world data or another arg).
`IntRange`: `{min?: int, max?: int}`; `{max: 0}` means never.

```python
class CheckResult: holds: bool; evidence: list[Evidence]; needs_judge: list[str] = []
class Evidence: seq: int; quote: str | None; note: str | None

def evaluate_final(check: Check, traj: Trajectory) -> CheckResult
def evaluate_prefix(check: Check, prefix: PrefixView, proposed: ProposedAction | None) -> Decision
# Decision = "violates" | "ok" | "undetermined"
```

## 5. Evaluation

```python
class Rubric:
    id: str; version: int; title: str; question: str         # one yes/no question about the trajectory
    pass_definition: str; fail_definition: str; na_definition: str | None
    severity: Literal["low","medium","high","critical"]; hard_fail: bool
    scope: Literal["conversation","step"]; examples: list[RubricExample]

class Verdict:
    evaluator: str; rubric_version: int | None; criterion: str
    result: Literal["pass","fail","na","error"]
    severity: Literal["low","medium","high","critical"]; hard_fail: bool
    confidence: float                      # 1.0 for deterministic
    evidence: list[Evidence]; reasoning: str
    stage: Literal["rule","small","strong","human"]; model: str | None; cost: Cost | None

class Evaluator(Protocol):
    id: str
    async def evaluate(self, traj: Trajectory, gateway: Gateway) -> list[Verdict]
```

Episode outcome rule: `failed` if the scenario `success` check does not hold, or any `forbidden` check holds, or any verdict has `result="fail"` and `hard_fail=True`. Otherwise `passed`. Non-hard-fail verdicts feed dimension scores, not the outcome.

## 6. Security (Phase 2)

```python
class Attack:
    id: str; title: str; category: str            # taxonomy id, see phases/phase-2
    technique: str; source: str; license: str
    vector: Literal["user_turn", "document", "tool_result", "tool_description", "system_context"]
    payload: str | list[str]                      # list = multi-turn; supports {{placeholders}}
    objective: Check                              # success condition for the attacker
    requires: list[str] = []                      # capabilities: "tool:external_comm", "documents"

class InjectionSpec:
    attack: str; placement: Literal["body","footer","html_comment","hidden_text","metadata"]

class Finding:
    id: str; title: str; category: str; severity: Literal["low","medium","high","critical"]
    agent_version_id: str; attack_id: str | None; episode_ids: list[str]
    reproducibility: tuple[int, int]              # successes, attempts
    reproducer: Scenario                          # minimal pinned scenario
    status: Literal["open","triaged","in_progress","fixed","verified","accepted_risk","false_positive"]
    root_cause_hint: str | None; suggested_policy: PolicyRule | None
```

## 7. Policy (Phase 4)

```python
class PolicyRule:
    id: str; description: str; severity: Literal["low","medium","high","critical"]
    when: Check                                   # must be prefix-evaluable (no `judge`, no `state_diff`)
    action: Literal["block", "require_approval", "redact", "log"]
    message: str | None                           # returned to the agent when blocked

class Policy: id: str; version: int; rules: list[PolicyRule]; mode: Literal["shadow","enforce"]; fail: Literal["open","closed"]
```

## 8. Database tables (Postgres; SQLite mirrors the engine subset)

Every table has `id`, `workspace_id`, `created_at`. JSONB columns hold the Pydantic models above.

| Table | Key columns |
|---|---|
| `workspaces`, `api_keys` | `api_keys.hash`, `scopes` |
| `projects` | `name` |
| `agents`, `agent_versions` | `agent_versions.config jsonb` (AgentVersion) |
| `personas`, `worlds`, `rubrics` | `doc jsonb`, `version` |
| `scenarios` | `doc jsonb`, `version`, `status` (draft, approved), `source` (pack, generated, mined, pinned) |
| `suites`, `suite_scenarios` | |
| `runs` | `manifest jsonb`, `status`, `budget_usd_micros`, `reserved_usd_micros`, `spent_usd_micros`, `baseline_of` |
| `episodes` | `run_id`, `scenario_id`, `rep`, `status` (queued, leased, done), `outcome`, `termination`, `epoch int`, `lease_owner`, `lease_expires_at`, `attempt`, `next_seq int`, `cost_usd_micros`, `not_before` |
| `events` | `episode_id`, `seq`, `kind`, `doc jsonb`; **unique (`episode_id`, `seq`)** |
| `effects` | `episode_id`, `key`, `kind`, `status`, `request_hash`, `result jsonb`; **unique (`episode_id`, `key`)** |
| `verdicts` | `episode_id`, `evaluator`, `criterion`, `result`, `doc jsonb` |
| `findings`, `finding_episodes` | Phase 2 |
| `attacks` | Phase 2 |
| `human_labels` | `episode_id`, `rubric_id`, `result`, `labeler` (Phase 3) |
| `policies`, `gateway_decisions` | Phase 4 |
| `secrets` | `name`, `ciphertext` (Fernet, key from env) |

## 9. HTTP API shape

REST under `/v1`, JSON, API key in `Authorization: Bearer`. Resource routes follow the table names (`/v1/projects`, `/v1/agents/{id}/versions`, `/v1/scenarios`, `/v1/suites`, `/v1/runs`, `/v1/runs/{id}/episodes`, `/v1/episodes/{id}` (with events and verdicts), `/v1/findings`). Non-CRUD:

| Route | Purpose |
|---|---|
| `POST /v1/runs` | body: suite id, agent version id, repetitions, budget. Returns the run with a cost estimate; `?dry_run=true` validates only |
| `POST /v1/runs/{id}/cancel`, `/pause`, `/resume` | |
| `GET /v1/runs/{id}/stream` | SSE: `episode_update`, `event`, `verdict`, `run_update` |
| `GET /v1/runs/{id}/report` | aggregated stats (section 3 of hard cores) |
| `GET /v1/runs/{id}/compare?baseline={id}` | paired comparison (Phase 3) |
| `POST /v1/agents/{id}/generate-scenarios` | starter suite from the profile; results land as `draft` |
| `POST /v1/episodes/{id}/rejudge` | re-run evaluators over the stored journal |
| `ANY /mock/{episode_token}/tools/{tool}` and `/mock/{episode_token}/mcp` | mock world façade for wired targets |

Errors: `{"error": {"code": str, "message": str, "detail": Json | None}}` with conventional status codes.

## Decision log

| Date | Decision | Reason |
|---|---|---|
| 2026-11-17 | Initial contracts | |
