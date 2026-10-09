import { Link } from "react-router-dom";
import type { EventRow, Source } from "../api";
import { clock } from "../format";
import { withSource } from "../source";
import SeverityBadge from "./SeverityBadge";

export default function FeedRow({ row, source, now }: { row: EventRow; source: Source; now: number }) {
  const to = withSource(
    `/sessions/${encodeURIComponent(row.agent)}/${encodeURIComponent(row.session_id)}?action=${row.index}&ts=${row.ts}`,
    source,
  );
  const fresh = now - row.scored_ts < 10;
  const status = row.assessment_state === "pending" ? "Pending" : row.judge_failed || row.assessment_state === "incomplete" ? "Incomplete" : row.coverage === "unknown_tool" ? "Unknown tool" : "";
  const stage = row.gateway && !row.gateway.failed ? "Gateway" : row.triage && !row.triage.failed ? "Triage" : "Rules";
  return (
    <Link to={to} className={fresh ? "row fresh" : "row"} data-testid="feed-row">
      <span className="time">{clock(row.ts)}</span>
      <span className="agent">{row.agent}</span>
      <span className="kind">{row.kind}</span>
      <span className="text" title={row.text}>
        {row.text}
      </span>
      <span className="action-risk"><SeverityBadge score={row.final_severity} />{status && <small className="warn">{status}</small>}</span>
      <span className="settled">{row.assessment_state === "pending" ? "Awaiting review" : stage}{row.output ? " · output" : ""}</span>
    </Link>
  );
}
