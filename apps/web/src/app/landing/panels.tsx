import { Trace } from "./trace";

const PANELS = [
  {
    fig: "Fig. 2a",
    title: "Find",
    read: "critical",
    fail: true,
    sub: "prompt injection",
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
    cap: "A red-team campaign against the deliberately broken Damn Vulnerable Agent files one critical finding.",
  },
  {
    fig: "Fig. 2b",
    title: "Fix",
    read: "100%",
    fail: false,
    sub: "block rate, offline",
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
    cap: "The rule is tested against stored trajectories with no model calls before it is allowed to enforce.",
  },
  {
    fig: "Fig. 2c",
    title: "Prove",
    read: "0 of 5",
    fail: false,
    sub: "attacks succeed",
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
    cap: "The finding closes only when the replay says so.",
  },
];

export function Panels() {
  return (
    <div className="lp-panels">
      {PANELS.map((p) => (
        <figure key={p.fig} className="lp-panel">
          <div className="lp-fig-label">
            <b>{p.fig}</b> {p.title.toLowerCase()}
          </div>
          <h3 className="lp-panel-title">{p.title}</h3>
          <div className={`lp-panel-read${p.fail ? " fail" : ""}`}>
            {p.read}
            <small>{p.sub}</small>
          </div>
          <Trace steps={p.steps} title={`${p.fig}: ${p.title}. ${p.read} ${p.sub}.`} />
          <dl>
            {p.rows.map(([k, v]) => (
              <div key={k} style={{ display: "contents" }}>
                <dt>{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
          <figcaption className="lp-cap">{p.cap}</figcaption>
        </figure>
      ))}
    </div>
  );
}
