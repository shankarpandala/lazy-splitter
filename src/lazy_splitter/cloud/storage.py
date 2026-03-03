"""Abstract cloud storage interface and concrete provider implementations.

This module defines :class:`CloudStorage`, an abstract base class that
normalises file operations across cloud providers, and four concrete
implementations:

* :class:`S3Storage` -- Amazon S3 (via ``boto3``)
* :class:`GCSStorage` -- Google Cloud Storage (via ``google-cloud-storage``)
* :class:`AzureBlobStorage` -- Azure Blob Storage (via ``azure-storage-blob``)
* :class:`LocalStorage` -- Local filesystem (useful for tests and offline work)

Third-party SDK packages are imported lazily so that only the provider
actually in use needs to be installed.
"""

from __future__ import annotations

import datetime
import fnmatch
import logging
import mimetypes
import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, List, Optional

from lazy_splitter.core.exceptions import CloudError
from lazy_splitter.core.utils import generate_checksum

from lazy_splitter.cloud.models import CloudFile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional third-party imports -- deferred to class bodies so that the
# module can always be imported regardless of which SDKs are installed.
# ---------------------------------------------------------------------------

_BOTO3_INSTALL_HINT = (
    "boto3 is required for S3 storage. "
    "Install it with: pip install boto3"
)

_GCS_INSTALL_HINT = (
    "google-cloud-storage is required for GCS storage. "
    "Install it with: pip install google-cloud-storage"
)

_AZURE_INSTALL_HINT = (
    "azure-storage-blob is required for Azure Blob storage. "
    "Install it with: pip install azure-storage-blob"
)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class CloudStorage(ABC):
    """Abstract interface for cloud file storage operations.

    Every concrete subclass must implement the six CRUD + query methods
    listed below.  Implementations should raise :class:`CloudError` for
    any provider-specific failure so that callers only need to handle a
    single exception type.
    """

    @abstractmethod
    def upload(self, local_path: str, remote_path: str) -> str:
        """Upload a local file to the remote storage backend.

        Parameters
        ----------
        local_path:
            Path to the file on the local filesystem.
        remote_path:
            Destination key / path in the remote storage.

        Returns
        -------
        str
            A URL (or URI) that can be used to reference the uploaded file.

        Raises
        ------
        CloudError
            If the upload fails for any reason.
        """

    @abstractmethod
    def download(self, remote_path: str, local_path: str) -> Path:
        """Download a file from remote storage to the local filesystem.

        Parameters
        ----------
        remote_path:
            Key / path of the file in the remote storage.
        local_path:
            Destination path on the local filesystem.

        Returns
        -------
        Path
            The local path where the file was saved.

        Raises
        ------
        CloudError
            If the download fails for any reason.
        """

    @abstractmethod
    def list_files(
        self,
        prefix: str = "",
        pattern: str = "*",
    ) -> List[str]:
        """List remote files matching *prefix* and *pattern*.

        Parameters
        ----------
        prefix:
            Key prefix to filter results (e.g. ``"documents/"``).
        pattern:
            Shell-style glob pattern applied to the file name component
            (e.g. ``"*.pdf"``).

        Returns
        -------
        list of str
            Remote keys / paths that match.
        """

    @abstractmethod
    def delete(self, remote_path: str) -> bool:
        """Delete a file from remote storage.

        Parameters
        ----------
        remote_path:
            Key / path of the file to delete.

        Returns
        -------
        bool
            ``True`` if the file was deleted, ``False`` if it did not exist.

        Raises
        ------
        CloudError
            If the deletion fails for a reason other than the file being
            absent.
        """

    @abstractmethod
    def exists(self, remote_path: str) -> bool:
        """Check whether a remote file exists.

        Parameters
        ----------
        remote_path:
            Key / path of the file to check.

        Returns
        -------
        bool
            ``True`` if the file exists, ``False`` otherwise.
        """

    @abstractmethod
    def get_url(self, remote_path: str) -> str:
        """Return a URL for accessing the remote file.

        The returned URL may be a public URL, a pre-signed URL, or a
        provider-specific URI depending on the backend configuration.

        Parameters
        ----------
        remote_path:
            Key / path of the file.

        Returns
        -------
        str
            URL or URI string.
        """

    # -- Convenience helpers (non-abstract) ----------------------------------

    def get_file_info(self, remote_path: str) -> CloudFile:
        """Return metadata for a remote file as a :class:`CloudFile`.

        The default implementation builds a minimal :class:`CloudFile` from
        :meth:`get_url`.  Subclasses should override this to populate all
        fields from the provider's metadata API.

        Parameters
        ----------
        remote_path:
            Key / path of the file.

        Returns
        -------
        CloudFile
            Metadata object.
        """
        name = remote_path.rsplit("/", 1)[-1] if "/" in remote_path else remote_path
        content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        return CloudFile(
            name=name,
            path=remote_path,
            content_type=content_type,
            url=self.get_url(remote_path),
        )


