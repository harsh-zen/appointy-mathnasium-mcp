import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from appointy_mathnasium_mcp import log_search
from appointy_mathnasium_mcp.errors import GcpLoggingError
from appointy_mathnasium_mcp.log_search import _build_custom_logs_filter, _search_custom_logs_internal


class LogSearchFilterTests(unittest.TestCase):
    def test_radius_wrapper_filter_adds_source_and_endpoint_terms(self):
        query, start, end, match_terms = _build_custom_logs_filter(
            source="radius_wrappers",
            text_terms=[],
            identifiers=["jason@example.com"],
            messages=[],
            query_ids=[],
            paths=[],
            endpoint_names=["customer-account"],
            status_codes=[],
            start_time="2026-07-01T00:00:00Z",
            end_time="2026-07-02T00:00:00Z",
            severity_min="DEFAULT",
            match_all_terms=False,
        )

        self.assertIn('jsonPayload.message="Successful" OR jsonPayload.message="Failed"', query)
        self.assertIn('"jason@example.com"', query)
        self.assertIn('"customer-account"', query)
        self.assertEqual(start, "2026-07-01T00:00:00Z")
        self.assertEqual(end, "2026-07-02T00:00:00Z")
        self.assertIn("jason@example.com", match_terms)
        self.assertIn("customer-account", match_terms)


    def test_message_filter_escapes_json_payload_field_without_name_error(self):
        query, _, _, match_terms = _build_custom_logs_filter(
            source="radius_wrappers",
            text_terms=[],
            identifiers=["megan.koslowski@gmail.com"],
            messages=["Failed", "Error"],
            query_ids=[],
            paths=[],
            endpoint_names=[],
            status_codes=[],
            start_time="2026-06-25T00:00:00Z",
            end_time="2026-07-10T23:59:59Z",
            severity_min="DEFAULT",
            match_all_terms=False,
        )

        self.assertIn('jsonPayload.message="Failed"', query)
        self.assertIn('jsonPayload.message="Error"', query)
        self.assertIn('"megan.koslowski@gmail.com"', query)
        self.assertIn("megan.koslowski@gmail.com", match_terms)

    def test_search_rejects_unfiltered_broad_scan(self):
        async def run():
            return await _search_custom_logs_internal(
                source="all",
                text_terms=[],
                identifiers=[],
                messages=[],
                query_ids=[],
                paths=[],
                endpoint_names=[],
                status_codes=[],
                start_time=None,
                end_time=None,
                severity_min="DEFAULT",
                match_all_terms=False,
                limit=10,
                include_payload=True,
            )

        import asyncio

        result = asyncio.run(run())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["matches"], [])


class LogSearchExecutionTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _entry(insert_id: str, timestamp: str):
        return SimpleNamespace(
            payload={"message": "Failed", "request": {"id": insert_id}},
            timestamp=datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(timezone.utc),
            severity="ERROR",
            insert_id=insert_id,
            log_name="projects/waqt-prod/logs/stdout",
            resource=SimpleNamespace(labels={"namespace_name": "prod"}),
            labels={},
        )

    async def test_long_range_is_chunked_newest_first_and_omits_payload(self):
        class FakeLoggingClient:
            def __init__(self):
                self.queries = []

            async def list_entries(self, *, filter_, limit):
                self.queries.append(filter_)
                index = len(self.queries)
                return [LogSearchExecutionTests._entry(f"entry-{index}", f"2026-07-0{9 - index}T12:00:00Z")]

        fake = FakeLoggingClient()
        with (
            patch.object(log_search, "gcp_logging", fake),
            patch.object(log_search, "GCP_LOG_CHUNK_HOURS", 48),
            patch.object(log_search, "GCP_LOG_TOTAL_TIMEOUT_SECONDS", 45),
        ):
            result = await _search_custom_logs_internal(
                source="radius_wrappers",
                text_terms=[],
                identifiers=["guardian@example.com"],
                messages=[],
                query_ids=[],
                paths=[],
                endpoint_names=["customer-account"],
                status_codes=[],
                start_time="2026-07-01T00:00:00Z",
                end_time="2026-07-08T00:00:00Z",
                severity_min="DEFAULT",
                match_all_terms=False,
                limit=3,
                include_payload=True,
            )

        self.assertEqual(len(fake.queries), 3)
        self.assertIn('timestamp>="2026-07-06T00:00:00Z"', fake.queries[0])
        self.assertIn('timestamp<="2026-07-08T00:00:00Z"', fake.queries[0])
        self.assertTrue(result["chunking"]["enabled"])
        self.assertEqual(result["chunking"]["planned"], 4)
        self.assertFalse(result["chunking"]["payloadIncluded"])
        self.assertEqual(result["summary"]["total"], 3)
        self.assertIsNone(result["matches"][0]["payload"])
        self.assertTrue(any("Raw payloads were omitted" in warning for warning in result["warnings"]))
        self.assertTrue(any("global result limit" in warning for warning in result["warnings"]))

    async def test_transient_gcp_error_is_retried(self):
        class FlakyLoggingClient:
            def __init__(self):
                self.calls = 0

            async def list_entries(self, *, filter_, limit):
                self.calls += 1
                if self.calls == 1:
                    raise GcpLoggingError("503 Service Unavailable")
                return [LogSearchExecutionTests._entry("entry-ok", "2026-07-02T00:00:00Z")]

        fake = FlakyLoggingClient()
        with (
            patch.object(log_search, "gcp_logging", fake),
            patch.object(log_search, "GCP_LOG_MAX_ATTEMPTS", 2),
            patch.object(log_search, "GCP_LOG_RETRY_BACKOFF_SECONDS", 0),
        ):
            result = await _search_custom_logs_internal(
                source="radius_wrappers",
                text_terms=[],
                identifiers=["guardian@example.com"],
                messages=[],
                query_ids=[],
                paths=[],
                endpoint_names=["customer-account"],
                status_codes=[],
                start_time="2026-07-01T00:00:00Z",
                end_time="2026-07-02T00:00:00Z",
                severity_min="DEFAULT",
                match_all_terms=False,
                limit=10,
                include_payload=False,
            )

        self.assertEqual(fake.calls, 2)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["chunking"]["chunks"][0]["attempts"], 2)
        self.assertEqual(result["summary"]["total"], 1)

    async def test_chunk_boundary_entries_are_deduplicated(self):
        duplicate = self._entry("same-insert-id", "2026-07-02T00:00:00Z")

        class BoundaryLoggingClient:
            def __init__(self):
                self.calls = 0

            async def list_entries(self, *, filter_, limit):
                self.calls += 1
                if self.calls == 1:
                    return [duplicate]
                return [duplicate, LogSearchExecutionTests._entry("older-entry", "2026-07-01T12:00:00Z")]

        fake = BoundaryLoggingClient()
        with (
            patch.object(log_search, "gcp_logging", fake),
            patch.object(log_search, "GCP_LOG_CHUNK_HOURS", 24),
        ):
            result = await _search_custom_logs_internal(
                source="radius_wrappers",
                text_terms=[],
                identifiers=["guardian@example.com"],
                messages=[],
                query_ids=[],
                paths=[],
                endpoint_names=["customer-account"],
                status_codes=[],
                start_time="2026-07-01T00:00:00Z",
                end_time="2026-07-03T00:00:00Z",
                severity_min="DEFAULT",
                match_all_terms=False,
                limit=10,
                include_payload=False,
            )

        self.assertEqual(fake.calls, 2)
        self.assertEqual(result["summary"]["total"], 2)
        self.assertEqual([row["insertId"] for row in result["matches"]], ["same-insert-id", "older-entry"])
        self.assertTrue(result["chunking"]["complete"])


if __name__ == "__main__":
    unittest.main()
