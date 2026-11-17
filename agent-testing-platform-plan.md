# Gauntlet: Agent Testing, Simulation and Security Platform

*Working title. Alternatives: Crucible, AgentProbe, Stresstest, Proving Ground.*

**One-liner:** Point it at any AI agent. It simulates hundreds of realistic and hostile users against a mock world, scores every conversation, finds security holes, pins every fix as a permanent regression test, and can enforce the lessons live as a runtime gateway.

**Document scope:** features and design only, no code. Every section says what the capability is, what it must contain, and why it matters. Items marked **[MVP]** are the vertical slice worth building first. Items marked **[Wow]** are the differentiators that make recruiters and founders stop scrolling.

---

## 1. Vision and positioning

### 1.1 The problem
- Teams ship agents (customer support, coding, data, voice, browser) with almost no systematic testing. "Vibe checks" and a handful of prompts are the norm.
- Agents are non-deterministic, multi-turn, tool-using, and stateful. Unit tests and simple prompt evals do not capture how they fail: wrong tool, wrong argument, loop, policy violation, leaked data, getting talked into something by a user, or being hijacked by content inside a tool result.
- Security is the same story. Prompt injection, tool abuse, and data exfiltration are real, but most teams find out in production.
- Model upgrades, prompt edits, and tool changes silently break behavior, and nobody can say what changed.

### 1.2 The product thesis
Testing and security for agents are the same problem: *put the agent in a controlled world with adversarial and realistic actors, observe everything, judge it rigorously, and turn every failure into a permanent test.* One platform should do all of it, with a closed loop:

**Simulate → Judge → Find failures → Explain → Fix → Pin as regression → Gate releases → Enforce at runtime → Learn from production → Simulate again.**

### 1.3 Who it is for
- Engineers building agents who want CI for agent quality.
- Security teams who need evidence about agent risk.
- Product and support leads who want to know "will it embarrass us?" before launch.
- Hiring managers evaluating you: it demonstrates systems depth, AI depth, security thinking, and product sense in one repo.

### 1.4 Design principles
1. **Framework-agnostic and black-box first.** Works against any agent reachable by HTTP, SDK, MCP, or a voice line. Gray-box (traces) and white-box (config access) unlock deeper checks, but are optional.
2. **Reproducible by default.** Every run is replayable from a manifest and recorded interactions. Flaky science is a bug.
3. **Statistical honesty.** Agents are probabilistic, so report rates and confidence intervals, not single pass/fail anecdotes.
4. **Deterministic checks first, LLM judges second.** Cheap, reliable rules catch most things. LLM judges handle the subjective remainder, and are themselves measured.
5. **Cost-aware.** Every run shows an estimate before it starts and a budget cap while it runs. It must work on free or cheap model tiers.
6. **Evidence over opinions.** Every verdict cites quotes, step numbers, and state diffs.
7. **Safe by construction.** Attack tooling runs only against targets the user has proven they own or are authorized to test.
8. **Open-core friendly.** Core engine and CLI open source, hosted dashboard optional.

### 1.5 Landscape and differentiation
Existing tools to study (verify their current state before you rely on this list): promptfoo (eval and red-team CLI), NVIDIA garak (LLM vulnerability scanner), Microsoft PyRIT (red-teaming framework), Sierra's tau-bench (simulated-user agent benchmark with the pass^k reliability metric), ETH's AgentDojo (prompt-injection benchmark for tool agents), Langfuse, LangSmith and Braintrust (tracing and evals), plus voice-testing startups.

What most of them do not combine in one product:
- Stateful, multi-turn user **simulation** with personas, plus **security** attacks in the same harness.
- A **mock world** with fault injection and end-state verification.
- **Closed loop** from red team finding to gateway rule to verified fix.
- **Policy testing** that measures both attack block rate and false positives.
- **Production mining** that converts real failures into new scenarios.
- **Meta-evaluation**: measuring and publishing the accuracy of your own judges and attackers.

That combination is your positioning.

---

## 2. Domain model (the vocabulary everything else uses)

- **Workspace / Project:** a tenant boundary and a grouping for one product's agents.
- **Target Agent:** the system under test, with a connector, a profile card, and versions.
- **Agent Version / Snapshot:** a labeled configuration (prompt, model, tools, policies) so runs are comparable over time.
- **Connector:** how the platform talks to the target (HTTP chat, SDK, MCP, voice, browser).
- **Environment (Mock World):** simulated tools, APIs, databases, documents, and websites the agent can use during tests.
- **Persona:** a simulated human (or adversary) with traits, knowledge, hidden facts, and behavioral rules.
- **Scenario:** a test case: goal, persona, starting world state, constraints, success criteria, termination rules.
- **Suite:** a named collection of scenarios (smoke, regression, security, load, voice).
- **Attack:** a reusable adversarial technique with metadata and success conditions.
- **Campaign:** a goal-driven red-team effort that generates and mutates attacks adaptively.
- **Run:** one execution of a suite against one agent version. Contains many **Episodes** (one scenario, one repetition).
- **Trajectory:** the full ordered record of an episode: messages, tool calls, tool results, state changes, timings, tokens.
- **Evaluator:** a rule, model, or human that scores a trajectory against a rubric.
- **Rubric:** a versioned definition of what good and bad look like, per dimension.
- **Finding:** a confirmed problem with severity, evidence, reproducer, and lifecycle status.
- **Baseline:** the reference run that new runs are compared against.
- **Gate:** a pass/fail policy applied to a run (for CI or release).
- **Policy (runtime):** a rule set enforced by the gateway.

---

## 3. High-level architecture

Think in five planes:

1. **Control plane:** API, auth, workspaces, projects, scenario and suite management, scheduling, budgets, reports. Stateless services backed by a relational database.
2. **Execution plane:** durable job queue and worker fleet that run episodes. Each worker coordinates the user simulator, the target agent connector, the mock world, and the trace recorder. Needs crash-safe, resumable execution, because episodes are long and expensive.
3. **Intelligence plane:** a model gateway (multi-provider, BYO keys, routing, fallbacks, caching, cost tracking) used by simulators, attackers, generators, and judges. It is its own service so you can swap providers and use free tiers.
4. **Data plane:** relational store for metadata, a trace store for trajectories and spans (relational with JSON is fine at first, an analytics store later), object storage for artifacts (audio, screenshots, cassettes, reports), cache and rate-limit store, and a vector index for clustering and scenario similarity search.
5. **Experience plane:** web dashboard, CLI, SDKs, GitHub integration, webhooks, and an MCP server so other agents can drive the platform.

Cross-cutting: tenant isolation, secrets vault, audit log, OpenTelemetry for the platform itself, feature flags, and background maintenance jobs (retention, re-indexing, judge calibration).

