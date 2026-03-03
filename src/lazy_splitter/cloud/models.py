"""Cloud-specific data models for lazy-splitter.

These dataclasses represent cloud file metadata and synchronisation results.
They are deliberately lightweight and serialisable so they can be written to
checkpoint files or returned by any storage backend.
"""

from __future__ import annotations

import dataclasses
import datetime
from typing import Any, Dict, List, Optional


@dataclasses.dataclass
class CloudFile:
    """Metadata for a single file stored in a cloud (or local) backend.

    Attributes
    ----------
    name:
        Base file name (e.g. ``"chapter_01.pdf"``).
    path:
        Full remote path or key (e.g. ``"books/chapter_01.pdf"``).
    size:
        File size in bytes.
    last_modified:
        Timestamp of the most recent modification.
    content_type:
        MIME content type (e.g. ``"application/pdf"``).
    url:
        Public or pre-signed URL for downloading the file, or an empty
        string when not applicable.
    checksum:
        Optional hex-digest checksum (algorithm varies by provider).
    metadata:
        Arbitrary extra data supplied by the storage backend.
    """

    name: str
    path: str
    size: int = 0
    last_modified: Optional[datetime.datetime] = None
    content_type: str = "application/octet-stream"
    url: str = ""
    checksum: Optional[str] = None
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a JSON-safe dictionary."""
        return {
            "name": self.name,
            "path": self.path,
            "size": self.size,
            "last_modified": self.last_modified.isoformat()
            if self.last_modified
            else None,
            "content_type": self.content_type,
            "url": self.url,
            "checksum": self.checksum,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CloudFile":
        """Reconstruct from a dictionary (e.g. loaded from a checkpoint)."""
        last_modified = data.get("last_modified")
        if isinstance(last_modified, str):
            last_modified = datetime.datetime.fromisoformat(last_modified)
        return cls(
            name=data["name"],
            path=data["path"],
            size=data.get("size", 0),
            last_modified=last_modified,
            content_type=data.get("content_type", "application/octet-stream"),
            url=data.get("url", ""),
            checksum=data.get("checksum"),
            metadata=data.get("metadata", {}),
        )


@dataclasses.dataclass
class SyncResult:
    """Aggregate result of a synchronisation operation.

    Attributes
    ----------
    uploaded:
        Number of files that were uploaded to the remote backend.
    downloaded:
        Number of files that were downloaded from the remote backend.
    skipped:
        Number of files that were unchanged and therefore skipped.
    errors:
        List of ``"path: error_message"`` strings for failed transfers.
    duration:
        Wall-clock time in seconds consumed by the synchronisation.
    """

    uploaded: int = 0
    downloaded: int = 0
    skipped: int = 0
    errors: List[str] = dataclasses.field(default_factory=list)
    duration: float = 0.0

    # -- Properties ----------------------------------------------------------

    @property
    def total_transferred(self) -> int:
        """Total number of files that were actually transferred."""
        return self.uploaded + self.downloaded

    @property
    def success(self) -> bool:
        """Whether the sync completed without any errors."""
        return len(self.errors) == 0

    # -- Public methods ------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a JSON-safe dictionary."""
        return {
            "uploaded": self.uploaded,
            "downloaded": self.downloaded,
            "skipped": self.skipped,
            "errors": list(self.errors),
            "duration": self.duration,
            "total_transferred": self.total_transferred,
            "success": self.success,
        }
