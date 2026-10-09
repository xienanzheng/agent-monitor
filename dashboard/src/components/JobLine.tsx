import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, type Job } from "../api";
import { clock } from "../format";

/** Track one job by id; onFinished runs once when it stops running (done or failed). */
export function useJobRunner(onFinished: () => void) {
  const [jobId, setJobId] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.job(jobId as string),
    enabled: jobId !== null,
    refetchInterval: (query) => (query.state.data?.status === "running" ? 1500 : false),
  });
  const job = q.data ?? null;
  const notified = useRef<string | null>(null);
  useEffect(() => {
    if (job && job.status !== "running" && notified.current !== job.id) {
      notified.current = job.id;
      onFinished();
    }
  }, [job, onFinished]);
  return { job, running: job?.status === "running", track: setJobId };
}

export default function JobLine({ job }: { job: Job | null }) {
  if (!job) return null;
  if (job.status === "running") {
    return (
      <p className="muted" role="status">
        Running {job.kind} (started {clock(job.started)})…
      </p>
    );
  }
  if (job.status === "failed") {
    return (
      <p className="error" role="status">
        The {job.kind} job failed: {job.error}
      </p>
    );
  }
  return (
    <p className="ok" role="status">
      The {job.kind} job finished{job.finished ? ` at ${clock(job.finished)}` : ""}.
    </p>
  );
}
