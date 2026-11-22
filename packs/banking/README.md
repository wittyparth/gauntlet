# Banking pack

A test pack for a retail banking assistant: one world (accounts, cards, transactions, payees,
disputes, KYC), seven tools, 20 scenarios and good/bad oracle trajectories.

Everything is fictional: the bank, the people, the numbers. The numbered rules in `policy.md` are
agent policy written to test an assistant's behaviour. They are not legal, regulatory or
financial guidance and must not be presented as such.

The tool handlers enforce data integrity only (records exist, uniqueness, status transitions).
Verification, identity, payee cool-off and dispute eligibility are the agent's job; the scenarios
test them. The signed-in customer is world state (`session/current`) set per scenario through
`world_overrides`.
