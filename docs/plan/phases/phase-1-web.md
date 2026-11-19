# Phase 1 web: P1-12, P1-13, P1-14

Batch f, one Sonnet agent, in order P1-12 then P1-14 then P1-13 (the episode viewer is the Phase 1 definition of done; do it before the wizard).

Read first: `docs/plan/README.md`, `docs/plan/02-contracts.md` (sections 2, 5, 8, 9), `docs/plan/phases/web-conventions.md` (all of it; it defines setup, shared components, the API client, the SSE hook, auth, state rules, Playwright rules and the verification checklist). **Load the `animate-ui` skill before each task.** Routes and fields named below are from contracts section 9 and the models in sections 1, 2 and 5; the exact response field names come from `src/lib/api/schema.d.ts`. Where the schema lacks something, omit that region and report it.

---

### P1-12: Web foundation

**Batch:** f. **Depends:** P1-9 (API running in compose), P0-1 (pnpm + Turborepo).

**Files:**
- `apps/web/package.json`, `components.json`, `tsconfig.json`, `next.config.ts`, `eslint.config.mjs`, `vitest.config.ts`, `playwright.config.ts`, `.env.example`, `.gitignore` (adds `e2e/.screens`, `test-results`)
- `apps/web/src/app/layout.tsx`, `providers.tsx`, `globals.css`
- `apps/web/src/app/login/page.tsx`
- `apps/web/src/app/api/session/route.ts`, `apps/web/src/app/api/gauntlet/[...path]/route.ts`
- `apps/web/src/app/(app)/layout.tsx`, `apps/web/src/app/(app)/page.tsx`
- `apps/web/src/components/ui/*` (generated), `apps/web/src/components/animate-ui/icons/*` (generated)
- `apps/web/src/components/shared/*.tsx` (every row of conventions section 4, one file each, kebab-case)
- `apps/web/src/lib/api/schema.d.ts` (generated), `client.ts`, `errors.ts`, `types.ts`, `hooks/projects.ts`
- `apps/web/src/lib/sse/use-run-stream.ts`, `adapter.ts`, `use-run-stream.test.ts`
- `apps/web/src/lib/format.ts`, `format.test.ts`, `query-keys.ts`
- `apps/web/e2e/global-setup.ts`, `fixtures.ts`, `login.spec.ts`, `shell.spec.ts`
- `apps/web/README.md` (what it owns; must not import anything outside `apps/web`)

**Interfaces:**
- Consumes: `GET /openapi.json`, `GET /v1/projects`, `GET /v1/runs/{id}/stream` (hook only, no screen yet).
- Produces: every shared component in conventions section 4; `$api`, `fetchClient`, `ApiError`; `useProjectList`; `useRunStream`; `formatUsd`, `formatDuration`, `formatPercent`, `shortId`; e2e `test` fixture with `seeded` helpers; scripts `dev build start lint typecheck test e2e gen:api audit`.

**Decisions:**
- Everything in conventions sections 1 to 9 is binding. This task implements it; it does not revisit it.
- No project switcher in Phase 1. The app uses the first project from `GET /v1/projects`; its name shows in `AccountMenu`. `useCurrentProject()` returns it.
- Sidebar nav in Phase 1: Agents (`bot`), Scenarios (`list`), Runs (`play`). Items for later phases are added by their own tasks.
- No command palette, no settings page, no notifications in Phase 1.
- Login screen has no decoration (no background component).

**Screen: Login** — route `/login`. Purpose: store the API key server-side. API: `POST /api/session` (Next handler, which calls `GET /v1/projects`).

```
+----------------------------------------------+
|                                              |
|            Gauntlet                          |
|            [ API key ............... ]       |
|            (inline error)                    |
|            [ Sign in ]                       |
|                                              |
+----------------------------------------------+
```

| Region | Component | Props / behaviour |
|---|---|---|
| Card | shadcn Card | centred, `max-w-sm` |
| Key field | shadcn Input `type="password"`, Label | autofocus, `autocomplete="off"` |
| Error | text in Auto Height | API `message`; `role="alert"` |
| Submit | Button (Animate UI press) | loading: disabled + `loader-circle` |

States: loading (button), error (inline), success (redirect to `next` or `/`). Playwright `login.spec.ts`: "login: rejects a bad key" (error text visible, still on `/login`); "login: accepts the seeded key" (lands on `/agents` or `/onboarding`, sidebar visible).

**Screen: App shell** — every `(app)` route.

```
+--------+-------------------------------------------------+
| Gaunt. | Breadcrumb > Breadcrumb            [actions]    |
|--------| <h1> Page title                                 |
| Agents |-------------------------------------------------|
| Scen.  |                                                 |
| Runs   |   page content                                  |
|        |                                                 |
|--------|                                                 |
| proj ▾ |                                                 |
+--------+-------------------------------------------------+
```

| Region | Component | Props / behaviour |
|---|---|---|
| Sidebar | Sidebar (Base UI family, Animate UI primitive) | `collapsible="icon"`, shared highlight on active item, animated trigger icon, icons `animateOnHover` |
| Footer | Dropdown Menu, Theme Toggler Button | project name, theme, Sign out (`log-out`) |
| Header | `PageHeader` (Breadcrumb, Button) | per page |
| Toasts | Base UI Toast viewport | bottom right |

Playwright `shell.spec.ts`: "shell: navigates between sections" (click Scenarios and Runs, `<h1>` changes, active item has `aria-current="page"`); "shell: sign out returns to login".

