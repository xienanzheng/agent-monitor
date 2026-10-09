import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api, type Source } from "../api";
import SeverityBadge from "../components/SeverityBadge";
import { short, timeAgo } from "../format";
import { useNow } from "../hooks/useNow";
import { withSource } from "../source";

export default function SessionsPage({ source }: { source: Source }) {
  const q = useQuery({ queryKey: ["sessions", source], queryFn: () => api.sessions(source), refetchInterval: 5000 });
  const navigate = useNavigate();
  const now = useNow();
  return (
    <div>
      <h1>Sessions</h1>
      {q.isPending && <p role="status" className="muted">Loading…</p>}
      {q.isError && <p className="error">Could not load sessions: {String(q.error)}</p>}
      {q.data && q.data.length === 0 && <p className="empty">No sessions yet.</p>}
      {q.data && q.data.length > 0 && (
        <div className="table-scroll" role="region" aria-label="Sessions table, scroll for more columns" tabIndex={0}><table className="table">
          <thead>
            <tr>
              <th>Agent</th>
              <th>Task</th>
              <th>Last activity</th>
              <th>Actions</th>
              <th>Highest</th>
              <th>Incidents</th>
            </tr>
          </thead>
          <tbody>
            {q.data.map((s) => (
              <tr
                key={`${s.agent}|${s.session_id}`}
                className="clickable"
                data-testid="session-row"
                tabIndex={0}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.currentTarget.click(); } }}
                onClick={() =>
                  navigate(withSource(`/sessions/${encodeURIComponent(s.agent)}/${encodeURIComponent(s.session_id)}`, source))
                }
              >
                <td>
                  {s.agent}
                  <div className="muted">{short(s.session_id)}</div>
                </td>
                <td className="text">{s.task || <span className="muted">(no task)</span>}</td>
                <td>{timeAgo(s.last_ts, now)}</td>
                <td>{s.actions}</td>
                <td>
                  <SeverityBadge score={s.max_severity} />
                </td>
                <td>{s.incidents}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
    </div>
  );
}
