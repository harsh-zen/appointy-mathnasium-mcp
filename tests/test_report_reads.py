import unittest
from unittest.mock import AsyncMock, patch

from appointy_mathnasium_mcp.support_reads import read_entity
from appointy_mathnasium_mcp.errors import AppointyApiError

G = "grp_test"
C = G + "/com_1"
L = C + "/loc_1"


def native(field, rows, more=False, offset=None):
    key = "data" if field == "enrollmentUnderUtilizationReport" else "node"
    return {
        field: {
            "edges": [{key: r} for r in rows],
            "total": 2,
            "pageInfo": {"hasNextPage": more, "nextOffset": offset},
        }
    }


class ReportReadTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        p = patch("appointy_mathnasium_mcp.scopes.MATHNASIUM_GROUP_ID", G)
        p.start()
        self.addCleanup(p.stop)

    async def test_monthly_forwarding_and_native_cursor(self):
        data = native(
            "enrollmentUnderUtilizationReport",
            [
                {
                    "enrolmentId": "enr_1",
                    "allowedSessions": 8,
                    "bookedSessions": [{"month": "2026-11", "count": 9}],
                }
            ],
            True,
            1,
        )
        args = dict(
            entity_type="monthly_utilization",
            parent_id=L,
            report_month="2026-11",
            timezone="Europe/London",
            limit=1,
        )
        with patch(
            "appointy_mathnasium_mcp.support_reads.graphql",
            new_callable=AsyncMock,
            return_value=data,
        ) as gql:
            r = await read_entity(**args)
            self.assertEqual(r["data"]["items"][0]["bookedSessions"][0]["count"], 9)
            self.assertEqual(gql.call_args.args[1]["date"], "2026-11-01T00:00:00Z")
            self.assertEqual(gql.call_args.args[1]["tz"], "Europe/London")
            data[next(iter(data))]["pageInfo"] = {
                "hasNextPage": False,
                "nextOffset": None,
            }
            await read_entity(**args, cursor=r["next_cursor"])
            self.assertEqual(gql.call_args.args[1]["o"], 1)
            for changed in [
                {"report_month": "2026-12"},
                {"timezone": "UTC"},
                {"parent_id": C},
                {"limit": 2},
            ]:
                with (
                    self.subTest(changed=changed),
                    self.assertRaisesRegex(ValueError, "different filters"),
                ):
                    await read_entity(**{**args, **changed}, cursor=r["next_cursor"])

    async def test_notification_address_dates_and_cursor(self):
        data = native(
            "notificationReport",
            [{"id": "n1", "notificationAddress": "parent@example.com"}],
            True,
            1,
        )
        args = dict(
            entity_type="notification_history",
            parent_id=L,
            notification_address="parent@example.com",
            start="2026-11-15T00:00:00Z",
            end="2026-11-16T00:00:00Z",
            limit=1,
        )
        with patch(
            "appointy_mathnasium_mcp.support_reads.graphql",
            new_callable=AsyncMock,
            return_value=data,
        ) as gql:
            r = await read_entity(**args)
            self.assertEqual(gql.call_args.args[1]["address"], "parent@example.com")
            self.assertEqual(r["data"]["total"], 2)
            data[next(iter(data))]["pageInfo"] = {
                "hasNextPage": False,
                "nextOffset": None,
            }
            await read_entity(**args, cursor=r["next_cursor"])
            with self.assertRaisesRegex(ValueError, "different filters"):
                await read_entity(
                    **{**args, "notification_address": "other@example.com"},
                    cursor=r["next_cursor"],
                )
            self.assertTrue(any("does not prove delivery" in w for w in r["warnings"]))

    async def test_overbooking_local_pages_and_truncation(self):
        data = {
            "mathnasiumOverBookingReport": {
                "nodes": [{"id": "a"}, {"id": "b"}],
                "total": 3,
                "downloadLimit": 2,
            }
        }
        args = dict(
            entity_type="overbooking_report",
            parent_id=L,
            report_month="2026-11",
            limit=1,
        )
        with patch(
            "appointy_mathnasium_mcp.support_reads.graphql",
            new_callable=AsyncMock,
            return_value=data,
        ) as gql:
            r = await read_entity(**args)
            self.assertEqual(r["status"], "partial")
            self.assertTrue(r["source_truncated"])
            self.assertEqual(r["data"]["items"], [{"id": "a"}])
            p = await read_entity(**args, cursor=r["next_cursor"])
            self.assertEqual(p["data"]["items"], [{"id": "b"}])
            self.assertFalse(p["has_more"])
            self.assertTrue(p["source_truncated"])
            self.assertNotIn("o", gql.call_args.args[1])

    async def test_empty_overbooking_is_success(self):
        with patch(
            "appointy_mathnasium_mcp.support_reads.graphql",
            new_callable=AsyncMock,
            return_value={
                "mathnasiumOverBookingReport": {
                    "nodes": [],
                    "total": 0,
                    "downloadLimit": 500,
                }
            },
        ):
            r = await read_entity(
                entity_type="overbooking_report", parent_id=C, report_month="2026-11"
            )
        self.assertEqual(r["status"], "success")
        self.assertEqual(r["data"]["items"], [])

    async def test_validation_before_network(self):
        cases = [
            dict(entity_type="monthly_utilization", parent_id=L),
            dict(
                entity_type="monthly_utilization", parent_id=L, report_month="2026-13"
            ),
            dict(
                entity_type="monthly_utilization",
                parent_id=L,
                report_month="2026-11",
                timezone="bad/zone",
            ),
            dict(
                entity_type="monthly_utilization",
                parent_id=L,
                report_month="2026-11",
                student_id=C + "/stu_1",
            ),
            dict(
                entity_type="overbooking_report",
                parent_id=L,
                report_month="2026-11",
                timezone="Europe/London",
            ),
            dict(
                entity_type="overbooking_report",
                parent_id=L,
                report_month="2026-11",
                limit=51,
            ),
            dict(
                entity_type="overbooking_report",
                parent_id=L + "/srv_1",
                report_month="2026-11",
            ),
            dict(
                entity_type="notification_history",
                parent_id=L,
                start="2026-11-01T00:00:00Z",
                end="2026-11-03T00:00:00Z",
            ),
            dict(entity_type="notification_history", parent_id=L),
            dict(
                entity_type="notification_history",
                parent_id=L,
                notification_address=" ",
            ),
            dict(
                entity_type="notification_history", parent_id=L, report_month="2026-11"
            ),
            dict(entity_type="overbooking_report", report_month="2026-11"),
            dict(
                entity_type="monthly_utilization",
                parent_id=L,
                report_month="2026-11",
                company=G + "/com_2",
            ),
        ]
        with patch(
            "appointy_mathnasium_mcp.support_reads.graphql", new_callable=AsyncMock
        ) as gql:
            for args in cases:
                with self.subTest(args=args), self.assertRaises(ValueError):
                    await read_entity(**args)
            gql.assert_not_called()

    async def test_malformed_pagination_rejected(self):
        for payload in [
            {},
            {"notificationReport": {"edges": [], "pageInfo": {}}},
            native("notificationReport", [], True, None),
            native("notificationReport", [], True, 0),
        ]:
            with (
                self.subTest(payload=payload),
                patch(
                    "appointy_mathnasium_mcp.support_reads.graphql",
                    new_callable=AsyncMock,
                    return_value=payload,
                ),
            ):
                with self.assertRaises(AppointyApiError):
                    await read_entity(
                        entity_type="notification_history",
                        parent_id=L,
                        start="2026-11-15T00:00:00Z",
                        end="2026-11-16T00:00:00Z",
                    )

    async def test_existing_entities_reject_report_arguments(self):
        with self.assertRaisesRegex(ValueError, "only to report"):
            await read_entity(
                entity_type="services", parent_id=L, report_month="2026-11"
            )

    async def test_upstream_denial_not_empty_success(self):
        with patch(
            "appointy_mathnasium_mcp.support_reads.graphql",
            new_callable=AsyncMock,
            side_effect=AppointyApiError("denied"),
        ):
            with self.assertRaises(AppointyApiError):
                await read_entity(
                    entity_type="monthly_utilization",
                    parent_id=L,
                    report_month="2026-11",
                )

    async def test_schema_lists_reports_and_arguments(self):
        from appointy_mathnasium_mcp.tools import mcp

        tool = next(
            t for t in await mcp.list_tools() if t.name == "mathnasium_get_entity"
        )
        props = tool.inputSchema["properties"]
        self.assertEqual(len(props["entityType"]["enum"]), 27)
        self.assertIn("reportMonth", props)
        self.assertIn("notificationAddress", props)
