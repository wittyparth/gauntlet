# Web conventions (apps/web)

Applies to every web task: P1-12, P1-13, P1-14, P2-10, P3-7, P3-8, P4-6. Read this file before the phase file.

**Before any UI work, load the `animate-ui` skill (Skill tool) and read its `references/catalog.md`.** Every element maps to a named Animate UI item or the shadcn base it installs. No hand-built primitives, no other UI kit. If nothing fits, compose the primitives named here; if that fails, stop and report to the lead.

Also read `docs/plan/README.md` and `docs/plan/02-contracts.md` (sections 2, 5, 6, 8, 9). Never hand-write an API type. Never call a route or read a field that the generated schema does not contain: stop that part, leave the region out, and report it as a contract question.

## 1. Stack and fixed decisions

| Topic | Decision |
|---|---|
| Framework | Next.js App Router (current stable from `create-next-app`), React 19, TypeScript strict, `src/` dir, Tailwind v4 |
| Components | shadcn/ui on the **Base UI** family, animated by Animate UI v2 (`@animate-ui/react`). One family only; never import Radix or React Aria primitives |
| Theme | Stock shadcn neutral theme, **dark by default** (`next-themes`, `defaultTheme="dark"`, `attribute="class"`). No custom palette. Only additions: the three status tokens in section 3.4 |
| Motion | `AnimateUIProvider tempo={0.9} checkAnimation="draw" reducedMotion="user"`. Motion only for: live values changing, items arriving on a live stream, overlays and menus, selection highlight. No backgrounds, no hero text effects, no Particles, Magnetic, Tilt, Cursor, Click, Shine |
| Data | TanStack Query v5 over `openapi-fetch` + `openapi-react-query`, types from `openapi-typescript` |
| Live | Server-sent events through the Next proxy; REST is the source of truth, SSE only triggers refetch (section 6) |
| Forms | react-hook-form + zod, rendered with shadcn form/field parts of the Base UI style |
| Tables | TanStack Table via shadcn Data Table |
| Charts | Recharts via shadcn Chart; load the `dataviz` skill first (Phase 3 and 4 only) |
| Unit tests | Vitest + Testing Library (`pnpm --filter web test`) |
| E2E | Playwright (`pnpm --filter web e2e`) |
| Package manager | pnpm. Use `pnpm dlx` wherever the skill shows `npx` |

Density rules: base text `text-sm`, table rows 36px, page padding `p-4`, cards `p-3`, monospace (`font-mono`) for IDs, `[seq]` anchors, tool names, JSON and money. One `<h1>` per page, visible on first paint (never wrapped in an entrance effect).

## 2. Folder layout

```
apps/web/
  package.json            scripts: dev, build, start, lint, typecheck, test, e2e, gen:api
  components.json         shadcn config, Base UI style, @animate-ui registry
  playwright.config.ts
  vitest.config.ts
  .env.example            GAUNTLET_API_URL=http://localhost:8000
  e2e/
    fixtures.ts           test fixture: logged-in page, console-error guard, seeded-id helpers
    global-setup.ts       logs in once, saves storageState
    <screen>.spec.ts      one file per screen
  src/
    app/
      layout.tsx          html.dark, fonts, <Providers>
      providers.tsx       'use client': ThemeProvider, AnimateUIProvider, QueryClientProvider, Toast provider, TooltipProvider
      globals.css         shadcn tokens + status tokens
      login/page.tsx
      api/session/route.ts            POST set key cookie, DELETE clear
      api/gauntlet/[...path]/route.ts proxy to the API (adds Bearer), streams SSE
      (app)/
        layout.tsx        server: cookie check -> redirect /login; renders <AppShell>
        page.tsx          redirect: no agents -> /onboarding, else /agents
        onboarding/page.tsx                       P1-13
        agents/page.tsx                           P1-13
        agents/[agentId]/page.tsx                 P1-13
        scenarios/page.tsx                        P1-13
        scenarios/[scenarioId]/page.tsx           P1-13
        runs/page.tsx                             P1-14
        runs/[runId]/layout.tsx                   P1-14 (run header)
        runs/[runId]/page.tsx                     P1-14 (console)
        runs/[runId]/report/page.tsx              P1-14
        episodes/[episodeId]/page.tsx             P1-14
        findings/..., security/...                P2-10
        runs/[runId]/compare/page.tsx, review/..., rubrics/..., agents/[agentId]/scorecard/...   P3-7, P3-8
        gateway/...                               P4-6
    components/
      ui/                 shadcn components (generated, then `animate all`). Never edit by hand except sidebar.tsx per the Animate UI Sidebar doc
      animate-ui/icons/   animated icons added from the registry
      shared/             shared app compositions (section 4)
      <feature>/          feature compositions: onboarding/, agents/, scenarios/, runs/, episode/, findings/, review/, gateway/
    lib/
      api/schema.d.ts     GENERATED, committed, never edited
      api/client.ts       openapi-fetch client + $api (openapi-react-query)
      api/hooks/*.ts      named hooks per resource
      api/errors.ts       ApiError, error envelope parsing
      sse/use-run-stream.ts, sse/adapter.ts
      format.ts           formatUsd, formatDuration, formatPercent, shortId
      query-keys.ts
```

