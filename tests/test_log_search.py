import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from appointy_mathnasium_mcp import log_search
from appointy_mathnasium_mcp.errors import GcpLoggingError
from appointy_mathnasium_mcp.log_search import (
    _build_custom_logs_filter,
    _search_custom_logs_internal,
)


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

        self.assertIn(
            'jsonPayload.message="Successful" OR jsonPayload.message="Failed"', query
        )
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
            timestamp=datetime.fromisoformat(
                timestamp.replace("Z", "+00:00")
            ).astimezone(timezone.utc),
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

            async def list_page(self, *, filter_, limit, page_token=None, timeout=20):
                self.queries.append(filter_)
                index = len(self.queries)
                return [
                    LogSearchExecutionTests._entry(
                        f"entry-{index}", f"2026-07-0{9 - index}T12:00:00Z"
                    )
                ], None

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

        self.assertEqual(len(fake.queries), 1)
        self.assertIn('timestamp>="2026-07-06T00:00:00Z"', fake.queries[0])
        self.assertIn('timestamp<="2026-07-08T00:00:00Z"', fake.queries[0])
        self.assertTrue(result["chunking"]["enabled"])
        self.assertEqual(result["chunking"]["planned"], 4)
        self.assertFalse(result["chunking"]["payloadIncluded"])
        self.assertEqual(result["summary"]["total"], 1)
        self.assertIsNone(result["matches"][0]["payload"])
        self.assertTrue(
            any(
                "Raw payloads were omitted" in warning for warning in result["warnings"]
            )
        )
        self.assertIsNotNone(result["next_cursor"])

    async def test_transient_gcp_error_is_retried(self):
        class FlakyLoggingClient:
            def __init__(self):
                self.calls = 0

            async def list_page(self, *, filter_, limit, page_token=None, timeout=20):
                self.calls += 1
                if self.calls == 1:
                    raise GcpLoggingError("503 Service Unavailable")
                return [
                    LogSearchExecutionTests._entry("entry-ok", "2026-07-02T00:00:00Z")
                ], None

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

    async def test_nonempty_chunk_returns_continuation_without_scanning_older_chunks(
        self,
    ):
        duplicate = self._entry("same-insert-id", "2026-07-02T00:00:00Z")

        class BoundaryLoggingClient:
            def __init__(self):
                self.calls = 0

            async def list_page(self, *, filter_, limit, page_token=None, timeout=20):
                self.calls += 1
                if self.calls == 1:
                    return [duplicate], None
                return [
                    duplicate,
                    LogSearchExecutionTests._entry(
                        "older-entry", "2026-07-01T12:00:00Z"
                    ),
                ], None

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

        self.assertEqual(fake.calls, 1)
        self.assertEqual(result["summary"]["total"], 1)
        self.assertEqual(result["matches"][0]["insertId"], "same-insert-id")
        self.assertFalse(result["chunking"]["complete"])
        self.assertIsNotNone(result["next_cursor"])




class LogContinuationTests(unittest.IsolatedAsyncioTestCase):
    def args(self):
        return dict(
            source="radius_wrappers",
            text_terms=[],
            identifiers=["example@test.invalid"],
            messages=[],
            query_ids=[],
            paths=[],
            endpoint_names=["student"],
            status_codes=[],
            start_time="2026-11-11T00:00:00Z",
            end_time="2026-11-11T01:00:00Z",
            severity_min="DEFAULT",
            match_all_terms=False,
            limit=1,
            include_payload=False,
        )

    async def test_native_cursor_no_dropped_rows(self):
        from unittest.mock import AsyncMock

        fake = SimpleNamespace(
            list_page=AsyncMock(
                side_effect=[
                    (
                        [LogSearchExecutionTests._entry("one", "2026-11-11T00:30:00Z")],
                        "page2",
                    ),
                    (
                        [LogSearchExecutionTests._entry("two", "2026-11-11T00:20:00Z")],
                        None,
                    ),
                ]
            )
        )
        with patch.object(log_search, "gcp_logging", fake):
            first = await _search_custom_logs_internal(**self.args())
            second = await _search_custom_logs_internal(
                **self.args(), cursor=first["next_cursor"]
            )
        self.assertEqual(fake.list_page.call_args.kwargs["page_token"], "page2")
        self.assertEqual(first["matches"][0]["insertId"], "one")
        self.assertEqual(second["matches"][0]["insertId"], "two")
        self.assertFalse(second["has_more"])

    async def test_timeout_returns_retryable_partial_not_empty_success(self):
        import asyncio
        from unittest.mock import AsyncMock

        fake = SimpleNamespace(list_page=AsyncMock(side_effect=asyncio.TimeoutError))
        with patch.object(log_search, "gcp_logging", fake):
            r = await _search_custom_logs_internal(**self.args())
        self.assertEqual(r["status"], "partial")
        self.assertTrue(r["partial"])
        self.assertIsNotNone(r["next_cursor"])

    async def test_summary_and_cursor_filter_binding(self):
        from unittest.mock import AsyncMock

        fake = SimpleNamespace(
            list_page=AsyncMock(
                return_value=(
                    [LogSearchExecutionTests._entry("one", "2026-11-11T00:30:00Z")],
                    "next",
                )
            )
        )
        with patch.object(log_search, "gcp_logging", fake):
            r = await _search_custom_logs_internal(**self.args(), summary_only=True)
            self.assertEqual(r["matches"], [])
            self.assertEqual(r["summary"]["total"], 1)
            bad = await _search_custom_logs_internal(
                **{**self.args(), "identifiers": ["different"]},
                cursor=r["next_cursor"],
                summary_only=True,
            )
            self.assertEqual(bad["status"], "failed")

class ConcurrentLogTests(unittest.IsolatedAsyncioTestCase):
    async def test_three_calls_can_run_together(self):
        import asyncio
        active = 0
        maximum = 0
        class Fake:
            async def list_page(self, **kwargs):
                nonlocal active, maximum
                active += 1
                maximum = max(maximum, active)
                await asyncio.sleep(0.02)
                active -= 1
                return [], None
        with patch.object(log_search, 'gcp_logging', Fake()):
            results = await asyncio.gather(*[_search_custom_logs_internal(**LogContinuationTests().args()) for _ in range(3)])
        self.assertEqual(maximum, 3)
        self.assertTrue(all(r['status'] == 'success' for r in results))


if __name__ == "__main__":
    unittest.main()
