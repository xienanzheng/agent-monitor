import { useQuery } from "@tanstack/react-query";
import { api, isFailed, type RuleView } from "../api";
import { categoryLabel } from "../format";

function describe(r: RuleView): string {
  if (r.type === "sequence") return `${r.previous_tag} → ${r.current_tag} within ${r.within_actions} actions`;
  const parts: string[] = [];
  if (r.pattern) parts.push(`text ~ /${r.pattern}/`);
  if (r.kinds.length) parts.push(`kind in ${r.kinds.join(", ")}`);
  if (r.tags_any.length) parts.push(`any tag of ${r.tags_any.join(", ")}`);
  if (r.tags_all.length) parts.push(`all tags ${r.tags_all.join(", ")}`);
  if (r.add_tags.length) parts.push(`adds ${r.add_tags.join(", ")}`);
  return parts.join("; ");
}

function RulesByCategory({ rules }: { rules: RuleView[] }) {
  if (rules.length === 0) return <p className="empty">No rules yet.</p>;
  const groups = new Map<string, RuleView[]>();
  for (const r of rules) groups.set(r.category, [...(groups.get(r.category) ?? []), r]);
  return (
    <>
      {[...groups.entries()].map(([category, rs]) => (
        <section key={category}>
          <h2>{categoryLabel(category)}</h2>
          <div className="table-scroll" role="region" aria-label="Rules table, scroll for more columns" tabIndex={0}><table className="table">
            <thead>
              <tr>
                <th>Id</th>
                <th>Type</th>
                <th>Score</th>
                <th>Match</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {rs.map((r) => (
                <tr key={r.id}>
                  <td>{r.id}</td>
                  <td>{r.type}</td>
                  <td>{r.score}</td>
                  <td>{describe(r)}</td>
                  <td>{r.reason}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        </section>
      ))}
    </>
  );
}

export default function RulesPage() {
  const q = useQuery({ queryKey: ["rules"], queryFn: api.rules });
  if (q.isError) return <p className="error">Could not load rules: {String(q.error)}</p>;
  if (!q.data) return <p className="muted">Loading…</p>;
  const { rules, features } = q.data;
  return (
    <div>
      <h1>Rules</h1>
      <p className="muted">
        Read-only. Edit <code>rules/rules.json</code> and <code>rules/features.json</code>, then restart the daemon.
      </p>
      {isFailed(rules) ? (
        <div className="banner error" role="alert">
          rules.json is invalid: {rules.error}
        </div>
      ) : (
        <RulesByCategory rules={rules} />
      )}
      <h2>Vocabulary (features.json)</h2>
      {isFailed(features) ? (
        <div className="banner error" role="alert">
          features.json is invalid: {features.error}
        </div>
      ) : features.length === 0 ? (
        <p className="empty">No vocabulary yet.</p>
      ) : (
        <div className="table-scroll" role="region" aria-label="Rules table, scroll for more columns" tabIndex={0}><table className="table">
          <thead>
            <tr>
              <th>Tag</th>
              <th>Pattern</th>
              <th>Kinds</th>
              <th>Fields</th>
            </tr>
          </thead>
          <tbody>
            {features.map((f) => (
              <tr key={`${f.tag}|${f.pattern}`}>
                <td>{f.tag}</td>
                <td>
                  <code>{f.pattern}</code>
                </td>
                <td>{f.kinds.join(", ") || "any"}</td>
                <td>{f.fields.join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
    </div>
  );
}