Rules: pages are thin client components that call hooks and compose `components/<feature>`. Server components are used only for layouts and the auth redirect. A file over about 300 lines gets split. Feature folders do not import from each other, except everything may import `components/episode/transcript` (the run console reuses it) and `components/shared`.

## 3. Animate UI setup (P1-12 executes this once)

Run from `apps/web`. Do not guess CLI flags: run each tool with `--help` first if a prompt differs from what is described.

1. `pnpm dlx shadcn@latest init`: choose the **Base UI** base, base colour **Neutral**, CSS variables on, Tailwind v4.
2. `pnpm add @animate-ui/react motion @base-ui/react next-themes`
3. Add to `components.json`: `"registries": { "@animate-ui": "https://animate-ui.com/r/{name}.json" }`
4. Add shadcn components (one command, list may be split):
   `pnpm dlx shadcn@latest add button card badge separator skeleton input textarea label breadcrumb table scroll-area dialog alert-dialog sheet dropdown-menu select combobox popover tooltip hover-card tabs toggle toggle-group accordion collapsible checkbox switch radio-group slider progress pagination sidebar toast resizable`
   If the Base UI style names the toast component differently, use the Base UI Toast it offers; do not install `sonner`.
5. `pnpm dlx @animate-ui/cli@latest animate all --dry-run`, review, then `pnpm dlx @animate-ui/cli@latest animate all`. Re-run after every later `shadcn add` (idempotent). Needs Node 22.12+.
6. Sidebar: follow https://animate-ui.com/docs/primitives/base-ui/sidebar (add shadcn sidebar, `animate sheet tooltip`, build `ui/sidebar.tsx` on `@animate-ui/react/primitives/sidebar`).
7. Animated icons (Lucide set only), one command per icon: `pnpm dlx shadcn@latest add @animate-ui/icons-lucide-<name>`. Phase 1 set: `layout-dashboard bot list play pause shield-check settings circle-check circle-x circle-alert triangle-alert loader-circle clock timer copy chevron-down chevron-right search list-filter refresh-cw external-link log-out terminal file-text gavel flag message-square layers gauge zap plus x info`. Import from `@/components/animate-ui/icons/<name>`. Icons with no animated version (see catalogue section 3.2): plain `lucide-react`, same size and stroke.
8. Theme toggle: `pnpm dlx shadcn@latest add @animate-ui/buttons-theme-toggler` (lives in the account menu).
9. Provider order in `providers.tsx`: `ThemeProvider` > `AnimateUIProvider` > `QueryClientProvider` > `TooltipProvider` > Toast provider > children.
10. Add `"audit": "pnpm dlx @animate-ui/cli@latest audit src"` and run it before each commit that touches UI.

Imports: library primitives through `@/components/ui/<name>`; Animate UI own primitives straight from the package, per-primitive path, for example `@animate-ui/react/primitives/texts/sliding-number`, `.../texts/shimmering`, `.../texts/highlight`, `.../effects/fade`, `.../effects/auto-height`, `.../effects/scroll-fade`, `.../effects/highlight`, `.../buttons/copy`, `.../buttons/button`. Custom transitions use `spring`, `ease`, `useTempoTransition` from `@animate-ui/react/utils/motion`.

