"""One background job at a time (scan or eval). Errors are kept, redacted; results are written only on success."""
import threading
import time
import uuid
from dataclasses import dataclass

from monitor.redact import redact


@dataclass
class Job:
    id: str
    kind: str
    status: str
    started: float
    finished: float | None = None
    summary: dict | None = None
    error: str | None = None


class JobRunner:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.current: Job | None = None
        self._jobs: dict[str, Job] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    def start(self, kind: str, fn) -> tuple[Job, bool]:
        with self._lock:
            if self.current is not None and self.current.status == "running":
                return self.current, False
            job = Job(id=uuid.uuid4().hex[:12], kind=kind, status="running", started=self.clock())
            self.current = job
            self._jobs[job.id] = job
            t = threading.Thread(target=self._run, args=(job, fn), daemon=True, name=f"monitor-job-{job.id}")
            self._threads[job.id] = t
        t.start()
        return job, True

    def _run(self, job: Job, fn) -> None:
        try:
            summary, status, error = fn(), "done", None
        except Exception as e:  # a failed job is reported, never raised into the server
            summary, status, error = None, "failed", redact(f"{type(e).__name__}: {e}")[:500]
        job.summary, job.error, job.finished = summary, error, self.clock()
        job.status = status  # set last, so a finished job always has finished/summary/error filled in

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def wait(self, job_id: str, timeout: float | None = None) -> None:
        t = self._threads.get(job_id)
        if t is not None:
            t.join(timeout)
