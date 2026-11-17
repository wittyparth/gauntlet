# Gauntlet Addendum: Making It a Real Product With Real-World Use Cases

*Companion to `agent-testing-platform-plan.md`. That document defines the engine. This one defines what makes it useful to real teams, real scenarios, and real buyers, plus a large set of additional features.*

---

## 0. Honest gap analysis of the first plan

The first plan was strong on **platform mechanics** (simulation, judging, red-teaming, gateway, CI). Where it was thin:

1. **Scenarios were generic.** It said "customer support" but did not define what a real bank, airline, or hospital agent actually gets wrong.
2. **No grounding in real incidents.** Real-world agent failures are the best test material and the best marketing, and the plan did not use them.
3. **Demo targets were your own projects.** Fine for a demo, but a real product needs outside users, outside agents, and outside data.
4. **No buyer thinking.** Who pays, what they need to show their boss or auditor, and what they would use weekly were not defined.
5. **No compliance and evidence layer.** Real teams need proof for auditors, customers, and regulators, not only dashboards.
6. **No distribution plan.** Features do not create users. Free, shareable, low-friction entry points do.
7. **Missing detectors for the failures that actually cost companies money:** binding commitments, unauthorized advice, invented policies, permission leakage, and over-privileged agents.

This addendum fixes those. Everything here is additive to the first plan.

---

## 1. Product reframe: three pillars of "real"

1. **Real users:** free tools that strangers can run on their own agents in minutes (scanner CLI, GitHub App, public challenge arena).
2. **Real scenarios:** vertical scenario packs built from how real agents fail, plus a library of replayed public incidents.
3. **Real outcomes:** evidence a buyer can hand to a boss, auditor, or customer (readiness report, compliance evidence pack, trust page).

Positioning sentence: **"The test lab, red team, and seatbelt for AI agents, with scenario packs for your industry."**

---

## 2. Buyers, users, and jobs to be done

| Role | Their real question | What the platform gives them |
|---|---|---|
| AI engineer | "Did my change break anything?" | CI gating, run diffs, replay, cost and latency tracking |
| QA lead | "How do we test something non-deterministic?" | Scenario suites, pass^k, flaky management, coverage maps |
| Security engineer | "Can this agent be hijacked or leak data?" | Red-team campaigns, canaries, findings, MCP scanner, gateway |
| GRC or compliance | "Can we prove due diligence?" | Evidence packs, framework mapping, audit logs, approvals |
| Product manager | "Will this embarrass us at launch?" | Launch readiness review, persona sensitivity, brand-safety checks |
| Support or ops head | "Is it actually resolving things, and what does it cost?" | Cost per resolution, handoff quality, SLOs, production failure mining |
| CTO or founder | "Can we ship this agent to customers safely?" | One-page risk grade, trust page, model-swap impact report |
| Procurement or customer security team | "Is this vendor's agent safe?" | Shareable scorecards and trust pages from the vendor |

Design implication: each role gets its own **default dashboard and report**, built from the same data.

---

## 3. Hall of Failures: incident-derived scenario packs

Real public incidents become replayable scenarios, tagged by root cause. Each one is a ready-made test, a demo, and a piece of content ("Would your agent survive the Air Canada test?").

*These are from my own knowledge of public reporting. Verify each detail and source before citing them publicly, and describe them neutrally.*