**Steps:**
- [ ] Load the `animate-ui` skill; read conventions fully.
- [ ] Scaffold `apps/web` with `create-next-app` (TypeScript, App Router, `src/`, Tailwind, ESLint, no example content); name the package `web`; add it to the pnpm workspace and Turborepo pipeline (`lint`, `typecheck`, `test`, `build`).
- [ ] Run the Animate UI setup, conventions section 3, steps 1 to 10. Commit: `chore(web): scaffold next app with animate ui`.
- [ ] Add `openapi-typescript`, `openapi-fetch`, `openapi-react-query`, `@tanstack/react-query`, `@tanstack/react-table`, `react-hook-form`, `zod`, `@hookform/resolvers`; dev: `vitest`, `@testing-library/react`, `jsdom`, `@playwright/test`. Start compose, run `gen:api`, commit the schema.
- [ ] Test first: `format.test.ts` (`formatUsd(12300) === '$0.0123'`, `formatUsd(2500000) === '$2.50'`, `shortId('ep_01HXYZABCDEFG') ` keeps prefix and last 4), `use-run-stream.test.ts` (cases in conventions section 6), `errors` parsing of the contract envelope. See them fail.
- [ ] Implement `lib/` (client, errors, hooks, sse, format), then the route handlers (`api/session`, `api/gauntlet`), then `providers.tsx`, layouts, login.
- [ ] Write `e2e/global-setup.ts`, `fixtures.ts`, `login.spec.ts`, `shell.spec.ts`; see them fail; implement shared components and the shell until green.
- [ ] Build every shared component from conventions section 4. Add a dev-only page `src/app/(app)/_kit/page.tsx` that renders each one in each state (excluded from nav; used for visual verification here and deleted at the end of P1-13).
- [ ] Verify in a real browser per conventions section 10 (login, shell, `_kit`), screenshots to `e2e/.screens/`.
- [ ] Gate: `pnpm --filter web lint && pnpm --filter web typecheck && pnpm --filter web test && pnpm --filter web e2e && pnpm --filter web audit`.
- [ ] Commit: `feat(web): app shell, api client, auth, shared components`.

**Done when:** gate green; login and shell specs pass against the seeded compose stack; `schema.d.ts` committed; no file in `src` hand-declares an API type; `_kit` screenshot shows every shared component in dark theme; SSE proxy verified by `curl -N` through `/api/gauntlet/v1/runs/<seeded run>/stream` with the cookie (response is `text/event-stream`, not buffered).

---

### P1-14: Run console, run report, episode viewer

**Batch:** f. **Depends:** P1-12.

**Files:**
- `apps/web/src/app/(app)/runs/page.tsx`
- `apps/web/src/app/(app)/runs/[runId]/layout.tsx`, `page.tsx`, `report/page.tsx`
- `apps/web/src/app/(app)/episodes/[episodeId]/page.tsx`
- `apps/web/src/lib/api/hooks/runs.ts`, `episodes.ts`, `scenarios.ts` (read hooks only; P1-13 extends `scenarios.ts`)
- `apps/web/src/components/runs/run-header.tsx`, `run-controls.tsx`, `run-table.tsx`, `episode-table.tsx`, `live-episode-panel.tsx`, `report-summary.tsx`, `report-scenario-table.tsx`, `report-failures.tsx`
- `apps/web/src/components/episode/episode-header.tsx`, `transcript.tsx`, `transcript-row.tsx`, `tool-timeline.tsx`, `state-diff.tsx`, `verdict-list.tsx`, `verdict-card.tsx`, `payloads.ts`, `selection.ts`, `quote-match.ts`, `diff-entries.ts`
- Tests: `apps/web/src/components/episode/quote-match.test.ts`, `diff-entries.test.ts`, `selection.test.ts`
- E2E: `apps/web/e2e/runs.spec.ts`, `run-console.spec.ts`, `run-report.spec.ts`, `episode-viewer.spec.ts`

**Interfaces:**
- Consumes: `GET /v1/runs`, `GET /v1/runs/{id}`, `GET /v1/runs/{id}/episodes`, `POST /v1/runs/{id}/cancel`, `POST /v1/runs/{id}/pause`, `POST /v1/runs/{id}/resume`, `GET /v1/runs/{id}/stream`, `GET /v1/runs/{id}/report`, `GET /v1/episodes/{id}` (with events and verdicts), `GET /v1/scenarios`. Types: `Event`, `Verdict`, `Evidence`, `PatchOp`, `Cost`, `Origin`, `Outcome`, `Termination`, `RunManifest`.
- Produces hooks: `useRunList`, `useRun`, `useRunEpisodes`, `useRunReport`, `useCancelRun`, `usePauseRun`, `useResumeRun`, `useEpisode`, `useScenarioMap`, `useEventSelection`.
- Produces components: `RunHeader`, `RunControls`, `RunTable`, `EpisodeTable`, `LiveEpisodePanel`, `ReportSummary`, `ReportScenarioTable`, `ReportFailures`, `EpisodeHeader`, `Transcript` (props `events`, `live?`, `compact?`), `ToolTimeline`, `StateDiff`, `VerdictList`, `VerdictCard`.

**Decisions (all four screens):**
- The run header (`runs/[runId]/layout.tsx`) is shared by console and report. A Toggle Group (single) "Console | Report" navigates between the two routes. A finished run opened at `/runs/{id}` stays on the console (it is the episode browser); the runs list links finished runs to `/report`, active runs to the console.
- Scenario titles: episodes carry `scenario_id`; join client-side with `useScenarioMap()` (from `GET /v1/scenarios`). No title found: show the id.
- Money comes from `spent_usd_micros`, `budget_usd_micros`, `cost_usd_micros` only, through `Money`.
- Episode "counts toward statistics" = outcome is `passed` or `failed` (contract D5). Other outcomes get the warning badge and the label "excluded from pass rate".
- No "add to regression suite", "mark as simulator error" or "re-judge" buttons in Phase 1 (CQ-W15).

#### Screen: Runs list — `/runs`

Purpose: find a run. API: `GET /v1/runs`.

```
<h1> Runs
[ All | Active | Finished ]                           
+------------------------------------------------------------+
| Status   | Suite | Agent version | Episodes | Cost | Created |
| ● Running| ...   | v3            | 42/90    | $0.31| 2m ago  |
+------------------------------------------------------------+
```

| Region | Component | Props / behaviour |
|---|---|---|
| Filter | `FilterBar` (Toggle Group single) | URL `?status=` |
| Table | `DataTable` | columns from the run and its `manifest` (`suite_id`, `agent_version.label`, `created_at`); row click navigates |
| Status cell | `RunStatusBadge` | `LiveStatusText` while active |

States: loading `LoadingRows`; empty `EmptyState` "No runs yet. Start one from an agent." action links to `/agents`; error `ErrorState`. Not live (refetch on focus). Playwright `runs.spec.ts` "runs: shows seeded data": `<h1>` Runs, at least one `episode-row`-style table row, clicking it changes the URL to `/runs/<id>`.

#### Screen: Run console — `/runs/[runId]`

Purpose: watch a run, control it, follow one episode live. API: `GET /v1/runs/{id}`, `GET /v1/runs/{id}/episodes`, `GET /v1/runs/{id}/stream`, `POST .../cancel|pause|resume`, `GET /v1/episodes/{id}` for the focused episode, `GET /v1/scenarios`.

