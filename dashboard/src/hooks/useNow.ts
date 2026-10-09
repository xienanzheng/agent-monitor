import { useEffect, useState } from "react";

/** The current time in seconds, refreshed every `intervalMs`, so relative times ("12s ago") keep ageing. */
export function useNow(intervalMs = 5000): number {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now() / 1000), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return now;
}
