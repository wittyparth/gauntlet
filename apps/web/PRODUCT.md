# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- Teams shipping LLM agents (support, SQL, email, copilot, banking agents) who need to know whether an agent works reliably, can be attacked, and can be stopped at runtime before it reaches production.
- Portfolio/showcase viewers (engineers, founders, hiring managers) judging the depth and craft of the work. The landing page serves both (confirmed 2026-11-24).

## Product Purpose

Gauntlet tests, attacks and guards AI agents in one loop: simulate realistic customers against a sandboxed world, red-team the agent with a library of real attacks, turn each confirmed finding into a runtime policy, and verify the fix by replaying the attack. Success: a team can show, with statistics and evidence, that a new agent version is better and safer than the last.

## Positioning

The closed loop is the claim: find (simulation + red team) → fix (policy suggested from the finding, tested offline, enforced at a gateway) → prove (verify run replays the attack; deterministic replay of recorded episodes against new versions; pass^k reliability with confidence intervals). Results are honest: benchmark pages publish unflattering numbers.

## Operating Context

- Web console (Next.js), CLI (`gauntlet scan mcp`, `lint`, `gate`, `mcp pin/diff`, `impact`, `evidence`), MCP server usable from Claude Code and other MCP clients, CI gate with PR comment and badge, OTLP trace ingest from production.
- Self-hosted: single-VPS Docker Compose with Caddy (Oracle free tier ARM, Hetzner, Coolify, Dokploy).

## Capabilities and Constraints

- Testing: scenarios, personas, simulated users, judges, run reports with cited evidence, per-role model picker.
- Regression: baseline compare and flips, pass^k reliability, failure clusters, agent_live replay of a recorded episode against a new version, migration report.
- Quality: blind review queue, rubric calibration (states "not calibrated, cannot gate" when kappa is low).
- Security: 297-attack library, campaigns, findings with SARIF export, posture and coverage, MCP scanning and tool pinning (rug-pull detection).
- Guard: policy engine (allow/block/redact/approve), suggested rules from findings, offline test, gateway, approvals inbox, verify-the-fix.
- Production: OTLP ingest with PII redaction, failure mining into draft scenarios.
- Packs and importers: enterprise copilot, banking, tau-bench, AgentDojo.
- Ops: SLOs, schedules, alerts, change impact, readiness, signed evidence packs verifiable offline.
- Public arena: visitors try to break a defended agent across 5 levels with a leaderboard.
- Runs on cheap non-frontier models (DeepSeek, Qwen, Gemini Flash-Lite class).

## Brand Commitments

- Name: Gauntlet. Tagline used in the demo video: "Test, attack, and guard your AI agents."
- Product UI is built on Animate UI (shadcn base); the landing page must use Animate UI too (user requirement).
- User requirement: premium, not cheap-looking, no generic AI-template look.

## Evidence on Hand

- Demo videos: `.demo/tour/final/gauntlet-tour-16x9.mp4` (2:49), highlights 16:9 and 9:16, `thumb.png`, `.srt` captions (gitignored; must be copied into `public/` to ship).
- Real end-to-end demo: campaign found a critical prompt-injection finding; policy blocked it; verify run: 0 of 5 attacks succeed, benign pass rate unchanged. Total live spend ~$0.11.
- Benchmarks (`docs/benchmarks/dva-recall-live-2026-11.md`): live recall 4/12 flaws (0.33) on one run, 4–6/12 across runs; 0 false positives in the control; full 297-attack run cost $0.24.
- Test suite: ~2190 Python tests, 80 Playwright e2e.
- Open source: user confirmed the claim; no LICENSE file exists yet and the repo is private (add both before publishing).
- None: customer logos, testimonials, pricing, user counts. Do not fabricate them.

## Product Principles

1. Prove it, don't claim it: every number links to a run, an episode, or evidence.
2. Honest by default: show uncertainty and unflattering results.
3. Cheap to run, easy to own: cheap models, one VPS.
4. Find, fix, prove is one loop, not three tools.