```
Runs > run_…k3f9
<h1> ecommerce-core on support-agent v3   ● Running  [Live]     [Pause] [Cancel]
[ Console | Report ]
+------------------+------------------+------------------+------------------+
| Progress 42 / 90 | Passed 31        | Failed 6         | Cost $0.31 / $2  |
| [=======>      ] | Excluded 5       |                  | [===>          ] |
+------------------+------------------+------------------+------------------+
+-------------------------------------------+----------------------------------+
| [All|Running|Failed|Passed|Excluded] (🔍) | refund-outside-window · rep 2    |
| Scenario            Rep Status  Out  Cost | ● Running      [Open episode ↗]  |
| refund-outside-win   2  ● run        $.01 | [3] user  I want a refund ...    |
| cancel-order         1  done   pass  $.01 | [4] agent Let me look that up    |
| address-change       1  done   FAIL  $.02 | [5] tool  get_order(order_id=..) |
| ...                                       | Agent is replying…               |
+-------------------------------------------+----------------------------------+
```

| Region | Component | Props / behaviour |
|---|---|---|
| Header | `PageHeader`, `RunStatusBadge`, Badge "Live" | Live badge reflects `useRunStream().status` |
| Controls | Button; `ConfirmDialog` (Alert Dialog) for Cancel | Pause shown when running, Resume when paused, both hidden when terminal. `toast.promise` on each |
| View switch | Toggle Group (single) | navigates |
| Stat cards | `StatCard` with `LiveNumber`, `Money`, Progress | Progress value = done / total. Counts: from the run if the schema has them, else computed from the episode list. Budget Progress turns `warning` above 80% |
| Episode filter | `FilterBar` (Toggle Group + Input) | client-side over the loaded list |
| Episode table | `DataTable` + `EpisodeStatusBadge`, `OutcomeBadge`, `Money` | row click sets `?episode=<id>` (focus); selected row marked with Highlight (controlled) and `aria-selected`. Double click or Enter opens `/episodes/<id>` |
| Live panel | `SplitPane` right side: `LiveEpisodePanel` = `Transcript compact live` inside Scroll Fade, `LiveStatusText`, Button link "Open episode" | follows the bottom while the user has not scrolled up; a "Jump to latest" Button appears otherwise |

Live behaviour: `useRunStream(runId, { focusedEpisodeId })`. Default focus when `?episode` is absent: the first episode with status `leased`; if none, none (panel shows `EmptyState` "Select an episode to follow it"). New transcript rows and verdict rows fade in; counters roll; nothing else moves.

States: loading (skeleton cards + `LoadingRows`); empty (run has no episodes yet: "Episodes are being queued", `loader-circle`); error (`ErrorState` per region; mutation errors as toast); live closed ("Live updates paused" badge, polling fallback); terminal (no Live badge, controls hidden, panel shows the selected episode statically).

Playwright `run-console.spec.ts`:
- "run console: shows seeded data": `<h1>` contains the suite name or run id; `stat-progress`, `stat-cost` visible; at least one `episode-row`; clicking a row shows `event-0` in the live panel; "Open episode" navigates to `/episodes/<id>`.
- "run console: updates live": mock REST to return snapshot A (10 of 30 done), mock the stream to emit `episode_update` then `event`, switch REST to snapshot B (11 done, one more event); assert `stat-progress` text becomes `11`, a new `event-<seq>` appears, cost text changes.
- "run console: cancel asks for confirmation": click Cancel, dialog visible, confirm, assert a `POST` to `.../cancel` was made (route-mocked 200).

#### Screen: Run report — `/runs/[runId]/report`

Purpose: the result of a run: how reliable, what failed, where to look. API: `GET /v1/runs/{id}/report`, `GET /v1/runs/{id}`, `GET /v1/runs/{id}/episodes`, `GET /v1/scenarios`.

```
<h1> … (shared run header)                       [ Console | Report ]
+-------------+--------------+----------------+-------------+-----------+
| Pass rate   | Scenarios    | Episodes       | Excluded    | Cost      |
| 81%         | 30           | 85 counted     | 5           | $1.92     |
| (72 to 88)  |              |                | (by outcome)|           |
+-------------+--------------+----------------+-------------+-----------+
(caution lines: judge family equals target family; world fidelity simulated)
Dimensions (rubrics)                                      
| Rubric / criterion   | Pass | Fail | N/A | Error | Severity |
Scenarios                              [ All | Failing | Flaky ]
| Scenario | Trials | Pass rate [bar] (interval) | Failing episodes → |
Failures
| Scenario · rep | Outcome | Failed criteria (badges) | → episode |
```

| Region | Component | Props / behaviour |
|---|---|---|
| Summary | `StatCard` x5 | values and interval from the report type; interval as text, Tooltip explains "95% interval, resampled by scenario" |
| Cautions | shadcn Card (warning border) + `triangle-alert` | only if the report carries those flags |
| Dimensions | `DataTable` + `SeverityBadge` | one row per rubric / criterion in the report |
| Scenario table | `DataTable`, Progress as rate bar, Toggle Group filter, Button links | sorted worst first; "Failing episodes" links to `/episodes/<id>` of the first failed rep, or to the console filtered `?outcome=failed&scenario=<id>` when several |
| Failures | `DataTable` + `OutcomeBadge` + `VerdictBadge` | failed episodes from the episode list; row click opens the episode |
| Excluded detail | Hover Card on the Excluded stat | count per non-counted outcome |

Binding rule: this screen renders what the generated report type contains. Each region above lists what it needs; if the type lacks it, omit the region and report (CQ-W10). No charts in Phase 1 (reliability curve is P3-7).

States: loading (skeleton cards and rows); run still active (banner Card "Run in progress, report is partial" with link to the console; data still shown); empty (no counted episodes: `EmptyState` "No episodes counted yet"); error `ErrorState`. Not live: refetch on focus and when `useRun` status changes to terminal.

Playwright `run-report.spec.ts` "run report: shows seeded data": `stat-pass-rate` matches `/\d+%/`; scenario table has at least one row; Failures has at least one row (seed has a failed episode); clicking it lands on `/episodes/<id>`.

#### Screen: Episode viewer — `/episodes/[episodeId]`

The most important screen. Purpose: understand exactly what happened in one episode and why it was judged that way, with every claim traceable to an event.

API: `GET /v1/episodes/{id}` (events and verdicts), `GET /v1/scenarios/{id}` if the episode response does not embed the scenario (title, goal, `max_turns`), `GET /v1/runs/{id}/episodes` (previous / next), `GET /v1/runs/{id}/stream` only while the episode is not `done`.

