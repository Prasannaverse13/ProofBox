import Link from "next/link";
import { Cube } from "@/components/Cube";
import { IconLayers, IconStairs, IconWire } from "@/components/Icons";

const steps = [
  ["01", "Fetch", "Paste a public repo link. The code is copied to the Vultr VM, never run there."],
  ["02", "Box", "A fresh container starts: no network, read only disk, no secrets, hard memory and time limits."],
  ["03", "Hunt", "The agent reads the code and calls Vultr Serverless Inference to suspect bugs."],
  ["04", "Prove", "For each suspect it writes an exploit test and runs it in the box. A pass is the only way in."],
  ["05", "Fix", "It writes a patch, reruns the proof (it must now fail) and the repo tests (they must pass)."],
  ["06", "Sign", "The box is deleted. Every event is hash chained and signed. Export Markdown, SARIF or JSON."],
];

const guards = [
  ["Network", "none", "Exfiltration fails at DNS."],
  ["Root filesystem", "read only", "rm -rf has nothing to delete."],
  ["Privileges", "uid 1000, caps dropped", "No root, no new privileges."],
  ["Processes", "128 max", "Fork bombs stop at the cap."],
  ["Memory", "512 MB", "Memory bombs are killed, not swapped."],
  ["Time", "30 s per command", "Infinite loops are killed twice over."],
  ["Secrets", "none inside", "The environment is empty by design."],
  ["Command policy", "checked first", "Installs, network tools and host access are denied before they run."],
  ["Audit trail", "hash chained", "Every event is chained and signed. Any edit breaks the chain."],
];

const samples = [
  ["hostile-invoices", "Hostile invoices", "Python", "A test suite that tries to steal, wipe and hang. Hides a path traversal."],
  ["vuln-vault", "Vuln vault", "Solidity", "An ETH vault. ProofBox drains it with a Foundry exploit, offline."],
  ["notes-api", "Notes API", "Node.js", "Forge an unsigned admin token and read every private note."],
];

