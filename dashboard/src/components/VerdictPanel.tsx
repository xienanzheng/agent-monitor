import type { Verdict } from "../api";
import { authorizationLabel, categoryLabel } from "../format";
import SeverityBadge from "./SeverityBadge";

/** "1. a 2. b" → ["a", "b"]; text without numbered steps stays one step. */
export function reasoningSteps(text: string): string[] {
  return text
    .split(/\s+(?=\d+\.\s)/)
    .map((s) => s.trim().replace(/^\d+\.\s*/, ""))
    .filter(Boolean);
}

export default function VerdictPanel({ title, verdict, testId }: { title: string; verdict: Verdict | null; testId: string }) {
  if (!verdict) {
    return (
      <section className="verdict" data-testid={testId}>
        <h3>{title}</h3>
        <p className="muted">Not run for this action.</p>
      </section>
    );
  }
  if (verdict.failed) {
    const causes: Record<string,string> = {timeout:"Inference timed out", truncated:"Response reached its generation limit", invalid_response:"Response failed validation", incomplete_response:"Response did not finish", model_unavailable:"Required model unavailable", unavailable:"Ollama unavailable", http_error:"Ollama request failed", empty_policy:"Monitoring policy missing", context_budget:"Evidence exceeds the reserved model context"};
    return (
      <section className="verdict" data-testid={testId}>
        <h3>{title}</h3>
        <p className="meta">{verdict.model} · {verdict.latency_s.toFixed(1)} s</p>
        {verdict.error_code && <p>{causes[verdict.error_code] ?? "Inference request failed"}</p>}
        <p className="warn">Judge failed: {verdict.reason || "no reply"}</p>
        {verdict.retry_errors && verdict.retry_errors.length > 0 && <p className="meta">Still incomplete after {verdict.request_attempts} requests. Earlier server error: {verdict.retry_errors.map(e => `HTTP ${e.http_status}`).join(", ")}.</p>}
      </section>
    );
  }
  const steps = reasoningSteps(verdict.reasoning || "");
  return (
    <section className="verdict" data-testid={testId}>
      <h3>
        {title} <SeverityBadge score={verdict.score} />{" "}
        <span className="muted">
          {verdict.model}
          {verdict.latency_s ? ` · ${verdict.latency_s.toFixed(1)} s` : ""}
        </span>
      </h3>
      <dl>
        <dt>Category</dt>
        <dd>{categoryLabel(verdict.category)}</dd>
        <dt>Authorization</dt>
        <dd>{authorizationLabel(verdict.authorization)}</dd>
        {verdict.boundary && (
          <>
            <dt>Boundary</dt>
            <dd>{verdict.boundary}</dd>
          </>
        )}
        <dt>Recoverability</dt>
        <dd>{verdict.recoverability}</dd>
        <dt>Confidence (self-reported)</dt>
        <dd>{Math.round(verdict.confidence * 100)}%</dd>
      </dl>
      {verdict.reason && <p className="reason">{verdict.reason}</p>}
      {verdict.retry_errors && verdict.retry_errors.length > 0 && <p className="meta">Completed after {verdict.request_attempts} requests. Retried server error: {verdict.retry_errors.map(e => `HTTP ${e.http_status} (${e.elapsed_s.toFixed(1)} s)`).join(", ")}. Retries share the original time budget.</p>}
      {verdict.timing && Object.keys(verdict.timing).length > 0 && <details><summary>Inference timing</summary><p className="meta">
        Load {(verdict.timing.load_s ?? 0).toFixed(1)} s · Prompt {(verdict.timing.prompt_s ?? 0).toFixed(1)} s · Generate {(verdict.timing.generation_s ?? 0).toFixed(1)} s
        {verdict.timing.output_tokens !== undefined && ` · ${verdict.timing.output_tokens} output tokens`}
      </p><p className="muted">Server timings exclude client overhead and may differ from total request latency.</p></details>}
      {steps.length > 0 && (
        <><h4>Evidence</h4><ol className="steps">
          {steps.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ol></>
      )}
    </section>
  );
}