# ---------------------------------------------------------------------------
# Amazon S3
# ---------------------------------------------------------------------------


class S3Storage(CloudStorage):
    """Amazon S3 storage backend using ``boto3``.

    Parameters
    ----------
    bucket:
        Name of the S3 bucket.
    region:
        AWS region name (e.g. ``"us-east-1"``).  When *None* the SDK
        default is used.
    access_key:
        AWS access key ID.  When *None* environment / IAM credentials are
        used.
    secret_key:
        AWS secret access key.
    endpoint_url:
        Custom endpoint URL (useful for S3-compatible services such as
        MinIO or DigitalOcean Spaces).
    """

    def __init__(
        self,
        bucket: str,
        region: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        endpoint_url: Optional[str] = None,
    ) -> None:
        try:
            import boto3  # type: ignore[import-untyped]
        except ImportError:
            raise CloudError(_BOTO3_INSTALL_HINT)

        self.bucket = bucket
        self.region = region
        self.endpoint_url = endpoint_url

        session_kwargs: dict = {}
        if region:
            session_kwargs["region_name"] = region
        if access_key and secret_key:
            session_kwargs["aws_access_key_id"] = access_key
            session_kwargs["aws_secret_access_key"] = secret_key

        client_kwargs: dict = {}
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url

        session = boto3.Session(**session_kwargs)
        self._client = session.client("s3", **client_kwargs)
        self._resource_bucket = session.resource("s3", **client_kwargs).Bucket(
            bucket
        )
        logger.debug("S3Storage initialised for bucket %r in region %r", bucket, region)

    # -- CloudStorage interface ----------------------------------------------

    def upload(self, local_path: str, remote_path: str) -> str:
        """Upload *local_path* to the S3 bucket under *remote_path*."""
        try:
            content_type = (
                mimetypes.guess_type(local_path)[0] or "application/octet-stream"
            )
            self._client.upload_file(
                local_path,
                self.bucket,
                remote_path,
                ExtraArgs={"ContentType": content_type},
            )
            url = self.get_url(remote_path)
            logger.info("Uploaded %s -> s3://%s/%s", local_path, self.bucket, remote_path)
            return url
        except Exception as exc:
            raise CloudError(
                f"S3 upload failed for {remote_path}: {exc}",
                provider="s3",
                remote_path=remote_path,
            ) from exc

    def download(self, remote_path: str, local_path: str) -> Path:
        """Download *remote_path* from S3 to *local_path*."""
        dest = Path(local_path)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            self._client.download_file(self.bucket, remote_path, str(dest))
            logger.info(
                "Downloaded s3://%s/%s -> %s", self.bucket, remote_path, dest
            )
            return dest
        except Exception as exc:
            raise CloudError(
                f"S3 download failed for {remote_path}: {exc}",
                provider="s3",
                remote_path=remote_path,
            ) from exc

    def list_files(self, prefix: str = "", pattern: str = "*") -> List[str]:
        """List objects in the bucket matching *prefix* and *pattern*."""
        try:
            matched: List[str] = []
            paginator = self._client.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=self.bucket, Prefix=prefix)
            for page in pages:
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    name = key.rsplit("/", 1)[-1] if "/" in key else key
                    if fnmatch.fnmatch(name, pattern):
                        matched.append(key)
            return matched
        except Exception as exc:
            raise CloudError(
                f"S3 list failed for prefix {prefix!r}: {exc}",
                provider="s3",
                prefix=prefix,
            ) from exc

    def delete(self, remote_path: str) -> bool:
        """Delete an object from the S3 bucket."""
        try:
            if not self.exists(remote_path):
                return False
            self._client.delete_object(Bucket=self.bucket, Key=remote_path)
            logger.info("Deleted s3://%s/%s", self.bucket, remote_path)
            return True
        except Exception as exc:
            raise CloudError(
                f"S3 delete failed for {remote_path}: {exc}",
                provider="s3",
                remote_path=remote_path,
            ) from exc

    def exists(self, remote_path: str) -> bool:
        """Check whether *remote_path* exists in the S3 bucket."""
        try:
            self._client.head_object(Bucket=self.bucket, Key=remote_path)
            return True
        except self._client.exceptions.ClientError:
            return False
        except Exception:
            return False

    def get_url(self, remote_path: str) -> str:
        """Return the S3 URL for *remote_path*."""
        if self.endpoint_url:
            return f"{self.endpoint_url.rstrip('/')}/{self.bucket}/{remote_path}"
        if self.region:
            return (
                f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{remote_path}"
            )
        return f"https://{self.bucket}.s3.amazonaws.com/{remote_path}"

    def get_file_info(self, remote_path: str) -> CloudFile:
        """Return detailed metadata for an S3 object."""
        try:
            resp = self._client.head_object(Bucket=self.bucket, Key=remote_path)
            name = (
                remote_path.rsplit("/", 1)[-1]
                if "/" in remote_path
                else remote_path
            )
            return CloudFile(
                name=name,
                path=remote_path,
                size=resp.get("ContentLength", 0),
                last_modified=resp.get("LastModified"),
                content_type=resp.get("ContentType", "application/octet-stream"),
                url=self.get_url(remote_path),
                checksum=resp.get("ETag", "").strip('"'),
                metadata=resp.get("Metadata", {}),
            )
        except Exception as exc:
            raise CloudError(
                f"S3 head_object failed for {remote_path}: {exc}",
                provider="s3",
                remote_path=remote_path,
            ) from exc