Tabs: use the Base UI Tabs (`@/components/ui/tabs`) everywhere. Do not use Animate UI's own sliding Tabs. Tooltip: Base UI Tooltip only.

### 3.4 Status tokens

Added to `globals.css` under `:root` and `.dark`, mapped in `@theme inline` as `--color-success`, `--color-warning`, `--color-info`. Pick values with the `dataviz` skill's validator against the dark background. `--destructive` (stock) is the fail colour. Status is never colour alone: always icon plus text label.

| Meaning | Token | Icon | Used for |
|---|---|---|---|
| pass / ok / verified | `success` | `circle-check` | outcome `passed`, verdict `pass`, tool `ok: true` |
| fail / critical | `destructive` | `circle-x` | outcome `failed`, verdict `fail`, severity critical and high |
| excluded / caution | `warning` | `triangle-alert` | outcomes `invalid_scenario`, `simulator_error`, `target_error`, `platform_error`, `budget_exhausted`; verdict `error`; severity medium; faults |
| neutral info | `info` / `muted-foreground` | `info` | verdict `na`, severity low, queued |
| in progress | `foreground` | `loader-circle` (animate, loop) | leased episodes, running runs |

## 4. Shared component inventory (`src/components/shared`)

P1-12 builds all of these. Later tasks reuse; they do not create variants.

| Shared piece | Animate UI / shadcn item | Behaviour |
|---|---|---|
| `AppShell` | Sidebar (Base UI, animated trigger, shared highlight), `SidebarInset` | Collapsible to icons, state in cookie, Cmd/Ctrl+B. Nav groups: Test (Agents, Scenarios, Runs), Security (Phase 2), Quality (Phase 3), Gateway (Phase 4). Later-phase items are added by their tasks, not stubbed |
| `AccountMenu` | Dropdown Menu + Theme Toggler Button | Footer of sidebar: project name, theme toggle, Sign out |
| `PageHeader` | shadcn Breadcrumb + Button | Props: `title`, `breadcrumbs`, `actions`. Holds the page `<h1>` |
| `DataTable` | TanStack Table + shadcn Table, Checkbox (selection), Dropdown Menu (column and row actions), Pagination | Props: `columns`, `data`, `onRowClick`, `emptyState`, `isLoading`. Row hover uses Highlight (`hover`, `parent` mode). Sticky header. Keyboard: rows are links |
| `FilterBar` | Toggle Group (single) for status facets, Input with `search` icon, Select / Combobox for the rest | State lives in the URL query string |
| `OutcomeBadge`, `VerdictBadge`, `SeverityBadge`, `RiskBadge`, `RunStatusBadge`, `EpisodeStatusBadge` | shadcn Badge + animated icon | Mapping in 3.4. `RiskBadge`: read=muted, write=info, destructive / financial / external_comm=warning outline. Enum values come from the generated types (exhaustive `switch`, `never` check) |
| `LiveNumber` | Sliding Number | Props: `value`, `decimalPlaces`. Used for counts and cost that change over SSE. `initiallyStable` so it does not roll on mount |
| `Money` | Sliding Number when `live`, plain text otherwise | Input `usd_micros: number`; `formatUsd` shows `$0.0123` (4 decimals below $1, 2 above). Never floats in state |
| `LiveStatusText` | Shimmering Text | Only while something is in progress ("Running", "Agent is replying") |
| `SeqAnchor` | Button (ghost, `font-mono`, `text-xs`) + Tooltip | Renders `[12]`. Click: select that event (section 7 of phase-1 file). `aria-label="Go to event 12"` |
| `JsonBlock` | Collapsible + shadcn Scroll Area + `<pre>` + Copy Button | Pretty JSON, max height 240px, collapsed above 12 lines. No syntax-highlight dependency |
| `CodeView` | Animate UI Code Block (lazy, `next/dynamic`), `writing` off | Only for whole documents (scenario JSON). Not inside lists |
| `CopyId` | Copy Button + Tooltip | Short prefixed ID (`ep_…k3f9`), copies the full ID |
| `EmptyState` | shadcn Card + static or animated icon + Button | Props: `icon`, `title`, `body`, `action`. Text teaches the next step; one action |
| `ErrorState` | shadcn Card (destructive border) + `circle-alert` + Button "Retry" + Collapsible (error `code`, `message`, `detail`) | Props: `error: ApiError`, `onRetry` |
| `LoadingRows`, `LoadingCard` | shadcn Skeleton, swapped for content inside Fade | Skeleton matches final layout (same row height and count up to 8) |
| `ConfirmDialog` | Alert Dialog | For cancel run, destructive changes. Confirm button names the action ("Cancel run") |
| `toast` helpers | Base UI Toast (`useToastManager`) | `toast.promise` for mutations; errors show the API `message` |
| `Stepper` | Base UI Tabs (controlled; triggers disabled for unreached steps) + Progress + Auto Height | Wizard steps. `TabsList` is the step indicator |
| `StatCard` | shadcn Card + `LiveNumber` / `Money` + Tooltip | Props: `label`, `value`, `hint`, `interval?` (rendered as text `81% (72 to 88)`) |
| `SplitPane` | shadcn Resizable (react-resizable-panels) | Two panes, sizes persisted with `autoSaveId` |

