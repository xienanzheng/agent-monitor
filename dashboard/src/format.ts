export type Level = "none" | "low" | "medium" | "high" | "critical";

export function severityLevel(score: number): Level {
  if (score >= 9) return "critical";
  if (score >= 7) return "high";
  if (score >= 5) return "medium";
  if (score >= 3) return "low";
  return "none";
}

const CATEGORY_LABELS: Record<string, string> = {
  data_exfiltration: "Data exfiltration",
  resource_exposure: "Resource exposure",
  prompt_injection: "Prompt injection",
  infrastructure_disruption: "Infrastructure disruption",
  shared_resource_destruction: "Shared resource destruction",
  undesirable_deletion: "Undesirable deletion",
  oversight_subversion: "Oversight subversion",
  unsafe_agent: "Unsafe agent",
  untrusted_code_execution: "Untrusted code execution",
  real_world_transaction: "Real-world transaction",
  vulnerability_introduction: "Vulnerability introduction",
  unapproved_dependency: "Unapproved dependency",
  privilege_escalation: "Privilege escalation",
  other: "Other",
};

export function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? category;
}

const AUTHORIZATION_LABELS: Record<string, string> = {
  explicit: "Explicitly asked",
  implied: "Implied by the task",
  unclear: "Unclear",
  out_of_scope: "Out of scope",
  forbidden: "Forbidden",
};

export function authorizationLabel(value: string): string {
  return AUTHORIZATION_LABELS[value] ?? value;
}

export function timeAgo(ts: number | null | undefined, now: number = Date.now() / 1000): string {
  if (ts === null || ts === undefined) return "never";
  const d = Math.max(0, now - ts);
  if (d < 60) return `${Math.floor(d)}s ago`;
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`;
  return `${Math.floor(d / 86400)}d ago`;
}

export function clock(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function when(ts: number): string {
  return new Date(ts * 1000).toLocaleString();
}

export function short(id: string): string {
  return id.slice(0, 8);
}

export function pct(x: number | null | undefined): string {
  return x === null || x === undefined ? "–" : `${Math.round(x * 100)}%`;
}
