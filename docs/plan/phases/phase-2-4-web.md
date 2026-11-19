# Phases 2 to 4 web: P2-10, P3-7, P3-8 (web parts), P4-6

Lower detail than Phase 1 on purpose: the backing APIs (P2-5, P2-6, P3-1, P3-5, P3-6, P4-1, P4-2, P4-5) are not yet in `02-contracts.md`. Each task therefore starts with a **contract check**: regenerate types, map every region below to a route and type in `schema.d.ts`, and report regions with no backing before building. Build only backed regions. Never invent a route or field.

Read first: `docs/plan/README.md`, `docs/plan/02-contracts.md` (sections 5, 6, 7, 9), `docs/plan/phases/web-conventions.md`, and `docs/plan/phases/phase-1-web.md` (the shared components, `Transcript`, `VerdictCard`, `CheckTree`, `StateDiff`, `useEventSelection`, `useRunStream`, `StartRunDialog` are reused, not rebuilt). **Load the `animate-ui` skill before each task; load the `dataviz` skill before any chart.**

Rules that hold for all four tasks:
- Same state rules, Playwright rules and browser checklist as conventions sections 8 to 10. One spec per screen, seeded data, screenshot.
- Charts: Recharts through shadcn Chart only, wrapped in a shadcn Card, tooltip restyled to tokens, no entrance animation beyond the library default, every chart has a table alternative on the same screen (the `DataTable` it summarises). Stat numbers beside charts use `LiveNumber`.
- Each task adds its own sidebar group and items (icons from the animated Lucide set).
- Each task extends `uv run gauntlet demo seed` expectations: list in the report what seeded data the specs needed (CQ-W6).

---

### P2-10: Findings inbox and detail, campaign launch, coverage heatmap, posture report

**Batch:** j. **Depends:** P2-5 (findings API), P2-6 (posture data), P2-4 (ownership verification), P1-12, P1-14.

**Files:**
- `apps/web/src/app/(app)/findings/page.tsx`, `findings/[findingId]/page.tsx`
- `apps/web/src/app/(app)/security/page.tsx` (posture + heatmap), `security/campaigns/new/page.tsx`
- `apps/web/src/lib/api/hooks/findings.ts`, `attacks.ts`, `security.ts`
- `apps/web/src/components/findings/finding-table.tsx`, `finding-header.tsx`, `status-menu.tsx`, `reproducer-card.tsx`, `evidence-episodes.tsx`, `suggested-rule-card.tsx`
- `apps/web/src/components/security/coverage-heatmap.tsx`, `posture-summary.tsx`, `tool-permission-table.tsx`, `campaign-form.tsx`
- `apps/web/e2e/findings.spec.ts`, `finding-detail.spec.ts`, `security-posture.spec.ts`, `campaign-launch.spec.ts`
- Edit: `apps/web/src/components/shared/app-shell.tsx` (Security group), `apps/web/src/components/agents/` (add open-findings card to the agent overview)

**Interfaces:**
- Consumes: `GET /v1/findings`, `GET /v1/findings/{id}`, `GET /v1/episodes/{id}`, `POST /v1/runs` (campaign, if that is how P2-5 exposes it); the lifecycle, replay, pin, export, attack-list, posture and coverage routes that P2-4, P2-5 and P2-6 add (CQ-W18 to CQ-W20). Types: `Finding`, `Attack`, `Scenario`, `PolicyRule`, `Check`.
- Produces: `useFindingList`, `useFinding`, `useUpdateFindingStatus`, `useAttackList`, `usePosture`, `useCoverage`; components `FindingTable`, `FindingHeader`, `StatusMenu`, `ReproducerCard`, `EvidenceEpisodes`, `SuggestedRuleCard`, `CoverageHeatmap`, `PostureSummary`, `ToolPermissionTable`, `CampaignForm`.

**Decisions:**
- Finding status values and transitions come from the contract enum (`open`, `triaged`, `in_progress`, `fixed`, `verified`, `accepted_risk`, `false_positive`). The UI offers every status in a menu; the server rejects illegal transitions and the toast shows why.
- No assignee, comments or ticket links (not in the `Finding` contract).
- The heatmap is a table, not a chart: rows = taxonomy categories, columns = vectors (`user_turn`, `document`, `tool_result`, `tool_description`, `system_context`). Cell = attempts and successes as text plus a background tint from a 5-step sequential scale (dataviz skill), with the number always visible.
- Campaign launch never offers a remote target that has not passed ownership verification: such versions are disabled with a Tooltip. Launch needs a typed confirmation in an Alert Dialog naming the agent.