# ---------------------------------------------------------------------------
# Google Cloud Storage
# ---------------------------------------------------------------------------


class GCSStorage(CloudStorage):
    """Google Cloud Storage backend using ``google-cloud-storage``.

    Parameters
    ----------
    bucket:
        Name of the GCS bucket.
    project:
        Google Cloud project ID.  When *None* the SDK default is used.
    credentials_path:
        Path to a service-account JSON key file.  When *None* Application
        Default Credentials are used.
    """

    def __init__(
        self,
        bucket: str,
        project: Optional[str] = None,
        credentials_path: Optional[str] = None,
    ) -> None:
        try:
            from google.cloud import storage as gcs_storage  # type: ignore[import-untyped]
        except ImportError:
            raise CloudError(_GCS_INSTALL_HINT)

        self.bucket_name = bucket

        client_kwargs: dict = {}
        if project:
            client_kwargs["project"] = project
        if credentials_path:
            os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", credentials_path)

        self._client = gcs_storage.Client(**client_kwargs)
        self._bucket = self._client.bucket(bucket)
        logger.debug(
            "GCSStorage initialised for bucket %r (project=%r)", bucket, project
        )

    # -- CloudStorage interface ----------------------------------------------

    def upload(self, local_path: str, remote_path: str) -> str:
        """Upload *local_path* to the GCS bucket under *remote_path*."""
        try:
            blob = self._bucket.blob(remote_path)
            content_type = (
                mimetypes.guess_type(local_path)[0] or "application/octet-stream"
            )
            blob.upload_from_filename(local_path, content_type=content_type)
            url = self.get_url(remote_path)
            logger.info(
                "Uploaded %s -> gs://%s/%s", local_path, self.bucket_name, remote_path
            )
            return url
        except Exception as exc:
            raise CloudError(
                f"GCS upload failed for {remote_path}: {exc}",
                provider="gcs",
                remote_path=remote_path,
            ) from exc

    def download(self, remote_path: str, local_path: str) -> Path:
        """Download *remote_path* from GCS to *local_path*."""
        dest = Path(local_path)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            blob = self._bucket.blob(remote_path)
            blob.download_to_filename(str(dest))
            logger.info(
                "Downloaded gs://%s/%s -> %s",
                self.bucket_name,
                remote_path,
                dest,
            )
            return dest
        except Exception as exc:
            raise CloudError(
                f"GCS download failed for {remote_path}: {exc}",
                provider="gcs",
                remote_path=remote_path,
            ) from exc

    def list_files(self, prefix: str = "", pattern: str = "*") -> List[str]:
        """List blobs in the bucket matching *prefix* and *pattern*."""
        try:
            matched: List[str] = []
            blobs = self._client.list_blobs(self._bucket, prefix=prefix)
            for blob in blobs:
                name = (
                    blob.name.rsplit("/", 1)[-1]
                    if "/" in blob.name
                    else blob.name
                )
                if fnmatch.fnmatch(name, pattern):
                    matched.append(blob.name)
            return matched
        except Exception as exc:
            raise CloudError(
                f"GCS list failed for prefix {prefix!r}: {exc}",
                provider="gcs",
                prefix=prefix,
            ) from exc

    def delete(self, remote_path: str) -> bool:
        """Delete a blob from the GCS bucket."""
        try:
            blob = self._bucket.blob(remote_path)
            if not blob.exists():
                return False
            blob.delete()
            logger.info("Deleted gs://%s/%s", self.bucket_name, remote_path)
            return True
        except Exception as exc:
            raise CloudError(
                f"GCS delete failed for {remote_path}: {exc}",
                provider="gcs",
                remote_path=remote_path,
            ) from exc

    def exists(self, remote_path: str) -> bool:
        """Check whether *remote_path* exists in the GCS bucket."""
        try:
            blob = self._bucket.blob(remote_path)
            return blob.exists()
        except Exception:
            return False

    def get_url(self, remote_path: str) -> str:
        """Return the GCS URL for *remote_path*."""
        return (
            f"https://storage.googleapis.com/{self.bucket_name}/{remote_path}"
        )

    def get_file_info(self, remote_path: str) -> CloudFile:
        """Return detailed metadata for a GCS blob."""
        try:
            blob = self._bucket.get_blob(remote_path)
            if blob is None:
                raise CloudError(
                    f"Blob not found: gs://{self.bucket_name}/{remote_path}",
                    provider="gcs",
                    remote_path=remote_path,
                )
            name = (
                blob.name.rsplit("/", 1)[-1]
                if "/" in blob.name
                else blob.name
            )
            return CloudFile(
                name=name,
                path=blob.name,
                size=blob.size or 0,
                last_modified=blob.updated,
                content_type=blob.content_type or "application/octet-stream",
                url=self.get_url(remote_path),
                checksum=blob.md5_hash,
            )
        except CloudError:
            raise
        except Exception as exc:
            raise CloudError(
                f"GCS metadata fetch failed for {remote_path}: {exc}",
                provider="gcs",
                remote_path=remote_path,
            ) from exc