export default function Home() {
  return (
    <>
      {/* ------------------------------------------------------------ hero */}
      <section className="hero">
        <div className="wrap">
          <p className="eyebrow new" style={{ marginBottom: 10 }}>Safe agent execution on Vultr</p>
          <h1>Bugs, with proof.</h1>
          <p className="lead">
            An AI auditor that proves every bug with a real exploit, fixes it, and runs all of it in a
            sealed box that cannot hurt you. No proof, no finding.
          </p>
          <div className="hero-ctas">
            <Link href="/console" className="btn pill">Run an audit</Link>
            <Link href="/#containment" className="btn ghost">See how it is contained</Link>
          </div>
          <Cube />
          <p className="strip-label">Built on</p>
          <div className="logo-strip">
            <span>Vultr Serverless Inference</span>
            <span>Vultr Cloud Compute</span>
            <span>Docker</span>
            <span>Foundry</span>
            <span>pytest</span>
            <span>Node.js</span>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------ how */}
      <section className="band ground" id="how">
        <div className="wrap split">
          <div>
            <p className="eyebrow">How it works</p>
            <h2 className="h-lg">An auditor that has to show its work.</h2>
            <p style={{ marginTop: 16 }}>
              Most AI code review guesses. ProofBox runs the code. A finding only exists if an exploit
              test it wrote passes inside the sandbox.
            </p>
            <ol className="steps">
              {steps.map(([n, t, d]) => (
                <li key={n}>
                  <span className="n">{n}</span>
                  <div>
                    <h4>{t}</h4>
                    <p>{d}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
          <div className="window" aria-label="Example proof test">
            <div className="window-bar">
              <i /><i /><i />
              <span className="window-title">proofbox_tests/test_traversal.py</span>
            </div>
            <pre>
              <span className="k">from</span> invoice_tools <span className="k">import</span> load_template{"\n\n\n"}
              <span className="k">def</span> test_template_traversal_reads_system_file():{"\n"}
              {"    "}leaked = load_template(<span className="s">&apos;../../../../../../etc/passwd&apos;</span>){"\n"}
              {"    "}<span className="k">assert</span> <span className="s">&apos;root:&apos;</span> <span className="k">in</span> leaked{"\n"}
              {"    "}<span className="k">print</span>(<span className="s">&apos;PROOFBOX_CONFIRMED read /etc/passwd&apos;</span>){"\n\n"}
              <span className="c"># sandbox result</span>{"\n"}
              <span className="c">PROOFBOX_CONFIRMED read /etc/passwd through load_template</span>{"\n"}
              <span className="c">1 passed in 0.01s</span>
            </pre>
          </div>
        </div>
      </section>

      <div className="divider" />

      {/* ------------------------------------------------------------ workloads */}
      <section className="band" id="samples">
        <div className="wrap">
          <div className="section-head">
            <p className="eyebrow">What it audits</p>
            <h2 className="h-lg">Three languages. One rule: prove it.</h2>
            <p>Pick a bundled sample or paste any public GitHub link.</p>
          </div>
          <div className="grid-3">
            {samples.map(([id, title, lang, blurb], i) => (
              <Link key={id} href={`/console?sample=${id}`} className="card sample">
                {i === 0 ? <IconWire /> : i === 1 ? <IconStairs /> : <IconLayers />}
                <h3 className="h-card">{title}</h3>
                <p>{blurb}</p>
                <div className="meta">
                  <span className="tag">{lang}</span>
                  <span className="tag">sample</span>
                </div>
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------ containment */}
      <section className="band ground" id="containment">
        <div className="wrap split">
          <div>
            <p className="eyebrow">Containment first</p>
            <h2 className="h-lg">Blast radius zero.</h2>
            <p style={{ marginTop: 16 }}>
              The code under audit is untrusted, so is the model&apos;s output. Both only ever touch a
              throwaway container. The agent loop never runs repo code in its own process.
            </p>
            <div className="guards">
              {guards.map(([name, value, note]) => (
                <div className="guard" key={name}>
                  <div>
                    <b>{name}</b>
                    <span>{note}</span>
                  </div>
                  <span className="tag">{value}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="window rust" aria-label="Sandbox launch command">
            <div className="window-bar">
              <i /><i /><i />
              <span className="window-title">sandbox.py</span>
            </div>
            <pre>
              <span className="c"># one fresh box per task</span>{"\n"}
              docker run -d <span className="k">\</span>{"\n"}
              {"  "}--network <span className="s">none</span> <span className="k">\</span>{"\n"}
              {"  "}--read-only <span className="k">\</span>{"\n"}
              {"  "}--cap-drop <span className="s">ALL</span> <span className="k">\</span>{"\n"}
              {"  "}--security-opt <span className="s">no-new-privileges</span> <span className="k">\</span>{"\n"}
              {"  "}--user <span className="s">1000:1000</span> <span className="k">\</span>{"\n"}
              {"  "}--memory <span className="s">512m</span> --memory-swap <span className="s">512m</span> <span className="k">\</span>{"\n"}
              {"  "}--pids-limit <span className="s">128</span> <span className="k">\</span>{"\n"}
              {"  "}--tmpfs <span className="s">/work:rw,exec,size=256m</span> <span className="k">\</span>{"\n"}
              {"  "}proofbox-sandbox sleep infinity{"\n\n"}
              <span className="c"># when the job ends, success or crash</span>{"\n"}
              docker rm -f -v proofbox-…{"\n\n"}
              <span className="c"># optional: --runtime runsc  (gVisor)</span>
            </pre>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------ light breath */}
      <section className="band light">
        <div className="wrap">
          <p className="eyebrow">Measured, not claimed</p>
          <h2 className="h-lg">The hostile sample, as run.</h2>
          <div className="stats">
            <div className="stat"><strong>6</strong><span>attack types contained: exfiltration, wipe, persistence, process storm, memory bomb, infinite loop</span></div>
            <div className="stat"><strong>0</strong><span>files changed on the host</span></div>
            <div className="stat"><strong>2</strong><span>boxes destroyed per audit: one for untrusted tests, one for the agent</span></div>
            <div className="stat"><strong>0</strong><span>unproven findings in the final report</span></div>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------ cta */}
      <section className="band cta">
        <div className="wrap">
          <h2>Point it at code you do not trust.</h2>
          <p className="lead" style={{ margin: "20px auto 0", maxWidth: 560 }}>
            Watch the box absorb the worst the repo can do, then read only what was proven.
          </p>
          <div className="hero-ctas">
            <Link href="/console" className="btn pill">Open the console</Link>
            <Link href="/console?sample=hostile-invoices" className="btn ghost">Run the hostile sample</Link>
          </div>
        </div>
      </section>
    </>
  );
}