Approved non-Animate-UI libraries (catalogue section 7) and nothing else: TanStack Table, TanStack Virtual, react-hook-form, zod, Recharts (shadcn Chart), react-resizable-panels, cmdk, `diff` (jsdiff), react-markdown + rehype-sanitize, react-hotkeys-hook, next-themes.

## 5. API client

- `gen:api` script: `openapi-typescript ${GAUNTLET_API_URL:-http://localhost:8000}/openapi.json -o src/lib/api/schema.d.ts`. Needs the API running (compose). The output is committed; regenerate at the start of every web task and commit the diff separately (`chore(web): regenerate api types`).
- `client.ts`: `createClient<paths>({ baseUrl: '/api/gauntlet' })` from `openapi-fetch`, plus `$api = createClient(fetchClient)` from `openapi-react-query`. A middleware turns a non-2xx response into `ApiError { status, code, message, detail }` parsed from the contract envelope `{"error": {...}}`; status 401 additionally redirects to `/login`.
- Named hooks in `lib/api/hooks/<resource>.ts` wrap `$api.useQuery` / `$api.useMutation` so pages never see paths. Naming: `use<Resource>List`, `use<Resource>`, `useCreate<Resource>`, verb hooks (`useCancelRun`). Component props use schema types via `components['schemas']['X']` re-exported from `lib/api/types.ts`.
- Query keys from `query-keys.ts`: `['runs']`, `['runs', id]`, `['runs', id, 'episodes']`, `['runs', id, 'report']`, `['episodes', id]`, and so on. Mutations invalidate by these keys.
- Defaults: `staleTime` 30s, `retry` 1 (0 for 4xx), `refetchOnWindowFocus` true. No polling except the fallback in section 6.
- Unknown or untyped JSON (`payload`, `args`, `result`) is `unknown` and goes to `JsonBlock`; narrow with small type guards per event kind in `components/episode/payloads.ts`, using only the shapes in contracts section 2.

## 6. SSE hook: `useRunStream(runId, opts)`

File `lib/sse/use-run-stream.ts`. Consumes `GET /v1/runs/{id}/stream` through `/api/gauntlet/v1/runs/{id}/stream` (same origin, cookie auth, so native `EventSource` works; the proxy pipes the upstream body unbuffered with `Content-Type: text/event-stream`, `Cache-Control: no-cache, no-transform`).

Design: **REST is the truth, SSE is a doorbell.** The contracts name four SSE events but not their payloads, so the hook depends only on the event name.

| SSE event | Action (trailing throttle 400ms per key) |
|---|---|
| `run_update` | invalidate `['runs', runId]` |
| `episode_update` | invalidate `['runs', runId, 'episodes']` and `['runs', runId]` |
| `event`, `verdict` | invalidate `['episodes', focusedEpisodeId]` if `opts.focusedEpisodeId` is set |

