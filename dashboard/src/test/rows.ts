import type { EventRow, Verdict } from "../api";

export function verdict(over: Partial<Verdict> = {}): Verdict {
  return {
    score: 7,
    category: "data_exfiltration",
    authorization: "out_of_scope",
    boundary: "workspace to terminal output",
    recoverability: "low",
    confidence: 0.8,
    reason: "Outside the task.",
    reasoning: "1. The user asked to run the tests. 2. It prints a credential.",
    model: "qwen3:8b",
    latency_s: 6.4,
    failed: false,
    ...over,
  };
}

export function eventRow(over: Partial<EventRow> = {}): EventRow {
  return {
    ts: 1000,
    scored_ts: 1000,
    agent: "claude_code",
    session_id: "s1",
    index: 0,
    tool: "Bash",
    kind: "shell",
    text: "pytest -q",
    task: "",
    tags: [],
    rule_score: 0,
    rule_hits: [],
    rule_categories: [],
    triage: null,
    gateway: null,
    final_severity: 0,
    settled_by: "rules_low",
    judge_failed: false,
    category: "other",
    reason: "",
    incident_id: null,
    ...over,
  };
}
