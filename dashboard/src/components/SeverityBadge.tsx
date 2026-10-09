import { severityLevel } from "../format";

export default function SeverityBadge({ score }: { score: number | null | undefined }) {
  if (score === null || score === undefined || Number.isNaN(score)) {
    return (
      <span className="sev sev-unknown" title="not scored">
        –
      </span>
    );
  }
  const level = severityLevel(score);
  const label = Number.isInteger(score) ? score.toFixed(0) : score.toFixed(1);
  return (
    <span className={`sev sev-${level}`} title={`severity ${score.toFixed(1)} (${level})`}>
      {label}
    </span>
  );
}

export function SeverityBar({ score }: { score: number }) {
  const width = Math.min(100, Math.max(0, score * 10));
  return (
    <span className="bar-track" title={`severity ${score.toFixed(1)}`}>
      <span className={`bar sev-${severityLevel(score)}`} style={{ width: `${width}%` }} />
    </span>
  );
}