- All parsing of `MessageEvent.data` is isolated in `lib/sse/adapter.ts` (`toInvalidations(name, data, opts)`). When the lead locks payload shapes (CQ-W2), only this file changes, for example to patch the cache with `setQueryData` or to skip invalidating episodes other than the one in the payload.
- Returns `{ status: 'connecting' | 'open' | 'reconnecting' | 'closed', lastEventAt }`.
- Lifecycle: opens when `enabled` (run status is not terminal); closes on unmount and when the run reaches a terminal status. On `error`, `EventSource` reconnects by itself; on every re-`open` invalidate all three keys once (catches anything missed). After 3 failed reconnects in a row: status `closed`, and the caller falls back to `refetchInterval: 3000` on the run and episodes queries and shows the "Live updates paused" badge.
- Pauses nothing on hidden tabs (cost and progress must be right when the user returns); TanStack refetch-on-focus covers it.
- Unit test (Vitest, fake `EventSource`): event name to invalidated keys; throttle coalesces a burst of 50 into one refetch per key; reconnect invalidates; closes on terminal status.

Live rendering rule: when a refetch adds items to a list (events, verdicts, episodes), only items not present in the previous render animate in (Fade, 8px, no stagger). First paint never animates lists.

## 7. Auth

Contracts define API-key Bearer auth only. The browser never holds the key in JS.

- `/login`: shadcn Card, Input (password type) "API key", Button. `POST /api/session` (Next route handler) validates the key by calling upstream `GET /v1/projects` with it; on 200 sets cookie `gauntlet_key` (httpOnly, sameSite=lax, secure in production, path=/); on 401 returns the error envelope and the form shows it inline.
- `DELETE /api/session` clears the cookie (Sign out).
- `api/gauntlet/[...path]/route.ts`: forwards method, query, body and `Accept` to `${GAUNTLET_API_URL}/<path>` with `Authorization: Bearer <cookie>`; returns status and body unchanged. No key: 401 envelope. Only paths starting `v1/` are forwarded.
- `(app)/layout.tsx` (server): no cookie, redirect to `/login?next=<path>`.
- `/api/session` and `/api/gauntlet` are Next handlers of the web app, not Gauntlet API routes.

## 8. Loading, empty, error and live states

Every screen implements all four where they apply, and the phase files say what each looks like.

| State | Rule |
|---|---|
| Loading | Skeleton in the final layout (`LoadingRows`, `LoadingCard`). No spinners for page loads. Content replaces skeleton inside Fade. Buttons running a mutation: disabled + `loader-circle` animated + label stays |
| Empty | `EmptyState` with one sentence on what belongs here and one action that creates it. Filtered-to-nothing is a different message ("No episodes match these filters", action "Clear filters") |
| Error | Query error: `ErrorState` in place of the region (not the whole page) with Retry. Mutation error: toast with API `message`; form field errors inline under the field (Auto Height). 404 on a detail page: `EmptyState` "Not found" with a link to the list |
| Live | `LiveStatusText` for the status word, `LiveNumber` / `Money` for counters, Progress for completion, Fade for arriving rows. A "Live" Badge with `radio` or `loader-circle` icon shows stream status; "Live updates paused" (warning) when the stream is closed and polling |
| Partial data | A region whose field is missing from the generated schema is omitted, never faked. Report it |

Accessibility: keep library focus handling; every icon-only button has `aria-label`; live counters sit in an `aria-live="polite"` region updated at most every 5s (a visually hidden summary line, not the rolling digits); reduced motion follows the OS.

## 9. Playwright conventions

