"""File synchronisation between local and cloud storage.

The :class:`CloudSync` class provides directory-level upload and download
operations with checksum-based change detection, progress tracking, and a
convenience :meth:`~CloudSync.process_remote` method for the common
"download, process, re-upload" workflow.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Union

from lazy_splitter.core.exceptions import CloudError
from lazy_splitter.core.utils import generate_checksum

from lazy_splitter.cloud.models import SyncResult
from lazy_splitter.cloud.storage import CloudStorage

logger = logging.getLogger(__name__)

# Type alias for user-supplied progress callbacks.
# Arguments: (current_file_index, total_files, current_file_name)
ProgressCallback = Callable[[int, int, str], None]


class CloudSync:
    """Synchronise files between a local directory and a cloud storage backend.

    Parameters
    ----------
    storage:
        An initialised :class:`CloudStorage` backend.
    checksum_algorithm:
        Hash algorithm used for change detection (default ``"sha256"``).
    progress_callback:
        Optional callable invoked once per file with
        ``(current_index, total, file_name)``.
    """

    def __init__(
        self,
        storage: CloudStorage,
        checksum_algorithm: str = "sha256",
        progress_callback: Optional[ProgressCallback] = None,
    ) -> None:
        self.storage = storage
        self.checksum_algorithm = checksum_algorithm
        self.progress_callback = progress_callback

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def sync_upload(
        self,
        local_dir: Union[str, Path],
        remote_prefix: str = "",
        pattern: str = "*",
        force: bool = False,
    ) -> SyncResult:
        """Upload an entire local directory to cloud storage.

        Only files whose local checksum differs from the remote checksum
        are transferred, unless *force* is ``True``.

        Parameters
        ----------
        local_dir:
            Path to the local directory to upload.
        remote_prefix:
            Key prefix prepended to every uploaded file
            (e.g. ``"backups/2024/"``).
        pattern:
            Shell-style glob pattern to filter files by name (e.g.
            ``"*.pdf"``).  Matching is applied to the file name only.
        force:
            When ``True``, upload every file regardless of checksum
            comparison.

        Returns
        -------
        SyncResult
            Aggregate statistics for the upload operation.
        """
        start = time.monotonic()
        result = SyncResult()
        root = Path(local_dir)

        if not root.is_dir():
            raise CloudError(
                f"Local directory does not exist: {root}",
                provider="sync",
                local_dir=str(root),
            )

        local_files = self._collect_local_files(root, pattern)
        total = len(local_files)
        logger.info(
            "sync_upload: %d files found in %s (prefix=%r)",
            total,
            root,
            remote_prefix,
        )

        for idx, local_path in enumerate(local_files, 1):
            rel = local_path.relative_to(root)
            remote_path = self._join_remote(remote_prefix, str(rel))
            file_name = local_path.name

            try:
                if not force and self._remote_matches_local(
                    remote_path, local_path
                ):
                    result.skipped += 1
                    logger.debug("Skipped (unchanged): %s", remote_path)
                else:
                    self.storage.upload(str(local_path), remote_path)
                    result.uploaded += 1
            except CloudError as exc:
                result.errors.append(f"{remote_path}: {exc.message}")
                logger.error("Upload error for %s: %s", remote_path, exc)
            except Exception as exc:
                result.errors.append(f"{remote_path}: {exc}")
                logger.error("Upload error for %s: %s", remote_path, exc)

            self._notify_progress(idx, total, file_name)

        result.duration = round(time.monotonic() - start, 4)
        logger.info(
            "sync_upload complete: uploaded=%d skipped=%d errors=%d (%.2fs)",
            result.uploaded,
            result.skipped,
            len(result.errors),
            result.duration,
        )
        return result

    def sync_download(
        self,
        remote_prefix: str,
        local_dir: Union[str, Path],
        pattern: str = "*",
        force: bool = False,
    ) -> SyncResult:
        """Download files from cloud storage into a local directory.

        Only files whose remote checksum differs from the local checksum
        are transferred, unless *force* is ``True``.

        Parameters
        ----------
        remote_prefix:
            Key prefix in the remote backend (e.g. ``"exports/"``).
        local_dir:
            Path to the local directory where files will be saved.
        pattern:
            Shell-style glob pattern to filter files by name.
        force:
            When ``True``, download every file regardless of checksum
            comparison.

        Returns
        -------
        SyncResult
            Aggregate statistics for the download operation.
        """
        start = time.monotonic()
        result = SyncResult()
        dest = Path(local_dir)
        dest.mkdir(parents=True, exist_ok=True)

        try:
            remote_files = self.storage.list_files(
                prefix=remote_prefix, pattern=pattern
            )
        except CloudError:
            raise
        except Exception as exc:
            raise CloudError(
                f"Failed to list remote files with prefix {remote_prefix!r}: {exc}",
                provider="sync",
            ) from exc

        total = len(remote_files)
        logger.info(
            "sync_download: %d remote files with prefix %r",
            total,
            remote_prefix,
        )

        for idx, remote_path in enumerate(remote_files, 1):
            # Strip the prefix to mirror the remote directory structure
            # locally.
            if remote_prefix and remote_path.startswith(remote_prefix):
                rel = remote_path[len(remote_prefix):].lstrip("/")
            else:
                rel = remote_path
            local_path = dest / rel
            file_name = Path(remote_path).name

            try:
                if not force and self._local_matches_remote(
                    local_path, remote_path
                ):
                    result.skipped += 1
                    logger.debug("Skipped (unchanged): %s", remote_path)
                else:
                    self.storage.download(remote_path, str(local_path))
                    result.downloaded += 1
            except CloudError as exc:
                result.errors.append(f"{remote_path}: {exc.message}")
                logger.error("Download error for %s: %s", remote_path, exc)
            except Exception as exc:
                result.errors.append(f"{remote_path}: {exc}")
                logger.error("Download error for %s: %s", remote_path, exc)

            self._notify_progress(idx, total, file_name)

        result.duration = round(time.monotonic() - start, 4)
        logger.info(
            "sync_download complete: downloaded=%d skipped=%d errors=%d (%.2fs)",
            result.downloaded,
            result.skipped,
            len(result.errors),
            result.duration,
        )
        return result

    def process_remote(
        self,
        remote_path: str,
        operation: Callable[[str], str],
        **kwargs: object,
    ) -> str:
        """Download a remote file, apply *operation*, and upload the result.

        This is a convenience method for the common workflow of fetching a
        file from cloud storage, running a local transformation on it, and
        pushing the result back.

        Parameters
        ----------
        remote_path:
            Key / path of the file in the remote backend.
        operation:
            A callable that receives the path to a local temporary file
            and returns the path to the output file (which may be the same
            file, or a new one).
        **kwargs:
            ``output_remote_path`` (str) -- If provided, the processed file
            is uploaded to this key instead of overwriting *remote_path*.

        Returns
        -------
        str
            URL of the uploaded result file.

        Raises
        ------
        CloudError
            If any step (download, process, or upload) fails.
        """
        output_remote_path = str(
            kwargs.get("output_remote_path", remote_path)
        )

        tmp_dir = tempfile.mkdtemp(prefix="lazy_cloud_sync_")
        file_name = (
            remote_path.rsplit("/", 1)[-1]
            if "/" in remote_path
            else remote_path
        )
        local_input = os.path.join(tmp_dir, file_name)

        try:
            # 1. Download
            logger.info("process_remote: downloading %s", remote_path)
            self.storage.download(remote_path, local_input)

            # 2. Process
            logger.info("process_remote: processing %s", local_input)
            local_output = operation(local_input)
            if not os.path.isfile(local_output):
                raise CloudError(
                    f"Operation did not produce an output file: {local_output}",
                    provider="sync",
                    remote_path=remote_path,
                )

            # 3. Upload
            logger.info(
                "process_remote: uploading result to %s", output_remote_path
            )
            url = self.storage.upload(local_output, output_remote_path)
            return url

        except CloudError:
            raise
        except Exception as exc:
            raise CloudError(
                f"process_remote failed for {remote_path}: {exc}",
                provider="sync",
                remote_path=remote_path,
            ) from exc
        finally:
            # Best-effort cleanup of the temporary directory.
            import shutil

            shutil.rmtree(tmp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_local_files(root: Path, pattern: str) -> List[Path]:
        """Recursively collect files under *root* matching *pattern*."""
        import fnmatch as _fnmatch

        matched: List[Path] = []
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                if _fnmatch.fnmatch(name, pattern):
                    matched.append(Path(dirpath) / name)
        matched.sort()
        return matched

    @staticmethod
    def _join_remote(prefix: str, relative: str) -> str:
        """Combine *prefix* and *relative* into a forward-slash path."""
        relative = relative.replace(os.sep, "/")
        if not prefix:
            return relative
        return prefix.rstrip("/") + "/" + relative.lstrip("/")

    def _remote_matches_local(
        self, remote_path: str, local_path: Path
    ) -> bool:
        """Return ``True`` if the remote file has the same checksum as *local_path*.

        When the remote checksum cannot be determined (e.g. the file does
        not exist yet), this returns ``False`` so the file will be
        transferred.
        """
        if not self.storage.exists(remote_path):
            return False
        try:
            remote_info = self.storage.get_file_info(remote_path)
        except CloudError:
            return False

        if not remote_info.checksum:
            return False

        local_checksum = generate_checksum(
            str(local_path), algorithm=self.checksum_algorithm
        )
        return remote_info.checksum == local_checksum

    def _local_matches_remote(
        self, local_path: Path, remote_path: str
    ) -> bool:
        """Return ``True`` if *local_path* has the same checksum as the remote file.

        When the local file does not exist or the remote checksum is
        unavailable, this returns ``False`` so the file will be
        transferred.
        """
        if not local_path.is_file():
            return False
        try:
            remote_info = self.storage.get_file_info(remote_path)
        except CloudError:
            return False

        if not remote_info.checksum:
            return False

        local_checksum = generate_checksum(
            str(local_path), algorithm=self.checksum_algorithm
        )
        return remote_info.checksum == local_checksum

    def _notify_progress(self, current: int, total: int, name: str) -> None:
        """Invoke the progress callback if one was registered."""
        if self.progress_callback is not None:
            try:
                self.progress_callback(current, total, name)
            except Exception:  # noqa: BLE001
                # Never let a broken callback halt synchronisation.
                logger.debug("Progress callback raised an exception", exc_info=True)
