import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type Source } from "../api";
import AnalysisStrip from "../components/AnalysisStrip";
import FeedRow from "../components/FeedRow";
import IncidentCard from "../components/IncidentCard";
import { rowKey } from "../feed";
import { useLiveFeed } from "../hooks/useLiveFeed";
import { useNow } from "../hooks/useNow";

export default function LivePage({ source }: { source: Source }) {
  const [onlyHigh, setOnlyHigh] = useState(false);
  const now = useNow();
  // Replayed events keep their recorded timestamps, so the 24 h window applies to live data only.
  const recentHours = source === "live" ? 24 : undefined;
  const incidents = useQuery({
    queryKey: ["incidents", source, "recent"],
    queryFn: () => api.incidents(source, recentHours),
    refetchInterval: 5000,
  });
  const feed = useLiveFeed(source);
  const rows = onlyHigh ? feed.rows.filter((r) => r.final_severity >= 5) : feed.rows;

  return (
    <div><h1>Live investigation</h1><AnalysisStrip source={source} /><div className="live">
      <section className="col">
        <h2>{source === "live" ? "Incidents (last 24 h)" : "Incidents (replay)"}</h2>
        {incidents.isPending && <p className="muted" role="status">Loading incidents…</p>}
        {incidents.isError && <p className="error">Could not load incidents: {String(incidents.error)}</p>}
        {incidents.data && incidents.data.length === 0 && <p className="empty">No incidents.</p>}
        {incidents.data?.map((i) => <IncidentCard key={i.id} incident={i} source={source} now={now} />)}
      </section>
      <section className="col">
        <div className="feed-head">
          <h2>Action stream</h2>
          <label>
            <input type="checkbox" checked={onlyHigh} onChange={(e) => setOnlyHigh(e.target.checked)} /> severity ≥ 5 only
          </label>
        </div>
        {feed.error && <p className="error">Feed error: {feed.error}</p>}
        {rows.length === 0 && !feed.error && <p className="empty">No events yet.</p>}
        <div className="rows">
          {rows.map((r) => (
            <FeedRow key={rowKey(r)} row={r} source={source} now={now} />
          ))}
        </div>
      </section>
    </div></div>
  );
}