**Screens:**

| Screen | Route | Purpose | API |
|---|---|---|---|
| Findings inbox | `/findings` | triage queue | `GET /v1/findings` |
| Finding detail | `/findings/[findingId]` | prove it, reproduce it, move it through its lifecycle | `GET /v1/findings/{id}`, `GET /v1/episodes/{id}` for the first evidence episode, status update route |
| Security posture | `/security` | coverage and risk at a glance per agent version | posture and coverage routes (P2-6) |
| Campaign launch | `/security/campaigns/new` | start an attack run | attack list, agent versions, run creation |

```
Findings inbox                              Finding detail
<h1> Findings                               Findings > fnd_…9c2d
[Open|Triaged|In progress|Fixed|All]        <h1> Refund issued from injected document   CRITICAL  [ Open ▾ ]
[severity ▾][category ▾][agent ▾] (🔍)      category prompt-injection/indirect · 7 of 10 reproduced · agent v3
| Sev | Title | Category | Repro | Agent |  +--------------------------------+----------------------------------+
| CRIT| Refund issued from…| inj | 7/10 |  | REPRODUCER (minimal scenario)  | EVIDENCE EPISODE  ep_…  [open ↗] |
                                            |  goal, attack payload (mono)   |  Transcript (compact) with the   |
Security posture                            |  objective: CheckTree          |  objective's evidence seq        |
<h1> Security posture   [agent version ▾]   |  [Copy JSON]                   |  selected and highlighted        |
[stat: findings by severity x4][coverage %] | SUGGESTED POLICY RULE ▸        |  other episodes: ep_… ep_… ep_…  |
COVERAGE          user doc tool desc sys    | ROOT CAUSE HINT                |                                  |
 prompt injection 12/40 3/20 ...            +--------------------------------+----------------------------------+
TOP FINDINGS (5)      TOOL PERMISSIONS
```

| Region | Component | Behaviour |
|---|---|---|
| Inbox filters | `FilterBar` (Toggle Group status, Select severity / category / agent version, Input) | URL query |
| Inbox table | `DataTable` + `SeverityBadge` + Badge (status) | reproducibility as `7/10`; default sort severity then newest; row click → detail |
| Status control | `StatusMenu`: Dropdown Menu (radio items) + `toast.promise` | optimistic update, rollback on error |
| Reproducer | `ReproducerCard`: Card + `CheckTree` (objective) + `<pre>` payload + Copy Button + Collapsible `JsonBlock` (full scenario) | payload shown as text, never rendered |
| Evidence | `EvidenceEpisodes`: `Transcript compact` from phase 1 + `useEventSelection`; episode switcher = Toggle Group of `episode_ids` | preselect the first evidence seq of the objective's verdict or check result when available |
| Suggested rule | `SuggestedRuleCard`: Card + Collapsible + `CheckTree` (`when`) + Badge (action) | read-only until P4-6 |
| Export, replay, pin | Dropdown Menu on the header (only items whose route exists) | downloads go through the proxy |
| Posture stats | `StatCard` | counts by severity |
| Heatmap | `CoverageHeatmap`: shadcn Table + Tooltip per cell + Hover Card (attack ids, link to filtered inbox) | per Decisions; keyboard focusable cells |
| Tool permissions | `ToolPermissionTable`: `DataTable` + `RiskBadge` | from the posture report |
| Campaign form | `CampaignForm`: Select (agent version), Checkbox group or Combobox (categories / attacks), Input (budget, repetitions), Switch (adaptive, if exposed), estimate `StatCard`, Alert Dialog | dry-run estimate as in `StartRunDialog`; success → `/runs/<id>` (the Phase 1 console) |

