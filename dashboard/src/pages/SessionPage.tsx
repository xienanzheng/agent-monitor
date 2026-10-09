import { useQuery } from "@tanstack/react-query";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api, type Source } from "../api";
import ActionPanel from "../components/ActionPanel";
import { SeverityBar } from "../components/SeverityBadge";
import { clock } from "../format";
import { withSource } from "../source";

export default function SessionPage({ source }: { source: Source }) {
  const { agent = "", sessionId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const q = useQuery({
    queryKey: ["session", source, agent, sessionId],
    queryFn: () => api.sessionActions(source, agent, sessionId),
    refetchInterval: 5000,
  });
  const rows = q.data ?? [];
  const actionParam = params.get("action");
  const incident = params.get("incident");
  const tsParam = params.get("ts");
  const selected =
    actionParam === null ? [] : rows.filter((r) => String(r.index) === actionParam && (tsParam === null || String(r.ts) === tsParam));
  const task = [...rows].reverse().find((r) => r.task)?.task ?? "";

  function setAction(index: number | null, ts?: number) {
    const p = new URLSearchParams(params);
    if (index === null) {
      p.delete("action");
      p.delete("ts");
    } else {
      p.set("action", String(index));
      if (ts !== undefined) p.set("ts", String(ts));
    }
    setParams(p);
  }

  return (
    <div>
      <p>
        <Link to={withSource("/sessions", source)}>← Sessions</Link>
      </p>
      <h1>{task || "(no task recorded)"}</h1>
      <p className="muted">
        {agent} · session {sessionId}
      </p>
      {q.isPending && <p role="status" className="muted">Loading…</p>}
      {q.isError && <p className="error">Could not load this session: {String(q.error)}</p>}
      {q.data && rows.length === 0 && <p className="empty">No actions recorded for this session.</p>}
      <ol className="timeline">
        {rows.map((r, i) => {
          const post = ["rules_post", "output_update"].includes(r.settled_by);
          const isSelected = String(r.index) === actionParam && (tsParam === null || String(r.ts) === tsParam);
          const classes = [post ? "post" : "", incident && r.incident_id === incident ? "hl" : "", isSelected ? "sel" : ""]
            .filter(Boolean)
            .join(" ");
          return (
            <li
              key={i}
              className={classes}
              data-testid="timeline-row"
              role="button"
              tabIndex={0}
              onClick={() => setAction(r.index, r.ts)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setAction(r.index, r.ts); }
              }}
            >
              <span className="time">{clock(r.ts)}</span>
              <span className="kind">{r.kind}</span>
              <span className="text" title={r.text}>
                {post ? (r.settled_by === "rules_post" ? "↳ rescored after its output" : "↳ output received") : r.text}
              </span>
              <span className="chips">
                {r.tags.map((t) => (
                  <span key={t} className="chip">
                    {t}
                  </span>
                ))}
              </span>
              <span className="hits">{r.rule_hits.join(", ")}</span>
              <SeverityBar score={r.final_severity} />
            </li>
          );
        })}
      </ol>
      {selected.length > 0 && <ActionPanel rows={selected} source={source} onClose={() => setAction(null)} />}
    </div>
  );
}
