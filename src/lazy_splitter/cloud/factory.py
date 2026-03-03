"""Factory for creating cloud storage backends.

The :func:`create_storage` function provides a single entry-point for
constructing any supported :class:`~lazy_splitter.cloud.storage.CloudStorage`
implementation.  It supports four providers:

* ``"s3"``    -- Amazon S3 (requires ``boto3``)
* ``"gcs"``   -- Google Cloud Storage (requires ``google-cloud-storage``)
* ``"azure"`` -- Azure Blob Storage (requires ``azure-storage-blob``)
* ``"local"`` -- Local filesystem (no extra dependencies)

Credentials can be supplied directly via keyword arguments, loaded from
environment variables, or left to each provider's own default credential
resolution chain.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from lazy_splitter.core.exceptions import CloudError

from lazy_splitter.cloud.storage import (
    AzureBlobStorage,
    CloudStorage,
    GCSStorage,
    LocalStorage,
    S3Storage,
)

logger = logging.getLogger(__name__)

# Mapping from provider name to the environment variables that supply
# default configuration values for each backend.
_ENV_DEFAULTS = {
    "s3": {
        "bucket": "AWS_S3_BUCKET",
        "region": "AWS_DEFAULT_REGION",
        "access_key": "AWS_ACCESS_KEY_ID",
        "secret_key": "AWS_SECRET_ACCESS_KEY",
        "endpoint_url": "AWS_ENDPOINT_URL",
    },
    "gcs": {
        "bucket": "GCS_BUCKET",
        "project": "GOOGLE_CLOUD_PROJECT",
        "credentials_path": "GOOGLE_APPLICATION_CREDENTIALS",
    },
    "azure": {
        "container": "AZURE_STORAGE_CONTAINER",
        "connection_string": "AZURE_STORAGE_CONNECTION_STRING",
    },
    "local": {
        "base_dir": "LAZY_SPLITTER_LOCAL_STORAGE_DIR",
    },
}

#: Set of recognised provider identifiers.
SUPPORTED_PROVIDERS = frozenset(_ENV_DEFAULTS.keys())


def _env(provider: str, key: str) -> Optional[str]:
    """Return the environment-variable value for *provider*/*key*, or ``None``."""
    var_name = _ENV_DEFAULTS.get(provider, {}).get(key)
    if var_name is None:
        return None
    return os.environ.get(var_name) or None


def create_storage(provider: str, **kwargs: object) -> CloudStorage:
    """Instantiate a :class:`CloudStorage` backend for *provider*.

    Explicit keyword arguments take precedence; missing values are filled
    from environment variables where applicable.

    Parameters
    ----------
    provider:
        One of ``"s3"``, ``"gcs"``, ``"azure"``, or ``"local"``.
    **kwargs:
        Provider-specific configuration (see the constructors of the
        individual storage classes for accepted keys).

    Returns
    -------
    CloudStorage
        A ready-to-use storage backend.

    Raises
    ------
    CloudError
        If *provider* is unrecognised, or if a required configuration
        value is missing.

    Examples
    --------
    >>> storage = create_storage("s3", bucket="my-bucket", region="us-west-2")
    >>> storage = create_storage("local", base_dir="/tmp/cloud-sim")
    """
    provider = provider.strip().lower()

    if provider not in SUPPORTED_PROVIDERS:
        raise CloudError(
            f"Unknown storage provider {provider!r}. "
            f"Supported providers: {sorted(SUPPORTED_PROVIDERS)}",
            provider=provider,
        )

    logger.debug("Creating %s storage backend", provider)

    if provider == "s3":
        return _create_s3(**kwargs)
    if provider == "gcs":
        return _create_gcs(**kwargs)
    if provider == "azure":
        return _create_azure(**kwargs)
    # provider == "local"
    return _create_local(**kwargs)


# ---------------------------------------------------------------------------
# Private per-provider constructors
# ---------------------------------------------------------------------------


def _create_s3(**kwargs: object) -> S3Storage:
    """Build an :class:`S3Storage` instance, filling gaps from env vars."""
    bucket = kwargs.get("bucket") or _env("s3", "bucket")
    if not bucket:
        raise CloudError(
            "S3 bucket name is required. Provide it via the 'bucket' "
            "parameter or the AWS_S3_BUCKET environment variable.",
            provider="s3",
        )

    region = kwargs.get("region") or _env("s3", "region")
    access_key = kwargs.get("access_key") or _env("s3", "access_key")
    secret_key = kwargs.get("secret_key") or _env("s3", "secret_key")
    endpoint_url = kwargs.get("endpoint_url") or _env("s3", "endpoint_url")

    return S3Storage(
        bucket=str(bucket),
        region=str(region) if region else None,
        access_key=str(access_key) if access_key else None,
        secret_key=str(secret_key) if secret_key else None,
        endpoint_url=str(endpoint_url) if endpoint_url else None,
    )


def _create_gcs(**kwargs: object) -> GCSStorage:
    """Build a :class:`GCSStorage` instance, filling gaps from env vars."""
    bucket = kwargs.get("bucket") or _env("gcs", "bucket")
    if not bucket:
        raise CloudError(
            "GCS bucket name is required. Provide it via the 'bucket' "
            "parameter or the GCS_BUCKET environment variable.",
            provider="gcs",
        )

    project = kwargs.get("project") or _env("gcs", "project")
    credentials_path = kwargs.get("credentials_path") or _env(
        "gcs", "credentials_path"
    )

    return GCSStorage(
        bucket=str(bucket),
        project=str(project) if project else None,
        credentials_path=str(credentials_path) if credentials_path else None,
    )


def _create_azure(**kwargs: object) -> AzureBlobStorage:
    """Build an :class:`AzureBlobStorage` instance, filling gaps from env vars."""
    container = kwargs.get("container") or _env("azure", "container")
    if not container:
        raise CloudError(
            "Azure container name is required. Provide it via the "
            "'container' parameter or the AZURE_STORAGE_CONTAINER "
            "environment variable.",
            provider="azure",
        )

    connection_string = kwargs.get("connection_string") or _env(
        "azure", "connection_string"
    )

    return AzureBlobStorage(
        container=str(container),
        connection_string=str(connection_string) if connection_string else None,
    )


def _create_local(**kwargs: object) -> LocalStorage:
    """Build a :class:`LocalStorage` instance, filling gaps from env vars."""
    base_dir = kwargs.get("base_dir") or _env("local", "base_dir")
    if not base_dir:
        raise CloudError(
            "Local storage base directory is required. Provide it via the "
            "'base_dir' parameter or the LAZY_SPLITTER_LOCAL_STORAGE_DIR "
            "environment variable.",
            provider="local",
        )

    return LocalStorage(base_dir=str(base_dir))