# ---------------------------------------------------------------------------
# Azure Blob Storage
# ---------------------------------------------------------------------------


class AzureBlobStorage(CloudStorage):
    """Azure Blob Storage backend using ``azure-storage-blob``.

    Parameters
    ----------
    container:
        Name of the Azure Blob container.
    connection_string:
        Azure Storage connection string.  When *None* the SDK tries the
        ``AZURE_STORAGE_CONNECTION_STRING`` environment variable.
    """

    def __init__(
        self,
        container: str,
        connection_string: Optional[str] = None,
    ) -> None:
        try:
            from azure.storage.blob import BlobServiceClient  # type: ignore[import-untyped]
        except ImportError:
            raise CloudError(_AZURE_INSTALL_HINT)

        self.container_name = container

        conn_str = connection_string or os.environ.get(
            "AZURE_STORAGE_CONNECTION_STRING", ""
        )
        if not conn_str:
            raise CloudError(
                "Azure connection string must be provided either as a "
                "parameter or via the AZURE_STORAGE_CONNECTION_STRING "
                "environment variable.",
                provider="azure",
            )

        self._service_client = BlobServiceClient.from_connection_string(conn_str)
        self._container_client = self._service_client.get_container_client(
            container
        )
        logger.debug(
            "AzureBlobStorage initialised for container %r", container
        )

    # -- CloudStorage interface ----------------------------------------------

    def upload(self, local_path: str, remote_path: str) -> str:
        """Upload *local_path* to the Azure container under *remote_path*."""
        try:
            content_type = (
                mimetypes.guess_type(local_path)[0] or "application/octet-stream"
            )
            blob_client = self._container_client.get_blob_client(remote_path)
            with open(local_path, "rb") as fh:
                blob_client.upload_blob(
                    fh,
                    overwrite=True,
                    content_settings=self._content_settings(content_type),
                )
            url = self.get_url(remote_path)
            logger.info(
                "Uploaded %s -> azure://%s/%s",
                local_path,
                self.container_name,
                remote_path,
            )
            return url
        except Exception as exc:
            raise CloudError(
                f"Azure upload failed for {remote_path}: {exc}",
                provider="azure",
                remote_path=remote_path,
            ) from exc

    def download(self, remote_path: str, local_path: str) -> Path:
        """Download *remote_path* from Azure to *local_path*."""
        dest = Path(local_path)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            blob_client = self._container_client.get_blob_client(remote_path)
            with open(str(dest), "wb") as fh:
                download_stream = blob_client.download_blob()
                download_stream.readinto(fh)
            logger.info(
                "Downloaded azure://%s/%s -> %s",
                self.container_name,
                remote_path,
                dest,
            )
            return dest
        except Exception as exc:
            raise CloudError(
                f"Azure download failed for {remote_path}: {exc}",
                provider="azure",
                remote_path=remote_path,
            ) from exc

    def list_files(self, prefix: str = "", pattern: str = "*") -> List[str]:
        """List blobs in the container matching *prefix* and *pattern*."""
        try:
            matched: List[str] = []
            blobs = self._container_client.list_blobs(name_starts_with=prefix)
            for blob in blobs:
                name = (
                    blob.name.rsplit("/", 1)[-1]
                    if "/" in blob.name
                    else blob.name
                )
                if fnmatch.fnmatch(name, pattern):
                    matched.append(blob.name)
            return matched
        except Exception as exc:
            raise CloudError(
                f"Azure list failed for prefix {prefix!r}: {exc}",
                provider="azure",
                prefix=prefix,
            ) from exc

    def delete(self, remote_path: str) -> bool:
        """Delete a blob from the Azure container."""
        try:
            if not self.exists(remote_path):
                return False
            blob_client = self._container_client.get_blob_client(remote_path)
            blob_client.delete_blob()
            logger.info(
                "Deleted azure://%s/%s", self.container_name, remote_path
            )
            return True
        except Exception as exc:
            raise CloudError(
                f"Azure delete failed for {remote_path}: {exc}",
                provider="azure",
                remote_path=remote_path,
            ) from exc

    def exists(self, remote_path: str) -> bool:
        """Check whether *remote_path* exists in the Azure container."""
        try:
            blob_client = self._container_client.get_blob_client(remote_path)
            blob_client.get_blob_properties()
            return True
        except Exception:
            return False

    def get_url(self, remote_path: str) -> str:
        """Return the Azure Blob URL for *remote_path*."""
        account_url = self._service_client.url.rstrip("/")
        return f"{account_url}/{self.container_name}/{remote_path}"

    def get_file_info(self, remote_path: str) -> CloudFile:
        """Return detailed metadata for an Azure blob."""
        try:
            blob_client = self._container_client.get_blob_client(remote_path)
            props = blob_client.get_blob_properties()
            name = (
                remote_path.rsplit("/", 1)[-1]
                if "/" in remote_path
                else remote_path
            )
            return CloudFile(
                name=name,
                path=remote_path,
                size=props.size or 0,
                last_modified=props.last_modified,
                content_type=(
                    props.content_settings.content_type
                    if props.content_settings
                    else "application/octet-stream"
                ),
                url=self.get_url(remote_path),
                checksum=props.etag.strip('"') if props.etag else None,
                metadata=dict(props.metadata) if props.metadata else {},
            )
        except Exception as exc:
            raise CloudError(
                f"Azure metadata fetch failed for {remote_path}: {exc}",
                provider="azure",
                remote_path=remote_path,
            ) from exc

    # -- Private helpers -----------------------------------------------------

    @staticmethod
    def _content_settings(content_type: str) -> Any:
        """Build an Azure ``ContentSettings`` object."""
        from azure.storage.blob import ContentSettings  # type: ignore[import-untyped]

        return ContentSettings(content_type=content_type)


