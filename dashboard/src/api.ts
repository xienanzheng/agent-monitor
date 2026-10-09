export type Source = "live" | "replay";

export interface Verdict {
  score: number | null;
  category: string;
  authorization: string;
  boundary: string;
  recoverability: string;
  confidence: number;
  reason: string;
  reasoning: string;
  model: string;
  latency_s: number;
  failed: boolean;
  error_code?: string | null;
  request_attempts?: number;
  retry_errors?: {error_code: string; http_status: number; elapsed_s: number}[];
  timing?: { load_s?: number; prompt_s?: number; generation_s?: number; server_s?: number; input_tokens?: number; output_tokens?: number };
}

export interface EventRow {
  ts: number;
  scored_ts: number;
  agent: string;
  session_id: string;
  index: number;
  tool: string;
  kind: string;
  text: string;
  task: string;
  tags: string[];
  rule_score: number;
  rule_hits: string[];
  rule_categories: string[];
  rule_reasons?: string[];
  triage: Verdict | null;
  gateway: Verdict | null;
  final_severity: number;
  settled_by: string;
  judge_failed: boolean;
  category: string;
  reason: string;
  incident_id: string | null;
  output?: string;
  action_id?: string;
  tool_use_id?: string;
  outcome?: string;
  coverage?: string;
  assessment_state?: string;
}

export interface Incident {
  id: string;
  agent: string;
  session_id: string;
  category: string;
  opened: number;
  updated: number;
  severity: number;
  signals: string[];
  action_count: number;
  latest_reason: string;
}

export interface Status {
  daemon: { running: boolean; responsive?: boolean; queue_depth?: number; socket: string };
  hooks: { claude: boolean; codex: boolean; claude_v1: boolean };
  last_event_ts: number | null;
  spool_backlog: number;
  daemon_errors: number;
  hook_errors?: number;
  unreadable_lines: number;
  source: Source;
  health?: {
    agents: Record<string, {configured: boolean; observed: boolean; executable_ok: boolean; last_event_ts: number | null; missing_events: string[]; errors: string[]}>;
    ollama: {reachable: boolean; missing: string[]; required: string[]};
    coverage: {unknown_tools: number};
  };
}

export interface SessionSummary {
  agent: string;
  session_id: string;
  task: string;
  first_ts: number;
  last_ts: number;
  actions: number;
  max_severity: number;
  incidents: number;
}

export interface EventsPage {
  rows: EventRow[];
  next: number;
  reset: boolean;
  file_id: number | null;
}

export type Missing = { missing: true };
export type Failed = { error: string };

export interface Overview {
  by_agent: Record<string, number>;
  by_kind: Record<string, number>;
  top_tools: [string, number][];
  policy: Record<string, number>;
  top_shell_commands: [string, number][];
}

export interface ActionRecord {
  agent: string;
  session_id: string;
  index: number;
  tool: string;
  kind: string;
  text: string;
}

export interface ActionsPage {
  total: number;
  page: number;
  page_size: number;
  rows: ActionRecord[];
}

export interface Alert {
  score: number;
  agent: string;
  tool: string;
  text: string;
}

export interface ScanResult {
  provenance?: {created_at: string; threshold: number; source: string; labels: string; hashes: Record<string,string>};
  n_actions: number;
  n_alerts: number;
  alerts_per_1000: number | null;
  top_alerts: Alert[];
  judge_sample?: { n_scored: number; n_alerts: number; judge_calls: number; judge_failures: number };
}

export interface ClassificationMetrics {
  recall: number | null; miss_rate: number | null; false_alarm_rate: number | null; precision: number | null;
}
export interface Analysis {
  pending?: number;
  source: Source; window: {hours: number | null; end_ts: number}; actions: number; flagged: number; incomplete: number;
  assessed: number; threshold: number; unknown_tools: number; categories: Record<string, number>;
  judging: {actions: number; median_latency_s: number | null; stage_attempts?: number; failures?: Record<string,number>; recovered_actions?: number; request_attempts?: number; retried_actions?: number};
}
export interface ScorerRow {
  n_pos_total?: number; n_neg_total?: number;
  n_scored?: number; n_pos?: number; n_neg?: number; n_incomplete?: number; coverage?: number;
  metrics?: ClassificationMetrics;
  categories?: Record<string, {n_actions: number; n_scored: number; confusion: {tp: number; fp: number; tn: number; fn: number}; metrics: ClassificationMetrics}>;
  operating_points?: Record<string, {threshold: number | null; reject_all?: boolean; actual_fpr: number | null; recall: number | null; threshold_source: string}>;
  auc: number | null;
  tpr_at_fpr: Record<string, number | null>;
  threshold_at_5pct: number | null;
  test_confusion: { tp: number; fp: number; tn: number; fn: number } | null;
  n_test: number;
  median_latency_ms: number | null;
  judge_calls?: number;
  judge_failures?: number;
  inference_requests?: number;
  inference_retries?: number;
}

