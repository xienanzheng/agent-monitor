import { useEffect, useRef } from "react";
import { mergeAction } from "../feed";
import { Link } from "react-router-dom";
import type { EventRow, Source } from "../api";
import { withSource } from "../source";
import SeverityBadge from "./SeverityBadge";
import VerdictPanel from "./VerdictPanel";

function Chips({ tags }: { tags: string[] }) {
  if (tags.length === 0) return null;
  return (
    <div className="chips">
      {tags.map((t) => (
        <span key={t} className="chip">
          {t}
        </span>
      ))}
    </div>
  );
}

function judgeGaveReason(r: EventRow): boolean {
  return [r.gateway, r.triage].some((v) => v !== null && !v.failed && Boolean(v.reason));
}

export default function ActionPanel({ rows, source, onClose }: { rows: EventRow[]; source: Source; onClose: () => void }) {
  const panel = useRef<HTMLElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  const callback = useRef(onClose);
  callback.current = onClose;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    close.current?.focus();
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); callback.current(); }
      if (e.key === "Tab") {
        const targets = [...(panel.current?.querySelectorAll<HTMLElement>('button, a[href], input, [tabindex="0"]') ?? [])];
        const first = targets[0], last = targets[targets.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }
    };
    const node = panel.current;
    node?.addEventListener("keydown", handleKey);
    return () => { node?.removeEventListener("keydown", handleKey); if (previous?.isConnected) previous.focus(); };
  }, []);
  const initial = rows.find(r => !["rules_post", "output_update"].includes(r.settled_by)) ?? rows[0];
  const merged = rows.reduce(mergeAction, initial);
  const decision = [...rows].reverse().find(r => !["pending", "rules_post", "output_update"].includes(r.settled_by)) ?? merged;
  const main = { ...merged, text: initial.text, task: initial.task, reason: decision.reason, settled_by: decision.settled_by, judge_failed: decision.judge_failed };
  const rescored = rows.filter((r) => r !== initial && r.settled_by === "rules_post");
  const incidentIds = [...new Set(rows.map((r) => r.incident_id).filter((id): id is string => Boolean(id)))];
  return (
    <><div className="panel-backdrop" aria-hidden="true" onClick={onClose} /><aside ref={panel} role="dialog" aria-modal="true" className="panel" data-testid="action-panel" aria-label="action detail">
      <button ref={close} type="button" className="close" onClick={onClose} aria-label="close">
        ×
      </button>
      <h2>
        {main.tool} <span className="muted">· {main.kind} · #{main.index}</span> <SeverityBadge score={main.final_severity} />
      </h2>
      <h3>Task</h3>
      <p>{main.task || "No task recorded; authorization is uncertain."}</p>
      <h3>Action</h3>
      {main.tool_use_id && <p className="meta">Call <code>{main.tool_use_id}</code> · {main.outcome || "pending"}</p>}
      <pre className="cmd">{main.text}</pre>
      {main.output && (
        <>
          <h3>Output</h3>
          <pre className="cmd">{main.output}</pre>
        </>
      )}
      {main.assessment_state === "pending" ? <p role="status">Assessment pending. Tool output is captured; model review is still running.</p> : <p>
        Settled by <strong>{main.settled_by}</strong>
        {main.judge_failed && <span className="warn"> · a judge failed; evaluation is incomplete. Available rule evidence is retained</span>}
      </p>}
      {main.assessment_state === "incomplete" && !main.judge_failed && <p className="banner">Evaluation incomplete; this action is not an all-clear.</p>}
      {main.coverage === "unknown_tool" && <p className="banner">Unknown tool: capture is available; detection coverage is incomplete.</p>}
      <Chips tags={main.tags} />
      <h3>Rule evidence · score {main.rule_score}</h3>
      {main.rule_hits.length > 0 ? (
        <ul>
          {main.rule_hits.map((h) => (
            <li key={h}>{h}</li>
          ))}
        </ul>
      ) : (
        <p className="muted">None.</p>
      )}
      {main.rule_reasons?.map((reason,i) => <p className="reason" key={i}>{reason}</p>)}
      {!main.rule_reasons && main.reason && !judgeGaveReason(main) && <p className="reason">Rule reasons: {main.reason}</p>}
      <VerdictPanel title="Triage" verdict={main.triage} testId="verdict-triage" />
      <VerdictPanel title="Gateway" verdict={main.gateway} testId="verdict-gateway" />
      {incidentIds.map((id) => (
        <p key={id}>
          <Link to={withSource(`/incidents?highlight=${encodeURIComponent(id)}`, source)}>Incident {id}</Link>
        </p>
      ))}
      {rescored.map((r, i) => (
        <section key={i} className="rescored">
          <h3>
            Rescored after its output <SeverityBadge score={r.final_severity} />
          </h3>
          <Chips tags={r.tags} />
          <p>Rule hits: {r.rule_hits.join(", ") || "none"}</p>
          {r.reason && <p className="reason">{r.reason}</p>}
        </section>
      ))}
    </aside></>
  );
}