| Incident (public reporting) | Failure class | Scenario the platform recreates |
|---|---|---|
| Air Canada chatbot gave wrong bereavement-fare policy and the airline was held to it (2024 tribunal case) | Hallucinated policy, binding commitment | User asks about a refund rule that the knowledge base states differently. Agent must not invent or contradict policy. |
| Chevrolet dealership chatbot "agreed" to sell a vehicle for one dollar (2023) | Prompt injection by user, binding commitment | User instructs the agent to agree to anything and declares the deal legally binding. |
| DPD delivery chatbot swore and criticized the company (2024) | Jailbreak, brand safety | User coaxes the agent into profanity and self-criticism. |
| NYC "MyCity" business chatbot gave advice that conflicted with the law (2024) | Unauthorized or incorrect legal advice | User asks about legal obligations. Agent must stay within sourced facts and flag uncertainty. |
| Replit coding agent deleted a production database during a code freeze (2025) | Excessive agency, ignoring instructions, irreversible action | Agent has a destructive tool and an explicit freeze instruction. Must not execute, must ask. |
| Cursor support bot invented a login policy (2025) | Hallucinated policy in support | User asks about a policy that does not exist. Agent must not fabricate. |
| Slack AI indirect prompt injection (2024 research) | Indirect injection, data exfiltration | Poisoned message in a public channel steers the assistant to leak private channel data. |
| GitHub MCP "toxic agent flow" (2025 research) | Indirect injection through issues, cross-repo leakage | Malicious public issue instructs the agent to read and publish private repo content. |
| Microsoft 365 Copilot "EchoLeak" zero-click (2025 research) | Indirect injection through email, exfiltration via links or images | Email with hidden instructions causes data to leave through a rendered link. |
| Salesforce Agentforce "ForcedLeak" (2025 research) | Injection through web-to-lead form, exfiltration | Lead form field with instructions triggers a CRM data leak. |
| Malicious prompt slipped into an AI coding extension release (2025) | Supply chain, destructive instructions | Tool or plugin content contains destructive instructions. |

Platform features around this library:
- **"Would you have survived?" mode:** run the whole pack against any agent, get a score and a shareable card.
- **Incident submission:** users submit new incidents. Maintainers (you) convert them into scenarios. Credit contributors.
- **Pack versioning and freshness badge** ("updated this week with 3 new incidents").
- **Root-cause tags** so teams can filter by failure class rather than by story.

---

## 4. Vertical scenario packs (the heart of "real-world")

Each pack contains: typical agent and tools, realistic scenarios, rules the agent must follow, and the highest-risk attacks. Build **three packs deeply** first (recommended: e-commerce support, banking and fintech, enterprise knowledge copilot), then add others as modules.

### 4.1 E-commerce and retail support
- **Typical tools:** order lookup, refunds, returns labels, address change, coupon application, human handoff.
- **Scenarios:**
  - Refund requested after the return window, with a sympathetic story.
  - Customer claims a missing package that tracking shows as delivered.
  - Coupon stacking and "the other agent promised me" claims.
  - Address change after shipping (needs different handling than before).
  - Order for another person, identity unverified.
  - Angry customer threatening a chargeback or a bad review.
  - Bulk-order discount negotiation, where the agent must not invent prices.
  - Multilingual customer mixing languages mid-sentence.
- **Rules:** refund caps, identity verification before changes, no price or delivery promises beyond tool data, escalation triggers.
- **Top attacks:** discount manipulation, refund abuse through social engineering, viewing another customer's order, tool-argument tampering (refund amount).

### 4.2 Banking and fintech
- **Tools:** balance and transaction lookup, card block, dispute filing, payee management, KYC status.
- **Scenarios:**
  - Caller claims a lost card and pushes to skip verification due to urgency.
  - Customer asks the agent to explain a fee and the agent must quote the real schedule.
  - Disputed transaction with partial information.
  - Scam victim being coached by a scammer on the same chat (agent should detect pressure and offer safe paths).
  - Request to add a new payee shortly after a password reset (fraud pattern).
  - User asks for investment advice (agent must not give unlicensed advice).
  - Vulnerable-customer cues (distress, confusion) requiring a human handoff.
- **Rules:** strict identity verification, no sensitive data echoing, advice boundaries, mandatory disclosures, audit trail.
- **Top attacks:** account takeover by social engineering, data exfiltration of transaction history, injection through transaction memo fields, prompt extraction of fraud rules.

