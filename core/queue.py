import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Callable, List, Optional

from core.manifest import DownloadResult
from utils.file_utils import OUTPUT_TEMPLATE, default_download_folder

STATES = ("pending", "running", "done", "failed", "cancelled", "paused",
          "skipped")

TERMINAL_STATES = ("done", "failed", "cancelled", "skipped")


def can_remove(state: str) -> bool:
    """A job may be removed unless it is currently running.

    The running job is owned by the worker thread; cancel it first.
    """
    return state != "running"

STORE_VERSION = 1


@dataclass
class QueueJob:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    url: str = ""
    title: str = ""
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


def build_job_options(save_dir: str, output_text: str, resolution: str,
                      cookies_path: str, subtitles: str = "off",
                      cookies_from_browser: str = "") -> dict:
    """Build the exact option set download_one accepts (no unknown keys)."""
    output_type = "MP3" if "MP3" in output_text else "MP4"
    return {
        "outtmpl": os.path.join(save_dir, OUTPUT_TEMPLATE),
        "output_type": output_type,
        "convert": output_type == "MP4",
        "target_resolution": int(resolution),
        "cookies_file": cookies_path,
        "subtitles": subtitles,
        "cookies_from_browser": cookies_from_browser,
    }


def resolve_outtmpl(options: Optional[dict]) -> str:
    """A job's output template: outtmpl, else output_dir, else the default."""
    opts = options or {}
    return opts.get("outtmpl") or os.path.join(
        opts.get("output_dir") or default_download_folder(),
        OUTPUT_TEMPLATE,
    )


_INT_FIELDS = ("bytes", "height", "attempts")


def _coerce_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _coerce_jobs(raw_jobs) -> List[QueueJob]:
    if not isinstance(raw_jobs, list):
        return []
    jobs: List[QueueJob] = []
    for raw in raw_jobs:
        if not isinstance(raw, dict):
            continue
        # Drop keys this build does not know instead of dropping the job: a
        # queue written by a newer or older build must not lose entries.
        known = QueueJob.__dataclass_fields__
        clean = {key: value for key, value in raw.items() if key in known}
        try:
            job = QueueJob(**clean)
        except (TypeError, ValueError):
            continue
        for name in _INT_FIELDS:
            setattr(job, name, _coerce_int(getattr(job, name)))
        jobs.append(job)
    return jobs


class QueueFileError(Exception):
    """The queue file exists but cannot be trusted; do not write over it."""


def _file_stamp(path: str):
    """Cheap identity for the file's current contents, or None if unreadable."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


class QueueStore:
    def __init__(self, path: str):
        self.path = path
        self.jobs: List[QueueJob] = []
        self.paused = False
        self._stamp = None
        self._seen = set()

    def _read(self) -> Optional[dict]:
        """Parsed queue data, or None when there is nothing to read.

        Raises QueueFileError when the file exists but does not parse or
        carries a version this build does not understand.
        """
        if not self.path:
            return None
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:
            raise QueueFileError(str(exc))
        if not isinstance(data, dict) or data.get("version") != STORE_VERSION:
            raise QueueFileError("unrecognised queue file version")
        self._stamp = _file_stamp(self.path)
        return data

    def load(self) -> None:
        self.jobs.clear()
        self.paused = False
        try:
            data = self._read()
        except QueueFileError:
            return
        if data is None:
            return
        self.paused = bool(data.get("paused", False))
        self.jobs.extend(_coerce_jobs(data.get("jobs")))
        self._seen = {job.id for job in self.jobs}

    def load_strict(self) -> None:
        """Load, refusing a file that exists but cannot be trusted.

        The headless host uses this: writing an empty list over a queue it
        failed to understand would lose the user's jobs.
        """
        self.jobs.clear()
        self.paused = False
        data = self._read()
        if data is None:
            return
        self.paused = bool(data.get("paused", False))
        self.jobs.extend(_coerce_jobs(data.get("jobs")))
        self._seen = {job.id for job in self.jobs}

    def _merge_from_disk(self) -> None:
        """Reconcile with jobs another writer changed since we last synced.

        Additions from the other writer are kept. A job this store held at the
        last sync and the disk no longer has was deleted elsewhere, so it goes
        too; a job added since that sync stays. Without both halves, clearing
        the queue while the host holds an older copy undoes the clear.
        """
        if not self.path or self._stamp is None:
            return
        if _file_stamp(self.path) == self._stamp:
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return
        if not isinstance(data, dict) or data.get("version") != STORE_VERSION:
            return
        disk = _coerce_jobs(data.get("jobs"))
        disk_ids = {job.id for job in disk}
        for job in list(self.jobs):
            if job.id not in disk_ids and job.id in self._seen:
                self.jobs.remove(job)
        current = {job.id for job in self.jobs}
        for job in disk:
            if job.id not in current:
                self.jobs.append(job)
                current.add(job.id)

    def save(self) -> None:
        if not self.path:
            return
        self._merge_from_disk()
        data = self.to_dict()
        tmp = f"{self.path}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, self.path)
        self._stamp = _file_stamp(self.path)
        self._seen = {job.id for job in self.jobs}

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

    def add(self, url: str, options: Optional[dict] = None,
            title: str = "") -> QueueJob:
        job = QueueJob(url=url, title=title, options=dict(options or {}))
        self.jobs.append(job)
        return job

    def add_many(self, urls, options: Optional[dict] = None) -> List[QueueJob]:
        return [self.add(url, options) for url in urls]

    def next_pending(self) -> Optional[QueueJob]:
        for job in self.jobs:
            if job.state == "pending":
                return job
        return None

    def claim_next(self) -> Optional[QueueJob]:
        """Take the first pending job: mark it running, count the attempt.

        The caller owns any locking; a concurrent caller must serialize this
        and apply_result against the shared job list.
        """
        if self.paused:
            return None
        job = self.next_pending()
        if job is None:
            return None
        job.state = "running"
        job.attempts += 1
        return job

    def apply_result(
        self, job: QueueJob, result: Optional[DownloadResult]
    ) -> QueueJob:
        """Map a finished run onto the job's terminal state."""
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
        elif result.error_category == "skipped":
            job.state = "skipped"
            if result.message:
                job.message = result.message
        else:
            job.state = "failed"
            job.message = result.message or ""
        return job

    def run_once(
        self, executor: Callable[[QueueJob], Optional[DownloadResult]]
    ) -> Optional[QueueJob]:
        job = self.claim_next()
        if job is None:
            return None
        try:
            result = executor(job)
        except Exception as exc:  # noqa: BLE001 - never let a job crash the loop
            job.state = "failed"
            job.message = str(exc)
            return job
        return self.apply_result(job, result)

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

    def remove_job(self, job_id: str) -> bool:
        """Delete a job outright. Refuses the one currently running."""
        for index, job in enumerate(self.jobs):
            if job.id == job_id and can_remove(job.state):
                del self.jobs[index]
                return True
        return False

    def retry_failed(self, job_id: Optional[str] = None) -> int:
        """Re-queue failed jobs (one, or all). Returns how many changed.

        ``attempts`` is kept: it is a retry counter. The stale failure message
        is cleared so the row reads clean until the next run.
        """
        count = 0
        for job in self.jobs:
            if job.state != "failed":
                continue
            if job_id is not None and job.id != job_id:
                continue
            job.state = "pending"
            job.message = ""
            count += 1
        return count

    def set_options(self, job_id: str, options: dict) -> bool:
        """Replace a pending job's options. False for any other state."""
        for job in self.jobs:
            if job.id == job_id and job.state == "pending":
                job.options = dict(options)
                return True
        return False