**Stack fit for you** (reuses what you have shipped): FastAPI, PostgreSQL, Redis, Celery or a custom durable workflow layer, S3-compatible storage, Next.js dashboard, Turborepo monorepo, Docker for sandboxes. Add an analytics store only when trace volume demands it.

---

## 4. Target agent integration (Connectors)

### 4.1 Connector types
- **HTTP chat endpoint [MVP]:** request and response templates, JSON path mapping for the reply text, conversation ID handling, header and auth injection.
- **OpenAI-compatible endpoint [MVP]:** zero-config for anything that speaks the chat completions shape, including streaming.
- **Streaming protocols:** server-sent events and WebSocket, with token-level timing capture.
- **Framework adapters:** LangGraph or LangChain graphs, CrewAI, OpenAI Agents SDK, AutoGen-style systems. Each adapter hooks tool calls and node transitions for gray-box tracing.
- **SDK wrapper:** a thin decorator-style integration so a Python or TypeScript function can be registered as a target, running locally and reporting to the platform.
- **MCP server target:** test an MCP server's tools directly, including tool description quality and security.
- **Container target:** the user supplies a Docker image or compose file, the platform runs it in a sandbox with controlled networking.
- **Voice target:** SIP number, WebRTC room (LiveKit), or phone dial-out. Later phase, see Section 5.9.
- **Browser or UI agent target:** the platform provides a controlled web environment and observes via a browser automation layer.
- **Async or webhook agents:** agents that reply later via callback, with timeout and correlation handling.
- **Agent-to-agent:** two or more targets conversing, for multi-agent system tests.

### 4.2 Connection setup experience
- Guided wizard: choose connector, paste endpoint or install SDK, send a test message, confirm the reply mapping visually.
- **Capability discovery:** import OpenAPI specs, MCP tool lists, or tool schemas to learn what the agent can do. Produces a **tool inventory** with risk classification (read, write, destructive, financial, external-communication).
- **Agent profile card:** purpose, audience, tools, data sensitivities, policies, language support, escalation paths, forbidden behaviors. Can be partly auto-extracted from a system prompt or docs, then edited by the user. The profile drives scenario and attack generation.
- **Knowledge of the agent's rules:** upload policy documents (refund policy, compliance rules). The platform converts them into checkable **policy rules** (see Section 7).

### 4.3 Observability levels
- **Black-box:** only inputs and outputs.
- **Gray-box [MVP+]:** OpenTelemetry or OpenInference trace ingestion lets the platform see internal tool calls, retrievals, and model calls. Enables tool-use evals and richer root-cause analysis.
- **White-box:** access to config or system prompt enables prompt-hardening suggestions and extraction-attack verification (does the leaked text match the real prompt?).

### 4.4 Safety and authorization of targets
- **Ownership verification:** for hosted endpoints, require a challenge (a token the target must echo, or a file at a known path) before attack suites can run. Local and self-hosted targets are implicitly authorized.
- **Scope controls:** allowed hosts, allowed tools, blocked destructive actions in real environments, global rate limits, kill switch.
- **Sandbox-only mode:** forces the target to use the mock world, never real systems.
- **Responsible-use banner and audit log** for every attack run.

### 4.5 Reliability of the connector itself
- Retries with backoff, timeout policy, and circuit breaker so a flaky target does not burn budget.
- Distinguish **target failures** (agent errored) from **platform failures** (our bug) in every report.
- Health checks and a connector self-test before every run.
- Secrets stored encrypted and never written to traces.

---

## 5. Simulation engine

This is the heart of the product. It turns "a list of prompts" into "realistic, repeatable, stateful interactions in a controlled world."