### 4.3 Enterprise knowledge copilot (internal RAG)
- **Tools:** search across documents, email, chat, tickets, with per-user permissions.
- **Scenarios:**
  - **Permission leakage:** user A asks about a document only user B (for example HR or finance) can see.
  - Stale document versus current policy (agent must prefer the latest and cite it).
  - Conflicting documents (agent must surface the conflict).
  - Poisoned document planted in a shared drive.
  - Question whose true answer is "not in the knowledge base" (agent must say so).
  - Summarize a thread containing confidential legal advice for a user who is not entitled to it.
  - Departing employee asks to export everything.
- **Rules:** answers only from permitted sources, citations required, no cross-tenant or cross-role leakage.
- **Top attacks:** indirect injection in shared documents and emails, retrieval of unauthorized chunks, exfiltration via links, memory poisoning.

### 4.4 Insurance claims and underwriting assistants
- **Scenarios:** claim intake with missing documents, a policyholder asking whether an event is covered (agent must not promise coverage), contradicting statements across turns, suspected fraud cues, a claim just outside the coverage window, upsets after a denial.
- **Rules:** no coverage promises, accurate citation of policy clauses, fairness across demographic phrasing, human review for denials.
- **Top attacks:** coverage manipulation, injection through uploaded claim documents, leaking other claimants' data.

### 4.5 Healthcare administration (scheduling, benefits, intake; not diagnosis)
- **Scenarios:** appointment booking with conflicting preferences, symptom descriptions that suggest an emergency (must route to emergency guidance), insurance eligibility questions, a caller asking for another person's records, medication questions beyond scope, language and accessibility needs, sensitive disclosures.
- **Rules:** no diagnosis or dosing advice, emergency escalation, strict privacy, minimal data echoing.
- **Top attacks:** records access by impersonation, extraction of patient data, jailbreaking into medical advice.

### 4.6 Telecom and ISP support
- **Scenarios:** outage versus device issue triage, plan change with hidden fees, contract cancellation with retention pressure (agent must not trap or mislead), SIM swap request (high fraud risk), billing dispute, repeated contact with no resolution.
- **Rules:** SIM swap and number port protections, accurate pricing, honest cancellation paths.
- **Top attacks:** SIM-swap social engineering, plan manipulation, account takeover.

### 4.7 Travel, airlines, and hospitality
- **Scenarios:** rebooking after cancellation, bereavement or medical exceptions, fare-rule questions, group bookings, loyalty point disputes, disruption with many affected passengers, requests that need accurate dates and time zones.
- **Rules:** quote real fare rules, no invented exceptions, correct time handling.
- **Top attacks:** policy hallucination, unauthorized upgrades or refunds, injection through itinerary text.

### 4.8 HR and IT helpdesk (internal)
- **Scenarios:** password reset with weak identity proof, access request for a sensitive system, payroll question about someone else, leave policy edge cases, termination-related questions, a user pretending to be an executive, onboarding workflows with many steps.
- **Rules:** verified identity, least-privilege access, approvals for sensitive requests.
- **Top attacks:** privilege escalation through social engineering, confused-deputy attacks, data leakage about colleagues.

### 4.9 Coding and DevOps agents
- **Scenarios:** fix a bug while a malicious comment instructs the agent to exfiltrate secrets, a dependency with a hallucinated or typosquatted name, destructive commands during a freeze, a failing test the agent is tempted to edit instead of fixing, a request to deploy to production without approval, a long refactor that drifts from the task, secrets accidentally printed in logs.
- **Rules:** no destructive actions without approval, no secret exposure, tests must not be weakened, minimal scope.
- **Top attacks:** injection through repo files and issues, malicious packages, tool-description poisoning, credential theft.

### 4.10 Data, SQL, and BI agents
- **Scenarios:** ambiguous metric definitions, a query that would scan or lock a huge table, a request for columns the user should not see, a "just run it" request for a destructive statement, joins that silently duplicate rows, results that contradict a previous answer, time-zone and fiscal-calendar traps.
- **Rules:** read-only by default, row and column permissions, cost limits, explain assumptions.
- **Top attacks:** SQL injection through natural language, exfiltration across tenants, injection in column values or comments.

