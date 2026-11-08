"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  type AuditCheck,
  type Containment,
  type Finding,
  type Fix,
  type Health,
  type JobSummary,
  type PbEvent,
  type PolicyDenial,
  type Sample,
} from "@/lib/api";

const GIT = /^https:\/\/(github\.com|gitlab\.com|bitbucket\.org|codeberg\.org)\/[\w.\-]+\/[\w.\-]+?(\.git)?\/?$/;

export function Console() {
  const router = useRouter();
  const params = useSearchParams();
  const jobParam = params.get("job");
  const sampleParam = params.get("sample");

  const [health, setHealth] = useState<Health | null>(null);
  const [offline, setOffline] = useState(false);
  const [samples, setSamples] = useState<Sample[]>([]);
  const [tab, setTab] = useState<"sample" | "git">("sample");
  const [sample, setSample] = useState<string>(sampleParam ?? "hostile-invoices");
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);

  const [events, setEvents] = useState<PbEvent[]>([]);
  const [job, setJob] = useState<JobSummary | null>(null);
  const [recent, setRecent] = useState<JobSummary[]>([]);
  const [chain, setChain] = useState<AuditCheck | null>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);

  const running = !!job && (job.state === "queued" || job.state === "running");

  useEffect(() => {
    api.health().then(setHealth).catch(() => setOffline(true));
    api.samples().then((r) => setSamples(r.samples)).catch(() => {});
    api.jobs().then((r) => setRecent(r.jobs)).catch(() => {});
  }, []);

  const stop = () => {
    esRef.current?.close();
    esRef.current = null;
  };

  const attach = useCallback((id: string) => {
    stop();
    setEvents([]);
    api.job(id).then((j) => setJob(j)).catch(() => {});
    const es = new EventSource(`/api/jobs/${id}/events`);
    esRef.current = es;
    es.onmessage = (m) => {
      const ev: PbEvent = JSON.parse(m.data);
      setEvents((prev) => (prev.some((p) => p.seq === ev.seq) ? prev : [...prev, ev]));
      if (ev.type === "done") {
        es.close();
        api.job(id).then(setJob).catch(() => {});
        api.jobs().then((r) => setRecent(r.jobs)).catch(() => {});
      } else if (ev.type === "status") {
        setJob((j) => (j ? { ...j, state: "running" } : j));
      }
    };
    es.onerror = () => {
      // The stream closes itself after "done". Anything else: refetch the truth.
      es.close();
      api.job(id).then(setJob).catch(() => {});
    };
  }, []);

  useEffect(() => {
    if (jobParam) attach(jobParam);
    return stop;
  }, [jobParam, attach]);

  useEffect(() => {
    if (sampleParam) {
      setTab("sample");
      setSample(sampleParam);
    }
  }, [sampleParam]);

  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [events.length]);

  const start = async () => {
    setError("");
    let source;
    if (tab === "sample") source = { type: "sample" as const, sample };
    else {
      if (!GIT.test(url.trim())) {
        setError("Use a public https link on github.com, gitlab.com, bitbucket.org or codeberg.org");
        return;
      }
      source = { type: "git" as const, url: url.trim() };
    }
    setStarting(true);
    try {
      const j = await api.create(source);
      setJob(j);
      router.replace(`/console?job=${j.id}`, { scroll: false });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the audit");
    } finally {
      setStarting(false);
    }
  };

  const finished = job?.state === "done" || job?.state === "failed";
  useEffect(() => {
    setChain(null);
    if (job && finished) api.audit(job.id).then(setChain).catch(() => {});
  }, [job?.id, finished]); // eslint-disable-line react-hooks/exhaustive-deps

  const view = useMemo(() => derive(events), [events]);
  const findings: Finding[] = (finished ? job!.findings : view.findings.filter((f) => f.proven)).map((f) =>
    f.fix || !view.fixes[f.id] ? f : { ...f, fix: view.fixes[f.id] },
  );
  const hasRun = events.length > 0 || !!job;

  return (
    <div className="console">
      <div className="wrap">
        <div className="console-head">
          <div>
            <p className="eyebrow">Console</p>
            <h1>Run an audit</h1>
          </div>
          <div className="health" aria-live="polite">
            {offline && <span className="tag high">API offline</span>}
            {health && (
              <>
                <span className={`tag ${health.mode === "live" ? "live" : ""}`}>
                  <i className="dot" />
                  {health.mode === "live" ? "live agent" : "demo agent"}
                </span>
                <span className="tag">{health.sandbox.image_ready ? "sandbox ready" : "sandbox image missing"}</span>
                <span className="tag">{health.sandbox.runtime}</span>
              </>
            )}
          </div>
        </div>

        {/* -------------------------------------------------- launcher */}
        <section className="launcher" aria-label="Start an audit">
          <div className="tabs" role="group" aria-label="Source type">
            <button aria-pressed={tab === "sample"} onClick={() => setTab("sample")}>Bundled sample</button>
            <button aria-pressed={tab === "git"} onClick={() => setTab("git")}>Public repo</button>
          </div>
          <div className="launch-row">
            {tab === "sample" ? (
              <div className="sample-pick">
                {samples.length === 0 && <span className="muted">Loading samples…</span>}
                {samples.map((s) => (
                  <button key={s.id} className="sample-opt" aria-pressed={sample === s.id} onClick={() => setSample(s.id)}>
                    <b>{s.title}</b>
                    <small>{s.blurb}</small>
                  </button>
                ))}
              </div>
            ) : (
              <div className="grow">
                <input
                  className="input"
                  aria-label="Repository URL"
                  placeholder="https://github.com/owner/repo"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && start()}
                  spellCheck={false}
                />
              </div>
            )}
            <button className="btn pill" onClick={start} disabled={starting || running || offline} style={{ alignSelf: "flex-start", height: 48, padding: "0 24px" }}>
              {starting ? "Starting…" : running ? "Running…" : "Run audit"}
            </button>
          </div>
          {error && <p className="error-line" role="alert">{error}</p>}
        </section>

        {/* -------------------------------------------------- live run */}
        {hasRun && (
          <div className="run-grid">
            <div className="window">
              <div className="window-bar">
                <i /><i /><i />
                <span className="window-title">
                  {job ? `job ${job.id.slice(0, 8)}` : "job"} · {job?.state ?? "starting"}
                </span>
              </div>
              <div className={`log ${running ? "" : ""}`} ref={logRef} aria-live="polite">
                {events.length === 0 && <div className="log-empty">Starting the box…</div>}
                {events.map((ev) => (
                  <LogItem key={ev.seq} ev={ev} />
                ))}
                {running && <div className="log-item sys"><span className="cursor">working</span></div>}
              </div>
            </div>

            <aside>
              <div className="panel">
                <h3>
                  Sandbox
                  <span className={`tag ${view.box.state === "running" ? "live" : ""}`}>{view.box.state ?? "idle"}</span>
                </h3>
                {view.boxes.map((b) => (
                  <div className="box-row" key={b.name}>
                    <code>{b.id}</code>
                    <span>{b.phase}</span>
                    <span className={`tag ${b.state === "running" ? "live" : ""}`}>
                      {b.state === "destroyed" ? `destroyed ${b.lifetime_s}s` : b.state}
                    </span>
                  </div>
                ))}
                {view.limits && (
                  <dl className="kv">
                    {Object.entries(view.limits).map(([k, v]) => (
                      <div key={k} style={{ display: "contents" }}>
                        <dt>{k.replace(/_/g, " ")}</dt>
                        <dd>{String(v)}</dd>
                      </div>
                    ))}
                  </dl>
                )}
              </div>

              <div className="panel">
                <h3>
                  Contained
                  <span className="tag">{view.containment.length}</span>
                </h3>
                {view.containment.length === 0 ? (
                  <p className="muted" style={{ marginTop: 12, fontSize: 14 }}>
                    Nothing hostile yet. Guards show up here the moment something is blocked.
                  </p>
                ) : (
                  <ul className="contain-list">
                    {view.containment.map((c, i) => (
                      <li key={i}>
                        <b>{c.kind}</b>
                        <span>{c.message}</span>
                      </li>
                    ))}
                  </ul>
                )}
                {view.integrity && (
                  <div className="integrity" role="status">
                    <span>Sandbox still standing: <b>{view.integrity.sandbox_alive ? "yes" : "no"}</b></span>
                    <span>Host files intact: <b>{view.integrity.host_files_intact ? "yes" : "no"}</b></span>
                  </div>
                )}
              </div>

              <div className="panel">
                <h3>
                  Policy guard
                  <span className="tag">{view.policy.length} denied</span>
                </h3>
                {view.policy.length === 0 ? (
                  <p className="muted" style={{ marginTop: 12, fontSize: 14 }}>
                    Every agent command is checked before it runs: no network, no installs, no privilege or host access.
                  </p>
                ) : (
                  <ul className="contain-list">
                    {view.policy.map((p, i) => (
                      <li key={i}>
                        <b>{p.rule}</b>
                        <span><code className="inline">{p.command}</code> {p.reason}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </aside>
          </div>
        )}

        {/* -------------------------------------------------- report */}
        {job && (job.state === "done" || job.state === "failed") && (
          <section className="report" aria-label="Audit report">
            <div className="report-head">
              <div>
                <p className="eyebrow">Report</p>
                <h2 style={{ marginTop: 10 }}>
                  {job.state === "failed"
                    ? "The audit stopped early"
                    : `${job.findings.length} proven ${job.findings.length === 1 ? "finding" : "findings"}`}
                </h2>
              </div>
              <div className="exports" role="group" aria-label="Download report">
                <a className="btn small" href={`/api/jobs/${job.id}/report.md`} download>Markdown</a>
                <a className="btn small" href={`/api/jobs/${job.id}/report.sarif`} download>SARIF</a>
                <a className="btn small" href={`/api/jobs/${job.id}/report.json`} download>JSON</a>
              </div>
            </div>
            <dl className="report-stats">
              <div><dt>Proven</dt><dd>{job.findings.length}</dd></div>
              <div><dt>Fixes verified</dt><dd>{job.findings.filter((f) => f.fix?.verified).length}</dd></div>
              <div><dt>Attacks contained</dt><dd>{job.containment.length}</dd></div>
              <div><dt>Denied by policy</dt><dd>{job.policy?.length ?? 0}</dd></div>
            </dl>
            {chain && (
              <div className={`chain ${chain.valid ? "ok" : "bad"}`} role="status">
                <span className="tag live"><i className="dot" />{chain.valid ? "audit chain intact" : `chain broken at event ${chain.broken_at}`}</span>
                <span>{chain.events} events hash chained · head <code>{chain.head.slice(0, 16)}…</code></span>
                {chain.signature && (
                  <span>signed <code>{chain.signature.slice(0, 16)}…</code> · {chain.signature_valid ? "signature valid" : "signature invalid"}</span>
                )}
              </div>
            )}
            {job.error && <p className="error-line">{job.error}</p>}
            {job.summary && <p className="summary">{job.summary}</p>}
            <div className="findings">
              {findings.map((f) => (
                <FindingCard key={f.id} f={f} />
              ))}
              {findings.length === 0 && job.state === "done" && (
                <p className="muted">No bug survived the proof step, so nothing is reported.</p>
              )}
            </div>
          </section>
        )}

        {/* -------------------------------------------------- recent */}
        {recent.length > 0 && (
          <section className="recent" aria-label="Recent audits">
            <p className="eyebrow">Recent audits</p>
            <div className="recent-list">
              {recent.slice(0, 6).map((r) => (
                <Link key={r.id} href={`/console?job=${r.id}`}>
                  <span>{r.source.type === "sample" ? r.source.sample : r.source.url}</span>
                  <span className="tag">{r.proven} proven</span>
                  {r.fixed > 0 && <span className="tag">{r.fixed} fixed</span>}
                  <span className={`tag ${r.state === "running" ? "live" : ""}`}>{r.state}</span>
                </Link>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

/* ================================================================ derive */

type Box = { name: string; id: string; phase: string; state: string; lifetime_s?: number };

function derive(events: PbEvent[]) {
  const boxes = new Map<string, Box>();
  let limits: Record<string, unknown> | null = null;
  const containment: Containment[] = [];
  type Integrity = { sandbox_alive: boolean; host_files_intact: boolean };
  let integrity = null as Integrity | null;
  const findings: Finding[] = [];
  const policy: PolicyDenial[] = [];
  const fixes: Record<string, Fix> = {};
  for (const ev of events) {
    const d = ev.data;
    if (ev.type === "sandbox") {
      boxes.set(d.name, { name: d.name, id: d.id, phase: d.phase, state: d.state, lifetime_s: d.lifetime_s });
      if (d.limits) limits = d.limits;
    } else if (ev.type === "containment") containment.push(d as Containment);
    else if (ev.type === "integrity") integrity = d as Integrity;
    else if (ev.type === "policy") policy.push(d as PolicyDenial);
    else if (ev.type === "fix") fixes[d.finding] = d as Fix;
    else if (ev.type === "finding") {
      const i = findings.findIndex((f) => f.id === d.id);
      if (i >= 0) findings[i] = d as Finding;
      else findings.push(d as Finding);
    }
  }
  const list = [...boxes.values()];
  const current = list[list.length - 1];
  return { boxes: list, box: current ?? { state: undefined }, limits, containment, integrity, findings, policy, fixes };
}

/* ================================================================ log */

function LogItem({ ev }: { ev: PbEvent }) {
  const d = ev.data;
  const t = `${ev.t.toFixed(1)}s`;
  switch (ev.type) {
    case "log":
      return <div className="log-item sys">{t} · {d.message}</div>;
    case "status":
      return <div className="log-item sys">{t} · agent started ({d.mode}{d.model ? `, ${d.model}` : ""})</div>;
    case "sandbox":
      return (
        <div className="log-item sys">
          {t} · sandbox {d.state} · {d.phase} · {d.id}
          {d.lifetime_s ? ` · lived ${d.lifetime_s}s` : ""}
        </div>
      );
    case "step": {
      const cmd = d.args?.command ?? d.args?.path ?? d.args?.title ?? (d.action === "fix" ? `patch ${d.args?.finding}` : undefined);
      return (
        <div className="log-item">
          <div className="meta"><span>{t}</span><span className="act">step {d.n} · {d.action}</span></div>
          {d.thought && <div className="thought">{d.thought}</div>}
          {cmd && <div className="cmd">{String(cmd)}</div>}
        </div>
      );
    }
    case "observation": {
      const text: string = d.text ?? d.result?.output ?? "";
      if (!text) return null;
      return (
        <div className="log-item">
          <pre>{text.length > 2400 ? text.slice(0, 2400) + "\n…" : text}</pre>
        </div>
      );
    }
    case "containment":
      return (
        <div className="log-item contain">
          <div className="meta"><span>{t}</span><span className="act">contained · {d.kind}</span></div>
          <div className="thought">{d.message}</div>
        </div>
      );
    case "integrity":
      return (
        <div className="log-item contain">
          <div className="meta"><span>{t}</span><span className="act">integrity check</span></div>
          <div className="thought">
            Sandbox alive: {d.sandbox_alive ? "yes" : "no"}. Host files intact: {d.host_files_intact ? "yes" : "no"}.
          </div>
        </div>
      );
    case "finding":
      return (
        <div className="log-item">
          <div className="meta">
            <span>{t}</span>
            <span className="act">{d.proven ? "proven" : "not proven, dropped"} · {d.title}</span>
          </div>
        </div>
      );
    case "policy":
      return (
        <div className="log-item contain">
          <div className="meta"><span>{t}</span><span className="act">policy denied · {d.rule}</span></div>
          <div className="thought">{d.reason}</div>
        </div>
      );
    case "fix":
      return (
        <div className="log-item">
          <div className="meta">
            <span>{t}</span>
            <span className="act">{d.verified ? "fix verified" : "fix rejected"} · {d.title}</span>
          </div>
          <div className="thought">
            Proof after patch exit {d.proof_exit} ({d.bug_gone ? "bug gone" : "bug still there"})
            {d.regress_command ? `. Repo tests exit ${d.regress_exit}.` : "."}
          </div>
        </div>
      );
    case "done":
      return (
        <div className="log-item sys">
          {t} · {d.state} · {d.proven} proven · {d.fixed ?? 0} fixed · {d.contained} contained · {d.denied ?? 0} denied
        </div>
      );
    default:
      return null;
  }
}

/* ================================================================ finding */

function FindingCard({ f }: { f: Finding }) {
  return (
    <article className="finding">
      <div className="finding-top">
        <div>
          <h3>{f.title}</h3>
          <p className="where">{f.file}{f.line ? `:${f.line}` : ""}</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <span className={`tag ${f.severity}`}>{f.severity}</span>
          <span className="tag live"><i className="dot" />proven</span>
          {f.fix?.verified && <span className="tag live">fix verified</span>}
          {f.attempts > 1 && <span className="tag">{f.attempts} attempts</span>}
        </div>
      </div>
      <p className="claim">{f.claim}</p>
      <div className="proof-grid">
        <div className="window">
          <div className="window-bar"><i /><i /><i /><span className="window-title">{f.test_path}</span></div>
          <pre>{f.test_code}</pre>
        </div>
        <div className="window rust">
          <div className="window-bar"><i /><i /><i /><span className="window-title">sandbox output · {f.duration}s</span></div>
          <pre>{f.output}</pre>
        </div>
      </div>
      {f.fix && <FixBlock fix={f.fix} />}
    </article>
  );
}

function FixBlock({ fix }: { fix: Fix }) {
  return (
    <div className="fix">
      <div className="fix-head">
        <span className={`tag ${fix.verified ? "live" : "high"}`}>{fix.verified ? "patch verified in sandbox" : "patch not verified"}</span>
        <p>{fix.summary}</p>
      </div>
      <div className="proof-grid">
        <div className="window">
          <div className="window-bar"><i /><i /><i /><span className="window-title">{fix.files.map((x) => x.path).join(", ")} · diff</span></div>
          <pre className="diff">
            {fix.diff.split("\n").map((line, i) => (
              <span key={i} className={line.startsWith("+") && !line.startsWith("+++") ? "add" : line.startsWith("-") && !line.startsWith("---") ? "del" : line.startsWith("@@") ? "hunk" : ""}>
                {line + "\n"}
              </span>
            ))}
          </pre>
        </div>
        <div className="window">
          <div className="window-bar"><i /><i /><i /><span className="window-title">after the patch</span></div>
          <div className="checks">
            <div className={fix.bug_gone ? "pass" : "fail"}>
              <b>{fix.bug_gone ? "Proof now fails" : "Proof still passes"}</b>
              <span>exit {fix.proof_exit}. {fix.bug_gone ? "The exploit no longer works." : "The bug is still there."}</span>
            </div>
            <div className={fix.regress_command && fix.regress_exit === 0 ? "pass" : "fail"}>
              <b>{fix.regress_command ? (fix.regress_exit === 0 ? "Repo tests pass" : "Repo tests broke") : "No repo tests run"}</b>
              <span><code>{fix.regress_command || "none"}</code></span>
            </div>
          </div>
          <pre className="after">{(fix.regress_output || fix.proof_output).slice(-900)}</pre>
        </div>
      </div>
    </div>
  );
}