### 5.1 Scenario model
Each scenario contains:
- **Goal:** what the simulated user wants (and what counts as success from the user's perspective).
- **Persona reference** and optional overrides.
- **Initial world state:** database contents, account data, documents, time and date, feature flags.
- **Available tools** for the agent in this scenario (can differ from the default inventory).
- **Hidden facts:** things the user knows but will only reveal if asked properly (order number, real reason for the call).
- **Constraints and traps:** an out-of-policy request, a contradictory instruction, missing information, a user who lies.
- **Success criteria:** conversation-level, state-level, and policy-level conditions.
- **Termination rules:** max turns, max cost, success reached, agent stuck, user gives up.
- **Tags:** intent, difficulty, risk area, language, channel, owner.
- **Expected behaviors and forbidden behaviors** as explicit lists for evaluators.

Scenarios are stored as structured, versioned documents. They can be edited in a visual studio or imported and exported as YAML or JSON so they live in the user's git repo.

### 5.2 Scenario sources (how you never start from a blank page)
1. **Auto-generation from the agent profile:** the platform reads purpose, tools, and policies and generates a balanced starter suite (happy paths, edge cases, policy boundaries, failure recovery). **[MVP]**
2. **Generation from documents:** upload FAQs, policy PDFs, API docs, or runbooks. The platform extracts testable rules and creates scenarios for each.
3. **Generation from tools:** for each tool, create scenarios that exercise correct use, missing arguments, wrong arguments, ordering dependencies, and error handling.
4. **Mutation of existing scenarios:** paraphrase, change persona, add noise, swap language, add distractions, escalate emotion, change constraints. Produces many variants from one seed.
5. **Production log mining:** convert real conversations into scenarios, with anonymization (see Section 11).
6. **Failure-driven generation:** after a finding, auto-generate neighbors of the failing scenario to probe the same weakness from different angles.
7. **Benchmark imports:** tau-bench style retail and airline tasks, AgentDojo suites, and others, so you can report comparable scores. **[Wow]**
8. **Template library:** curated, tagged scenario packs per industry (e-commerce support, banking, healthcare scheduling, HR helpdesk, travel, SaaS support, internal IT desk, coding assistant, data analyst, sales assistant).
9. **Coverage-guided generation:** the platform identifies untested tools, policies, intents, and personas, and proposes scenarios to fill the gaps.
10. **Human review step:** generated scenarios land in an approval queue so the user can accept, edit, or reject before they enter a suite.

### 5.3 Persona engine
Personas make simulated users feel real and expose different failure modes.
- **Trait dimensions:** goal clarity, patience, technical literacy, emotional state (calm, anxious, angry, grieving), verbosity, politeness, honesty, persistence, trust in AI, domain knowledge, reading level, multitasking or distraction, formality, typo rate, slang and dialect, language and code-switching, accessibility needs (screen reader phrasing, cognitive load, voice-only).
- **Behavior rules:** "never volunteers information unless asked directly," "changes mind once mid-conversation," "gets frustrated after two misunderstandings," "asks for a human after three failures."
- **Adversarial intents:** social engineer, boundary pusher, prompt injector, competitor probing for the system prompt, scammer impersonating an employee, curious teenager, refund abuser.
- **Knowledge model:** what the persona knows, believes (possibly wrongly), and has on hand (documents, IDs).
- **Consistency enforcement:** a persona memory that prevents the simulator from contradicting itself or leaking hidden facts early. A separate "persona guard" check flags simulator drift.
- **Persona library and sampling:** weighted distributions (for example, 60% cooperative, 25% impatient, 10% confused, 5% adversarial) so a suite reflects a realistic user mix.
- **Persona sensitivity analysis:** after a run, report which traits correlate with failure ("agent success drops from 91% to 54% with low-literacy, high-anger personas"). **[Wow]**

### 5.4 Conversation simulation
- **User simulator:** an LLM role-playing the persona with strict instructions, hidden facts, and turn-by-turn state. Options for cheaper scripted or rule-based users on deterministic scenarios.
- **Turn management:** variable turn pacing, optional delays, partial messages, message bursts, edits, and retractions.
- **Conversation dynamics to test:**
  - Interruptions and topic switches.
  - Mid-conversation goal change.
  - Ambiguous or incomplete requests that require clarification.
  - Contradicting earlier statements.
  - Pasting long, messy content.
  - Multilingual and code-switched turns.
  - Silence, one-word replies, and sarcasm.
  - Returning user across sessions (memory tests).
  - Multi-party chats (a manager and an employee in the same thread).
  - Very long conversations that stress context limits and summarization.
- **Termination detection:** success reached, user satisfied, stuck loop, agent refuses repeatedly, budget exhausted, or max turns. The termination reason is itself a recorded outcome.
- **Simulator quality controls:** the simulator is tested too (does it stay in character, does it follow hidden-fact rules). Judge simulator fidelity separately so you do not blame the agent for a bad simulator.

### 5.5 Environment simulation (the mock world)
- **Mock tool layer:** auto-generated mock servers from OpenAPI specs and MCP schemas, so users get a working sandbox in minutes. **[MVP]**
- **Stateful mock backends:** in-memory or lightweight database with seed data generators (customers, orders, tickets, accounts, calendars, files). Tools read and write real state, so the agent's actions have consequences.
- **Two response modes:**
  - *Deterministic:* real logic over seeded data. Used for state verification.
  - *LLM-simulated:* a model invents plausible responses when no logic exists. Cheaper to set up, noisier, and clearly labeled in reports.
- **World-state diff verification [Wow]:** at the end of an episode, compare the world state to the expected end state. This catches an agent that says "refund issued" but did not issue one, or issued two.
- **Fault injection:** latency spikes, timeouts, HTTP 4xx and 5xx, rate limits, malformed or truncated JSON, empty results, huge payloads, duplicate responses, stale data, partial success, schema drift (a field renamed), contradictory results from two tools, and tools that flip between available and unavailable.
- **Poisoned content:** documents, emails, web pages, search results, and tool outputs that contain hidden instructions or misleading facts. Used by security scenarios and by robustness scenarios.
- **Simulated web and documents:** a fake website set, mailbox, file system, and calendar for browser, email, and file agents.
- **Time control:** simulated clock, so "appointment tomorrow" and "refund window expired" are testable and deterministic.
- **Snapshots and rollback:** save world state at any step, branch from it, and replay alternative agent decisions.
- **Real-environment mode (optional):** run against a staging environment through a sandbox, with guardrails that block destructive calls.

### 5.6 Determinism, replay, and reliability statistics
- **Run manifest:** captures agent version, model versions, parameters, scenario version, persona version, seeds, environment image, judge versions, and platform version.
- **Record and replay (cassettes) [Wow]:** record every model call and tool response, so a failure can be replayed exactly, and judges can be re-run on old trajectories without re-running the agent.
- **Repetition and variance:** run each scenario N times. Report pass rate with confidence intervals.
- **pass^k reliability:** the probability the agent succeeds on all k independent attempts, which is far more informative for production than average success. **[Wow]**
- **Flaky scenario detection:** scenarios whose outcome varies due to simulator or judge noise rather than agent behavior get flagged and quarantined for repair.
- **Seed sweeps** to explore sensitivity, and temperature controls for the simulator.
- **Drift annotations:** note when the underlying model provider changed behavior.

### 5.7 Scheduling, scale, and cost control
- **Cost estimator** before launch (expected tokens, expected calls, expected dollars) and **hard budget caps** during a run.
- **Concurrency control** with per-provider rate-limit awareness and backoff.
- **Priority queues:** smoke tests jump ahead of nightly full suites.
- **Pause, resume, cancel, and retry-failed-only.**
- **Adaptive sampling:** stop early when results are statistically clear (very high or very low pass rate), and spend the budget on ambiguous scenarios. **[Wow]**
- **Dry-run mode:** validates scenarios, connectors, and mock worlds without calling expensive models.
- **Load and soak testing mode:** many parallel simulated users, measure latency, error rate, rate-limit behavior, and cost under load.

### 5.8 Multi-agent and long-horizon testing
- Test orchestrators and sub-agents together and individually.
- Track message passing between agents, handoff correctness, duplicated work, deadlocks, and runaway loops.
- Inject a compromised or faulty sub-agent to test containment.
- Long-horizon tasks with checkpoints: score progress at milestones, not only the final answer.

### 5.9 Voice simulation (Phase 5, optional but high-impact)
- **Simulated callers:** persona drives text, converted to speech by an open-source text-to-speech model, with accent, speed, and noise controls.
- **Speech to text** on the agent's audio to evaluate content, using an open-source recognizer.
- **Telephony realism:** background noise, poor connection, packet loss, barge-in (user talks over the agent), long pauses, DTMF tones, hold music, and mid-sentence corrections.
- **Voice-specific metrics:** time to first audio, turn-taking latency, interruption handling, talk-over rate, silence gaps, transcription error sensitivity, and prosody or tone checks.
- **Integration:** LiveKit rooms and SIP trunks as connectors. No paid realtime API required, because the platform tests the agent, it does not need to be a premium voice stack.
- Reuses the same scenarios, personas, and judges as text, which is the selling point.

---

## 6. Evaluation system

### 6.1 Evaluator families
**Deterministic evaluators (fast, cheap, trusted) [MVP]**
- Text and format: regex, exact and fuzzy match, JSON schema validation, required and forbidden phrases, length limits, language check.
- Tool-call assertions: tool was called or not, called with correct arguments, called in a valid order, called exactly once, never called.
- State assertions: the end world state matches expectations.
- Policy rules compiled from documents (Section 7).
- Safety detectors: PII patterns, secret and key patterns, canary tokens, forbidden URLs, markdown-image exfiltration patterns.
- Efficiency checks: turn count, tool calls count, repeated identical calls, loop detection, token and cost thresholds, latency percentiles.

**Model-based evaluators (LLM judges) [MVP]**
- Task completion and goal achievement with partial credit.
- Helpfulness, correctness, completeness.
- Groundedness and hallucination against provided context or tool results.
- Instruction following and persona or brand voice adherence.
- Tone, empathy, and de-escalation quality.
- Over-refusal and under-refusal (refused something legitimate, or complied with something it should refuse).
- Honesty about limits (did it admit it could not do something, or pretend).
- Clarification quality (asked the right question, at the right time).
- Escalation correctness (handed off when it should, not when it should not).
- Safety and harm assessment.
- Conversation-level and step-level scoring.

**Trajectory evaluators**
- Was the path sensible or wasteful?
- Did the agent recover from tool errors?
- Did it verify before taking irreversible actions?
- Did it ask for confirmation on risky steps?
- Did it leak internal reasoning or tool names to the user?

**Comparative evaluators**
- Pairwise comparison of two agent versions on the same scenario with position-bias controls.
- Reference-based comparison against a gold transcript or gold final state.

**Human evaluators**
- Annotation queue with side-by-side transcript, tool timeline, and judge reasoning.
- Labels override automated verdicts and feed calibration.

### 6.2 Making judges trustworthy (this is where cheap platforms fail)
- **Rubrics as versioned artifacts** with anchored scale descriptions (what a 1, 3, and 5 look like) and explicit failure definitions.
- **Evidence requirement:** every verdict must quote transcript spans and reference step numbers. Verdicts without evidence are rejected.
- **Reasoning before score** and structured output validation.
- **Judge ensembles:** multiple judges or multiple samples, with majority or conservative aggregation, and a disagreement flag.
- **Cascades to save money:** rules first, small model second, strong model only on uncertain or high-severity cases. **[Wow]**
- **Bias controls:** randomize positions, hide agent identity, normalize length effects.
- **Calibration against human labels:** maintain a golden labeled set per rubric, measure agreement (accuracy, precision and recall for failures, Cohen's kappa), and block a rubric from gating CI until it meets a minimum agreement threshold.
- **Judge drift monitoring:** re-run the golden set when judge models or prompts change, and alert on shifts.
- **Self-consistency checks:** the same trajectory judged repeatedly should produce stable results.
- **Judge-model separation:** warn when the judge and the target are the same model family, since self-preference bias inflates scores.

### 6.3 Scoring model
- Per-episode, per-dimension scores with severity weighting (a policy violation outweighs a clumsy sentence).
- Hard-fail rules: some failures zero the episode regardless of other scores.
- Composite scores with user-defined weights.
- **Release readiness score** combining success rate, reliability (pass^k), safety, cost, and latency, with confidence intervals. **[Wow]**
- Separate "agent failed" from "scenario invalid" and "simulator misbehaved" outcomes.

### 6.4 Metric catalog
Task success rate, pass^k reliability, partial-goal progress, policy violation rate, hallucination rate, tool selection accuracy, argument accuracy, tool error recovery rate, unnecessary tool call rate, loop rate, clarification rate, escalation precision and recall, refusal precision and recall, average turns to resolution, cost per resolved task, p50 and p95 latency, tokens per task, sensitivity to persona traits, robustness under fault injection, security attack success rate, leakage rate, and unsafe-action rate.

---

## 7. Policy and rules compiler

Many agent failures are "it did something the business does not allow." Make policies first-class.
- **Policy ingestion:** upload natural-language policies (refund rules, KYC steps, medical disclaimers, tone guidelines).
- **Rule extraction:** the platform proposes atomic, testable rules ("refunds over $100 require manager approval," "never reveal another customer's data," "always verify identity before account changes").
- **Rule typing:** each rule is tagged as machine-checkable (tool and state conditions), model-checkable (needs a judge), or human-only.
- **Rule review UI:** edit, approve, set severity, and link to scenarios.
- **Compiled checks:** machine-checkable rules become deterministic evaluators and mock-world assertions.
- **Policy coverage report:** which rules have scenarios, which have none, and which were violated.
- **Policy versioning and diff:** when policy changes, show which scenarios and baselines are affected.
- **Reuse at runtime:** the same rules feed the gateway (Section 9), so test and enforcement never diverge.

---

## 8. Security and red-team module

### 8.1 Threat taxonomy (the coverage map)
Map everything to recognized frameworks so reports carry credibility: the OWASP Top 10 for LLM Applications, OWASP's agentic AI threat guidance, MITRE ATLAS, and the NIST AI Risk Management Framework (check the current versions when you build). The platform shows a **coverage heatmap**: which threat categories have been tested, how many attacks, and the success rate.

Categories to implement:
1. **Direct prompt injection:** the user tries to override instructions (ignore previous rules, fake system messages, role reassignment).
2. **Indirect prompt injection [highest value]:** malicious instructions hidden in content the agent reads: emails, web pages, documents, PDFs, RAG chunks, calendar invites, tool outputs, API responses, code comments, image text (OCR), and spreadsheet cells.
3. **Jailbreaks:** roleplay and hypotheticals, persona switching, encoding tricks (base64, ROT13, leetspeak), multilingual and low-resource languages, unicode homoglyphs and invisible characters, payload splitting across turns, many-shot priming, gradual escalation (crescendo), fictional framing, and refusal-suppression prompts.
4. **System prompt and configuration extraction:** direct asks, translation tricks, "repeat the words above," summarization tricks, and tool-description leakage.
5. **Sensitive data disclosure:** PII, credentials, internal documents, other users' data, other tenants' data, and training or context leakage. Tested with planted **canary secrets** (Section 8.3).
6. **Excessive agency and tool abuse:** unauthorized actions, privilege escalation, confused-deputy attacks (the agent uses its authority on behalf of the attacker), parameter tampering, chaining low-risk tools into a high-risk outcome, and acting without confirmation.
7. **Injection through tools:** SQL injection through natural-language-to-SQL agents, command injection, path traversal, server-side request forgery through fetch tools, and template injection.
8. **Data exfiltration channels:** rendering attacker-controlled images or links in markdown, sending data to external URLs through tools, encoding data into URLs, email forwarding, and calendar-invite leaks.
9. **Memory and RAG poisoning:** planting malicious or false content in long-term memory, vector stores, or knowledge bases, and persistence across sessions.
10. **MCP-specific attacks:** tool poisoning (malicious instructions in tool descriptions), rug pulls (tool behavior or description changes after approval), tool shadowing (one server's tool impersonating or overriding another's), cross-server data leaks, over-permissioned tools, and unauthenticated servers.
11. **Social engineering of the agent:** impersonating an admin or developer, urgency and authority pressure, emotional manipulation, and fake policy updates.
12. **Resource abuse (denial of wallet):** infinite loops, recursion, token bombs, expensive tool call chains, and cost amplification.
13. **Harmful or policy-violating content:** domain-specific harms depending on the agent's audience.
14. **Bias and fairness probes:** differential treatment across demographic phrasing in decisions such as eligibility or pricing.
15. **Multi-agent attacks:** injection propagating from one agent to another, compromised sub-agents, and message spoofing between agents.
16. **Supply chain:** malicious plugins, skills, or tool packages, and hallucinated dependency or tool names that an attacker could register.
17. **Overreliance and deception:** the agent claims it did something it did not, or fabricates citations or tool results.

### 8.2 Attack engine
- **Attack library:** versioned, tagged (category, technique, difficulty, applicable agent types, required capabilities), with a source and a safe-use note. Seeded by your own curation and by imports from open datasets and scanners.
- **Static attacks:** curated payloads run as is. Fast regression baseline. **[MVP]**
- **Mutation engine:** paraphrase, translate, encode, obfuscate, wrap in roleplay, split across turns, embed in a document, and combine techniques.
- **Adaptive attacker agents [Wow]:** an LLM attacker with a goal (for example, "get the agent to email the customer list to an outside address") that reads the target's replies, adjusts strategy, and keeps trying within a budget. Implement known strategies: iterative refinement (PAIR style), tree-of-attacks search (TAP style), and gradual multi-turn escalation (crescendo style).
- **Search-based strategies:** genetic mutation and beam search over attack variants, using a fitness signal from partial success.
- **Attack objectives, not just prompts:** each campaign has a **success condition** that is checked deterministically wherever possible (a canary token appeared in output, a forbidden tool was called, a world-state change occurred).
- **Indirect injection harness:** builds poisoned documents, emails, web pages, and tool results in the mock world and places them in the agent's path, with realistic placement (footer, hidden text, metadata, comment).
- **Attacker budget and stop rules:** max attempts, max cost, stop on first success or continue to measure frequency.
- **Safety rails for the attack tooling itself:** attacks run only against authorized targets, outputs involving truly dangerous content (weapons, self-harm instructions) are classified and truncated in storage so the platform does not become a harmful-content generator.

### 8.3 Deterministic detection tools
- **Canary tokens:** plant fake secrets, API keys, and customer records in the mock world and system context. Any appearance in output or tool arguments is a confirmed leak. **[Wow]**
- **Honeytools:** decoy tools that no legitimate flow should call. A call is a proof of hijack.
- **Honey-records:** decoy accounts and documents that belong to "other users."
- **Egress monitor:** every outbound URL, email recipient, and tool argument is checked against an allowlist.
- **Taint tracking (research-grade, optional):** mark content from untrusted sources and detect when it influences privileged tool calls.

### 8.4 Findings management
- **Finding record:** title, category (mapped to frameworks), severity, affected agent version, evidence (full trajectory, quotes, state diff), reproducibility rate (for example, 7 of 10 attempts), and the exact attack used.
- **Severity model:** custom scoring based on impact, exploitability, required attacker skill, reach (how many users), and whether data or actions are irreversible.
- **Replay button:** one click to re-run the exact attack against the current version.
- **Minimal reproducer (shrinking) [Wow]:** automatically reduce a successful attack to the shortest version that still works (like test-case minimization), making findings clear and fixes easier to verify.
- **Root-cause hints:** the platform suggests whether the failure came from prompt weakness, over-broad tool permissions, missing confirmation steps, retrieval of untrusted content, or lack of output filtering.
- **Suggested mitigations:** hardened prompt wording, tool permission changes, argument validators, confirmation steps, gateway rules, and architecture changes (for example, separating a privileged and a quarantined model).
- **Lifecycle:** open, triaged, in progress, fixed, verified, accepted risk, false positive. Verification means automatic re-run of the pinned reproducer.
- **Regression pinning:** every fixed finding becomes a permanent scenario in the security regression suite.
- **Deduplication and clustering:** many attack variants that exploit one root cause collapse into one finding with variants listed.
- **Exports:** PDF and markdown reports, JSON, and SARIF so findings appear in GitHub code scanning. Ticket integrations (GitHub Issues, Jira, Linear).

### 8.5 Benchmarks and comparability
Import and report against public benchmarks so numbers are comparable (verify availability and licenses): AgentDojo, InjecAgent, tau-bench, HarmBench, JailbreakBench, and probe sets from garak. Provide a **head-to-head mode** that runs your attacker against the same targets as other open-source scanners and reports differences in coverage and success rate. **[Wow]**

### 8.6 Agent security posture report
A single exportable document per agent version:
- Executive summary and overall risk grade.
- Threat coverage heatmap.
- Top findings with evidence.
- Tool permission review (which tools are over-privileged).
- Data exposure map (what sensitive data the agent can reach).
- Comparison to the previous version.
- Recommended fixes in priority order.
- Compliance mapping (OWASP, NIST, and relevant internal controls).

---

## 9. Gateway mode (runtime protection)

The same intelligence used to test is deployed to protect. It sits between the application, the model, and the tools.

### 9.1 Deployment forms
- **Reverse proxy** in front of the model API and tool APIs.
- **SDK middleware** wrapping tool execution inside the agent.
- **MCP gateway** that proxies MCP servers and enforces policies on tool listing and tool calls.
- **Sidecar** pattern for container deployments.
- **Shadow mode** (observe and log only) versus **enforce mode** (block, modify, or require approval), switchable per policy.

### 9.2 Inspection pipeline
- **Input scanning:** prompt-injection detection, jailbreak patterns, toxic content, PII in user input, and abnormal length or encoding.
- **Content-origin tagging:** label every piece of context as trusted (system), user, or untrusted external (tool output, web, email, document). This tag follows the content through the pipeline.
- **Output scanning:** PII and secret redaction, canary detection, URL and markdown-image allowlisting, hallucinated link detection, and policy checks.
- **Tool-call interception:** every tool call is checked before execution.
- **Detection layers as a cascade:** fast heuristics and regex, a small open-source classifier (for example, Meta's Prompt Guard or Llama Guard class models, verify current options), and an LLM check only for ambiguous or high-risk cases. Tune for latency.

### 9.3 Policy engine
- **Policy-as-code** in a human-readable format with versioning, review, and rollback.
- **Rule types:**
  - Tool allowlists and denylists per user role, per agent, and per context.
  - Argument constraints (amount limits, allowed domains, allowed tables and columns, read-only mode).
  - Rate and budget limits per user, per session, and per tool.
  - **Taint rules:** content from untrusted sources cannot trigger privileged tools without approval.
  - Required approvals: human-in-the-loop for high-impact actions, with timeout and fallback behavior.
  - Data-loss prevention rules per data class.
  - Sequence rules ("after reading external content, block outbound email").
- **Approval workflows:** approve or deny from the dashboard, Slack, or email, with context and the exact action shown.
- **Fail-open or fail-closed** setting per policy, with explicit documentation of the tradeoff.
- **Latency budget:** overhead is measured and displayed. A gateway that adds seconds will not be adopted.

### 9.3b MCP-specific protections
- **Tool description pinning:** hash tool descriptions and schemas at approval time, alert or block on change (defends against rug pulls).
- **Server allowlist and trust levels.**
- **Namespace isolation** to prevent tool shadowing.
- **Description scanning** for hidden instructions before the model ever sees them.
- **Per-server permissions and scopes** and credential isolation.

### 9.4 Policy testing (the feature most security tools lack) **[Wow]**
- Run any proposed policy against two suites:
  1. **Attack suite:** what fraction of known attacks does it block?
  2. **Benign suite:** what fraction of legitimate scenarios does it break?
- Show the tradeoff curve (block rate versus false positive rate), per rule and in total.
- **Simulate before enforcing:** replay a week of production traffic through the policy in shadow mode to see what would have been blocked.
- **Closed loop:** a finding from the red team generates a suggested gateway rule, which is tested on both suites, then proposed for enforcement, then verified by re-running the pinned attack. This loop is the story you tell in demos.

### 9.5 Audit and forensics
- Immutable, searchable log of every decision (allowed, blocked, modified, approved) with the reason and the policy version.
- Incident timeline view that reconstructs an attack across turns and tool calls.
- Export for compliance and incident response.

---

## 10. Regression testing and CI/CD

- **Versioned agent snapshots:** every run is tied to an agent version, with a diff of what changed (prompt, model, tools, policies).
- **Baselines:** pick any run as the baseline per suite. Support multiple baselines (production, last release, best known).
- **Run comparison [MVP]:**
  - Scenario-level flip analysis: newly failing, newly passing, unchanged, flaky.
  - Dimension-level deltas (accuracy, safety, tone, cost, latency).
  - Statistical significance: is the change real or noise? Show confidence intervals and a plain-language verdict.
  - Side-by-side trajectory diff for any scenario.
- **GitHub integration [MVP+]:**
  - GitHub Action and GitHub App that runs a chosen suite on every pull request.
  - PR comment with a summary table, top regressions, links to replays, and cost of the run.
  - Status check that gates merges on user-defined thresholds (minimum success rate, zero critical findings, maximum cost per task, maximum p95 latency).
  - Badges for READMEs showing the latest score.
- **CLI:** run suites locally or in any CI system, with machine-readable output and exit codes.
- **Test selection:** run only scenarios affected by the change (touched tools, touched prompt sections, changed policies), plus a small always-on smoke set. Full suites run nightly.
- **Scheduled runs:** nightly regression, weekly deep security scan, and continuous canary runs against production-like environments.
- **Model migration reports [Wow]:** "swap model A for model B" runs the same suites on both and produces a quality, cost, latency, and safety comparison with a recommendation and a Pareto chart.
- **Prompt A/B testing:** compare prompt variants with proper statistics, and promote a winner.
- **Flaky test management:** quarantine, auto-retry policy, and a flakiness dashboard.
- **Notifications:** Slack, email, and webhooks on regressions, new critical findings, budget thresholds, and failed gates.

---

## 11. Production feedback loop

- **Trace ingestion:** standard OpenTelemetry and OpenInference spans, plus import from popular tracing tools, plus a simple API.
- **Privacy on ingest:** configurable PII redaction, field allowlists, sampling, and retention windows. Self-hosting option for sensitive data.
- **Failure mining:** detect bad conversations automatically using signals such as user frustration phrases, repeated rephrasing, thumbs-down, escalations to humans, tool errors, loops, abandonment, and judge-flagged failures.
- **Conversation to scenario conversion:** extract goal, persona traits, hidden facts, and the failure point from a real conversation, anonymize it, and propose it as a scenario. One click to add to the regression suite. **[Wow]**
- **Online evaluation:** sampled production traces run through the same judges, producing live quality and safety trends.
- **Drift detection:** alert when intent mix, tool usage, failure rate, or judge scores shift.
- **Coverage analysis:** compare production intents and tools against test coverage to show blind spots ("34% of production traffic is about order changes, but only 4% of your scenarios are").
- **Attack detection in production:** flag real prompt-injection attempts and feed them into the attack library (with privacy handling).

---

## 12. Analytics and insights

- **Failure clustering [Wow]:** embed failed trajectories, cluster them, and have a model name each cluster ("agent issues refunds before verifying identity"). Show cluster size, trend, and example episodes. This answers "where does my agent actually fail?" in seconds.
- **Root-cause attribution:** classify failures by source: prompt, tool definition, retrieval, model capability, policy gap, mock-world artifact, or simulator error.
- **Trajectory visualization:** a graph or timeline of each episode showing messages, tool calls, retries, state changes, and judge annotations on the step where things went wrong.
- **Step-level blame:** identify the earliest decisive error in a long trajectory.
- **Replay console:** scrub through a conversation with a synchronized world-state panel.
- **Sensitivity analysis:** which persona traits, fault types, and languages degrade performance most.
- **Reliability curves:** success rate as k increases (pass^k), and as difficulty increases.
- **Cost and latency analytics:** per scenario, per tool, per model, with outlier detection.
- **Leaderboards:** compare agent versions, models, and prompts on the same suites.
- **Test suite health:** scenario count, coverage of tools, policies, personas, and threat categories, flaky rate, and stale scenarios.
- **Executive dashboard:** one-page score, trend, top risks, and release readiness.
- **Natural-language analytics:** ask questions such as "which scenarios started failing after the prompt change?" and get answers with links to evidence.

---

## 13. Product experience

### 13.1 Core screens
- **Onboarding wizard [MVP]:** connect an agent, auto-generate about 30 scenarios, run them, and see the first report in under 10 minutes. First impressions decide adoption.
- **Agent overview:** profile card, tool inventory with risk labels, latest scores, open findings, and coverage.
- **Scenario studio:** list, filter, tags, visual editor, YAML or JSON view, import and export, version history, duplicate and mutate, and generation tools.
- **Persona studio:** create, mix, and preview personas, with a chat preview against the simulator.
- **Environment studio:** edit mock tools and seed data, define fault injection profiles, build poisoned documents, and preview responses.
- **Run console [MVP]:** live progress, streaming transcripts with tool calls and judge verdicts appearing as they happen, running cost, and pause and cancel controls.
- **Run report:** summary, metrics, failures grouped by cluster, and links into episodes.
- **Episode viewer:** transcript, tool timeline, world-state diff, evaluator results with evidence, and one-click "add to regression suite" or "mark as simulator error."
- **Compare view:** baseline versus candidate.
- **Findings inbox:** triage, assign, link tickets, verify fixes.
- **Human review queue:** keyboard-driven labeling with judge predictions shown or hidden, and an active-learning order that surfaces the most informative cases first.
- **Rubric and judge manager:** edit rubrics, view calibration scores, compare judge versions.
- **Gateway console:** policies, live decisions, approval inbox, and policy test results.
- **Settings:** providers and keys, budgets, members and roles, integrations, retention, audit log.

### 13.2 Collaboration and sharing
- Workspaces, roles (owner, admin, engineer, reviewer, viewer), and comments on episodes and findings.
- Shareable read-only report links with redaction options.
- Notifications and a clear activity feed.

### 13.3 Developer experience
- **CLI and SDKs** in Python and TypeScript.
- **Config as code:** everything (suites, personas, policies, rubrics) can live in the repo.
- **Public REST API and webhooks.**
- **MCP server for the platform itself [Wow]:** lets coding agents run tests and read results, so "ask your coding assistant to red-team your agent" works.
- **Local mode:** run the entire engine locally with SQLite-style storage for quick experiments and for demos without a server.
- **Great docs:** quickstart, concepts, recipes per framework, a cookbook of scenario patterns, and an attack catalog.
- **Polish:** dark mode, keyboard shortcuts, command palette, empty states that teach, and fast pages even with thousands of episodes.

---

## 14. Platform engineering requirements

- **Multi-tenancy and isolation:** strict data separation, per-tenant encryption keys for secrets, and row-level access control.
- **Authentication:** email, Google, and GitHub sign-in, API keys with scopes, and service accounts for CI.
- **Sandboxing untrusted code:** container targets and code-executing agents run in resource-limited sandboxes with restricted networking and filesystem access.
- **Durable execution:** episodes checkpoint after each step, resume after worker crashes, handle idempotent retries, and never double-charge a tool call in the mock world.
- **Model gateway:**
  - Multi-provider abstraction with BYO keys.
  - Routing by task (cheap model for simulation and easy judging, strong model for hard judging and attacking).
  - Free-tier-friendly rate-limit handling and automatic fallbacks.
  - Response caching (semantic and exact) for judge calls.
  - Per-run, per-project, and per-org cost accounting.
  - Local model support for classifiers and cheap judging.
- **Storage:** efficient trajectory storage and indexing, large artifact handling, retention policies, export, and deletion on request.
- **Observability of the platform:** traces, metrics, structured logs, and error tracking. Dogfood: test the platform's own assistant features with itself.
- **Security of the platform:** secrets management, input validation, SSRF protection on connector URLs, signed webhooks, audit trails, dependency scanning, and a published security note.
- **Performance targets:** the dashboard stays responsive with 100k+ episodes, a 500-episode run completes within a predictable window given the rate limits, and the gateway overhead stays small enough to be practical.
- **Quality of the platform:** unit and integration tests, golden tests for judges, contract tests for connectors, and a chaos test of the execution engine.
- **Migrations and versioning:** schema migrations, scenario schema versioning with upgraders, and backward-compatible APIs.
- **Self-hosting:** docker-compose quickstart and a documented configuration reference.

---

## 15. Meta-evaluation: proving the platform itself works

This section is what separates a serious project from a demo. Most tools never measure themselves.

1. **Planted-vulnerability benchmark ("Damn Vulnerable Agent") [Wow]:** build an intentionally flawed reference agent family (support agent, SQL agent, email assistant, MCP-tool agent) with a catalog of known planted bugs and vulnerabilities, at varying difficulty. Publish it. Measure the platform's **detection recall** (found 41 of 46 planted issues), **precision** (false findings), and time to detection. Publishing this benchmark also gives the community something to use, which creates inbound attention.
2. **Judge accuracy study:** label a few hundred episodes by hand (ideally with a second labeler, such as a friend or colleague), and report agreement between each judge configuration and humans, plus cost per judgment. Show that your cascade matches the strong judge at a fraction of the cost.
3. **Simulator fidelity study:** compare simulated conversations to real ones on measurable features (length, clarification rate, topic drift).
4. **Attacker effectiveness:** compare your adaptive attacker against static payload scanners on the same targets, same budget.
5. **Reproducibility report:** re-run the same suite many times and publish variance, flaky rate, and cassette replay exactness.
6. **Benchmark reproduction:** reproduce a published number on tau-bench or AgentDojo for a known model, within a reasonable margin, to prove the harness is sound.
7. **Cost report:** cost per 1,000 episodes at different judge configurations.

---

## 16. Proof, demos, and how to present it

### 16.1 Demo targets
- **Your own shipped agents** (GhostWriterAI, NL2SQL, MCPForge, Issue to PR, Voice Studio, FlexAI): run the platform against them and report real findings and real fixes. "I red-teamed my own six agents, found N issues, fixed them, and pinned them as regressions" is the headline.
- **Damn Vulnerable Agent** for a controlled, repeatable showcase.
- **A popular open-source agent** (with permission and responsible disclosure norms) for external credibility.

### 16.2 Demo narrative (3 minutes)
1. Connect an agent in under a minute.
2. Auto-generated scenarios and personas run live.
3. Failures cluster into three root causes.
4. An adaptive attacker gets the agent to leak a canary secret, and the finding shrinks to a three-line reproducer.
5. A suggested gateway rule is tested on attack and benign suites, then enforced.
6. The same attack now fails, the finding flips to verified, and the pull request check turns green.
7. Show the model-swap report and the release readiness score.

### 16.3 Artifacts to publish
- Open-source repo with excellent README, architecture diagram, and quickstart.
- Docs site.
- Technical blog posts: how the user simulator works, why pass^k matters, how judges are calibrated, how canary tokens enable deterministic leak detection, lessons from red-teaming my own agents.
- Benchmark page with the Damn Vulnerable Agent results and judge accuracy.
- A short video and a hosted live demo with sample data.
- LinkedIn series built from the findings (each vulnerability is a post).

### 16.4 What to tell recruiters and founders
"I built a platform that tests and secures AI agents. It simulates thousands of users and attackers, measures reliability with pass^k, detects leaks with canary tokens, calibrates its judges against human labels, and closes the loop by turning findings into gateway policies that are tested for false positives before enforcement." Back it with three numbers: detection recall on planted bugs, judge-human agreement, and findings fixed in your own agents.

---

## 17. Phased roadmap

Estimates assume roughly 15 to 20 focused hours per week alongside a job. Adjust to your pace. Cut lines are listed so you always have something shippable.

**Phase 0: Foundations (about 1 week)**
Monorepo, auth, workspace and project model, model gateway with two providers, cost tracking, trace schema, CI for the platform itself, design system. Decide naming and branding.

**Phase 1: Vertical slice MVP (about 3 weeks) [ship this first]**
- HTTP and OpenAI-compatible connectors.
- Agent profile card and tool inventory from OpenAPI.
- Scenario schema, auto-generation of starter scenarios, persona library (10 personas).
- User simulator with hidden facts.
- Mock tool layer generated from OpenAPI with seeded stateful data.
- Deterministic evaluators and a first set of LLM judges with evidence requirement.
- Durable execution with budgets.
- Run console with live streaming, episode viewer, simple report.
- CLI to run a suite.
*Definition of done:* connect a real agent, get a credible report with failures and evidence in 10 minutes.

**Phase 2: Security core (about 3 weeks)**
- Threat taxonomy and attack library (100+ attacks across the main categories).
- Canary tokens, honeytools, egress monitor.
- Indirect injection harness in the mock world.
- Mutation engine and one adaptive attacker strategy.
- Findings model, severity, replay, regression pinning.
- Security posture report.
*Cut line:* skip search-based strategies and benchmark imports.

**Phase 3: Regression and rigor (about 3 weeks)**
- Agent versions, baselines, run comparison with statistics.
- Repetitions, pass^k, flaky detection, cassette record and replay.
- GitHub Action and PR comments, gating.
- Judge calibration tooling, human review queue, rubric management.
- Failure clustering and root-cause attribution.
*Cut line:* skip adaptive sampling and test selection.

**Phase 4: Gateway and policies (about 3 weeks)**
- Policy compiler from documents.
- Gateway as SDK middleware and reverse proxy, shadow and enforce modes.
- Tool-call policy engine, content-origin tagging, output scanning.
- MCP gateway protections (pinning, allowlists, description scanning).
- Policy testing on attack and benign suites, closed-loop suggestion from findings.
*Cut line:* implement SDK middleware and MCP protections first, defer proxy form.

**Phase 5: Production loop, voice, and polish (about 3 to 4 weeks)**
- Trace ingestion, failure mining, conversation-to-scenario conversion, drift and coverage analytics.
- Voice simulation with open-source speech models and LiveKit.
- Benchmark imports and head-to-head scanner comparison.
- Damn Vulnerable Agent and the meta-evaluation studies.
- MCP server for the platform, docs, demo video, launch.

**Total:** roughly 14 to 16 weeks for the full vision. A strong, demo-able product exists at the end of Phase 2, and a standout one at the end of Phase 3.

---

## 18. Risks and mitigations

- **Scope explosion:** this plan is large by design. Mitigation: ship the Phase 1 slice, treat everything else as modules, and publish after Phase 2.
- **Judge unreliability:** mitigated by deterministic checks first, evidence requirements, ensembles, and calibration gates.
- **Simulator drift and unrealistic users:** mitigated by persona guards, fidelity studies, and the ability to mark episodes as simulator errors.
- **Non-determinism and flaky results:** mitigated by repetitions, statistics, cassettes, and quarantine.
- **LLM cost:** mitigated by cascades, caching, cheap models for simulation, adaptive sampling, estimators, and hard caps.
- **Misuse of attack tooling:** mitigated by ownership verification, scope controls, audit logs, safe handling of dangerous outputs, and clear terms.
- **Free-tier rate limits:** mitigated by queueing, backoff, multi-provider routing, and local models for classifiers.
- **Moving targets:** MCP, agent frameworks, and benchmarks change quickly. Mitigation: adapter architecture and a plugin interface for connectors, attacks, and evaluators.
- **Positioning risk (crowded space):** mitigated by the closed loop, the meta-evaluation proof, and the policy-testing and conversation-to-scenario features that others lack.
- **Burnout and job-search timing:** mitigated by phases that each end in something publishable.

---

## 19. Cost plan and where to spend your Fable credits

- **Cheap and free tiers for volume:** user simulation, simple judging, scenario generation, and attack mutation can run on small or free-tier models. Use local open-source classifiers for injection detection.
- **Strong models only where quality matters:** hard-case judging, adaptive attacker reasoning, root-cause analysis, and report writing.
- **Caching and cascades** reduce judge cost dramatically.
- **Spend Fable credits on planning and hard design problems**, not on bulk runs:
  1. Domain model and schema design.
  2. Durable execution design and failure handling.
  3. Judge and rubric design, calibration methodology.
  4. Threat taxonomy, attack library structure, severity model.
  5. Policy language design and the policy-testing method.
  6. Gateway architecture and latency budget.
  7. Statistical methods for comparisons and adaptive sampling.
  8. Dashboard information architecture.
  9. Review of each phase before building it, and a post-phase architecture critique.

---

## 20. The differentiator shortlist (build these and the project stands out)

1. Closed loop from red-team finding to gateway rule to verified fix.
2. Policy testing with block rate and false-positive curves.
3. World-state diff verification in a stateful mock world.
4. pass^k reliability and statistically honest comparisons.
5. Canary tokens and honeytools for deterministic detection.
6. Minimal reproducer shrinking for attacks.
7. Judge calibration, cascades, and published judge accuracy.
8. Conversation-to-scenario mining from production failures.
9. Planted-vulnerability benchmark (Damn Vulnerable Agent) with published recall.
10. Failure clustering with plain-language root causes.
11. Model-swap impact report with a Pareto chart.
12. MCP security scanner and gateway protections, plus an MCP server for the platform itself.
13. Persona sensitivity analysis.
14. Cassette record and replay.
15. Voice agent testing with simulated callers on open-source speech models.

---

## 21. Open decisions to settle early

1. **Name and brand.**
2. **Open-core boundaries:** what is open source (engine, CLI, attack library) and what is hosted-only.
3. **Primary target agent type for the MVP:** customer support (most relatable) is the recommended default, with data and MCP agents second.
4. **First model providers** and which free tiers to rely on.
5. **Execution engine choice:** extend a task queue or build a small durable workflow layer.
6. **Trace store choice** and the point at which you add an analytics database.
7. **Policy language format.**
8. **Which benchmarks to reproduce first** (recommended: tau-bench retail and AgentDojo).
9. **Hosting of the live demo** and sample data.
10. **Responsible-disclosure approach** if you test third-party open-source agents.

---

## 22. Suggested planning sessions to run with Fable

Run these in order, saving each output into a `docs/` folder in the repo:
1. **Product requirements and MVP cut:** turn this document into user stories and a ruthless MVP scope.
2. **Domain model and database schema.**
3. **Execution engine design:** durability, retries, budgets, concurrency, cassettes.
4. **Simulation design:** persona model, simulator prompts and guards, termination logic.
5. **Evaluation design:** rubrics, judge cascade, calibration plan, golden set creation.
6. **Security design:** taxonomy, attack schema, adaptive attacker, canaries, severity model, shrinking.
7. **Gateway and policy design:** policy language, inspection pipeline, MCP protections, policy testing.
8. **API and SDK design.**
9. **Dashboard IA and UX flows.**
10. **Test and meta-evaluation plan:** Damn Vulnerable Agent catalog, studies, publishing plan.
11. **Launch plan:** docs, blog series, demo, LinkedIn content calendar.