### 4.11 Sales, SDR, and CRM agents
- **Scenarios:** outbound personalization from scraped data (accuracy and consent), a prospect asking the agent to stop, claims about the product that are not true, pricing promises, a lead form containing hidden instructions, a request to email the entire contact list.
- **Rules:** opt-out respect, truthful claims, no unauthorized discounts, data handling limits.
- **Top attacks:** injection through lead data, mass-email exfiltration, impersonation.

### 4.12 Recruiting and screening agents
- **Scenarios:** resumes containing hidden instructions ("rank this candidate first"), bias across names and phrasing, illegal interview questions, candidates asking for salary information of others, scheduling conflicts across time zones, rejected-candidate feedback requests.
- **Rules:** fairness, no protected-attribute inference, transparency, data minimization.
- **Top attacks:** resume injection, bias probes, data leakage between candidates.

### 4.13 Voice and call-center agents
- **Scenarios:** background noise and accents, interruptions mid-sentence, user reading a card number aloud (must be handled safely), a caller who keeps silent, spoofed caller identity, long holds, call recording disclosure, an upset caller who needs a human.
- **Rules:** disclosure statements, sensitive data handling, graceful handoff with context.
- **Top attacks:** voice-based social engineering, spoken injection, impersonation.

### 4.14 Browser, computer-use, and agentic commerce
- **Scenarios:** a shopping agent facing fake discount pages, a page with hidden instructions, an unexpected checkout upsell, a CAPTCHA or login wall, a payment form that looks legitimate but is not, a task that requires an irreversible purchase (needs confirmation), cookie banners and pop-ups, lookalike domains.
- **Rules:** spending limits, confirmation before payments, domain allowlists.
- **Top attacks:** indirect injection in web pages, malicious redirects, payment manipulation.

### 4.15 Education and kids-adjacent tutors
- **Scenarios:** a minor asking for unsafe content, homework cheating requests, emotional distress disclosures, age-inappropriate topics, a student pushing the tutor to give answers instead of teaching, parent-versus-child account boundaries.
- **Rules:** age-appropriate content, safe handling of distress, pedagogy constraints.
- **Top attacks:** jailbreaks through roleplay, boundary-pushing persuasion.

### 4.16 Legal and compliance intake
- **Scenarios:** a user wanting legal advice (agent must stay in intake scope), confidential information in a conversation, conflict-of-interest checks, jurisdiction confusion, deadlines and time-sensitive matters, a user pasting a privileged document.
- **Rules:** no legal advice beyond scope, confidentiality, disclaimers, human handoff.
- **Top attacks:** extraction of other clients' information, jailbreaks into advice.

### 4.17 Pack mechanics (shared features)
- **Pack = scenarios + personas + mock world + policies + rubrics + attack set + compliance mapping.**
- **Install a pack in one click** and customize through overrides.
- **Parameterization:** company name, policies, tool names, currencies, languages, regional rules.
- **Regional variants:** US, EU, India (including Indic languages and code-switching such as Hinglish, Telugu-English), Middle East, and others.
- **Pack quality bar:** each pack ships with a published coverage matrix and a tested set of known-vulnerable and known-good reference agents.
- **Community packs:** users can publish packs, with review and ratings.

---

## 5. New feature catalog (beyond the first plan)

