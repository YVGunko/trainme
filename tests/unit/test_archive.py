import io
import json
import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.garmin.archive import _activity_day, _store_bytes
from app.main import app
from app.storage.blob import put_private
from app.storage.crypto import decrypt, encrypt


class CryptoTest(unittest.TestCase):
    def test_round_trip(self) -> None:
        payload = encrypt('{"di_token":"secret"}', "local-key")
        self.assertNotIn(b"secret", payload)
        self.assertEqual(decrypt(payload, "local-key"), '{"di_token":"secret"}')


class ArchiveRouteTest(unittest.TestCase):
    def test_archive_requires_the_service_secret(self) -> None:
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            response = client.post("/archive")
        self.assertEqual(response.status_code, 401)

    def test_archive_returns_the_storage_summary(self) -> None:
        summary = {
            "activity": {
                "kind": "activity",
                "source_format": "zip",
                "source_path": "garmin/1/activity/9/abc.zip",
                "source_sha256": "abc",
                "byte_size": 4,
                "stored": True,
            },
            "day": {
                "kind": "day",
                "day": "2026-10-09",
                "source_format": "json",
                "source_path": "garmin/1/day/2026-10-09/def.json",
                "source_sha256": "def",
                "byte_size": 8,
                "stored": True,
            },
        }
        client = TestClient(app)
        with patch.dict(os.environ, {"SERVICE_SECRET": "expected"}, clear=True):
            with patch("app.main.archive_latest", return_value=summary):
                response = client.post(
                    "/archive",
                    headers={"Authorization": "Bearer expected"},
                )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), summary)
        self.assertNotIn("di_token", response.text)


class StoreBytesTest(unittest.TestCase):
    def test_existing_hash_is_not_uploaded_again(self) -> None:
        connection = MagicMock()
        existing = {
            "kind": "activity",
            "source_path": "garmin/1/activity/9/abc.zip",
            "source_sha256": "abc",
        }
        with patch("app.garmin.archive.find_raw_object", return_value=existing):
            with patch("app.garmin.archive.put_private") as upload:
                record = _store_bytes(
                    connection,
                    body=b"zip",
                    kind="activity",
                    source_format="zip",
                    pathname="garmin/1/activity/9",
                    extension="zip",
                    content_type="application/zip",
                    garmin_activity_id=9,
                    day=None,
                )
        upload.assert_not_called()
        self.assertFalse(record["stored"])

    def test_activity_day_uses_the_local_date(self) -> None:
        self.assertEqual(_activity_day({"startTimeLocal": "2026-10-09 07:21:13"}), "2026-10-09")


class BlobRequestTest(unittest.TestCase):
    def test_put_uses_a_private_blob_request(self) -> None:
        body = json.dumps({"pathname": "garmin/1/activity/9/abc.zip"}).encode()
        response = MagicMock()
        response.read.return_value = body
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        with patch.dict(os.environ, {"BLOB_READ_WRITE_TOKEN": "vercel_blob_rw_store123_secret"}, clear=False):
            with patch("app.storage.blob.urllib.request.urlopen", return_value=response) as urlopen:
                pathname = put_private("garmin/1/activity/9/abc.zip", b"zip", "application/zip")
        self.assertEqual(pathname, "garmin/1/activity/9/abc.zip")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_method(), "PUT")
        self.assertEqual(request.get_header("X-vercel-blob-access"), "private")
        self.assertEqual(request.get_header("X-vercel-blob-store-id"), "store123")
        self.assertIn("pathname=garmin%2F1%2Factivity%2F9%2Fabc.zip", request.full_url)
        self.assertIsInstance(request.data, bytes)
        self.assertNotIsInstance(request.data, io.StringIO)