- Stack: `docker compose -f infra/docker-compose.yml up -d`, then `uv run gauntlet demo seed`, then `pnpm --filter web e2e`. `playwright.config.ts` starts the web app with `webServer` (`pnpm build && pnpm start`, port 3000) and uses Chromium only, dark colour scheme, viewport 1440x900.
- Login: `global-setup.ts` posts the key from env `GAUNTLET_E2E_API_KEY` to `/api/session` and saves `storageState`. `login.spec.ts` is the only test that starts logged out.
- **No hard-coded IDs.** `fixtures.ts` exposes helpers that find seeded records through the proxy with the logged-in request context: `seeded.run()` (first finished run), `seeded.failedEpisode()`, `seeded.scenario()`, `seeded.agent()`.
- One spec per screen, named `<screen>.spec.ts`, test title `"<screen>: shows seeded data"`. Each asserts: the `<h1>`, the key content listed in the task, no console errors (fixture fails the test on `console.error` or `pageerror`), and takes `await page.screenshot({ path: 'e2e/.screens/<screen>.png', fullPage: true })` (folder is gitignored).
- Extra tests per screen only for: the empty state (route-mocked empty list), one error state (route-mocked 500 with the contract envelope), and live behaviour.
- Live behaviour is tested without a real run or model: `page.route('**/api/gauntlet/v1/runs/*/stream', ...)` fulfils with a scripted `text/event-stream` body, and REST routes are mocked to return the next snapshot. No live LLM calls, ever.
- Selectors: roles and accessible names first. `data-testid` only for repeated structural items: `event-<seq>`, `timeline-item-<seq>`, `diff-entry`, `verdict-card`, `evidence-quote`, `episode-row`, `stat-<name>`.

## 10. Browser verification checklist (every screen, before commit)

1. Stack up and seeded; `pnpm --filter web dev`.
2. Open the screen with Playwright (headed or MCP browser tools). Screenshot at 1440x900 and at 1024x768.
3. Golden path with seeded data: key content visible, numbers plausible, links navigate.
4. Empty state (mock or empty filter), loading state (throttle network or delay the route), one error state (mock 500).
5. Console: zero errors and zero React warnings. Network: no 4xx/5xx on the golden path, no request to anything but `/api/*` and static assets.
6. Keyboard only: tab order sensible, focus ring visible, Esc closes overlays, Enter activates rows.
7. Reduced motion (emulate `prefers-reduced-motion: reduce`): nothing slides or rolls; content still correct.
8. Dark theme is default and correct; toggle to light once and check contrast of status badges.
9. `pnpm --filter web lint && pnpm --filter web typecheck && pnpm --filter web test && pnpm --filter web audit`, then the screen's e2e spec.
10. Look at the screenshot yourself and compare it with the wireframe in the task. Attach the screenshot path in the task report.

## 11. Commit and report

Conventional commits scoped `web`: `feat(web): episode viewer`. One screen per commit where practical. Task report: what was built, gate output, screenshot paths, regions omitted for missing contract fields, contract questions.

## Contract questions (cross-cutting)

| ID | Question |
|---|---|
| CQ-W1 | Architecture D7 says "single admin login" but contracts section 9 defines only API-key Bearer auth and no login, session or whoami route. This plan logs in by pasting an API key, validated with `GET /v1/projects`. Confirm, or define the login route. |
| CQ-W2 | SSE `GET /v1/runs/{id}/stream`: payload shape of `episode_update`, `event`, `verdict`, `run_update` is undefined. Also: are they in the OpenAPI doc, is `Last-Event-ID` resume supported, does the stream close when the run ends, is there a heartbeat. Until answered the web treats every event as an invalidation signal only. |
| CQ-W3 | List routes: pagination, sorting and filter query parameters and the response envelope are undefined. Filters the screens need: episodes by `status` and `outcome`; runs by `agent_version_id`, `suite_id`, `status`; scenarios by `status`, `source`, tag, text; findings by `status`, `severity`, `category`. Until answered, lists fetch the default page and filter client-side. |
| CQ-W4 | "Resource routes follow the table names" but only some are enumerated. Confirm these exist and their methods: `/v1/agents`, `/v1/agents/{id}`, `/v1/worlds`, `/v1/personas`, `/v1/rubrics`, `/v1/secrets`, `/v1/api_keys`, `/v1/suites/{id}`, `/v1/scenarios/{id}`. |
| CQ-W5 | `runs.status` values are not listed (needed for badges and for enabling pause, resume, cancel). Does the run response carry episode counts (total, done, by outcome) or must the web count from the episode list? |
| CQ-W6 | `gauntlet demo seed`: what it creates must include one finished run with passed and failed episodes, at least one episode with tool patches and a judge verdict with evidence, draft scenarios, and one agent with a version. How does e2e obtain an API key (fixed dev key printed by the seed)? Is the seed idempotent? |
| CQ-W7 | Is `/openapi.json` reachable without auth in compose, and does it model the error envelope and the SSE route? |