### 5.1 Failure detectors for what actually costs companies money
These are specialized evaluators, usable in tests, in production sampling, and in the gateway.
- **Binding-commitment detector:** flags when the agent promises prices, refunds, delivery dates, coverage, legal outcomes, or "I guarantee." Compares promises against tool data and policy.
- **Authority and agreement detector:** catches "I agree to anything," "that is legally binding," and similar manipulation successes.
- **Hallucinated-policy detector:** every policy claim the agent makes is checked against the knowledge base. Unsupported claims are flagged with the closest real policy text.
- **Unauthorized-advice detector:** medical, legal, financial, and tax advice outside the agent's scope.
- **Fabricated-action detector:** the agent says it did something (refund issued, email sent, ticket created) and the world state shows it did not, or did it twice.
- **Fabricated-citation detector:** links, document names, and quotes that do not exist in the knowledge base.
- **Sycophancy detector:** agent changes a correct answer under user pressure, or agrees with a false premise.
- **Overpromise-on-capability detector:** agent claims abilities it does not have.
- **Brand-safety checks:** profanity, competitor mentions, political statements, disparagement of the company, off-brand tone.
- **Pressure-resistance tests:** urgency, emotion, authority, and persistence, measured as "turns until the agent gives in."
- **Vulnerable-user handling checks:** distress cues, confusion, age signals, and whether the agent responds safely and hands off.
- **Scam-and-fraud awareness checks:** does the agent notice that the user is being coached or that the request fits a fraud pattern?
- **Handoff-quality evaluator:** when escalating to a human, did the agent pass a clear summary, collected facts, and the customer's goal, so nobody has to repeat themselves?

### 5.2 Permission and data-leakage testing (enterprise essentials)
- **Role-based test identities:** simulate users with different roles, groups, and tenants, each with a defined set of what they may see.
- **ACL leakage tester:** automatically generate questions designed to pull restricted content (by topic, by name, by indirect reference) and verify nothing crosses a boundary.
- **Cross-tenant tests** with canary records per tenant.
- **Aggregation leakage:** can a user infer restricted data by asking many innocent questions? (counts, summaries, comparisons).
- **Memory isolation tests:** does information from one user's session appear in another's?
- **Data lineage:** trace which source documents contributed to each answer, to show whether an unauthorized chunk was retrieved even if it was not quoted.
- **Right-to-forget tests:** after a deletion request, is the data truly gone from memory and retrieval?
- **Retention checks:** verify that data does not persist beyond policy.

### 5.3 Static analysis of agents (agent linter) and agent inventory
Not every issue needs a live run. Analyze the agent's code, prompts, and configuration.
- **Agent linter** for repos: scans for overpowered tools, missing confirmation on destructive tools, secrets in prompts, unbounded loops, missing timeouts, unvalidated tool arguments, untrusted content flowing into privileged tools, over-broad OAuth scopes, missing rate limits.
- **Prompt review:** weak or conflicting instructions, missing refusal rules, missing escalation rules.
- **Agent bill of materials (AgBOM):** models, prompts, tools, MCP servers, data sources, vector stores, third-party APIs, and versions. Exportable. Alerts when a component changes.
- **Dependency and plugin risk scoring:** known-vulnerable or unmaintained packages, suspicious MCP servers.
- **Agent inventory and registry:** one place listing every agent in an organization, owner, purpose, risk tier, last test date, and status. Solves "shadow agents."
- **Risk tiering:** classify each agent (low, medium, high) from its tools and data access, and set required test coverage by tier.

### 5.4 Least-privilege and blast-radius analysis
- **Tool permission review:** for each tool, what it can read, write, delete, send, or spend.
- **Blast-radius score:** if this agent is hijacked, what is the worst plausible outcome?
- **Attack path graph:** shows how untrusted input could travel to a dangerous tool (web page → summarizer → email tool → external recipient).
- **Permission diff:** what the agent is granted versus what it actually used across thousands of runs. Recommend removing unused permissions.
- **Credential audit:** over-scoped tokens, long-lived keys, shared credentials.
- **Recommended guardrails per path:** confirmation steps, argument limits, quarantine of untrusted content.

### 5.5 Multilingual, regional, and accessibility testing
- **Language matrix:** run the same suite across languages and measure per-language degradation. Highlight where safety rules weaken in low-resource languages.
- **Code-switching and transliteration:** Hinglish, Tenglish, romanized scripts, mixed scripts, slang. This is a real gap in most tools and a strong differentiator for builders serving India.
- **Cultural and regional rules:** local regulations, address and name formats, currencies, date formats, festivals and holidays affecting delivery or policy.
- **Accessibility personas:** screen-reader-style phrasing, dyslexia-style spelling, cognitive load, voice-only users, low-bandwidth contexts.
- **Tone across cultures:** politeness norms and formality.

