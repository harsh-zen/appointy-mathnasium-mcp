import unittest
from unittest.mock import AsyncMock, patch
from appointy_mathnasium_mcp.support_reads import (
    read_entity,
    encode_cursor,
    decode_cursor,
    window,
)
from appointy_mathnasium_mcp.scopes import full_id
from appointy_mathnasium_mcp.errors import AppointyApiError

G = "grp_test"
C = G + "/com_1"
L = C + "/loc_1"
S = C + "/stu_1"


class VerifiedReadTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.scope = patch("appointy_mathnasium_mcp.scopes.MATHNASIUM_GROUP_ID", G)
        self.scope.start()
        self.addCleanup(self.scope.stop)

    async def test_short_ids_and_foreign_scope(self):
        self.assertEqual(await full_id("loc_1", company="com_1"), L)
        self.assertEqual(await full_id("stu_1", company=C), S)
        with self.assertRaises(ValueError):
            await full_id("grp_other/com_1/loc_1")
        with self.assertRaises(ValueError):
            await full_id("stu_1")

    async def test_validation_no_network(self):
        for kind, args in [
            ("bookable_slots", dict(parent_id=L)),
            ("enrollment_balance", {}),
            ("availability_window", dict(parent_id=L)),
            ("recurring_series", {}),
        ]:
            with (
                self.subTest(kind=kind),
                patch(
                    "appointy_mathnasium_mcp.support_reads.graphql",
                    new_callable=AsyncMock,
                ) as gql,
            ):
                with self.assertRaises(ValueError):
                    await read_entity(entity_type=kind, **args)
                gql.assert_not_called()

    async def test_booking_policy_preserved(self):
        data = {
            "serviceSetting": {
                "bookingRules": {
                    "leadAndCancellationSetting": {
                        "forCancellation": {
                            "policyType": "AllowUpdate",
                            "minAdvanceInterval": {
                                "interval": {"count": 24, "frequency": "HOUR"}
                            },
                        }
                    }
                }
            }
        }
        with patch(
            "appointy_mathnasium_mcp.support_reads.graphql",
            new_callable=AsyncMock,
            return_value=data,
        ):
            r = await read_entity(entity_type="booking_rules", parent_id=L)
            self.assertEqual(r["data"], data)
            self.assertIn("AllowUpdate", r["warnings"][0])

    async def test_rule_native_pagination(self):
        data = {
            "openHourRules": {
                "edges": [{"node": {"id": "rule_1"}}],
                "pageInfo": {"hasNextPage": True, "endCursor": "next"},
            }
        }
        with patch(
            "appointy_mathnasium_mcp.support_reads.graphql",
            new_callable=AsyncMock,
            return_value=data,
        ) as gql:
            first = await read_entity(
                entity_type="availability_rules", parent_id=L, limit=1
            )
            await read_entity(
                entity_type="availability_rules",
                parent_id=L,
                limit=1,
                cursor=first["next_cursor"],
            )
            self.assertEqual(gql.call_args.args[1]["a"], "next")
            with self.assertRaises(ValueError):
                await read_entity(
                    entity_type="availability_rules",
                    parent_id=C + "/loc_2",
                    cursor=first["next_cursor"],
                )

    async def test_local_slot_output_bounded(self):
        data = {
            "mathnasiumAvailability": {
                "nodes": [
                    {
                        "studentId": S,
                        "slots": [{"slot": {"capacity": 5}} for _ in range(5)],
                    }
                ]
            }
        }
        with patch(
            "appointy_mathnasium_mcp.support_reads.graphql",
            new_callable=AsyncMock,
            return_value=data,
        ):
            r = await read_entity(
                entity_type="bookable_slots",
                parent_id=L,
                student_id=S,
                enrollment_id=S + "/enr_1",
                service_id=L + "/srv_1",
                duration=1800,
                start="2026-11-12T00:00:00Z",
                end="2026-11-13T00:00:00Z",
                limit=2,
            )
            self.assertEqual(len(r["data"]["mathnasiumAvailability"]["items"]), 2)
            self.assertTrue(r["has_more"])
            self.assertIn("not establish", r["warnings"][0])

    async def test_incomplete_cursor_is_error(self):
        with patch(
            "appointy_mathnasium_mcp.support_reads.graphql",
            new_callable=AsyncMock,
            return_value={"openHourRules": {"pageInfo": {"hasNextPage": True}}},
        ):
            with self.assertRaises(AppointyApiError):
                await read_entity(entity_type="availability_rules", parent_id=L)

    def test_window_and_cursor_validation(self):
        for start, end in [
            ("2026-11-12", "2026-11-13"),
            ("2026-11-13T00:00:00Z", "2026-11-12T00:00:00Z"),
        ]:
            with self.assertRaises(ValueError):
                window(start, end)
        c = encode_cursor("x", {"a": 1})
        self.assertEqual(decode_cursor(c, {"a": 1}), "x")
        with self.assertRaises(ValueError):
            decode_cursor(c, {"a": 2})


class SettingsFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_company_missing_from_cache_uses_direct_read(self):
        from appointy_mathnasium_mcp.domain import _get_context_entity_internal

        raw = {"data": {"viewer": {"groups": [{"id": G, "companies": []}]}}}
        with (
            patch("appointy_mathnasium_mcp.domain.MATHNASIUM_GROUP_ID", G),
            patch("appointy_mathnasium_mcp.scopes.MATHNASIUM_GROUP_ID", G),
            patch(
                "appointy_mathnasium_mcp.domain._get_group_context_raw_cached",
                new_callable=AsyncMock,
                return_value=raw,
            ),
            patch(
                "appointy_mathnasium_mcp.support_reads.graphql",
                new_callable=AsyncMock,
                return_value={"company": {"id": C, "metadata": "", "apps": []}},
            ) as gql,
        ):
            r = await _get_context_entity_internal(
                entity_type="company_settings",
                company_id="com_1",
                location_id=None,
                refresh=False,
            )
            self.assertEqual(r["status"], "success")
            self.assertEqual(gql.call_args.args[1]["id"], C)

    async def test_conflicting_scope_rejected(self):
        with (
            patch("appointy_mathnasium_mcp.scopes.MATHNASIUM_GROUP_ID", G),
            patch(
                "appointy_mathnasium_mcp.support_reads.graphql", new_callable=AsyncMock
            ) as gql,
        ):
            with self.assertRaises(ValueError):
                await read_entity(
                    entity_type="booking_rules", parent_id=L, company=G + "/com_2"
                )
            gql.assert_not_called()


class CatalogTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_catalog_and_read_only_hints(self):
        from appointy_mathnasium_mcp import tools

        catalog = await tools.mcp.list_tools()
        by_name = {t.name: t for t in catalog}
        self.assertEqual(len(catalog), 7)
        for name in [
            "mathnasium_get_entity",
            "mathnasium_find_appointments",
            "mathnasium_search_custom_logs",
        ]:
            self.assertTrue(by_name[name].annotations.readOnlyHint)
        props = by_name["mathnasium_get_entity"].inputSchema["properties"]
        self.assertIn("bookable_slots", props["entityType"]["enum"])
        self.assertIn("cursor", props)
        self.assertNotIn("query", props)
