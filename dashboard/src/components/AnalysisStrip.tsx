import { useQuery } from "@tanstack/react-query";
import { api, type Source } from "../api";
import { categoryLabel } from "../format";

export default function AnalysisStrip({ source }: {source: Source}) {
  const q = useQuery({queryKey: ["analysis", source], queryFn: () => api.analysis(source), refetchInterval: 5000});
  if (q.isError) return <p className="banner" role="alert">Analysis unavailable. Action counts could not be verified.</p>;
  if (!q.data) return <p role="status" className="muted">Loading action analysis…</p>;
  const a = q.data;
  const failures = Object.entries(a.judging.failures ?? {});
  return <section className="analysis" aria-label="Action analysis">
    <p className="meta">{source === "live" ? "Live · last 24 hours" : "Replay · complete selected recording"} · one count per action · flagged at severity ≥ {a.threshold}</p>
    <dl className="analysis-strip">
      <div><dt>Unique actions</dt><dd>{a.actions}</dd></div>
      <div><dt>Flagged actions</dt><dd>{a.flagged}<small> / {a.actions}</small></dd></div>
      <div><dt>Incomplete assessments</dt><dd className={a.incomplete ? "warn" : ""}>{a.incomplete}<small> / {a.actions}</small></dd></div>
      <div><dt>Median judging time</dt><dd>{a.judging.median_latency_s === null ? "Unavailable" : `${a.judging.median_latency_s.toFixed(1)} s`}<small> · {a.judging.actions} assessment attempts</small></dd></div>
    </dl>
    {(a.pending ?? 0)>0 && <p role="status" className="meta">Awaiting inference: {a.pending} action{a.pending === 1 ? "" : "s"}. Captured evidence is available; assessments are pending.</p>}
    {failures.length > 0 && <p className="meta">{failures.reduce((n,[,count]) => n+count,0)} failed stage calls / {a.judging.stage_attempts} stage calls · {failures.map(([cause,n]) => `${cause.replaceAll("_"," ")} ${n}`).join(" · ")}. Historical failures remain in this window.</p>}
    {(a.judging.recovered_actions ?? 0) > 0 && <p className="meta">Recovered by fallback: {a.judging.recovered_actions} action{a.judging.recovered_actions === 1 ? "" : "s"}; final assessments completed despite an earlier failed stage.</p>}
    {(a.judging.retried_actions ?? 0)>0 && <p className="meta">Server retries: {a.judging.retried_actions} action{a.judging.retried_actions === 1 ? "" : "s"} · {a.judging.request_attempts} requests across {a.judging.stage_attempts} stages. Final assessment states determine completeness.</p>}
    <p className="meta">Flagged categories ({a.flagged} action{a.flagged === 1 ? "" : "s"}): {Object.entries(a.categories).map(([c,n]) => `${categoryLabel(c)} ${n}`).join(" · ") || "none"}.
      {a.unknown_tools > 0 && <span className="warn"> {a.unknown_tools} unknown tools; coverage incomplete.</span>}</p>
  </section>;
}
