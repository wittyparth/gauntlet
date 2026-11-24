import Link from "next/link";

import { Hero } from "./hero";
import { Panels } from "./panels";
import { Reliability } from "./reliability";

const RUNS = [
  { run: "Run 1", what: "library attacks, three agents", hits: 4, of: 12, recall: "4/12", fp: "20", fpTone: "bad", cost: "$0.24", note: "297-attack library, live models. The control was not clean: echo and decode objectives fired on a fixed world." },
  { run: "Run 2", what: "hardened objectives, adaptive attacker", hits: 6, of: 12, recall: "6/12", fp: "1", fpTone: "mid", cost: "$0.17", note: "Best run. One echo-style false positive, fixed afterwards and not re-measured live." },
  { run: "Run 3", what: "confirmation run", hits: 4, of: 12, recall: "4/12", fp: "4", fpTone: "bad", cost: "$0.18", note: "Two flaws flipped back to missed with no code change: model variance. The fixed email world still leaked." },
  { run: "Run 4", what: "email agent only, rulings applied", hits: 2, of: 6, recall: "2/6", fp: "0", fpTone: "good", cost: "$0.10", note: "First clean control. Recall that came from permitted behaviour was removed, so it fell." },
] as const;

const SURFACES = [
  ["Console", "Runs, reports with cited evidence, findings, policies, approvals, posture.", "/login"],
  ["CLI", "Scan an MCP server, lint, gate a build, pin tool definitions, diff them.", "gauntlet scan mcp"],
  ["MCP", "The same tools inside Claude Code and any MCP client.", "gauntlet mcp pin"],
  ["CI gate", "A pull request comment and a README badge, backed by evidence that expires.", "gauntlet gate"],
  ["Production", "OTLP traces in, PII redacted, failures mined into draft scenarios.", "POST /v1/traces"],
  ["Evidence", "Signed packs of a run, verifiable offline by someone who never saw the console.", "gauntlet evidence"],
] as const;

