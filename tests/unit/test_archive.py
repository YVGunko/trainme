import io
import json
import os
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.garmin.archive import _activity_day, _store_bytes, archive_latest
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


class ArchiveSelectionTest(unittest.TestCase):
    def test_stored_latest_activity_is_not_downloaded_again(self) -> None:
        client = _garmin_client(
            [
                {"activityId": 9, "startTimeLocal": "2026-10-09 07:21:13"},
                {"activityId": 8, "startTimeLocal": "2026-10-07 18:47:45"},
            ]
        )
        with _archive_patches(client, activity_ids={9}, days={"2026-10-09"}):
            result = archive_latest()
        client.download_activity.assert_called_once()
        self.assertEqual(client.download_activity.call_args.args[0], "8")
        client.get_sleep_data.assert_called_once_with("2026-10-07")
        self.assertEqual(result["activity"]["garmin_activity_id"], 8)
        self.assertTrue(result["activity"]["stored"])

    def test_stored_activity_with_a_missing_day_does_not_redownload_the_zip(self) -> None:
        client = _garmin_client(
            [{"activityId": 9, "startTimeLocal": "2026-10-09 07:21:13"}]
        )
        with _archive_patches(client, activity_ids={9}, days=set()):
            result = archive_latest()
        client.download_activity.assert_not_called()
        client.get_sleep_data.assert_called_once_with("2026-10-09")
        self.assertFalse(result["activity"]["stored"])
        self.assertTrue(result["day"]["stored"])

    def test_fully_stored_page_does_not_call_garmin_files(self) -> None:
        client = _garmin_client(
            [
                {"activityId": 9, "startTimeLocal": "2026-10-09 07:21:13"},
                {"activityId": 8, "startTimeLocal": "2026-10-07 18:47:45"},
            ]
        )
        with _archive_patches(client, activity_ids={9, 8}, days={"2026-10-09", "2026-10-07"}):
            result = archive_latest()
        client.download_activity.assert_not_called()
        client.get_sleep_data.assert_not_called()
        client.get_heart_rates.assert_not_called()
        self.assertFalse(result["activity"]["stored"])
        self.assertEqual(result["activity"]["garmin_activity_id"], 9)
        self.assertEqual(result["day"]["day"], "2026-10-09")

    def test_new_activity_on_a_stored_day_does_not_refetch_the_day(self) -> None:
        client = _garmin_client(
            [{"activityId": 9, "startTimeLocal": "2026-10-09 07:21:13"}]
        )
        with _archive_patches(client, activity_ids=set(), days={"2026-10-09"}):
            result = archive_latest()
        client.download_activity.assert_called_once()
        client.get_sleep_data.assert_not_called()
        client.get_heart_rates.assert_not_called()
        self.assertTrue(result["activity"]["stored"])
        self.assertFalse(result["day"]["stored"])


def _garmin_client(activities: list[dict]) -> MagicMock:
    client = MagicMock()
    client.profile_id = 51300124
    client.client.dumps.return_value = "{}"
    client.get_activities.return_value = activities
    client.download_activity.return_value = b"zip"
    client.get_sleep_data.return_value = {"dailySleepDTO": {}}
    client.get_heart_rates.return_value = {"restingHeartRate": 48}
    return client


def _raw(kind: str, activity_id: int | None, day: str | None) -> dict:
    return {
        "kind": kind,
        "garmin_activity_id": activity_id,
        "day": day,
        "source_format": "zip" if kind == "activity" else "json",
        "source_path": f"garmin/1/{kind}/stored",
        "source_sha256": f"sha-{kind}-{activity_id or day}",
        "byte_size": 4,
    }


class _archive_patches:
    def __init__(self, client: MagicMock, activity_ids: set[int], days: set[str]) -> None:
        self.client = client
        self.activity_ids = activity_ids
        self.days = days
        self._stack = None

    def __enter__(self) -> None:
        from contextlib import ExitStack

        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.__exit__.return_value = False

        def find_activity(_connection: object, activity_id: int) -> dict | None:
            if activity_id in self.activity_ids:
                return _raw("activity", activity_id, None)
            return None

        def find_day(_connection: object, day: str) -> dict | None:
            if day in self.days:
                return _raw("day", None, day)
            return None

        def store(_connection: object, **kwargs: object) -> dict:
            return {
                "kind": kwargs["kind"],
                "garmin_activity_id": kwargs["garmin_activity_id"],
                "day": kwargs["day"],
                "source_format": kwargs["source_format"],
                "source_path": "garmin/1/new",
                "source_sha256": "new",
                "byte_size": 3,
                "stored": True,
            }

        stack = ExitStack()
        stack.enter_context(
            patch.dict(os.environ, {"TOKEN_ENCRYPTION_KEY": "local-key"}, clear=False)
        )
        stack.enter_context(patch("app.garmin.archive._login", return_value=self.client))
        stack.enter_context(patch("app.garmin.archive.connect", return_value=connection))
        stack.enter_context(patch("app.garmin.archive.ensure_schema"))
        stack.enter_context(patch("app.garmin.archive.load_token", return_value=None))
        stack.enter_context(patch("app.garmin.archive.save_token"))
        stack.enter_context(
            patch("app.garmin.archive.find_activity_raw_object", side_effect=find_activity)
        )
        stack.enter_context(patch("app.garmin.archive.find_day_raw_object", side_effect=find_day))
        stack.enter_context(patch("app.garmin.archive._store_bytes", side_effect=store))
        self._stack = stack
        stack.__enter__()
        return None

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._stack is not None:
            self._stack.__exit__(exc_type, exc, tb)


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
