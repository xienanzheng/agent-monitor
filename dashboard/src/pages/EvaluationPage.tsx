import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useCallback, useState } from "react";
import { api, isFailed, isMissing, type EvalResults } from "../api";
import JobLine, { useJobRunner } from "../components/JobLine";
import { pct } from "../format";

function ScorerTable({ results }: { results: EvalResults }) {
  const p = results.provenance;
  const legacy = results.schema_version !== 2 || !p;
  const first = Object.values(results.scorers)[0];
  if (legacy) return <>
    <p className="banner">Legacy measurements · unknown provenance. Dataset, prompts, and threshold selection cannot be verified.</p>
    <p className="muted">These are individual recorded measurements. Comparability is unverified; unavailable values (–) were not recorded.</p>
    {Object.entries(results.scorers).map(([name,r]) => <section key={name}>
      <h2>{name} · legacy measurement</h2>
      <div className="table-scroll" role="region" aria-label={`${name} legacy measurement, scroll for more columns`} tabIndex={0}><table className="table evaluation-table">
        <thead><tr><th>Scorer</th><th>AUC</th><th>Recorded recall at 1% / 5%</th><th>Stored threshold</th><th>TP / FP / TN / FN</th><th>Median action latency</th><th>Judge failures</th></tr></thead>
        <tbody><tr><td>{name}</td><td>{r.auc === null ? "–" : r.auc.toFixed(3)}</td>
          <td>{pct(r.tpr_at_fpr["0.01"])} / {pct(r.tpr_at_fpr["0.05"])}</td><td>{r.threshold_at_5pct ?? "–"}</td>
          <td>{r.test_confusion ? `${r.test_confusion.tp} / ${r.test_confusion.fp} / ${r.test_confusion.tn} / ${r.test_confusion.fn}` : "–"}</td>
          <td>{r.median_latency_ms === null ? "–" : `${r.median_latency_ms.toFixed(1)} ms`}</td>
          <td>{r.judge_calls ? `${r.judge_failures ?? 0} / ${r.judge_calls}` : "–"}</td></tr></tbody>
      </table></div>
    </section>)}
  </>;
  return <>
    <>
      <p className="meta">{p.dataset_kind === "original_synthetic" ? "Original synthetic trajectories" : "User-supplied labels"} · {p.dataset} · {results.split} split · {p.created_at}</p>
      <p>Thresholds selected on development data, then applied unchanged. {p.dev_trajectories} development / {p.test_trajectories} held-out trajectories.</p>
      <details><summary>Run provenance</summary><p>Models: {p.models.join(", ") || "rules only"}</p><dl className="provenance">{Object.entries(p.hashes).map(([k,v]) => <div key={k}><dt>{k}</dt><dd><code>{v}</code></dd></div>)}</dl></details>
    </>
    {first?.n_pos_total !== undefined && <p>Evaluated classes: <strong>{first.n_pos_total} harmful / {first.n_neg_total} benign</strong> · {first.n_test} actions before assessment exclusions.</p>}
    <p className="muted">Comparisons below share this run’s dataset and split. Rates use assessed actions; unavailable rates (–) have no class denominator or no valid threshold. AUC needs both classes. Judge coverage and failures are reported separately. Request counts include development threshold selection and the selected split; cached passes reuse assessments.</p>
    <div className="table-scroll" role="region" aria-label="Scorer comparison, scroll for more columns" tabIndex={0}><table className="table evaluation-table">
      <thead><tr><th>Scorer</th><th>Assessed classes</th><th>Coverage</th><th>AUC</th><th>Recall / miss</th><th>False alarm / precision</th><th>Recall at dev 1% / 5%</th><th>Threshold / achieved FPR</th><th>TP / FP / TN / FN</th><th>Median action latency</th><th>Judge failures</th></tr></thead>
      <tbody>{Object.entries(results.scorers).map(([name,r]) => <tr key={name}>
        <td>{name}</td><td>{r.n_pos ?? "–"} harmful / {r.n_neg ?? "–"} benign</td>
        <td>{r.n_scored ?? "–"} / {r.n_test} ({pct(r.coverage ?? null)})<br/>{r.n_incomplete ?? "–"} incomplete</td>
        <td>{r.auc === null ? "–" : r.auc.toFixed(3)}</td>
        <td>{pct(r.metrics?.recall ?? null)} / {pct(r.metrics?.miss_rate ?? null)}</td>
        <td>{pct(r.metrics?.false_alarm_rate ?? null)} / {pct(r.metrics?.precision ?? null)}</td>
        <td>{pct(r.tpr_at_fpr["0.01"])} / {pct(r.tpr_at_fpr["0.05"])}</td>
        <td>{r.operating_points?.["0.05"]?.reject_all ? "Reject all" : r.threshold_at_5pct ?? "–"} / {pct(r.operating_points?.["0.05"]?.actual_fpr ?? null)}</td>
        <td>{r.test_confusion ? `${r.test_confusion.tp} / ${r.test_confusion.fp} / ${r.test_confusion.tn} / ${r.test_confusion.fn}` : "–"}</td>
        <td>{r.median_latency_ms === null ? "–" : `${r.median_latency_ms.toFixed(1)} ms`}</td>
        <td>{r.judge_calls ? `${r.judge_failures ?? 0} / ${r.judge_calls}` : "–"}
          {r.inference_requests !== undefined && <><br/>{r.inference_requests} requests · {r.inference_retries ?? 0} {r.inference_retries===1 ? "retry" : "retries"}</>}
        </td>
      </tr>)}</tbody>
    </table></div>
    {Object.entries(results.scorers).map(([name,r]) => r.categories && <section key={name}>
      <h2>{name} · category results</h2>
      <div className="table-scroll" role="region" aria-label={`${name} category results, scroll for more columns`} tabIndex={0}><table className="table">
        <thead><tr><th>Category</th><th>Assessed / actions</th><th>Recall</th><th>Miss rate</th><th>False alarm rate</th><th>Precision</th><th>TP / FP / TN / FN</th></tr></thead>
        <tbody>{Object.entries(r.categories).map(([cat,c]) => <tr key={cat}><td>{cat.replaceAll("_"," ")}</td><td>{c.n_scored} / {c.n_actions}</td><td>{pct(c.metrics?.recall ?? null)}</td><td>{pct(c.metrics?.miss_rate ?? null)}</td><td>{pct(c.metrics?.false_alarm_rate ?? null)}</td><td>{pct(c.metrics?.precision ?? null)}</td><td>{c.confusion ? `${c.confusion.tp} / ${c.confusion.fp} / ${c.confusion.tn} / ${c.confusion.fn}` : "–"}</td></tr>)}</tbody>
      </table></div>
    </section>)}
    {results.limitations && <section><h2>Interpretation limits</h2><ul>{results.limitations.map(l => <li key={l}>{l}</li>)}</ul></section>}
  </>;
}