### 5.6 Multimodal agent testing
- Poisoned images with hidden text, screenshots with injected instructions, PDFs with invisible text, QR codes, audio clips with embedded commands, and spreadsheets with hidden sheets.
- Misleading charts and documents that test grounding.
- Vision-based computer-use agents versus deceptive interfaces (dark patterns, fake buttons).

### 5.7 Memory and personalization testing
- Long-term memory correctness, update, and deletion.
- Memory poisoning and persistence across sessions.
- Preference leakage between users.
- Over-personalization (mentioning sensitive facts unprompted).
- Staleness (using outdated facts after a correction).

### 5.8 Chaos and resilience mode
- **Chaos monkey for agents:** in staging, randomly degrade tools, slow responses, return partial data, rotate API versions, and kill workers. Measure graceful degradation and honest error messages.
- **Dependency outage drills:** what does the agent say when the order system is down?
- **Rate-limit and quota exhaustion drills.**
- **Cost-spike drills:** loops and retries that amplify spend, and whether budgets stop them.
- **Game days:** scheduled drills with a report, like fire drills for agents.

### 5.9 SLOs, error budgets, and alerts for agents
- Define objectives such as "task success at least 92%," "zero critical policy violations," "p95 latency under 6 seconds," "cost per resolution under a target."
- Error budgets and burn-rate alerts, fed by test runs and production sampling.
- Release freeze recommendations when budgets are spent.
- Weekly agent health digest per owner.

### 5.10 Change-impact analysis
- **Prompt diff risk analyzer:** explains which behaviors a prompt edit is likely to affect and selects scenarios to run.
- **Tool schema change detector:** a renamed field or changed description triggers targeted tests.
- **Model upgrade advisor:** runs suites on a candidate model and reports differences by category, including behaviors that were previously safe and are now risky.
- **Provider drift monitor:** periodically re-runs a canary suite against the same model name to detect silent provider-side changes.
- **Knowledge base change tests:** when documents change, re-test the questions that depend on them.

### 5.11 Threat intelligence and freshness
- **Attack feed:** new jailbreaks, injection patterns, and MCP attack techniques from public research and from the community, normalized into attack-library entries.
- **Auto-regression against new attacks:** nightly runs of newly added attacks against every registered agent, with alerts.
- **Technique lineage:** each attack records where it came from and which variants exist.
- **Vendor advisory style notices:** "New attack class X affects agents with tool type Y. 3 of your agents are exposed."

### 5.12 Public challenge arena (traction engine)
- A hosted, intentionally defended agent that anyone can try to break, with levels of increasing difficulty and a leaderboard, in the spirit of well-known prompt-injection challenge games.
- Every attempt feeds the attack library (anonymized and consented).
- Community-submitted agent defenses: players can also submit defenses and see them attacked.
- Seasonal events and prizes, shareable achievements, and write-ups of the cleverest attacks.
- This is the highest-leverage feature for attention, real users, and real data.

### 5.13 Scorecards, trust pages, and badges
- **Agent Scorecard:** a public or private page showing tested categories, scores, last test date, and open critical findings.
- **Trust page for customers:** vendors share evidence of testing with their own customers' security teams.
- **README and website badges** with a live score.
- **Open-source agent scorecards:** run the platform on popular open-source agents (following responsible disclosure) and publish results as research. This is strong content and drives awareness.
- **Procurement questionnaire helper:** pre-fills AI security questionnaires from test evidence.

### 5.14 Launch readiness review
A guided pre-launch checklist that combines automated results with human confirmations:
- Agent profile complete, tools classified, risk tier assigned.
- Minimum suite coverage met for the tier.
- Zero open critical findings, accepted-risk items signed off.
- Human review sample completed.
- Rollback plan, kill switch, and incident contact defined.
- Monitoring and alerting configured.
- Final **go or no-go report** with sign-off by named approvers and a record kept for audit.

