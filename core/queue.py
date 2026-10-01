import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Callable, List, Optional

from core.manifest import DownloadResult

STATES = ("pending", "running", "done", "failed", "cancelled", "paused")

TERMINAL_STATES = ("done", "failed", "cancelled")

STORE_VERSION = 1


@dataclass
class QueueJob:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    url: str = ""
    state: str = "pending"
    message: str = ""
    path: Optional[str] = None
    bytes: int = 0
    height: int = 0
    attempts: int = 0
    options: dict = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


def _coerce_jobs(raw_jobs) -> List[QueueJob]:
    if not isinstance(raw_jobs, list):
        return []
    jobs: List[QueueJob] = []
    for raw in raw_jobs:
        if not isinstance(raw, dict):
            continue
        try:
            jobs.append(QueueJob(**raw))
        except (TypeError, ValueError):
            continue
    return jobs


class QueueStore:
    def __init__(self, path: str):
        self.path = path
        self.jobs: List[QueueJob] = []
        self.paused = False

    def load(self) -> None:
        self.jobs.clear()
        self.paused = False
        if not self.path:
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        if not isinstance(data, dict) or data.get("version") != STORE_VERSION:
            return
        self.paused = bool(data.get("paused", False))
        self.jobs.extend(_coerce_jobs(data.get("jobs")))

    def save(self) -> None:
        if not self.path:
            return
        data = self.to_dict()
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, self.path)

    def to_dict(self) -> dict:
        return {
            "version": STORE_VERSION,
            "paused": self.paused,
            "jobs": [asdict(j) for j in self.jobs],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "QueueStore":
        store = cls("")
        if isinstance(data, dict) and data.get("version") == STORE_VERSION:
            store.paused = bool(data.get("paused", False))
            store.jobs.extend(_coerce_jobs(data.get("jobs")))
        return store


class Queue:
    def __init__(self, store: Optional[QueueStore] = None):
        self.store = store if store is not None else QueueStore("")
        self.jobs: List[QueueJob] = self.store.jobs

    @property
    def paused(self) -> bool:
        return self.store.paused

    def add(self, url: str, options: Optional[dict] = None) -> QueueJob:
        job = QueueJob(url=url, options=dict(options or {}))
        self.jobs.append(job)
        return job

    def add_many(self, urls, options: Optional[dict] = None) -> List[QueueJob]:
        return [self.add(url, options) for url in urls]

    def next_pending(self) -> Optional[QueueJob]:
        for job in self.jobs:
            if job.state == "pending":
                return job
        return None

    def run_once(
        self, executor: Callable[[QueueJob], Optional[DownloadResult]]
    ) -> Optional[QueueJob]:
        if self.paused:
            return None
        job = self.next_pending()
        if job is None:
            return None
        job.state = "running"
        job.attempts += 1
        try:
            result = executor(job)
        except Exception as exc:  # noqa: BLE001 - never let a job crash the loop
            job.state = "failed"
            job.message = str(exc)
            return job
        if not isinstance(result, DownloadResult):
            job.state = "failed"
            job.message = "executor returned no result"
            return job
        if result.status == "ok":
            job.state = "done"
            job.path = result.path
            job.bytes = result.bytes or 0
            job.height = result.height or 0
            if result.message:
                job.message = result.message
        elif result.error_category == "cancelled":
            job.state = "cancelled"
            if result.message:
                job.message = result.message
        else:
            job.state = "failed"
            job.message = result.message or ""
        return job

    def pause(self) -> None:
        self.store.paused = True

    def resume(self) -> None:
        self.store.paused = False

    def cancel_all(self) -> None:
        for job in self.jobs:
            if job.state not in TERMINAL_STATES:
                job.state = "cancelled"

    def cancel_job(self, job_id: str) -> bool:
        for job in self.jobs:
            if job.id == job_id and job.state not in TERMINAL_STATES:
                job.state = "cancelled"
                return True
        return False