function EvalForm({ onFinished }: { onFinished: () => void }) {
  const files = useQuery({ queryKey: ["labelled-files"], queryFn: api.labelledFiles });
  const [labelled, setLabelled] = useState("");
  const [noJudge, setNoJudge] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const run = useJobRunner(onFinished);
  const chosen = labelled || files.data?.[0] || "";

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const r = await api.runEval(chosen, noJudge);
      run.track(r.job.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  if (files.data && files.data.length === 0) {
    return (
      <p className="muted">
        Put labelled <code>.jsonl</code> files in <code>data/labelled/</code> to run an eval here.
      </p>
    );
  }
  return (
    <form className="run" onSubmit={submit}>
      <h2>Re-run eval (dev split)</h2>
      <label>
        Labelled file{" "}
        <select value={chosen} onChange={(e) => setLabelled(e.target.value)}>
          {files.data?.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
      </label>
      <label>
        <input type="checkbox" checked={noJudge} onChange={(e) => setNoJudge(e.target.checked)} /> rules only (no judge)
      </label>
      <button type="submit" disabled={run.running || !chosen}>
        Re-run eval
      </button>
      <JobLine job={run.job} />
      {error && <p className="error">{error}</p>}
    </form>
  );
}

export default function EvaluationPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["eval"], queryFn: api.evalResults });
  const refresh = useCallback(() => void qc.invalidateQueries({ queryKey: ["eval"] }), [qc]);
  return (
    <div>
      <h1>Evaluation</h1>
      {q.isPending && <p role="status" className="muted">Loading…</p>}
      {q.isError && <p className="error">Could not load eval results: {String(q.error)}</p>}
      {q.data && isMissing(q.data) && (
        <p className="empty">
          No eval results yet: run one below or with <code>uv run monitor eval</code>.
        </p>
      )}
      {q.data && isFailed(q.data) && (
        <p className="error" role="alert">
          {q.data.error}
        </p>
      )}
      {q.data && !isMissing(q.data) && !isFailed(q.data) && <ScorerTable results={q.data} />}
      <EvalForm onFinished={refresh} />
    </div>
  );
}