export interface EvalResults {
  schema_version?: number; legacy?: boolean; limitations?: string[];
  provenance?: {created_at: string; dataset: string; dataset_kind: string; hashes: Record<string, string>; models: string[]; threshold_source: string; dev_trajectories: number; test_trajectories: number};
  split: string;
  scorers: Record<string, ScorerRow>;
}

export interface ActionRuleView {
  type: "action";
  id: string;
  category: string;
  score: number;
  pattern: string | null;
  kinds: string[];
  tags_any: string[];
  tags_all: string[];
  add_tags: string[];
  reason: string;
}

export interface SequenceRuleView {
  type: "sequence";
  id: string;
  category: string;
  score: number;
  previous_tag: string;
  current_tag: string;
  within_actions: number;
  reason: string;
}

export type RuleView = ActionRuleView | SequenceRuleView;

export interface FeatureView {
  tag: string;
  pattern: string;
  kinds: string[];
  fields: string[];
}

export interface RulesResponse {
  rules: RuleView[] | Failed;
  features: FeatureView[] | Failed;
}

export interface Job {
  id: string;
  kind: "scan" | "eval";
  status: "running" | "done" | "failed";
  started: number;
  finished: number | null;
  summary: Record<string, unknown> | null;
  error: string | null;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function token(): string {
  return document.querySelector<HTMLMetaElement>('meta[name="monitor-token"]')?.content ?? "";
}

async function errorMessage(r: Response): Promise<string> {
  try {
    const body = await r.json();
    const msg = body.error ?? body.detail ?? r.statusText;
    return typeof msg === "string" ? msg : JSON.stringify(msg);
  } catch {
    return r.statusText;
  }
}

async function getJSON<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new ApiError(r.status, await errorMessage(r));
  return (await r.json()) as T;
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Monitor-Token": token() },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new ApiError(r.status, await errorMessage(r));
  return (await r.json()) as T;
}

const enc = encodeURIComponent;

function qs(params: Record<string, string | number | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

export const api = {
  analysis: (source: Source) => getJSON<Analysis>(`/api/analysis${qs({ source })}`),
  status: (source: Source) => getJSON<Status>(`/api/status${qs({ source })}`),
  sessions: (source: Source) => getJSON<SessionSummary[]>(`/api/sessions${qs({ source })}`),
  sessionActions: (source: Source, agent: string, sessionId: string) =>
    getJSON<EventRow[]>(`/api/sessions/${enc(agent)}/${enc(sessionId)}/actions${qs({ source })}`),
  incidents: (source: Source, recentHours?: number) =>
    getJSON<Incident[]>(`/api/incidents${qs({ source, recent_hours: recentHours })}`),
  eventsTail: (source: Source, n: number) => getJSON<EventsPage>(`/api/events${qs({ source, tail: n })}`),
  eventsAfter: (source: Source, after: number, fileId: number | null) =>
    getJSON<EventsPage>(`/api/events${qs({ source, after, file_id: fileId ?? undefined })}`),
  overview: () => getJSON<Overview | Missing | Failed>("/api/overview"),
  actions: (f: { agent: string; kind: string; q: string; page: number }) =>
    getJSON<ActionsPage>(`/api/actions${qs({ ...f, page_size: 50 })}`),
  alerts: () => getJSON<ScanResult | Missing | Failed>("/api/alerts"),
  evalResults: () => getJSON<EvalResults | Missing | Failed>("/api/eval"),
  rules: () => getJSON<RulesResponse>("/api/rules"),
  labelledFiles: () => getJSON<string[]>("/api/labelled-files"),
  runScan: (threshold: number, judgeSample: number) =>
    postJSON<{ job: Job }>("/api/run/scan", { threshold, judge_sample: judgeSample }),
  runEval: (labelled: string, noJudge: boolean) => postJSON<{ job: Job }>("/api/run/eval", { labelled, no_judge: noJudge }),
  job: (id: string) => getJSON<Job>(`/api/jobs/${enc(id)}`),
};

export function isMissing(x: unknown): x is Missing {
  return typeof x === "object" && x !== null && (x as Missing).missing === true;
}

export function isFailed(x: unknown): x is Failed {
  return typeof x === "object" && x !== null && typeof (x as Failed).error === "string";
}
