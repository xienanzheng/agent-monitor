import { Link } from "react-router-dom";
import type { Incident, Source } from "../api";
import { categoryLabel, short, timeAgo } from "../format";
import { withSource } from "../source";
import SeverityBadge from "./SeverityBadge";

export default function IncidentCard({ incident, source, now }: { incident: Incident; source: Source; now: number }) {
  const to = withSource(
    `/sessions/${encodeURIComponent(incident.agent)}/${encodeURIComponent(incident.session_id)}?incident=${encodeURIComponent(incident.id)}`,
    source,
  );
  const actions = `${incident.action_count} action${incident.action_count === 1 ? "" : "s"}`;
  return (
    <Link to={to} className="card incident" data-testid="incident-card">
      <SeverityBadge score={incident.severity} />
      <div>
        <div className="title">{categoryLabel(incident.category)}</div>
        <div className="sub">
          {incident.agent} · session {short(incident.session_id)} · {actions} · updated {timeAgo(incident.updated, now)}
        </div>
        {incident.latest_reason && <div className="reason">{incident.latest_reason}</div>}
      </div>
    </Link>
  );
}
