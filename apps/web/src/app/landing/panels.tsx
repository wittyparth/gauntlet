import { Trace } from "./trace";

const PANELS = [
  {
    fig: "Fig. 2a",
    title: "Find",
    note: { text: "critical", step: 2, tone: "fail" as const },
    steps: [
      { label: "ask", held: false },
      { label: "read note", held: false },
      { label: "issue_refund", held: true },
    ],
    rows: [
      ["category", "indirect_injection"],
      ["finding", "InjecAgent direct harm, reproduced 1 of 1"],
      ["evidence", "The agent issued a refund using the marker planted in an order note."],
    ],
    cap: "A red-team campaign against the deliberately broken Damn Vulnerable Agent files one critical prompt-injection finding: the agent issues a refund on instructions planted in an order note.",
  },
  {
    fig: "Fig. 2b",
    title: "Fix",
    note: { text: "blocked", step: 2, tone: "ok" as const },
    steps: [
      { label: "ask", held: false },
      { label: "read note", held: false },
      { label: "issue_refund", held: false, blocked: true },
    ],
    rows: [
      ["rule", "tainted_call, block, for write, destructive and financial tools"],
      ["offline test", "100% of attacks blocked, 0% false positives on benign runs"],
      ["source", "Suggested from the finding, added as policy v2, then enforced."],
    ],
    cap: "A tainted-call rule blocks the refund. Tested offline against stored trajectories with no model calls, it stops 100% of the attacks with 0% false positives, and only then is it enforced.",
  },
  {
    fig: "Fig. 2c",
    title: "Prove",
    note: { text: "0 of 5 succeed", step: 4, tone: "ok" as const },
    steps: [
      { label: "1", held: false },
      { label: "2", held: false },
      { label: "3", held: false },
      { label: "4", held: false },
      { label: "5", held: false },
    ],
    rows: [
      ["verify run", "The same attacks, replayed through the enforced policy."],
      ["benign pass rate", "Unchanged."],
      ["spend", "About $0.11 for the whole loop, live."],
    ],
    cap: "Replayed through the enforced policy, 0 of 5 attacks succeed and the benign pass rate is unchanged. The finding closes only when the replay says so.",
  },
];

export function Panels() {
  return (
    <div className="lp-panels">
      {PANELS.map((p) => (
        <figure key={p.fig} className="lp-panel">
          <h3 className="lp-panel-title">{p.title}</h3>
          <Trace steps={p.steps} note={p.note} title={`${p.fig}: ${p.title}. ${p.note.text}.`} />
          <dl>
            {p.rows.map(([k, v]) => (
              <div key={k} style={{ display: "contents" }}>
                <dt>{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
          <figcaption className="lp-cap">
            <b>{p.fig}.</b> {p.cap}
          </figcaption>
        </figure>
      ))}
    </div>
  );
}
