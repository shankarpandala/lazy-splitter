"""Cloud storage integration for lazy-splitter.

This package provides a unified interface for uploading, downloading, and
synchronising files with cloud storage providers (AWS S3, Google Cloud
Storage, Azure Blob Storage) as well as a local-filesystem backend for
testing and offline use.

Quick import examples::

    from lazy_splitter.cloud import CloudStorage, S3Storage, LocalStorage
    from lazy_splitter.cloud import create_storage
    from lazy_splitter.cloud import CloudSync
    from lazy_splitter.cloud import CloudFile, SyncResult
"""

from __future__ import annotations

from lazy_splitter.cloud.factory import (
    SUPPORTED_PROVIDERS,
    create_storage,
)
from lazy_splitter.cloud.models import (
    CloudFile,
    SyncResult,
)
from lazy_splitter.cloud.storage import (
    AzureBlobStorage,
    CloudStorage,
    GCSStorage,
    LocalStorage,
    S3Storage,
)
from lazy_splitter.cloud.sync import (
    CloudSync,
)

__all__ = [
    # Abstract base
    "CloudStorage",
    # Concrete implementations
    "S3Storage",
    "GCSStorage",
    "AzureBlobStorage",
    "LocalStorage",
    # Factory
    "create_storage",
    "SUPPORTED_PROVIDERS",
    # Sync
    "CloudSync",
    # Models
    "CloudFile",
    "SyncResult",
]
