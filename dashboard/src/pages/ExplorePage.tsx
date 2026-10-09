import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useCallback, useState } from "react";
import { Bar, BarChart, ResponsiveContainer, CartesianGrid, Tooltip, XAxis, YAxis } from "recharts";
import { api, isFailed, isMissing, type Overview } from "../api";
import JobLine, { useJobRunner } from "../components/JobLine";
import SeverityBadge from "../components/SeverityBadge";

const KINDS = ["shell", "code_exec", "file_write", "file_read", "network", "browser", "mcp", "agent", "other"];
const BAR_COLOR = "#2864b7";

function toBars(counts: Record<string, number>) {
  return Object.entries(counts)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count);
}

export function fullAccessShare(o: Overview): number | null {
  const entries = Object.entries(o.policy ?? {});
  const total = entries.reduce((sum, [, v]) => sum + v, 0);
  if (!total) return null;
  const full = entries.filter(([k]) => k.includes("danger-full-access")).reduce((sum, [, v]) => sum + v, 0);
  return full / total;
}

export function fullAccessText(o: Overview): string {
  const share = fullAccessShare(o);
  return share === null
    ? "No sandbox policy recorded."
    : `${Math.round(share * 100)}% of Codex actions with a recorded sandbox policy ran with danger-full-access ` +
        "(Claude Code permission modes are not recorded by ingest).";
}

function OverviewSection({ overview }: { overview: Overview }) {
  return (
    <section>
      <h2>Traffic overview</h2>
      <div className="charts">
        <figure>
          <figcaption>Actions per agent</figcaption>
          <ResponsiveContainer width="100%" height={200}><BarChart data={toBars(overview.by_agent)}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" />
            <YAxis />
            <Tooltip />
            <Bar dataKey="count" fill={BAR_COLOR} />
          </BarChart></ResponsiveContainer>
        </figure>
        <figure>
          <figcaption>Actions per kind</figcaption>
          <ResponsiveContainer width="100%" height={200}><BarChart data={toBars(overview.by_kind)}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" />
            <YAxis />
            <Tooltip />
            <Bar dataKey="count" fill={BAR_COLOR} />
          </BarChart></ResponsiveContainer>
        </figure>
      </div>
      <p>{fullAccessText(overview)}</p>
      <h3>Top tools</h3>
      <div className="table-scroll" role="region" aria-label="Explore table, scroll for more columns" tabIndex={0}><table className="table compact">
        <tbody>
          {overview.top_tools.slice(0, 10).map(([tool, n]) => (
            <tr key={tool}>
              <td>{tool}</td>
              <td>{n}</td>
            </tr>
          ))}
        </tbody>
      </table></div>
    </section>
  );
}

function ActionBrowser({ agents }: { agents: string[] }) {
  const [agent, setAgent] = useState("");
  const [kind, setKind] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const res = useQuery({
    queryKey: ["actions", agent, kind, q, page],
    queryFn: () => api.actions({ agent, kind, q, page }),
    placeholderData: keepPreviousData,
  });
  const pages = res.data ? Math.max(1, Math.ceil(res.data.total / res.data.page_size)) : 1;
  return (
    <section>
      <h2>Actions</h2>
      <div className="filters">
        <select aria-label="agent" value={agent} onChange={(e) => { setAgent(e.target.value); setPage(1); }}>
          <option value="">all agents</option>
          {agents.map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </select>
        <select aria-label="kind" value={kind} onChange={(e) => { setKind(e.target.value); setPage(1); }}>
          <option value="">all kinds</option>
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        <input aria-label="search" placeholder="search text" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        <span className="muted">{res.data ? `${res.data.total} actions` : ""}</span>
      </div>
      {res.isPending && <p className="muted" role="status">Loading actions…</p>}
      {res.data?.total === 0 && <p className="empty">No actions match these filters.</p>}
      {res.isError && <p className="error">Could not load actions: {String(res.error)}</p>}
      <div className="table-scroll" role="region" aria-label="Explore table, scroll for more columns" tabIndex={0}><table className="table">
        <thead>
          <tr>
            <th>Agent</th>
            <th>Tool</th>
            <th>Kind</th>
            <th>Text</th>
          </tr>
        </thead>
        <tbody>
          {res.data?.rows.map((a, i) => (
            <tr key={`${a.session_id}|${a.index}|${i}`}>
              <td>{a.agent}</td>
              <td>{a.tool}</td>
              <td>{a.kind}</td>
              <td className="text" title={a.text}>
                <code>{a.text.slice(0, 300)}</code>
              </td>
            </tr>
          ))}
        </tbody>
      </table></div>
      <div className="pager">
        <button type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>
          Previous
        </button>
        <span>
          Page {page} of {pages}
        </span>
        <button type="button" disabled={page >= pages} onClick={() => setPage(page + 1)}>
          Next
        </button>
      </div>
    </section>
  );
}

function ScanForm() {
  const qc = useQueryClient();
  const [threshold, setThreshold] = useState(6);
  const [judgeSample, setJudgeSample] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(() => void qc.invalidateQueries({ queryKey: ["alerts"] }), [qc]);
  const run = useJobRunner(refresh);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const r = await api.runScan(threshold, judgeSample);
      run.track(r.job.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <form className="run" onSubmit={submit}>
      <label>
        Threshold{" "}
        <input type="number" min={0} max={10} step={0.5} value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} />
      </label>
      <label>
        Judge sample{" "}
        <input type="number" min={0} max={500} value={judgeSample} onChange={(e) => setJudgeSample(Number(e.target.value))} />
      </label>
      <button type="submit" disabled={run.running}>
        Re-run scan
      </button>
      <JobLine job={run.job} />
      {error && <p className="error">{error}</p>}
    </form>
  );
}

