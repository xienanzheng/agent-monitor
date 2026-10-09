import { useEffect, useState } from "react";
import { api, type EventRow, type Source } from "../api";
import { mergeFeed } from "../feed";

/** The last 50 rows, then new rows every few seconds from the byte-offset cursor. A shrunk file re-tails. */
export function useLiveFeed(source: Source, intervalMs = 3000): { rows: EventRow[]; error: string | null } {
  const [rows, setRows] = useState<EventRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cursor: number | null = null;
    let fileId: number | null = null;
    let stopped = false;
    let busy = false;
    setRows([]);

    async function tick(): Promise<void> {
      if (busy || stopped || document.hidden) return;
      busy = true;
      try {
        if (cursor === null) {
          const t = await api.eventsTail(source, 50);
          if (stopped) return;
          cursor = t.next;
          fileId = t.file_id;
          setRows(mergeFeed([], t.rows, true));
        } else {
          const page = await api.eventsAfter(source, cursor, fileId);
          if (stopped) return;
          if (page.reset) {
            cursor = null;
          } else {
            cursor = page.next;
            fileId = page.file_id;
            if (page.rows.length > 0) setRows((prev) => mergeFeed(prev, page.rows, false));
          }
        }
        setError(null);
      } catch (e) {
        if (!stopped) setError(e instanceof Error ? e.message : String(e));
      } finally {
        busy = false;
      }
    }

    void tick();
    const id = window.setInterval(() => void tick(), intervalMs);
    return () => {
      stopped = true;
      window.clearInterval(id);
    };
  }, [source, intervalMs]);

  return { rows, error };
}
