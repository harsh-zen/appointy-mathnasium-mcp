import unittest

from appointy_mathnasium_mcp import clients
from appointy_mathnasium_mcp.errors import AppointyApiError


class AppointyClientConfigTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_surfaces_missing_config_without_name_error(self):
        client = clients.AppointyClient()
        original_base_url = clients.APPOINTY_API_BASE_URL
        original_api_key = clients.APPOINTY_API_KEY
        original_group_id = clients.MATHNASIUM_GROUP_ID
        try:
            clients.APPOINTY_API_BASE_URL = ""
            clients.APPOINTY_API_KEY = None
            clients.MATHNASIUM_GROUP_ID = None
            with self.assertRaises(AppointyApiError) as raised:
                await client._request("GET", "/health")
            self.assertIn(
                "Missing required environment variables", str(raised.exception)
            )
        finally:
            clients.APPOINTY_API_BASE_URL = original_base_url
            clients.APPOINTY_API_KEY = original_api_key
            clients.MATHNASIUM_GROUP_ID = original_group_id


class StudentScopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_hydrates_only_confirmed_group_ids(self):
        import base64
        import json
        from unittest.mock import AsyncMock, patch

        client = clients.AppointyClient()
        g = "grp_test"
        rows = [
            {"appointy_id": g + "/com_1/stu_1"},
            {"appointy_id": "grp_other/com_2/stu_2"},
        ]
        encoded = base64.b64encode(json.dumps(rows).encode()).decode()
        with (
            patch.object(clients, "MATHNASIUM_GROUP_ID", g),
            patch.object(
                client,
                "_graphql",
                new_callable=AsyncMock,
                return_value={
                    "data": {"mathnasiumSearchEntity": {"encodedData": encoded}}
                },
            ) as gql,
            patch.object(
                client,
                "get_student_detail_graphql",
                new_callable=AsyncMock,
                return_value={"data": {"student": {"id": g + "/com_1/stu_1"}}},
            ) as hydrate,
        ):
            result = await client.find_students_graphql(
                parent_id=g, student_name="Example"
            )
            self.assertEqual(len(result["data"]["students"]["edges"]), 1)
            self.assertEqual(hydrate.await_count, 1)
            self.assertIn("mathnasiumSearchEntity", gql.call_args.kwargs["query"])
            self.assertNotIn("students(parent:", gql.call_args.kwargs["query"])


class NativeLogPageTests(unittest.TestCase):
    def test_single_rpc_timeout_token_and_conversion(self):
        from unittest.mock import MagicMock, patch
        from google.cloud.logging_v2.types import LogEntry, ListLogEntriesResponse

        response = ListLogEntriesResponse(
            entries=[
                LogEntry(
                    log_name="projects/waqt-prod/logs/stdout",
                    json_payload={"message": "Failed"},
                    insert_id="test-entry",
                )
            ],
            next_page_token="next-native",
        )
        pager = MagicMock()
        pager.pages = iter([response])
        client = MagicMock()
        client.list_log_entries.return_value = pager
        with (
            patch(
                "google.cloud.logging_v2.services.logging_service_v2.LoggingServiceV2Client",
                return_value=client,
            ),
            patch.object(clients, "_ensure_google_credentials_file"),
            patch.object(clients, "require_gcp_logging_config", return_value=None),
            patch.object(clients, "logging_v2") as high,
        ):
            high.Client.return_value.project = "waqt-prod"
            entries, token = clients.GcpLoggingClient()._list_page_sync(
                filter_="exact-filter",
                limit=50,
                page_token="previous-native",
                timeout=3.5,
            )
            self.assertEqual(token, "next-native")
            self.assertEqual(entries[0].payload, {"message": "Failed"})
            self.assertEqual(entries[0].insert_id, "test-entry")
            self.assertEqual(client.list_log_entries.call_args.kwargs["timeout"], 3.5)
            self.assertIsNone(client.list_log_entries.call_args.kwargs["retry"])
            self.assertEqual(
                client.list_log_entries.call_args.kwargs["request"]["page_token"],
                "previous-native",
            )
            client.transport.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