function AlertsSection() {
  const q = useQuery({ queryKey: ["alerts"], queryFn: api.alerts });
  const d = q.data;
  return (
    <section>
      <h2>Real-traffic scan</h2><p className="muted">Unlabelled traffic measures alert volume. False-positive rate is unavailable without ground-truth labels.</p>
      {q.isPending && <p role="status" className="muted">Loading…</p>}
      {q.isError && <p className="error">Could not load scan results: {String(q.error)}</p>}
      {d && isMissing(d) && <p className="empty">Not run yet.</p>}
      {d && isFailed(d) && (
        <p className="error" role="alert">
          {d.error}
        </p>
      )}
      {d && !isMissing(d) && !isFailed(d) && (
        <>
          <p>
            {d.provenance ? <span className="meta">{d.provenance.created_at} · rule threshold {d.provenance.threshold}<br/></span> : <span className="meta">Legacy scan · time and threshold provenance unavailable.<br/></span>}
            {d.n_alerts} alerts in {d.n_actions} actions ({d.alerts_per_1000 ?? "–"} per 1,000).
          </p>
          {d.judge_sample && (
            <p className="muted">
              Judge sample: {d.judge_sample.n_alerts} alerts in {d.judge_sample.n_scored} scored
              {d.judge_sample.judge_failures ? `, ${d.judge_sample.judge_failures} judge failures` : ""}.
            </p>
          )}
          <div className="table-scroll" role="region" aria-label="Explore table, scroll for more columns" tabIndex={0}><table className="table">
            <thead>
              <tr>
                <th>Score</th>
                <th>Agent</th>
                <th>Tool</th>
                <th>Text</th>
              </tr>
            </thead>
            <tbody>
              {d.top_alerts.map((a, i) => (
                <tr key={i}>
                  <td>
                    <SeverityBadge score={a.score} />
                  </td>
                  <td>{a.agent}</td>
                  <td>{a.tool}</td>
                  <td className="text" title={a.text}>
                    <code>{a.text}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table></div>
        </>
      )}
      <ScanForm />
    </section>
  );
}

export default function ExplorePage() {
  const ov = useQuery({ queryKey: ["overview"], queryFn: api.overview });
  const overview = ov.data && !isMissing(ov.data) && !isFailed(ov.data) ? ov.data : null;
  return (
    <div>
      <h1>Explore</h1>
      <p className="meta">Source: ingested historical traffic · complete stored file.</p>
      {ov.isPending && <p className="muted" role="status">Loading traffic overview…</p>}
      {ov.isError && <p className="error">Could not load the overview: {String(ov.error)}</p>}
      {ov.data && isMissing(ov.data) && (
        <p className="empty">
          No ingested traffic yet: run <code>uv run monitor ingest</code>.
        </p>
      )}
      {ov.data && isFailed(ov.data) && (
        <p className="error" role="alert">
          {ov.data.error}
        </p>
      )}
      {overview && <OverviewSection overview={overview} />}
      <ActionBrowser agents={overview ? Object.keys(overview.by_agent) : []} />
      <AlertsSection />
    </div>
  );
}