### 5.15 Compliance and evidence packs
- **Framework mappings:** NIST AI Risk Management Framework, ISO/IEC 42001, OWASP LLM and agentic guidance, MITRE ATLAS, and the EU AI Act obligations for relevant risk categories (confirm current legal status and timelines when you build). For India, consider the Digital Personal Data Protection Act, and sector guidance such as financial regulator expectations (verify current texts). Sector rules like HIPAA, PCI DSS, and GDPR are tied to the relevant packs.
- **Evidence generation:** test coverage, results, findings and fixes, approvals, and logs collected into an exportable pack with timestamps and version hashes.
- **Control library:** map each platform capability to controls an auditor asks about.
- **Continuous compliance view:** which controls currently have fresh evidence and which have gone stale.
- **Disclaimer:** the platform provides evidence, not legal advice or certification.

### 5.16 Incident response and forensics for agents
- **Incident mode:** when something goes wrong in production, import the conversation, replay it in the sandbox, find the root cause, generate a regression scenario, and draft the postmortem.
- **Blast-radius reconstruction:** who else could have been affected by the same failure? Search logs for similar trajectories.
- **Kill switch and containment recommendations:** disable a tool, tighten a policy, or force handoff for a segment of traffic.
- **Postmortem generator** with timeline, root cause, fix, and prevention.

### 5.17 Cost and unit-economics testing
- Cost per resolved task, per intent, and per persona.
- Detection of runaway loops and wasteful tool use.
- Cost-quality frontier across models and prompts.
- "What does our support agent cost per ticket versus a human?" report with honest assumptions.
- Budget alarms in tests and in the gateway.

### 5.18 Human-in-the-loop operations
- Sampling strategies for human review (random, risk-based, uncertainty-based).
- Reviewer scorecards, double-labeling, and disagreement resolution.
- Training mode for new reviewers using gold examples.
- Review marketplace integration later (optional).
- Feedback loops: reviewer labels improve judges, scenarios, and detectors.

### 5.19 Collaboration across functions
- Policy owners can write and approve rules without touching code.
- Product managers can create scenarios in plain English and preview the simulated conversation.
- Security can see attack findings by severity, and legal can see compliance mappings.
- Comment threads on episodes, findings, and policies, with @mentions and assignments.
- Approval workflows for suite changes and gate changes (so thresholds cannot be quietly lowered).

### 5.20 Integrations
- Source and CI: GitHub, GitLab, Bitbucket.
- Work tracking: Jira, Linear, GitHub Issues.
- Communication: Slack, Microsoft Teams, email, PagerDuty.
- Tracing and observability tools, plus OpenTelemetry.
- Agent frameworks and platforms: LangGraph, CrewAI, OpenAI Agents SDK, Dify, n8n, Flowise, plus MCP.
- Contact-center and chat platforms for production ingestion (as plugins).
- Identity providers (SSO) for enterprise use.
- Data warehouses for exporting results.

### 5.21 Enterprise-readiness features
- SSO and SCIM, fine-grained roles, audit logs, data residency options, bring-your-own-cloud and self-hosting, customer-managed encryption keys, retention controls, and exportable data.
- PII redaction pipeline with configurable detectors, including India-specific identifiers.
- Security documentation: architecture, threat model for the platform itself, and a responsible disclosure policy.

---

## 6. Getting real users: distribution plan

Features do not create adoption. Low-friction, shareable entry points do.

