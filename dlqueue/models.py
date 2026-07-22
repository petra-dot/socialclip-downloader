import uuid
from enum import Enum


class DownloadStatus(Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class QueueItem:
    def __init__(self, url: str, options: dict = None):
        self.id = str(uuid.uuid4())[:8]
        self.url = url
        self.status = DownloadStatus.QUEUED
        self.options = options or {}
        self.retries = 0
        self.created_at = None
        self.error_message = ""
        self.progress = 0
