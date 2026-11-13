import unittest
from unittest.mock import AsyncMock, patch

from appointy_mathnasium_mcp.support_reads import read_entity
from appointy_mathnasium_mcp import tools

G = "grp_test"
L = G + "/com_1/loc_1"
BASE = dict(
    entity_type="activity_logs",
    parent_id=L,
    start="2026-11-01T00:00:00Z",
    end="2026-11-02T00:00:00Z",
)


class ActivityFilterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        p = patch("appointy_mathnasium_mcp.scopes.MATHNASIUM_GROUP_ID", G)
        p.start()
        self.addCleanup(p.stop)

    async def test_filters_forwarded_and_echoed(self):
        data = {"activityLogs": {"edges": [], "pageInfo": {"hasNextPage": False}}}
        with patch(
            "appointy_mathnasium_mcp.support_reads.graphql",
            new_callable=AsyncMock,
            return_value=data,
        ) as gql:
            r = await read_entity(
                **BASE,
                event_ids=["ale_1"],
                display_event_name="Service updated",
                user_email="actor@example.com",
                user_id="usr_1",
                ip_address="192.0.2.1",
            )
        f = gql.call_args.args[1]["filter"]
        self.assertEqual(f["activityLogEventId"], ["ale_1"])
        for k, v in {
            "displayEventName": "Service updated",
            "userEmail": "actor@example.com",
            "userId": "usr_1",
            "ipAddress": "192.0.2.1",
        }.items():
            self.assertEqual(f[k], v)
            self.assertEqual(r["filters"][k], v)
        self.assertEqual(f["dateRange"]["startTime"], BASE["start"])

    async def test_unsupported_rejected_before_network(self):
        for k in [
            "entity_id",
            "service_id",
            "student_id",
            "guardian_id",
            "enrollment_id",
            "instructor_id",
            "duration",
        ]:
            with (
                self.subTest(k=k),
                patch(
                    "appointy_mathnasium_mcp.support_reads.graphql",
                    new_callable=AsyncMock,
                ) as gql,
            ):
                with self.assertRaisesRegex(ValueError, "does not support filters"):
                    await read_entity(**BASE, **{k: 30 if k == "duration" else "id"})
                gql.assert_not_called()

    async def test_blank_filters_rejected(self):
        for k in ["display_event_name", "user_email", "user_id", "ip_address"]:
            with (
                self.subTest(k=k),
                self.assertRaisesRegex(ValueError, "must not be blank"),
            ):
                await read_entity(**BASE, **{k: " "})

    async def test_cursor_bound_to_each_new_filter(self):
        data = {
            "activityLogs": {
                "edges": [],
                "pageInfo": {"hasNextPage": True, "nextOffset": 1},
            }
        }
        args = dict(
            display_event_name="Event",
            user_email="actor@example.com",
            user_id="usr_1",
            ip_address="192.0.2.1",
        )
        with patch(
            "appointy_mathnasium_mcp.support_reads.graphql",
            new_callable=AsyncMock,
            return_value=data,
        ) as gql:
            first = await read_entity(**BASE, **args)
            await read_entity(**BASE, **args, cursor=first["next_cursor"])
            self.assertEqual(gql.call_args.args[1]["o"], 1)
            gql.reset_mock()
            for key in args:
                with (
                    self.subTest(key=key),
                    self.assertRaisesRegex(ValueError, "different filters"),
                ):
                    await read_entity(
                        **BASE, **{**args, key: "changed"}, cursor=first["next_cursor"]
                    )
            gql.assert_not_called()

    async def test_public_legacy_type_and_wrong_entity_rejected(self):
        with (
            patch.object(tools, "require_config", return_value=None),
            patch.object(tools, "read_entity", new_callable=AsyncMock) as read,
        ):
            r = await tools.mathnasium_get_entity(
                entityType="activity_logs", parentId=L, type="service"
            )
            self.assertEqual(r["status"], "failed")
            self.assertIn("type is not a supported filter", r["error"])
            r = await tools.mathnasium_get_entity(
                entityType="services", parentId=L, userId="usr_1"
            )
            self.assertEqual(r["status"], "failed")
            read.assert_not_called()

    async def test_catalog_explains_filter_scope(self):
        catalog = {t.name: t for t in await tools.mcp.list_tools()}
        props = catalog["mathnasium_get_entity"].inputSchema["properties"]
        for k in ["displayEventName", "userEmail", "userId", "ipAddress"]:
            self.assertIn("activity_logs only", props[k]["description"])
        self.assertIn("Always rejected", props["type"]["description"])