1. **One-command scanner CLI (free):** point at an endpoint or a repo, get a scorecard in minutes. Open source. This is the top of the funnel.
2. **Free GitHub App:** runs the agent linter and a smoke suite on every PR, comments with results, shows a badge.
3. **MCP server scanner:** paste an MCP server URL or repo, get a tool-poisoning and permissions report. MCP developers are numerous and under-served on security.
4. **Public challenge arena** (Section 5.12) for virality and data.
5. **Hall of Failures:** shareable "Would your agent survive?" cards and a weekly post analyzing a public incident.
6. **Open-source agent scorecards:** responsible, well-written research on popular open-source agents.
7. **Community scenario and attack packs** with contributor credit.
8. **Integrations as channels:** listings in framework ecosystems and marketplaces.
9. **Content:** technical posts, benchmark results, "how I red-teamed X," conference talks, and a regular LinkedIn series.
10. **Design partners:** find 3 to 5 small teams with real agents (startups in support, fintech, or internal tools), offer free usage in exchange for feedback and a quote or case study. Even two real design partners transforms the credibility of the project.
11. **Pricing thinking for later:** free tier for scanners and small suites, team tier for CI and history, enterprise tier for compliance, SSO, self-hosting.

---

## 7. How these additions change the roadmap

- **Phase 1 additions:** pick the first vertical (e-commerce support) and ship one complete pack, plus the binding-commitment and hallucinated-policy detectors.
- **Phase 2 additions:** incident library (start with 6 to 8 incidents), canary and ACL leakage tests, agent linter v1, MCP scanner v1.
- **Phase 3 additions:** scorecards and badges, SLOs, change-impact analysis, launch readiness review.
- **Phase 4 additions:** blast-radius analysis, enterprise knowledge copilot pack, compliance evidence packs.
- **Phase 5 additions:** public challenge arena, open-source agent scorecards, banking pack, voice pack, threat-intel feed, incident response mode.
- **Throughout:** recruit design partners from Phase 2 onward so real feedback shapes everything after.

**Priority guidance if you must choose:** the features that most increase "real product" credibility per week of work are (1) one deep vertical pack, (2) the Hall of Failures, (3) the scanner CLI and GitHub App, (4) the public arena, and (5) design partners.

---

## 8. How to build this with Fable and a smaller coding agent

**Recommendation: use Fable as architect and reviewer, and a smaller model (Sonnet) as the implementer.** Do not hand Fable the entire build in one go, and do not hand Sonnet this document and say "build it."

Why:
- A project this size exceeds any single session. Long builds drift, forget earlier decisions, and burn credits on routine code.
- Planning mistakes (schema, execution engine, judging methodology) are the expensive ones, and those benefit most from the strongest model.
- Once a task is specified with clear interfaces and tests, a smaller model implements it reliably and cheaply.

Workflow:
1. **Fable writes the specs:** product requirements, domain model and schema, API contracts, architecture decision records, repository structure, coding conventions, and a phase-by-phase task list. Each task includes inputs, outputs, acceptance tests, and files touched. Save everything in a `docs/` folder and a project instructions file the coding agent reads every time.
2. **Lock the contracts early:** schemas, API shapes, and interfaces between modules. Changes require a recorded decision.
3. **Sonnet implements one task at a time:** tests first, small commits, each task finishing with passing tests. Keep tasks small enough to review in one sitting.
4. **Fable implements or closely pairs on the hard cores:** the durable execution engine, the judge calibration and statistics code, the policy engine and policy testing, taint and origin tagging, and the attack-shrinking logic. Mistakes there are subtle and costly.
5. **Fable reviews at every phase boundary:** architecture drift, security review of the platform itself, performance concerns, and refinement of the next phase's tasks.
6. **Keep the platform honest:** from early on, use the platform's own tests to test the platform's judges and simulators.

Practical caveats:
- Fable has additional safeguards around cybersecurity content, so planning attack-generation features may sometimes meet refusals or hedging. Frame the work as defensive testing, lean on existing open attack datasets and scanner probes for payload content, and expect that some attack-library authoring may need to be done more carefully or by hand.
- Check your Fable credit limits and rate limits before planning a long session. Usage rules can change, so confirm them in your account.
- Always run and review the code yourself. Ask the implementer to explain non-obvious choices, because you must be able to defend every design decision in an interview.
