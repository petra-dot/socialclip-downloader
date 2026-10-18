"""A persistent list of files waiting to be converted.

Qt-free and thread-free: the worker owns the thread, this owns the data and the
pure transitions. Mirrors core/queue.py so the two lists behave the same way.
"""

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

STORE_VERSION = 1

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

TERMINAL_STATES = (STATUS_DONE, STATUS_FAILED, STATUS_CANCELLED)


@dataclass
class ConvertJob:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    path: str = ""
    target_format: str = "mp4"
    resolution: int = 0
    copy_streams: Optional[bool] = None
    state: str = STATUS_PENDING
    message: str = ""
    output_path: str = ""
    added_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


def _options_dict(options) -> dict:
    options = options or {}
    return {
        "target_format": options.get("target_format") or "mp4",
        "resolution": int(options.get("resolution") or 0),
        "copy_streams": options.get("copy_streams"),
    }


class ConvertQueue:
    """The job list plus the pure transitions the worker drives."""

    def __init__(self, store=None):
        self.store = store
        self.jobs: List[ConvertJob] = []

    def add(self, paths, options) -> List[ConvertJob]:
        known = {job.path for job in self.jobs}
        baked = _options_dict(options)
        added = []
        for path in paths:
            path = (path or "").strip()
            if not path or path in known:
                continue
            known.add(path)
            job = ConvertJob(path=path, **baked)
            self.jobs.append(job)
            added.append(job)
        return added

    def _find(self, job_id) -> Optional[ConvertJob]:
        for job in self.jobs:
            if job.id == job_id:
                return job
        return None

    def remove(self, job_id) -> bool:
        job = self._find(job_id)
        if job is None or job.state == STATUS_RUNNING:
            return False
        self.jobs.remove(job)
        return True

    def set_options(self, job_ids, options) -> int:
        baked = _options_dict(options)
        wanted = set(job_ids)
        changed = 0
        for job in self.jobs:
            if job.id in wanted and job.state == STATUS_PENDING:
                job.target_format = baked["target_format"]
                job.resolution = baked["resolution"]
                job.copy_streams = baked["copy_streams"]
                changed += 1
        return changed

    def claim_next(self) -> Optional[ConvertJob]:
        for job in self.jobs:
            if job.state == STATUS_PENDING:
                job.state = STATUS_RUNNING
                return job
        return None

    def apply_result(self, job_id, result) -> None:
        job = self._find(job_id)
        if job is None:
            return
        category = getattr(result, "error_category", None)
        if getattr(result, "status", "") == "ok":
            job.state = STATUS_DONE
            job.output_path = getattr(result, "path", "") or ""
            job.message = getattr(result, "message", "") or ""
        elif category == "cancelled":
            job.state = STATUS_CANCELLED
            job.message = getattr(result, "message", "") or "Cancelled."
        else:
            job.state = STATUS_FAILED
            job.message = getattr(result, "message", "") or "Conversion failed."

    def retry_failed(self, job_id=None) -> int:
        count = 0
        for job in self.jobs:
            if job.state == STATUS_FAILED and (job_id is None or job.id == job_id):
                job.state = STATUS_PENDING
                job.message = ""
                count += 1
        return count

    def clear_finished(self) -> int:
        before = len(self.jobs)
        self.jobs[:] = [job for job in self.jobs
                        if job.state not in TERMINAL_STATES]
        return before - len(self.jobs)

    def pending_count(self) -> int:
        return sum(1 for job in self.jobs if job.state == STATUS_PENDING)


def _coerce_jobs(raw) -> List[ConvertJob]:
    if not isinstance(raw, list):
        return []
    known = ConvertJob.__dataclass_fields__
    out: List[ConvertJob] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        clean = {k: v for k, v in item.items() if k in known}
        try:
            out.append(ConvertJob(**clean))
        except (TypeError, ValueError):
            continue
    return out


class ConvertStore:
    """convert.json. Atomic write, tolerant load, never drops a job."""

    def __init__(self, path: Optional[str] = None):
        # Imported here, not at module level: core.paths.convert_path() is added
        # in Task 2, and this module must import cleanly before it exists.
        if path is None:
            from core.paths import convert_path
            path = convert_path()
        self.path = path
        self.jobs: List[ConvertJob] = []

    def load(self) -> None:
        self.jobs = []
        if not self.path:
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        if not isinstance(data, dict) or data.get("version") != STORE_VERSION:
            return
        self.jobs.extend(_coerce_jobs(data.get("jobs")))
        # A job cannot be running across a restart: demote anything the last
        # session left mid-flight so it can be retried or removed.
        for job in self.jobs:
            if job.state == STATUS_RUNNING:
                job.state = STATUS_PENDING

    def save(self) -> None:
        if not self.path:
            return
        data = {"version": STORE_VERSION,
                "jobs": [asdict(job) for job in self.jobs]}
        tmp = "%s.%d.%s.tmp" % (self.path, os.getpid(), uuid.uuid4().hex)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, self.path)