URL state: `#e-<seq>` selected event; `?tab=verdicts|tools|state` right pane tab (default `verdicts`); `?q=<index>` not used. Deep links must restore selection and scroll.

```
Runs > run_…k3f9 > refund-outside-window · rep 2            [‹ Prev] [Next ›]
<h1> refund-outside-window    ✖ Failed   max_turns · 9 turns · $0.021 · 48s   ep_…a1b2 ⧉
Goal: Get a refund for an order delivered 45 days ago
+----------------------------------------------+-------------------------------------+
| TRANSCRIPT             [Messages|All events] | [ Verdicts 5 | Tools 4 | State 2 ]  |
|                                              |-------------------------------------|
| [0]  platform  episode started               | ✖ FAIL  policy_adherence   high     |
| [1]  user      Hi, I want a refund for ...   |   strong judge · conf 0.93 · HARD   |
| [2]  agent     Sure, let me check that.      |   Reasoning ▸                       |
| [3]  tool →    get_order {order_id: "o_17"}  |   Evidence                          |
| [4]  tool ←    ok · 12ms  ▸ result           |   [6] "I've issued a full refund    |
| [5]  tool →    issue_refund {amount: 129.0}  |        of $129.00"                  |
|      ⚠ financial                             |   [5] issue_refund called           |
| [6]  tool ←    ok · 9ms · 2 changes ▸        |-------------------------------------|
| [7]  agent     I've issued a full refund of  | ✔ PASS  task_completion   medium    |
|      ▓▓$129.00▓▓ to your card.               |   rule · conf 1.00                  |
| [8]  user      Thanks!                       |   ...                               |
| [9]  platform  ended: failed (user_done)     |                                     |
+----------------------------------------------+-------------------------------------+
Tools tab:                                State tab:
 12ms  get_order      read      ok   [3→4]   ▾ refunds        +1
  9ms  issue_refund   financial ok   [5→6]      + ref_1  {amount: 129.0, ...}   [6]
       ▸ args  ▸ result  ▸ patch (2)         ▾ orders         ~1
 ⚠ fault http_500 on get_order      [10]        ~ o_17  status: delivered → refunded [6]
```

Layout: `SplitPane` horizontal, default 60/40, min 35% each. Both panes scroll independently, full viewport height below the header. Below 1024px the right pane becomes a bottom Sheet opened by a Button; do not spend more than that on small screens.

**Selection model** (`selection.ts`, `useEventSelection()`): one selected `seq` and one optional `quote`, stored in the URL hash (`#e-12`) and React state. API: `{ selectedSeq, quote, select(seq, quote?), clear() }`. `select` does three things: update the hash with `history.replaceState`, scroll the transcript row `event-<seq>` into view (`block: 'center'`, `behavior: 'smooth'`, or `'auto'` under reduced motion), and move the Highlight to that row. If the transcript is in "Messages" mode and the target is not a message, switch to "All events" first. Every `[seq]` anywhere on the page (`SeqAnchor`) calls `select`. Selecting an event also highlights its counterpart: the Tools tab item whose call or result seq matches, and State tab entries caused by it get `data-related="true"` (a left border in `--ring`).

**Region mapping:**

