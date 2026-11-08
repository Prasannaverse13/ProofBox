export type Source = { type: "sample"; sample: string } | { type: "git"; url: string };

export type Sample = { id: string; title: string; blurb: string };

export type Health = {
  ok: boolean;
  mode: "demo" | "live";
  model: string;
  sandbox: { docker: boolean; image_ready: boolean; image: string; runtime: string };
  limits: { network: string; memory: string; cpus: string; pids: number; command_timeout_s: number };
};

export type Finding = {
  id: string;
  title: string;
  severity: "critical" | "high" | "medium" | "low" | string;
  file?: string | null;
  line?: number | null;
  claim: string;
  test_path: string;
  test_code: string;
  command: string;
  proven: boolean;
  exit_code: number;
  output: string;
  duration: number;
  attempts: number;
  fix?: Fix;
};

export type Fix = {
  summary: string;
  files: { path: string }[];
  diff: string;
  bug_gone: boolean;
  proof_exit: number;
  proof_output: string;
  regress_command: string;
  regress_exit: number | null;
  regress_output: string;
  verified: boolean;
};

export type PolicyDenial = { command: string; origin: string; step: number; rule: string; reason: string };

export type AuditCheck = {
  valid: boolean;
  broken_at: number | null;
  events: number;
  head: string;
  signature: string | null;
  signature_valid?: boolean;
  finished: boolean;
};

export type Containment = { kind: string; message: string; command: string; origin: string; step: number };

export type PbEvent = { seq: number; t: number; type: string; data: Record<string, any> };

export type JobSummary = {
  id: string;
  source: Source;
  state: "queued" | "running" | "done" | "failed";
  created_at: number;
  findings: Finding[];
  containment: Containment[];
  policy: PolicyDenial[];
  summary: string;
  error: string;
  proven: number;
  fixed: number;
  audit_head: string;
  signature: string;
};

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}

export const api = {
  health: () => fetch("/api/health", { cache: "no-store" }).then(j<Health>),
  samples: () => fetch("/api/samples").then(j<{ samples: Sample[] }>),
  jobs: () => fetch("/api/jobs", { cache: "no-store" }).then(j<{ jobs: JobSummary[] }>),
  create: (source: Source) =>
    fetch("/api/jobs", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ source }),
    }).then(j<JobSummary>),
  audit: (id: string) => fetch(`/api/jobs/${id}/audit`, { cache: "no-store" }).then(j<AuditCheck>),
  job: (id: string) => fetch(`/api/jobs/${id}`, { cache: "no-store" }).then(j<JobSummary & { events: PbEvent[] }>),
};
