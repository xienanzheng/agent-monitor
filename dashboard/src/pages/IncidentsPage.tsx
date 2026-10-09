import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, type Source } from "../api";
import SeverityBadge from "../components/SeverityBadge";
import { categoryLabel, short, when } from "../format";
import { withSource } from "../source";

export default function IncidentsPage({ source }: { source: Source }) {
  const q = useQuery({ queryKey: ["incidents", source, "all"], queryFn: () => api.incidents(source), refetchInterval: 5000 });
  const [params] = useSearchParams();
  const highlight = params.get("highlight");
  const navigate = useNavigate();
  return (
    <div>
      <h1>Incidents</h1>
      {q.isPending && <p role="status" className="muted">Loading…</p>}
      {q.isError && <p className="error">Could not load incidents: {String(q.error)}</p>}
      {q.data && q.data.length === 0 && <p className="empty">No incidents.</p>}
      {q.data && q.data.length > 0 && (
        <div className="table-scroll" role="region" aria-label="Incidents table, scroll for more columns" tabIndex={0}><table className="table">
          <thead>
            <tr>
              <th>Severity</th>
              <th>Category</th>
              <th>Agent</th>
              <th>Session</th>
              <th>Opened</th>
              <th>Updated</th>
              <th>Signals</th>
              <th>Actions</th>
              <th>Latest reason</th>
            </tr>
          </thead>
          <tbody>
            {q.data.map((i) => (
              <tr
                key={i.id}
                className={i.id === highlight ? "clickable hl" : "clickable"}
                tabIndex={0}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.currentTarget.click(); } }}
                onClick={() =>
                  navigate(
                    withSource(
                      `/sessions/${encodeURIComponent(i.agent)}/${encodeURIComponent(i.session_id)}?incident=${encodeURIComponent(i.id)}`,
                      source,
                    ),
                  )
                }
              >
                <td>
                  <SeverityBadge score={i.severity} />
                </td>
                <td>{categoryLabel(i.category)}</td>
                <td>{i.agent}</td>
                <td>{short(i.session_id)}</td>
                <td>{when(i.opened)}</td>
                <td>{when(i.updated)}</td>
                <td>{i.signals.join(", ")}</td>
                <td>{i.action_count}</td>
                <td className="text" title={i.latest_reason}>
                  {i.latest_reason}
                </td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
    </div>
  );
}
