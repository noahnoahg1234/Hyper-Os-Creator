"""Background jobs (downloads, builds) with progress for the web UI."""
from __future__ import annotations

import threading
import time
import traceback
import uuid
from typing import Any, Callable, Dict, List, Optional


class Job:
    def __init__(self, title: str):
        self.id = uuid.uuid4().hex[:12]
        self.title = title
        self.status = "running"
        self.done = 0
        self.total = 0
        self.message = ""
        self.result: Any = None
        self.error: Optional[str] = None
        self.started = time.time()
        self.cancelled = False

    def progress(self, done: int, total: int) -> None:
        self.done, self.total = done, total

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "title": self.title, "status": self.status, "done": self.done, "total": self.total,
                "message": self.message, "result": self.result, "error": self.error, "started": self.started}


_jobs: Dict[str, Job] = {}
_lock = threading.Lock()


def start(title: str, fn: Callable[[Job], Any]) -> Job:
    job = Job(title)

    def run() -> None:
        try:
            job.result = fn(job)
            job.status = "done"
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI
            job.status = "error"
            job.error = f"{exc}"
            job.message = traceback.format_exc(limit=3)
    with _lock:
        _jobs[job.id] = job
    threading.Thread(target=run, daemon=True).start()
    return job


def get(job_id: str) -> Optional[Job]:
    return _jobs.get(job_id)


def all_jobs() -> List[Dict[str, Any]]:
    return [j.to_dict() for j in sorted(_jobs.values(), key=lambda j: -j.started)][:50]