export default function LandingPage() {
  return (
    <>
      <header className="lp-wrap">
        <div className="lp-mast">
          <Link href="/landing" className="lp-mast-name">
            Gauntlet<span>Plate 1, results</span>
          </Link>
          <nav className="lp-nav" aria-label="Primary">
            <a href="#film">Film</a>
            <a href="#method">Method</a>
            <a href="#results">Results</a>
            <Link href="/arena">Arena</Link>
            <Link href="/login">Console</Link>
          </nav>
        </div>
      </header>

      <main>
        <Hero />

        <section className="lp-wrap lp-sec" id="method" aria-labelledby="method-h">
          <div className="lp-sec-head">
            <h2 className="lp-h2" id="method-h">
              Find a hole. Fix it. Prove it.
            </h2>
            <p>
              One loop, drawn from a real run against a deliberately vulnerable support agent. Each panel plots the
              same thing: whether the attacker&apos;s objective held, step by step.
            </p>
          </div>
          <Panels />
        </section>

        <section className="lp-sec" aria-label="Reliability" style={{ paddingBlock: 0 }}>
          <Reliability />
        </section>

        <section className="lp-wrap lp-sec" id="results" aria-labelledby="results-h">
          <div className="lp-sec-head">
            <h2 className="lp-h2" id="results-h">
              What it found, and what it missed.
            </h2>
            <p>
              We ran Gauntlet against its own test agents with cheap live models. Recall is four to six of twelve
              planted flaws, and it moves between runs. We publish the misses and the false positives.
            </p>
          </div>
          <div className="lp-table-wrap">
            <table className="lp-table">
              <caption>
                <b>Table 1.</b> Recall of planted flaws against the Damn Vulnerable Agent, live models, one seed per
                run. A false positive is a finding raised against the same attacks on a world with the flaws removed.
              </caption>
              <thead>
                <tr>
                  <th scope="col">Run</th>
                  <th scope="col">Flaws found</th>
                  <th scope="col">Control false positives</th>
                  <th scope="col">Live cost</th>
                </tr>
              </thead>
              <tbody>
                {RUNS.map((r) => (
                  <tr key={r.run}>
                    <th scope="row">
                      {r.run}
                      <small>{r.what}</small>
                    </th>
                    <td className="num mid">
                      <span className="strip" aria-hidden>
                        {Array.from({ length: r.of }, (_, i) => (
                          <i key={i} className={i < r.hits ? "hit" : ""} />
                        ))}
                      </span>
                      {r.recall}
                      <small>{r.note}</small>
                    </td>
                    <td className={`num ${r.fpTone}`} data-label="control false positives">{r.fp}</td>
                    <td className="num" data-label="live cost">{r.cost}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="lp-table-foot">
            <p className="lp-cap" style={{ marginTop: 0 }}>
              The full 297-attack library costs <span className="mono">$0.24</span> to run. Run 4 covers the email agent
              only; the support and SQL controls were already <span className="mono">0</span> in run 3.
            </p>
            <Link href="/benchmarks" className="lp-link">
              Open the benchmarks
            </Link>
          </div>
        </section>

        <section className="lp-wrap lp-sec" aria-labelledby="where-h">
          <div className="lp-sec-head">
            <h2 className="lp-h2" id="where-h">
              Wherever the agent runs.
            </h2>
            <p>The same loop from a terminal, an editor, a pull request and production traffic.</p>
          </div>
          <dl className="lp-surf">
            {SURFACES.map(([name, text, cmd]) => (
              <div key={name}>
                <dt>{name}</dt>
                <dd>
                  {text}
                  <code>{cmd}</code>
                </dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="lp-wrap lp-sec" aria-labelledby="own-h">
          <div className="lp-run">
            <div>
              <h2 className="lp-h2" id="own-h">
                Runs on one VPS, with cheap models.
              </h2>
              <p className="lp-prose lp-prose-dim" style={{ marginTop: "1.5rem" }}>
                Docker Compose and Caddy on a 4 GB machine: Oracle Always Free, Hetzner, Coolify or Dokploy. The models
                in the benchmark are DeepSeek V4 Flash, Qwen3.7 Flash and Gemini 2.5 Flash-Lite. Spend is capped per run
                and per day.
              </p>
              <dl className="lp-facts">
                <div>
                  <dt>full attack run</dt>
                  <dd>$0.24</dd>
                </div>
                <div>
                  <dt>tests</dt>
                  <dd>~2190</dd>
                </div>
                <div>
                  <dt>e2e specs</dt>
                  <dd>80</dd>
                </div>
              </dl>
              <p className="lp-prose lp-prose-dim" style={{ marginTop: "2rem", fontSize: "0.9375rem" }}>
                Open source. The repository and licence are published with the first release.
              </p>
            </div>
            <div>
              <div className="lp-fig-label" style={{ marginBottom: "0.8rem" }}>
                <b>Fig. 4</b> self-host quick start
              </div>
              <pre className="lp-term" aria-label="Self-host commands">
                <span className="c"># any Ubuntu or Debian VPS, 4 GB RAM or more{"\n"}</span>
                git clone &lt;repo-url&gt; /opt/gauntlet &amp;&amp; cd /opt/gauntlet{"\n"}
                sudo ./deploy/bootstrap.sh --domain gauntlet.example.com{"\n"}
                <span className="c"># prints the admin key once; open the site and paste it</span>
              </pre>
            </div>
          </div>
        </section>

        <section className="lp-wrap lp-sec" aria-labelledby="close-h">
          <div className="lp-close">
            <div>
              <h2 className="lp-h2" id="close-h">
                Read the figures, then break something.
              </h2>
              <p className="lp-prose lp-prose-dim" style={{ marginTop: "1.5rem" }}>
                Watch the run, try to defeat the defended agent yourself, or open the console and aim Gauntlet at your
                own.
              </p>
            </div>
            <nav className="lp-close-actions" aria-label="Next steps">
              <a href="#film">
                Watch the film <span>2:49</span>
              </a>
              <Link href="/arena">
                Try the arena <span>5 levels</span>
              </Link>
              <Link href="/login">
                Open the console <span>admin key</span>
              </Link>
            </nav>
          </div>
        </section>
      </main>

      <footer className="lp-wrap">
        <div className="lp-foot">
          <span>Gauntlet. Figures come from this repository&apos;s own runs.</span>
          <nav aria-label="Footer">
            <Link href="/benchmarks">Benchmarks</Link>
            <Link href="/arena">Arena</Link>
            <Link href="/login">Console</Link>
          </nav>
        </div>
      </footer>
    </>
  );
}
