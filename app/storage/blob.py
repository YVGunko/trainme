import json
import os
import urllib.error
import urllib.parse
import urllib.request


class BlobNotConfigured(Exception):
    """Raised when BLOB_READ_WRITE_TOKEN is missing."""


class BlobUploadError(Exception):
    """Raised when Vercel Blob rejects an upload."""


def put_private(pathname: str, body: bytes, content_type: str) -> str:
    token = os.environ.get("BLOB_READ_WRITE_TOKEN", "")
    if not token:
        raise BlobNotConfigured
    store_id = _store_id(token)
    url = "https://vercel.com/api/blob/?" + urllib.parse.urlencode({"pathname": pathname})
    request = urllib.request.Request(
        url,
        data=body,
        method="PUT",
        headers={
            "authorization": f"Bearer {token}",
            "x-vercel-blob-store-id": store_id,
            "x-api-version": "12",
            "x-vercel-blob-access": "private",
            "x-content-type": content_type,
            "x-add-random-suffix": "0",
            "x-content-length": str(len(body)),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        if error.code in {400, 409} and "already exists" in detail.lower():
            return pathname
        raise BlobUploadError(f"Blob upload failed with HTTP {error.code}") from error
    stored_path = payload.get("pathname")
    if not isinstance(stored_path, str) or not stored_path:
        raise BlobUploadError("Blob upload did not return a pathname")
    return stored_path


def _store_id(token: str) -> str:
    parts = token.split("_")
    if len(parts) < 4 or not parts[3]:
        raise BlobNotConfigured
    return parts[3]