# ---------------------------------------------------------------------------
# Local filesystem (testing / offline)
# ---------------------------------------------------------------------------


class LocalStorage(CloudStorage):
    """Local-filesystem storage backend.

    This implementation mirrors the cloud storage interface but reads and
    writes files under a configurable *base_dir*.  It is ideal for testing,
    local development, and scenarios where cloud connectivity is unavailable.

    Parameters
    ----------
    base_dir:
        Root directory that acts as the "bucket" / container.  Created
        automatically if it does not exist.
    """

    def __init__(self, base_dir: str) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("LocalStorage initialised at %s", self.base_dir)

    # -- Internal helpers ----------------------------------------------------

    def _resolve(self, remote_path: str) -> Path:
        """Resolve *remote_path* to an absolute path under *base_dir*."""
        return self.base_dir / remote_path

    # -- CloudStorage interface ----------------------------------------------

    def upload(self, local_path: str, remote_path: str) -> str:
        """Copy *local_path* into the local storage directory."""
        src = Path(local_path)
        if not src.is_file():
            raise CloudError(
                f"Local file not found: {src}",
                provider="local",
                local_path=local_path,
            )
        dest = self._resolve(remote_path)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dest))
            url = self.get_url(remote_path)
            logger.info("Copied %s -> %s", src, dest)
            return url
        except Exception as exc:
            raise CloudError(
                f"Local upload failed for {remote_path}: {exc}",
                provider="local",
                remote_path=remote_path,
            ) from exc

    def download(self, remote_path: str, local_path: str) -> Path:
        """Copy a file from local storage to *local_path*."""
        src = self._resolve(remote_path)
        if not src.is_file():
            raise CloudError(
                f"Remote file not found in local storage: {src}",
                provider="local",
                remote_path=remote_path,
            )
        dest = Path(local_path)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dest))
            logger.info("Copied %s -> %s", src, dest)
            return dest
        except Exception as exc:
            raise CloudError(
                f"Local download failed for {remote_path}: {exc}",
                provider="local",
                remote_path=remote_path,
            ) from exc

    def list_files(self, prefix: str = "", pattern: str = "*") -> List[str]:
        """List files under *base_dir* matching *prefix* and *pattern*."""
        root = self._resolve(prefix) if prefix else self.base_dir
        if not root.exists():
            return []

        matched: List[str] = []
        search_root = root if root.is_dir() else root.parent
        for dirpath, _dirnames, filenames in os.walk(search_root):
            for name in filenames:
                if fnmatch.fnmatch(name, pattern):
                    full = Path(dirpath) / name
                    # Express the result relative to base_dir.
                    try:
                        rel = full.relative_to(self.base_dir)
                    except ValueError:
                        continue
                    rel_str = str(rel).replace(os.sep, "/")
                    if rel_str.startswith(prefix):
                        matched.append(rel_str)
        matched.sort()
        return matched

    def delete(self, remote_path: str) -> bool:
        """Delete a file from local storage."""
        target = self._resolve(remote_path)
        if not target.is_file():
            return False
        try:
            target.unlink()
            logger.info("Deleted %s", target)
            return True
        except Exception as exc:
            raise CloudError(
                f"Local delete failed for {remote_path}: {exc}",
                provider="local",
                remote_path=remote_path,
            ) from exc

    def exists(self, remote_path: str) -> bool:
        """Check whether *remote_path* exists under *base_dir*."""
        return self._resolve(remote_path).is_file()

    def get_url(self, remote_path: str) -> str:
        """Return a ``file://`` URL for the local path."""
        resolved = self._resolve(remote_path)
        return resolved.as_uri()

    def get_file_info(self, remote_path: str) -> CloudFile:
        """Return metadata for a local file."""
        target = self._resolve(remote_path)
        if not target.is_file():
            raise CloudError(
                f"File not found in local storage: {target}",
                provider="local",
                remote_path=remote_path,
            )
        stat = target.stat()
        name = target.name
        content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        return CloudFile(
            name=name,
            path=remote_path,
            size=stat.st_size,
            last_modified=datetime.datetime.fromtimestamp(
                stat.st_mtime, tz=datetime.timezone.utc
            ),
            content_type=content_type,
            url=self.get_url(remote_path),
            checksum=generate_checksum(str(target)),
        )