States: inbox empty ("No findings. Launch a campaign to look for some." action → campaign); filtered-empty; detail 404; posture with no attack runs yet (`EmptyState` + action); heatmap cell with zero attempts shows "not tested" in muted text, not a zero tint. No live state on these screens (the campaign's run console is the live view).

Playwright: `findings.spec.ts` "findings: shows seeded data" (a row with a severity badge; status filter narrows; row → detail). `finding-detail.spec.ts` "finding detail: shows seeded data" (title, reproducibility text `/\d+\s*(of|\/)\s*\d+/`, a `CheckTree` node under Reproducer, at least one `event-*` row in the evidence transcript; changing status issues the update request, route-mocked). `security-posture.spec.ts` "security posture: shows seeded data" (heatmap has at least one category row and one non-empty cell; top findings link works). `campaign-launch.spec.ts` "campaign launch: requires confirmation" (form filled, run creation route-mocked, Alert Dialog confirm, lands on `/runs/<id>`); "unverified remote target is disabled" if the seed has one.

**Steps:**
- [ ] Load `animate-ui` and `dataviz` skills. Regenerate API types. Do the contract check; report unbacked regions (expected candidates: CQ-W18 to CQ-W20).
- [ ] Write the four specs; see them fail.
- [ ] Build hooks, then inbox, then detail (reusing `Transcript`, `CheckTree`), then posture and heatmap, then campaign form. Add the Security sidebar group and the open-findings card on the agent overview.
- [ ] Browser-verify each screen (conventions section 10), screenshots. Check the heatmap in light and dark and with reduced motion.
- [ ] Gate (lint, typecheck, test, e2e, audit). Commits: `feat(web): findings inbox and detail`, `feat(web): security posture and campaign launch`.

**Done when:** four specs pass on seeded findings from a DVA attack run; from a finding a user reaches the exact cited event in an evidence episode in one click; no region displays invented data; contract questions reported.

---

### P3-7: Compare view, reliability charts, review queue, rubric manager, clusters on run report

**Batch:** m. **Depends:** P3-1, P3-2, P3-5, P3-6, P1-14.

**Files:**
- `apps/web/src/app/(app)/runs/[runId]/compare/page.tsx`
- `apps/web/src/app/(app)/review/page.tsx`
- `apps/web/src/app/(app)/rubrics/page.tsx`, `rubrics/[rubricId]/page.tsx`
- `apps/web/src/lib/api/hooks/compare.ts`, `review.ts`, `rubrics.ts`
- `apps/web/src/components/compare/compare-summary.tsx`, `flip-table.tsx`, `baseline-picker.tsx`, `trajectory-diff.tsx`
- `apps/web/src/components/runs/reliability-chart.tsx`, `cluster-list.tsx` (and edit `report/page.tsx`, `report-scenario-table.tsx` for flaky / quarantine markers)
- `apps/web/src/components/review/review-item.tsx`, `label-bar.tsx`, `review-progress.tsx`
- `apps/web/src/components/rubrics/rubric-table.tsx`, `rubric-detail.tsx`, `calibration-card.tsx`
- `apps/web/src/components/episode/episode-header.tsx` (add Re-judge button)
- `apps/web/e2e/compare.spec.ts`, `review-queue.spec.ts`, `rubrics.spec.ts`, `rubric-detail.spec.ts`; extend `run-report.spec.ts`

**Interfaces:**
- Consumes: `GET /v1/runs/{id}/compare?baseline={id}`, `GET /v1/runs/{id}/report`, `GET /v1/runs`, `POST /v1/episodes/{id}/rejudge`, `GET /v1/rubrics` (CQ-W4), plus the review-queue, label, golden-set, calibration, cluster and quarantine routes that P3-2, P3-5 and P3-6 add (CQ-W21, CQ-W22). Types: `Rubric`, `Verdict`, comparison and report types.
- Produces: `useRunComparison`, `useReviewQueue`, `useSubmitLabel`, `useRubricList`, `useRubric`, `useRejudgeEpisode`; components `CompareSummary`, `FlipTable`, `BaselinePicker`, `TrajectoryDiff`, `ReliabilityChart`, `ClusterList`, `ReviewItem`, `LabelBar`, `CalibrationCard`.

**Decisions:**
- The comparison verdict (`regression`, `improvement`, `no detectable change`, `inconclusive`) and its plain-language sentence are shown exactly as the API returns them (hard-cores section 3). The web computes no statistics.
- Compare is reached from the run header: Button "Compare" opens `BaselinePicker` (Dialog + Combobox of runs on the same suite), then navigates to `/runs/{id}/compare?baseline={id}`.
- Trajectory diff: two `Transcript compact` panes side by side in `SplitPane` (baseline left, candidate right), opened from a flip-table row in a Sheet. Text differences inside paired messages use `diff` (jsdiff) word diff with `ins` / `del` rendering. No alignment algorithm in the web: rows are paired by index within message kind unless the API supplies an alignment.
- Reliability chart: line chart of pass^k for k = 1..n from the report, one series for the run (two on the compare page), interval as a band; x axis integer k; y axis 0 to 100 percent. Follow the `dataviz` skill for colours and labelling.
- Review queue is keyboard-first: `p` pass, `f` fail, `n` not applicable, `s` skip, `j` / `k` next / previous, `h` show or hide the judge prediction (hidden by default so the label is unbiased). Order is whatever the API returns.
- Rubric manager is read-mostly: view definition, examples, versions, calibration numbers and the `gating_allowed` flag. Editing a rubric is offered only if the schema has a create-version route; it is a Dialog form that creates a new version, never an in-place edit.
- Re-judge: Button in the episode header, `ConfirmDialog`, `toast.promise`, then invalidate the episode.

**Screens:**

| Screen | Route | Purpose | API |
|---|---|---|---|
| Compare | `/runs/[runId]/compare?baseline=` | did the candidate get better or worse, and where | `GET /v1/runs/{id}/compare?baseline={id}`, both runs, both reports |
| Run report additions | `/runs/[runId]/report` | reliability curve, flaky markers, failure clusters | `GET /v1/runs/{id}/report` |
| Review queue | `/review` | label trajectories against a rubric | review queue and label routes |
| Rubric list / detail | `/rubrics`, `/rubrics/[rubricId]` | what each judge asks and how far to trust it | `GET /v1/rubrics`, rubric detail, calibration |

```
Compare                                             Review queue
<h1> v4 vs baseline v3      ▼ Regression            <h1> Review   rubric: policy_adherence ▾   12 of 40
"Pass rate fell 6.1 points (−9.8 to −2.4)…"         [=======>                ]
[Δ pass rate][baseline 84%][candidate 78%][cost Δ]  Question: Did the agent follow the refund policy?
RELIABILITY (pass^k, both runs)   [chart]           pass = …   fail = …   n/a = …            (▸ definitions)
FLIPS  [Newly failing 4|Newly passing 1|Flaky 3|Stable]  +-----------------------------------------------+
| Scenario | Baseline | Candidate | p | → diff |    | Transcript (compact, [seq] anchors)           |
                                                    +-----------------------------------------------+
Rubric detail                                       Judge prediction: hidden  [h to show]
<h1> policy_adherence  v3  high  hard fail          [ Pass (p) ] [ Fail (f) ] [ N/A (n) ] [ Skip (s) ]
Question / pass / fail / n/a definitions
CALIBRATION  kappa 0.71 (0.58–0.82) · n 64 · τ 0.8 · gating allowed ✓
EXAMPLES ▸   VERSIONS ▸
```

| Region | Component | Behaviour |
|---|---|---|
| Verdict banner | shadcn Card + Badge + icon (`trending-down` destructive, `trending-up` success, `info` neutral) + sentence | never colour alone |
| Compare stats | `StatCard` | deltas signed, interval as text |
| Reliability | `ReliabilityChart` (shadcn Chart line + band) in Card; table toggle (Toggle Group "Chart / Table") | |
| Flip table | Base UI Tabs with count Badges + `DataTable`; rate cells use Progress + `n/m` text | row action opens `TrajectoryDiff` |
| Trajectory diff | Sheet (right, wide) + `SplitPane` + two `Transcript compact` + Select (which rep) | |
| Clusters on report | `ClusterList`: Accordion per cluster (name, count Badge, root-cause text), content = episode links | above the Failures table; omitted if the report has no clusters |
| Flaky / quarantine | Badge "flaky" / "quarantined" in the scenario table + Toggle Group filter | quarantine toggle (Switch) only if a route exists |
| Review item | `ReviewItem`: Card (rubric question, Collapsible definitions) + `Transcript compact` + Collapsible (judge verdict via `VerdictCard`, hidden by default) | |
| Label bar | `LabelBar`: Toggle Group (single) of Buttons showing their key; sticky bottom | hotkeys via react-hotkeys-hook; submit then advance; `aria-live` announces "Labelled fail, 13 of 40" |
| Progress | Progress + `LiveNumber` | |
| Rubric table | `DataTable`: title, version, `SeverityBadge`, hard fail, kappa, Badge "not calibrated" / "gating allowed" | |
| Rubric detail | Cards + Accordion (examples, versions) + `CalibrationCard` (`StatCard`s: kappa with interval, accuracy, precision / recall on fail, labelled n, τ, escalation rate, cost per verdict) | |

States: compare with no shared scenarios or no baseline chosen (`EmptyState` with `BaselinePicker`); `inconclusive` shows the API's "run N more repetitions" line prominently; review queue empty ("Nothing to review" with what feeds the queue); label submit error keeps the item and toasts; rubric with no golden set ("Not calibrated: needs at least 40 labelled items" using the numbers from hard-cores 5.4 only if the API returns the counts).

Playwright: `compare.spec.ts` "compare: shows seeded data" (verdict banner text is one of the four verdicts; flip tabs present; opening a flip row shows two transcripts). `review-queue.spec.ts` "review queue: labels with the keyboard" (press `f`, assert a label request with result fail, route-mocked, and the counter advances; judge prediction hidden until `h`). `rubrics.spec.ts` and `rubric-detail.spec.ts` "shows seeded data" (question text; calibration card or the not-calibrated marker). `run-report.spec.ts` gains: reliability chart region visible with an accessible name, and its table alternative has k = 1 equal to the pass rate stat.

**Steps:**
- [ ] Load `animate-ui` and `dataviz` skills. Regenerate types; contract check; report gaps (CQ-W21, CQ-W22).
- [ ] Specs first, failing. Unit test first for the word-diff render helper (`trajectory-diff`), and for hotkey handling in `LabelBar`.
- [ ] Build in this order: compare, report additions, review queue, rubrics, re-judge button. Add the Quality sidebar group (Review, Rubrics).
- [ ] Browser-verify each (label 5 items using only the keyboard; check charts in dark and light; reduced motion). Screenshots.
- [ ] Gate. Commits per screen: `feat(web): compare view`, `feat(web): reliability and clusters on report`, `feat(web): review queue`, `feat(web): rubric manager`.

**Done when:** specs pass; the compare page shows the API's verdict and sentence verbatim; a reviewer can label a queue without the mouse; every chart has a table alternative; gaps reported.

---

### P3-8 (web parts): Model migration report, scorecard page

**Batch:** m (same agent, after P3-7). **Depends:** P3-1, P3-7.

**Files:**
- `apps/web/src/app/(app)/agents/[agentId]/migration/page.tsx`
- `apps/web/src/app/(app)/agents/[agentId]/scorecard/page.tsx`
- `apps/web/src/lib/api/hooks/migration.ts`
- `apps/web/src/components/migration/pareto-chart.tsx`, `migration-table.tsx`, `version-pair-picker.tsx`
- `apps/web/src/components/agents/scorecard.tsx`
- `apps/web/e2e/migration.spec.ts`, `scorecard.spec.ts`

**Interfaces:** Consumes the migration-report and scorecard routes P3-8's server part adds (CQ-W23), `GET /v1/agents/{id}/versions`, `GET /v1/runs/{id}/compare?baseline={id}`. Produces `useMigrationReport`, `useScorecard`; `ParetoChart`, `MigrationTable`, `VersionPairPicker`, `Scorecard`.

**Decisions:**
- The migration page is the compare view's data for two agent versions on one suite plus cost and latency: it reuses `CompareSummary` and `FlipTable` and adds only the Pareto chart and the version picker.
- Pareto chart: scatter, x = cost per episode (dollars from micro-dollars), y = pass rate, one labelled point per version, the frontier drawn as a step line; direct labels, no legend (dataviz skill). Table alternative below.
- Scorecard is a print-friendly single column (`@media print` hides the shell): agent name and version, date, suite, pass rate with interval, pass^k at k = 1, 3, 5 when present, per-rubric results, open findings by severity (if Phase 2 is present), cost. No motion on this page at all (`AnimateUIProvider reducedMotion="always"` nested around it).

**Screens:** `/agents/[agentId]/migration?base=<ver>&candidate=<ver>&suite=<id>` (purpose: should we switch models) and `/agents/[agentId]/scorecard?version=<ver>` (purpose: a shareable summary).

| Region | Component |
|---|---|
| Pair picker | `VersionPairPicker`: two Select + Select (suite) + Button; if no run pair exists, `StartRunDialog` for the missing side |
| Summary, flips | `CompareSummary`, `FlipTable` (from P3-7) |
| Pareto | `ParetoChart` (shadcn Chart scatter) in Card + Toggle Group "Chart / Table" + `MigrationTable` (`DataTable`) |
| Scorecard | shadcn Card sections, `StatCard` (static), shadcn Table, Badges; header Button "Print" (`window.print()`), Copy Button for the page link |

States: no runs for the chosen pair (`EmptyState` with the run action); one side still running (banner, partial data, link to console); scorecard with no finished run ("Run a suite to produce a scorecard").

Playwright: `migration.spec.ts` "migration: shows seeded data" (two version labels visible, Pareto region and its table show two rows). `scorecard.spec.ts` "scorecard: shows seeded data" (agent name, pass rate `/\d+%/`, rubric table rows; `page.emulateMedia({ media: 'print' })` hides the sidebar).

**Steps:**
- [ ] Load `animate-ui` and `dataviz`. Regenerate types; contract check (CQ-W23).
- [ ] Specs first, failing. Build migration, then scorecard. Link both from the agent overview header (Dropdown Menu "Reports").
- [ ] Browser-verify, including print preview of the scorecard. Screenshots. Gate. Commit `feat(web): migration report and scorecard`.

**Done when:** both specs pass; the scorecard prints on one or two pages without the shell; no statistics computed in the browser.

---

### P4-6: Gateway console, policy editor, policy test results with tradeoff chart, approval inbox

**Batch:** p. **Depends:** P4-2 (gateway, decision log, approvals), L8 and P4-1 (policy engine, offline testing, compiler), P4-5 (finding to rule loop), P2-10.

**Files:**
- `apps/web/src/app/(app)/gateway/page.tsx` (console: decisions)
- `apps/web/src/app/(app)/gateway/policies/page.tsx`, `gateway/policies/[policyId]/page.tsx`
- `apps/web/src/app/(app)/gateway/approvals/page.tsx`
- `apps/web/src/lib/api/hooks/policies.ts`, `gateway.ts`, `approvals.ts`
- `apps/web/src/components/gateway/decision-table.tsx`, `decision-detail.tsx`, `mode-control.tsx`
- `apps/web/src/components/gateway/policy-table.tsx`, `rule-list.tsx`, `rule-form.tsx`, `check-editor.tsx`
- `apps/web/src/components/gateway/policy-test-results.tsx`, `tradeoff-chart.tsx`, `rule-breakdown-table.tsx`
- `apps/web/src/components/gateway/approval-card.tsx`
- `apps/web/e2e/gateway-console.spec.ts`, `policies.spec.ts`, `policy-editor.spec.ts`, `approvals.spec.ts`
- Edit `apps/web/src/components/findings/suggested-rule-card.tsx` (add "Add to policy" action)

**Interfaces:**
- Consumes: policy and decision resource routes that follow the `policies` and `gateway_decisions` tables, and the policy-test, approval and suggestion routes P4-1, P4-2 and P4-5 add (CQ-W24). Types: `Policy`, `PolicyRule`, `Check`, `Finding`, `Evidence`.
- Produces: `usePolicyList`, `usePolicy`, `useSavePolicy`, `useRunPolicyTest`, `useGatewayDecisions`, `useApprovals`, `useDecideApproval`; components `DecisionTable`, `DecisionDetail`, `ModeControl`, `PolicyTable`, `RuleList`, `RuleForm`, `CheckEditor`, `PolicyTestResults`, `TradeoffChart`, `RuleBreakdownTable`, `ApprovalCard`.

**Decisions:**
- **Check editing is JSON, not a visual builder.** `CheckEditor` = shadcn Textarea (`font-mono`) with the check as JSON, validated client-side against the generated JSON Schema or zod for `Check`, with a live read-only `CheckTree` preview beside it and inline errors. Server validation is the authority: a rule whose `when` uses `judge` or `state_diff` is rejected by the API (not prefix-evaluable) and that message is shown on the field.
- Saving a policy creates a new version (contract `Policy.version`); the editor shows the version and never edits in place.
- Switching `mode` from `shadow` to `enforce`, or `fail` from `open` to `closed`, goes through an Alert Dialog that shows the latest policy test numbers (block rate, false-positive rate) or the warning "this version has not been tested".
- Policy test results are shown as returned (hard-cores 7.2): block rate, false-positive rate, per-rule breakdown, tradeoff table. Each blocked or broken trajectory links to its episode at the blocking event (`/episodes/<id>#e-<seq>`).
- Tradeoff chart: line with points, x = false-positive rate, y = block rate, one point per rule subset in the API's greedy order, each point labelled with the rule added; table alternative.
- Live decisions: if the API offers a decision stream, reuse the doorbell pattern from `useRunStream` in a `useDecisionStream` hook with its own adapter; otherwise poll every 5s while the tab is visible, with the "Live" Badge showing which mode is active. New rows fade in at the top; nothing else moves.
- Approvals: Approve and Deny are both explicit Buttons with equal weight; Deny asks for an optional reason in a Popover. An approval that expired or was decided elsewhere fades out with a toast.

**Screens:**

| Screen | Route | Purpose | API |
|---|---|---|---|
| Gateway console | `/gateway` | what the gateway is deciding right now | decisions list (and stream if any), policies |
| Policy list | `/gateway/policies` | policies, versions, mode | policies list |
| Policy editor + tests | `/gateway/policies/[policyId]` | edit rules, test offline, switch mode | policy detail, save, policy test |
| Approval inbox | `/gateway/approvals` | humans decide `require_approval` actions | approvals list, decide |

```
Gateway console                                       Policy editor
<h1> Gateway   policy: support-prod v7  ENFORCE [Live] <h1> support-prod  v7   [ Shadow | Enforce ]  fail: closed ▾
[decisions 1h][blocked][approvals pending 2][p50 ms]   [ Rules 6 | Test results | JSON ]
[All|Block|Require approval|Redact|Log] (🔍 tool)      +---------------------------+---------------------------+
| Time | Action | Rule | Tool / message | Agent | →   | RULES                     | RULE: no-tainted-refund   |
| 12:01| BLOCK  | no-tainted-refund | issue_refund |  |  ● no-tainted-refund  crit | description [..........]  |
                                                       |  ○ refund-cap         high | severity [critical ▾]     |
Approval inbox                                         |  + Add rule                | action   [block ▾]        |
<h1> Approvals   2 pending                             |                           | when (JSON)   | preview    |
+---------------------------------------------------+ |                           | {...}         | CheckTree  |
| issue_refund {amount: 480}   rule refund-cap  high | |                           | message [..............]  |
| requested 2m ago · agent v3 · ▸ context            | +---------------------------+---------------------------+
|                         [ Deny ]   [ Approve ]     | Test results: block 92% · false positives 3% · [Run test]
+---------------------------------------------------+ TRADEOFF [chart]   PER RULE [table]   TRAJECTORIES [table →]
```

| Region | Component | Behaviour |
|---|---|---|
| Console stats | `StatCard` + `LiveNumber` | only stats the API provides |
| Decision filter | `FilterBar` (Toggle Group by action, Input) | |
| Decision table | `DecisionTable`: `DataTable` + Badge (action: block destructive, require_approval warning, redact info, log muted) | row opens `DecisionDetail` |
| Decision detail | Sheet + rule summary + `CheckTree` + `JsonBlock` (proposed action) + evidence list with `SeqAnchor` links when tied to an episode | |
| Mode | `ModeControl`: Toggle Group (single) + Select (fail) + Alert Dialog | per Decisions |
| Policy table | `DataTable`: name, version, mode Badge, rule count, last test numbers | |
| Editor layout | Base UI Tabs (Rules / Test results / JSON) + `SplitPane` | unsaved changes: Badge "Unsaved" + Alert Dialog on navigation away |
| Rule list | `RuleList`: Highlight (click) list of rules with `SeverityBadge`, action Badge; Button "Add rule"; Dropdown Menu (duplicate, delete) | |
| Rule form | `RuleForm`: react-hook-form + zod; Input, Textarea, Select; `CheckEditor`; field errors in Auto Height | |
| Test results | `PolicyTestResults`: `StatCard`s, `TradeoffChart` (shadcn Chart) with table toggle, `RuleBreakdownTable`, trajectories `DataTable` with episode links; Button "Run test" with `toast.promise` | |
| Running test | `LiveStatusText` + Progress if the API reports progress, otherwise Skeleton | |
| Approvals | `ApprovalCard`: Card + `RiskBadge` + `JsonBlock` (args) + Collapsible (context transcript, compact) + Buttons + Popover (deny reason) | list wrapped in Auto Height; decided cards fade out |
| From a finding | `SuggestedRuleCard` gains Button "Add to policy" → Dialog (Select policy) → opens the editor with the rule prefilled and unsaved | |

States: no policy yet (`EmptyState` "Create a policy, or start from a finding's suggested rule"); console with no decisions ("No traffic yet" plus how to wrap an agent with the SDK middleware, one line and a docs link); policy never tested (Test results tab `EmptyState` with Run test); test with no stored attack or benign trajectories (API message shown); approvals empty ("Nothing waiting"); save rejected (field-level message on the offending rule); live paused badge.

Playwright: `gateway-console.spec.ts` "gateway console: shows seeded data" (a decision row with an action badge; opening it shows the rule id; "updates live" with mocked list snapshots). `policies.spec.ts` "policies: shows seeded data". `policy-editor.spec.ts` "policy editor: shows seeded data" (rule list, selecting a rule shows its `when` JSON and a `CheckTree` node); "rejects an invalid check" (type invalid JSON, inline error, Save disabled); "enforce asks for confirmation" (Alert Dialog shows test numbers or the untested warning). `approvals.spec.ts` "approvals: approve and deny" (route-mocked decide calls; card leaves the list).

**Steps:**
- [ ] Load `animate-ui` and `dataviz`. Regenerate types; contract check; report gaps (CQ-W24).
- [ ] Unit tests first: `CheckEditor` validation (valid check parses; unknown `type` errors; JSON syntax error position), `ModeControl` confirmation logic. Specs first, failing.
- [ ] Build: policy list, editor (rules, then JSON tab, then test results and chart), console, approvals, then the finding "Add to policy" action. Add the Gateway sidebar group (Console, Policies, Approvals with a pending-count Badge).
- [ ] Browser-verify each screen; walk the closed loop once by hand: finding → add suggested rule → run test → see block rate → switch to enforce. Screenshots of each step.
- [ ] Gate. Commits: `feat(web): policy editor and tests`, `feat(web): gateway console`, `feat(web): approval inbox`.

**Done when:** four specs pass; the closed loop can be walked in the UI without leaving it; switching to enforce is impossible without seeing the test numbers or the untested warning; every chart has a table alternative; gaps reported.

---

## Contract questions (Phases 2 to 4 web)

Cross-cutting CQ-W1 to CQ-W7 are in `web-conventions.md`; CQ-W8 to CQ-W17 in `phase-1-web.md`.

| ID | Question |
|---|---|
| CQ-W18 | Findings (P2-5): list filters; how status is changed (route and body) and which transitions are legal; routes for replay, verify, pin into the `security-regression` suite, and SARIF / markdown export. The vision's "assign" and "link tickets" have no fields on `Finding`; the web omits them. Which evidence (event seq) proves the objective for a finding's episode, so the detail page can preselect it? |
| CQ-W19 | Campaign launch: how an attack run is created (is it `POST /v1/runs` with extra fields, or its own route), how attacks or categories, mutations and adaptive mode are selected, the attack list route (`/v1/attacks`), where ownership-verification status of a remote target is read, and the kill-switch route. |
| CQ-W20 | Posture report and coverage heatmap (P2-6): routes and shapes (category × vector attempts and successes, top findings, tool permission review), and a route or file for the taxonomy (category ids, titles, OWASP / ATLAS mapping). |
| CQ-W21 | Phase 3 run data: response shape of `GET /v1/runs/{id}/compare`; how a baseline is set (`runs.baseline_of`); whether a trajectory-diff route or alignment exists; where pass^k per k with intervals, flaky and quarantine flags, the adaptive-sampling flag and failure clusters (name, members, root cause) appear in the report; quarantine toggle route. |
| CQ-W22 | Review and rubrics (P3-5): routes for the review queue (ordering, per rubric), submitting a `human_labels` row, golden sets, starting calibration and reading its results (kappa with interval, accuracy, precision, recall, τ, escalation rate, cost per verdict, labelled counts, `gating_allowed`), rubric versions, and creating a rubric version. |
| CQ-W23 | Migration report and scorecard (P3-8): routes and shapes (per-version pass rate, cost per episode, latency, Pareto frontier membership; scorecard contents), and whether the badge endpoint (P3-4) should be linked from the scorecard. |
| CQ-W24 | Gateway and policy (P4-1, P4-2, P4-5): exact paths for policies and gateway decisions; policy save and versioning; offline policy test route, whether it is a job, and its result shape (block rate, false-positive rate, per-rule, tradeoff table, per-trajectory first block seq); decision list filters and whether a live stream exists; approvals list and decide routes with expiry; "suggest rule from finding" and policy-compiler review routes; gateway stats (latency, counts) for the console. |
