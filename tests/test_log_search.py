import unittest

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


if __name__ == "__main__":
    unittest.main()
