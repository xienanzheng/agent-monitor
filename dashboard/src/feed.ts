import type { EventRow } from "./api";
export const FEED_MAX = 300;
export function rowKey(r: EventRow): string {
  return r.action_id ?? `${r.agent}|${r.session_id}|${r.index}|${r.ts}`;
}
export function mergeAction(previous: EventRow, next: EventRow): EventRow {
  return { ...previous, ...next, final_severity: Math.max(previous.final_severity, next.final_severity),
    triage: next.triage ?? previous.triage, gateway: next.gateway ?? previous.gateway,
    output: next.output ?? previous.output };
}
/** One row per action, with revisions merged in file order. */
export function mergeFeed(current: EventRow[], incoming: EventRow[], reset: boolean, max = FEED_MAX): EventRow[] {
  const byId = new Map((reset ? [] : current).map(r => [rowKey(r), r]));
  for (const r of incoming) {
    const key = rowKey(r), previous = byId.get(key);
    byId.set(key, previous ? mergeAction(previous, r) : r);
  }
  return [...byId.values()].sort((a,b) => b.scored_ts - a.scored_ts).slice(0,max);
}
