import { useQuery } from "@tanstack/react-query";
import { api, type Source, type Status } from "../api";
import { timeAgo } from "../format";
import { useNow } from "../hooks/useNow";

function Light({ on, label, title }: { on: boolean; label: string; title: string }) {
  return (
    <span className={on ? "light on" : "light off"} title={title}>
      ● {label}
    </span>
  );
}

function Banners({ status }: { status: Status }) {
  const messages: string[] = [];
  if (!status.daemon.running) messages.push("Monitoring is off: run `uv run monitor daemon`.");
  if (status.health ? !Object.values(status.health.agents).some(a => a.configured && a.executable_ok) : !status.hooks.claude && !status.hooks.codex) {
    messages.push("No live hooks installed: run `uv run monitor install-hooks --agent claude`.");
  }
  if (status.hooks.claude_v1) {
    messages.push("The old v1 hook is installed in Claude Code and cannot read v2 rules: remove it with `uv run monitor uninstall-hook --backup <path>`.");
  }
  if (status.health?.ollama && (!status.health.ollama.reachable || status.health.ollama.missing.length)) messages.push(`Model coverage incomplete: ${status.health.ollama.reachable ? "missing " + status.health.ollama.missing.join(", ") : "Ollama unavailable"}.`);
  if (status.health?.coverage.unknown_tools) messages.push(`${status.health.coverage.unknown_tools} observed unknown tools; detection coverage is incomplete.`);
  if (messages.length === 0) return null;
  return (
    <div className="banners">
      {messages.map((m) => (
        <div key={m} className="banner">
          {m.split(/`([^`]+)`/).map((part,i) => i % 2 ? <code key={i}>{part}</code> : part)}
        </div>
      ))}
    </div>
  );
}

export default function StatusBar({ source, onSourceChange }: { source: Source; onSourceChange: (s: Source) => void }) {
  const q = useQuery({ queryKey: ["status", source], queryFn: () => api.status(source), refetchInterval: 5000 });
  const s = q.data;
  const now = useNow();
  return (
    <header className="statusbar">
      <strong className="brand">Agent Monitor</strong>
      {s ? (
        <>
          <Light on={s.daemon.responsive ?? s.daemon.running} label={s.daemon.running && s.daemon.responsive === false ? "daemon unresponsive" : "daemon"} title={s.daemon.running ? `listening on ${s.daemon.socket}` : "not running"} />
          {(["claude", "codex"] as const).map(agent => {
            const h = s.health?.agents[agent];
            const configured = h ? h.configured && h.executable_ok : s.hooks[agent];
            const state = !configured ? "unconfigured" : h?.observed ? "events observed" : "configured · awaiting events";
            return <Light key={agent} on={configured && Boolean(h?.observed)} label={`${agent === "claude" ? "Claude" : "Codex"}: ${state}`} title={h?.last_event_ts ? `Last observation ${timeAgo(h.last_event_ts, now)}; observations do not guarantee full coverage` : state} />;
          })}
          <span className="meta">last event {timeAgo(s.last_event_ts, now)}</span>
          {s.spool_backlog > 0 && <span className="meta warn">{s.spool_backlog} spooled</span>}
          {Boolean(s.hook_errors) && <span className="meta warn">{s.hook_errors} hook errors</span>}
          {s.daemon_errors > 0 && <span className="meta warn">{s.daemon_errors} daemon errors</span>}
          {s.unreadable_lines > 0 && <span className="meta warn">{s.unreadable_lines} unreadable lines</span>}
        </>
      ) : q.isError ? (
        <span className="meta warn">dashboard server unreachable</span>
      ) : (
        <span className="meta">loading…</span>
      )}
      <div className="toggle" role="group" aria-label="data source">
        {(["live", "replay"] as Source[]).map((x) => (
          <button key={x} type="button" aria-pressed={x === source} className={x === source ? "active" : ""} onClick={() => onSourceChange(x)}>
            {x === "live" ? "Live" : "Replay"}
          </button>
        ))}
      </div>
      {s && <Banners status={s} />}
    </header>
  );
}