| Region | Component | Props / behaviour |
|---|---|---|
| Breadcrumb, Prev / Next | `PageHeader`, Button with `chevron-left` / `chevron-right` | order = `GET /v1/runs/{id}/episodes` order; keyboard `[` and `]` (react-hotkeys-hook) |
| Title row | `OutcomeBadge`, Badge (termination), `Money`, `CopyId` | turns = count of `user_message` events; duration = sum of `wall_ms`; outcome and termination from `episode_ended` payload or the episode row |
| Goal line | text, Collapsible for long goals | from the scenario |
| Transcript container | Scroll Fade + Highlight (`controlledItems`, `parent` mode, click false) | Highlight value = `selectedSeq`. Not virtualised (episodes are tens to low hundreds of events); if events exceed 400, use TanStack Virtual |
| Mode switch | Toggle Group (single) "Messages / All events" | default All events. Messages = `user_message` and `agent_message` only |
| Row (`TranscriptRow`) | `HighlightItem` + `SeqAnchor` + actor Badge + body | `id="e-<seq>"`, `data-testid="event-<seq>"`, grid `auto auto 1fr`. Arriving rows (live) wrap in Fade |
| `user_message`, `agent_message` body | plain text, `whitespace-pre-wrap`; Highlight Text for a matched evidence quote | text from `payload.text`. Not markdown-rendered (show exactly what was said) |
| `tool_call` body | `font-mono` tool name + inline one-line args preview + `RiskBadge` (when the tool's risk is known) + Collapsible `JsonBlock` (args) | `payload.tool`, `payload.args`, `payload.via` as a small Badge |
| `tool_result` body | ok / error icon + `wall_ms` + "n changes" Button (opens State tab filtered to this seq) + Collapsible `JsonBlock` (result) | `payload.ok`, `payload.error`, `payload.patch.length`; error text in destructive |
| `fault_injected` body | Badge warning + fault `kind` and `tool` | from `payload.fault` |
| `episode_started`, `sim_note`, `check_result`, `verdict`, `episode_ended` | muted one-line summary + Collapsible `JsonBlock` | `episode_ended`: outcome, termination, detail. Others: generic JSON (shapes not in the contract, CQ-W9) |
| Origin marker | Badge outline "untrusted" + Tooltip (source, markers) | when `origin.trust === 'untrusted_external'` |
| Cost / latency | Tooltip on the row's right edge | `cost.usd_micros`, tokens, `model`, `wall_ms` |
| Right pane | Base UI Tabs with count Badges | value in `?tab=` |
| Verdicts tab | `VerdictList`: Toggle Group filter (All / Fail / Pass / Other), then `VerdictCard`s | sort: fail hard first, then fail by severity, error, pass, na |
| `VerdictCard` | shadcn Card + `VerdictBadge` + `SeverityBadge` + Badge "hard fail" + Badge stage (`rule` / `small` / `strong` / `human`) + Collapsible (reasoning) + evidence list | header: `criterion`, `evaluator`. Meta line: stage, `model`, confidence as `0.93`, cost `Money`. `data-testid="verdict-card"`. Arriving live: Fade inside Auto Height |
| Evidence item | Button (ghost, full width, left aligned) containing `SeqAnchor` + quote in quotes + `note` muted | `data-testid="evidence-quote"`. Click: `select(seq, quote)`. Active item gets `aria-pressed` |
| Tools tab (`ToolTimeline`) | Accordion (multiple) items, one per tool call | built by pairing `tool_call` and `tool_result` on `payload.call_id`. Trigger row: `wall_ms` of the result, tool name, `RiskBadge`, ok / error / pending icon, `SeqAnchor` for call and result. Content: `JsonBlock` args, result, patch. Fault events render between items as a warning row. A proportional duration bar: Progress with value = this call's `wall_ms` / max `wall_ms` |
| State tab (`StateDiff`) | Accordion (multiple, all open) per collection; header has count Badges `+a −r ~c` | entries from `diff-entries.ts`. Each entry: kind icon (`plus` success, `x` destructive, `refresh-cw` info), record id `font-mono`, `SeqAnchor` to the causing event, `data-testid="diff-entry"`. added / removed: Collapsible `JsonBlock` of the record. changed: table of `path: old → new`, old in muted strike-through, new in foreground |
| State empty | `EmptyState` | "The agent changed nothing in the world." (and, for black-box targets with no tool events, "No world state for this target type.") |

**Evidence quote highlighting** (`quote-match.ts`): `findQuote(text, quote): { start, end } | null`. Normalise both sides the same way the judge validator does (contract D4, hard-cores 5.2): lower-case, collapse whitespace runs to one space, map curly quotes to straight. Search on the normalised text, then map the match back to original offsets (keep an index map while normalising). On a hit, split the row text into before / match / after and render the match with Animate UI Highlight Text (`transition` about 0.4s) plus `<mark>` semantics; it stays highlighted until another selection. On a miss (tool events, truncated results, `quote: null`), highlight the whole row only. Never show "quote not found" to the user; the row highlight is the fallback.

**State diff data** (`diff-entries.ts`): view model `DiffEntry { collection, id, kind: 'added' | 'removed' | 'changed', seq, record?, changes?: { path, before, after }[] }`.
1. If the generated episode type has a server-computed state diff (compacted, with causing seq, per hard-cores 2.2), map it directly. This is the intended source (CQ-W8).
2. Otherwise build from the journal: for each `tool_result` event with `payload.patch`, each `PatchOp` becomes an entry with `seq` = that event's seq: `add` → added (`value`), `remove` → removed (`before`), `replace` → changed, with `changes` = shallow-then-recursive comparison of `before` and `value` producing dotted paths, lists reported whole. Do not compact across events in the fallback (an add then a remove shows as two entries, each linked to its own event); label the tab "State changes" instead of "State diff" in this mode.
Group by collection, order by seq.

**Live** (episode not `done`): `useRunStream(runId, { focusedEpisodeId })`; new rows and verdict cards fade in; a `LiveStatusText` line at the bottom of the transcript ("Running"); header shows `EpisodeStatusBadge` instead of the outcome. When the episode ends, the stream is dropped and the outcome badge replaces the status.

**States:** loading (header skeleton, 8 skeleton transcript rows, 3 skeleton cards); empty transcript (queued episode: `EmptyState` "This episode has not started"); no verdicts ("No verdicts yet" while running; "No evaluators ran" when done); error (`ErrorState` full pane; 404 → "Episode not found" with link to Runs); bad hash (`#e-999` not present: ignore, no error).

**Unit tests (write first):**
- `quote-match.test.ts`: exact hit; case and whitespace differences; curly vs straight quotes; offsets map back correctly on text with multiple spaces and newlines; miss returns null; empty or null quote returns null.
- `diff-entries.test.ts`: add / replace / remove ops map to kinds with the right seq; nested path changes (`address.city`); list change reported whole; grouping and ordering; server diff path used when present.
- `selection.test.ts`: `select` sets hash and state; initial hash restores selection; unknown seq ignored.

**Playwright `episode-viewer.spec.ts`** (uses `seeded.failedEpisode()`):
- "episode viewer: shows seeded data": `<h1>` visible; outcome badge text "Failed"; `event-0` and at least one `user_message` and `agent_message` row visible; at least one `verdict-card`; Tools tab shows at least one `timeline-item-*`; State tab shows at least one `diff-entry`; screenshot.
- "episode viewer: evidence scrolls to and highlights the cited event": click the first `evidence-quote`; read its seq; assert URL hash is `#e-<seq>`, `event-<seq>` is in the viewport and has `data-selected="true"`; if the cited event is a message, a `mark` inside it contains the quote text (compare normalised).
- "episode viewer: diff entry links to its causing event": open State tab, click the `SeqAnchor` in the first `diff-entry`, assert `event-<seq>` in viewport, selected, and it is a `tool_result` row.
- "episode viewer: deep link restores selection": goto `/episodes/<id>#e-3`, assert `event-3` selected and in viewport.
- "episode viewer: not found": route-mock 404 envelope, assert "Episode not found".

**Steps:**
- [ ] Load the `animate-ui` skill. Regenerate API types (`gen:api`), read the episode, run and report types in `schema.d.ts`, and list every region in this task whose data is missing. Report those; build the rest.
- [ ] Write the three unit test files; see them fail. Implement `quote-match.ts`, `diff-entries.ts`, `selection.ts`, `payloads.ts` until green.
- [ ] Write `episode-viewer.spec.ts`; see it fail. Build `Transcript` and `TranscriptRow`, then `VerdictCard` / `VerdictList`, then `ToolTimeline`, then `StateDiff`, then the page. Green.
- [ ] Verify the episode viewer in a real browser (conventions section 10). Specifically check by eye: clicking evidence scrolls and highlights; long tool results stay collapsed; 1024px width; reduced motion. Screenshot. Commit `feat(web): episode viewer`.
- [ ] Write `run-console.spec.ts`; fail; build hooks, `RunHeader`, `RunControls`, `EpisodeTable`, `LiveEpisodePanel`, the page. Green. Browser-verify, including one real live run if the stack can run one with `FakeLLM` or a cassette (otherwise the mocked-stream test is the proof; say which in the report). Commit `feat(web): run console`.
- [ ] Write `run-report.spec.ts` and `runs.spec.ts`; fail; build; green; browser-verify; commit `feat(web): run report and runs list`.
- [ ] Add "Runs" data to the sidebar if not present. Full gate: `pnpm --filter web lint && pnpm --filter web typecheck && pnpm --filter web test && pnpm --filter web e2e && pnpm --filter web audit`.

**Done when:** all four specs and three unit files pass; in the seeded failed episode, clicking each evidence quote selects and scrolls to the right `[seq]` row and highlights the quote when it is in a message; every state-diff entry links to a `tool_result` event; the console reflects a mocked stream within one throttle window; no hand-written API types; screenshots of all four screens attached; omitted regions and contract questions listed in the report.

---

### P1-13: Onboarding wizard, agent overview, scenario list and viewer

**Batch:** f. **Depends:** P1-12 (and P1-14 for the run hooks and the redirect target).

**Files:**
- `apps/web/src/app/(app)/onboarding/page.tsx`
- `apps/web/src/app/(app)/agents/page.tsx`, `agents/[agentId]/page.tsx`
- `apps/web/src/app/(app)/scenarios/page.tsx`, `scenarios/[scenarioId]/page.tsx`
- `apps/web/src/lib/api/hooks/agents.ts`, `scenarios.ts` (extend), `suites.ts`, `worlds.ts`, `runs.ts` (add `useCreateRun`, `useRunEstimate`)
- `apps/web/src/components/onboarding/wizard.tsx`, `step-agent.tsx`, `step-target.tsx`, `step-scenarios.tsx`, `step-run.tsx`, `wizard-schema.ts`
- `apps/web/src/components/agents/agent-table.tsx`, `profile-card.tsx`, `target-card.tsx`, `tool-inventory.tsx`, `latest-runs-card.tsx`, `start-run-dialog.tsx`
- `apps/web/src/components/scenarios/scenario-table.tsx`, `scenario-summary.tsx`, `check-tree.tsx`, `scenario-json.tsx`
- Tests: `apps/web/src/components/onboarding/wizard-schema.test.ts`, `apps/web/src/components/scenarios/check-tree.test.tsx`
- E2E: `apps/web/e2e/onboarding.spec.ts`, `agents.spec.ts`, `agent-overview.spec.ts`, `scenarios.spec.ts`, `scenario-viewer.spec.ts`
- Delete `apps/web/src/app/(app)/_kit/` at the end.

**Interfaces:**
- Consumes: `GET/POST /v1/projects`, `GET/POST /v1/agents`, `GET/POST /v1/agents/{id}/versions`, `POST /v1/agents/{id}/generate-scenarios`, `GET /v1/scenarios`, `GET /v1/scenarios/{id}`, `GET/POST /v1/suites`, `POST /v1/runs` (and `?dry_run=true`), `GET /v1/runs`, `GET /v1/worlds` and `GET /v1/worlds/{id}` (CQ-W4). Types: `AgentVersion`, `AgentProfile`, `HostedTargetConfig`, `OpenAICompatTargetConfig`, `HttpTargetConfig`, `Scenario`, `NamedCheck`, `Check`, `Suite`, `ToolSpec`, `WorldSpec`.
- Produces hooks: `useAgentList`, `useAgent`, `useAgentVersions`, `useCreateAgent`, `useCreateAgentVersion`, `useGenerateScenarios`, `useScenarioList`, `useScenario`, `useSuiteList`, `useCreateSuite`, `useWorldList`, `useWorld`, `useCreateRun`, `useRunEstimate`.
- Produces components: `Wizard`, `AgentTable`, `ProfileCard`, `TargetCard`, `ToolInventory`, `LatestRunsCard`, `StartRunDialog`, `ScenarioTable`, `ScenarioSummary`, `CheckTree`, `ScenarioJson`.

**Decisions:**
- Scenario screens are read-only in Phase 1: list, filter, view. No editor, no version history, no YAML (JSON only, no extra dependency).
- The wizard creates real records at each step (no client-side draft store). Going back edits by creating a new agent version, never by mutating. Wizard progress is in the URL (`?step=2&agent=<id>&version=<id>&suite=<id>`) so a reload resumes.
- Target kinds offered: `hosted` (default, recommended label), `openai_compat`, `http`. `wired` is a Switch on the two remote kinds (contract field `wired: bool`). Secrets: `api_key_secret` is a Select of existing secret names only if a secrets list route exists in the schema; otherwise a plain Input for the secret name with helper text "create it with the CLI" (CQ-W16).
- Scenario source in the wizard: Toggle Group "Use a pack suite | Generate from profile". Pack path lists `GET /v1/suites`. Generate path calls `POST /v1/agents/{id}/generate-scenarios`; the drafts are shown for selection. Approval of drafts is done only if the schema has a way to do it (CQ-W12); otherwise the selected drafts go into the suite as they are.
- Budget input is dollars in the form, converted to integer micro-dollars before sending. Default budget $2.00, repetitions 1.
- Agent overview shows only what Phase 1 can back: profile, target, tool inventory, recent runs. No findings or coverage cards (Phase 2 adds them).
- Tool inventory source: the world of the most recent run's first scenario (scenario `world` is an id → `GET /v1/worlds/{id}`, or an inline `WorldSpec`), filtered by `HostedTargetConfig.tools` when not null. No run yet: empty state (CQ-W13).

#### Screen: Onboarding wizard — `/onboarding`

Purpose: from nothing to a first running suite in under 10 minutes. API per step below.

```
<h1> Set up your first agent
[ 1 Agent ]—[ 2 Target ]—[ 3 Scenarios ]—[ 4 Run ]        [=====>        ] step 2 of 4
+---------------------------------------------------------------------------+
| Step 2: How should Gauntlet reach it?                                     |
| ( Hosted ✓ recommended | OpenAI-compatible | HTTP )                       |
|  Model            [ select / input            ]                           |
|  System prompt    [ textarea, mono, 10 rows   ]                           |
|  Temperature      [—o————] 0.0                                            |
|  World            [ ecommerce ▾ ]  6 tools: get_order read, issue_refund… |
|                                                   [ Back ]   [ Continue ] |
+---------------------------------------------------------------------------+
```

| Step | Fields (contract model) | API on Continue |
|---|---|---|
| 1 Agent | name; `AgentProfile`: purpose, audience, policies_text (Textarea), forbidden_behaviors (one per line), languages | `POST /v1/projects` only if none exists; `POST /v1/agents` |
| 2 Target | hosted: model, system_prompt, temperature, tools (all, or pick from the chosen world). openai_compat: base_url, model, api_key_secret, wired. http: url, method, headers, body_template (JSON textarea), reply_path, conversation_id_path, stateful, wired | `POST /v1/agents/{id}/versions` (label `v1`) |
| 3 Scenarios | source toggle; pack: pick a suite. generate: Button "Generate scenarios", then a checklist of drafts (title, goal, tags) | generate: `POST /v1/agents/{id}/generate-scenarios`; then `POST /v1/suites` with the chosen scenario ids (pack path: no call) |
| 4 Run | repetitions, budget; shows estimate | `POST /v1/runs?dry_run=true` on entering the step and on field change (debounced 500ms); `POST /v1/runs` on Start → redirect `/runs/<id>` |

| Region | Component | Props / behaviour |
|---|---|---|
| Step indicator + panel | `Stepper` (Base UI Tabs controlled + Progress + Auto Height) | step from `?step=` |
| Target kind, scenario source | Toggle Group (single) | |
| Inputs | shadcn Input, Textarea, Label, Select, Combobox (model, world), Slider (temperature, step 0.1), Switch (wired, stateful), Checkbox (tool subset, draft selection) | react-hook-form + zod per step (`wizard-schema.ts`); errors inline in Auto Height |
| World preview | Hover Card or inline list of tool name + `RiskBadge` | from `GET /v1/worlds/{id}` |
| Generating | `LiveStatusText` "Generating scenarios" + Skeleton rows | while the mutation is pending; no fake progress |
| Draft list | `DataTable` with Checkbox selection, select all | default all selected |
| Estimate | `StatCard` (estimated cost `Money`, episodes = scenarios × repetitions) | from the dry-run response; warning text if estimate exceeds budget and Start disabled |
| Nav | Button Back (ghost), Continue / Start run (primary) | disabled while pending |

States: loading (worlds, suites: Skeleton in the control); empty (no worlds or no pack suites: that option disabled with Tooltip explaining; generate returns zero drafts: `EmptyState` "Nothing generated. Add more detail to the profile." action Back to step 1); error (step mutation fails: toast + stay on the step with values kept; dry-run fails: inline error in the estimate card with the API message, which is how validation problems surface).

Playwright `onboarding.spec.ts`: "onboarding: completes the pack path": fill step 1, choose Hosted with seeded world and a model string, pick the seeded pack suite, set budget, assert estimate visible, with `POST /v1/runs` route-mocked to return a run id (no real run is started in tests), click Start, assert navigation to `/runs/<id>`. "onboarding: validates required fields": Continue on empty step 1 shows inline errors and makes no request.

#### Screen: Agents list — `/agents`

Purpose: pick an agent. API: `GET /v1/agents`. `DataTable` (name, purpose truncated, created); header action Button "New agent" → `/onboarding`. Empty: `EmptyState` "No agents yet" action "Set up your first agent". Playwright `agents.spec.ts` "agents: shows seeded data": seeded agent name visible; row click → `/agents/<id>`.

#### Screen: Agent overview — `/agents/[agentId]`

Purpose: what this agent is, what it can touch, how it did lately. API: `GET /v1/agents/{id}`, `GET /v1/agents/{id}/versions`, `GET /v1/runs` (filtered to this agent's versions client-side), `GET /v1/scenarios/{id}` + `GET /v1/worlds/{id}` for the tool inventory, `GET /v1/suites` + `POST /v1/runs` in the start dialog.

```
Agents > support-agent
<h1> support-agent      [ version: v3 ▾ ]                       [ Start run ]
+-------------------------------+---------------------------------------------+
| PROFILE                       | TOOLS (6)                    by risk ▾      |
| Purpose  ...                  | issue_refund    financial     python        |
| Audience ...                  | send_email      external_comm crud          |
| Languages en, es              | cancel_order    destructive   crud          |
| Policies ▸  Forbidden ▸       | get_order       read          crud          |
+-------------------------------+---------------------------------------------+
| TARGET  hosted · model · temp | RECENT RUNS                                 |
| System prompt ▸               | Finished  ecommerce-core  81%  $1.92  2h →  |
+-------------------------------+---------------------------------------------+
```

| Region | Component | Props / behaviour |
|---|---|---|
| Version picker | Select | URL `?version=`; default latest |
| Profile | `ProfileCard`: shadcn Card + Collapsible (policies_text, forbidden_behaviors) | |
| Target | `TargetCard`: Card + Badge (kind, wired) + Collapsible (`system_prompt` in `<pre>`, or URL / reply_path for remote) | never shows secret values, only the secret name |
| Tools | `ToolInventory`: `DataTable` (name mono, `RiskBadge`, handler kind, Badge "untrusted output", Badge "honeytool") sorted by risk; description in Hover Card | source per Decisions |
| Recent runs | `LatestRunsCard`: up to 5 rows, `RunStatusBadge`, pass rate if the run or report exposes it, `Money`, link | |
| Start run | `StartRunDialog`: Dialog + Select (suite) + Input (repetitions, budget) + estimate (dry run) + Button | same logic as wizard step 4; success → `/runs/<id>` |

States: loading (four `LoadingCard`); empty tools ("Run a suite to see the tool inventory"), empty runs ("No runs yet" action Start run); error per card; 404 → "Agent not found". Playwright `agent-overview.spec.ts` "agent overview: shows seeded data": agent name `<h1>`; Profile, Target, Tools, Recent runs headings visible; at least one tool row with a risk badge; a recent run link navigates to the run.

#### Screen: Scenario list — `/scenarios`

Purpose: browse and filter scenarios. API: `GET /v1/scenarios`.

```
<h1> Scenarios                                                    128
[ All | Approved | Draft ]  [ source ▾ ] [ tag ▾ ] (🔍 search title or goal)
| Title | Persona | Tags | Source | Status | v | Security |
```

| Region | Component | Props / behaviour |
|---|---|---|
| Filters | `FilterBar`: Toggle Group (status), Select (source: pack, generated, mined, pinned), Combobox (tag key:value from loaded rows), Input | URL query; client-side until CQ-W3 |
| Table | `DataTable` | Tags as Badges (max 3, "+n" in Tooltip); Security column shows `shield-check` when `attack` is set; row click → viewer |
| Count | `LiveNumber` (not live; static) | filtered count |

States: loading; empty ("No scenarios. Generate a starter suite from an agent."); filtered-empty; error. Playwright `scenarios.spec.ts` "scenarios: shows seeded data": rows visible; typing a seeded title fragment narrows rows; the Draft filter shows only rows with a Draft badge.

#### Screen: Scenario viewer — `/scenarios/[scenarioId]`

Purpose: read one scenario exactly as the engine will run it. API: `GET /v1/scenarios/{id}`; `GET /v1/worlds/{id}` when `world` is an id.

```
Scenarios > refund-outside-window
<h1> refund-outside-window   v2  approved  pack          [ Summary | JSON ]
+------------------------------------+------------------------------------+
| GOAL  ...                          | SUCCESS (must hold)                |
| PERSONA impatient-customer         | all                                |
|   overrides: patience 0.2          |  ├ tool_called issue_refund max 0  |
| OPENING "..." / written by sim     |  └ output contains "30 days"       |
| HIDDEN FACTS (3) ▸                 | FORBIDDEN                          |
| MAX TURNS 12   TAGS ...            |  high  refund_issued  ▸ check      |
| WORLD ecommerce · 6 tools ▸        | RUBRICS policy_adherence, tone     |
+------------------------------------+------------------------------------+
```

| Region | Component | Props / behaviour |
|---|---|---|
| View switch | Base UI Tabs "Summary / JSON" | `?view=` |
| Summary left | shadcn Card sections, Collapsible (hidden facts, world tools), Badges (tags) | hidden facts collapsed by default with label "not shown to the agent or the judge" |
| `CheckTree` | nested Collapsible rows, Badge for node `type`, mono summary per node | recursive renderer over the `Check` union (contract section 4): `all` / `any` / `not` / `sequence` are branches; leaves render a one-line summary of their fields. Unknown `type` → `JsonBlock`. Exhaustive `switch` on the generated union |
| Forbidden | list: `SeverityBadge`, id, description, Collapsible `CheckTree` | |
| Rubrics | Badges | ids only in Phase 1 |
| Attack | Card with `shield-check`, shown only if `attack` is set | raw `JsonBlock` in Phase 1 |
| JSON | `CodeView` (Code Block, lazy) + Copy Button | the scenario document |

States: loading (`LoadingCard` x2); error; 404 "Scenario not found". Unit `check-tree.test.tsx`: renders nested `all` > `not` > `tool_called`; leaf summaries for `tool_called` (tool, count), `state_diff`, `output`; unknown type falls back to JSON. Playwright `scenario-viewer.spec.ts` "scenario viewer: shows seeded data": title `<h1>`, Goal text, "Success" heading with at least one check node, JSON tab shows the scenario id text.

**Steps:**
- [ ] Load the `animate-ui` skill. Regenerate API types; check which CQ-flagged routes exist (`/v1/worlds`, `/v1/agents`, secrets, scenario approval, dry-run response fields). Report gaps; apply the fallbacks in Decisions.
- [ ] Unit tests first: `wizard-schema.test.ts` (per-step zod: required fields, URL validity, dollars → micros conversion is integer, `body_template` must parse as JSON), `check-tree.test.tsx`. Fail, implement, green.
- [ ] Scenario list and viewer: write the two specs, fail, build, green, browser-verify, commit `feat(web): scenario list and viewer`.
- [ ] Agents list and overview: specs, fail, build, green, browser-verify, commit `feat(web): agent overview`.
- [ ] Wizard: spec, fail, build step by step, green. Browser-verify by really completing the pack path once against the stack up to the dry-run estimate; screenshot each step. Commit `feat(web): onboarding wizard`.
- [ ] `(app)/page.tsx` redirect: zero agents → `/onboarding`, else `/agents`. Delete `_kit`. Full gate including `audit`.

**Done when:** five specs and two unit files pass; a new user with an empty project can reach a run console from `/onboarding` using only the UI (pack path); the scenario viewer renders every `Check` type present in the seeded e-commerce pack without falling back to raw JSON; screenshots of all five screens attached; omitted regions and contract questions listed.

---

## Contract questions (Phase 1 web)

Cross-cutting questions CQ-W1 to CQ-W7 are in `web-conventions.md`.

| ID | Question |
|---|---|
| CQ-W8 | `GET /v1/episodes/{id}`: exact response shape. Field names for events and verdicts; does it embed the scenario (title, goal, `max_turns`), the run id, `attempt`; does it include the computed state diff (`Trajectory.diff()`, with the causing `seq` per entry) and/or `initial_world` and `final_world`? The JSON shape of `StateDiff` exists only as prose in hard-cores 2.2. Does the route return partial events for an episode still running? Without a server diff the viewer shows the uncompacted patch log from `tool_result.payload.patch`. |
| CQ-W9 | Payload shapes for `episode_started`, `sim_note`, `check_result` and `verdict` events are not defined in contracts section 2. They render as generic JSON. |
| CQ-W10 | `GET /v1/runs/{id}/report`: response shape. The report screen needs: suite pass rate with interval, counted and excluded episode counts by outcome, per-scenario trials / rate / interval, per-rubric (dimension) pass, fail, na and error counts with severity, total cost, the self-preference caution flag, and `world_fidelity`. |
| CQ-W11 | `POST /v1/runs`: exact body field names, the name and unit of the cost estimate in the response, and what `?dry_run=true` returns (estimate, validation errors per scenario). |
| CQ-W12 | `POST /v1/agents/{id}/generate-scenarios`: request body (count, world id, persona set), synchronous or a job, response shape. How a `draft` scenario becomes `approved` (no route or field is defined). How scenarios and suites are scoped to a project or agent. |
| CQ-W13 | `AgentVersion` has no reference to a world, so the agent overview cannot list the tool inventory with risk labels directly, and the episode viewer cannot show a tool's risk beside a `tool_call` (the payload has only the tool name). Is there a link (agent version → world, or risk echoed on the event)? |
| CQ-W14 | Agent overview in the vision shows latest scores, open findings and coverage. There is no aggregate route; "latest run for this agent" needs a runs filter (CQ-W3). Phase 1 shows recent runs only. |
| CQ-W15 | Episode actions from the vision ("add to regression suite", "mark as simulator error") have no route. `POST /v1/episodes/{id}/rejudge` is in contracts section 9 but its implementation is roadmap task P3-3. Phase 1 web ships none of the three; confirm. |
| CQ-W16 | Secrets: is there `GET/POST /v1/secrets`, and what is the create body? OpenAPI import to tools (P1-7) has no API route, so the wizard cannot offer "upload an OpenAPI file". |
| CQ-W17 | Contracts section 1 lists the target union as `hosted | openai_compat | http | wired` but defines three config classes, with `wired` as a boolean on the two remote ones. The wizard treats wired as that flag. Confirm. |
