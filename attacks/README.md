# Attack data

* `taxonomy.yaml`: the 17 threat categories (`Attack.category` values) with OWASP LLM 2025, OWASP
  Agentic (T-numbers) and MITRE ATLAS ids. Every id was verified against the official pages on the
  `verified_on` date in the file header (URLs in `sources`); unverifiable ids are left out.
* `objectives.yaml`: objective templates keyed `category:vector` for importers (P2-2). Objectives
  are limited to canary exfiltration, unauthorised tool calls, policy bypass and cross-user data
  leakage in the mock world.
* `library/<source>/<category>.yaml`: imported attacks (P2-2). Load and validate with
  `gauntlet_core.security.load_attacks`.
