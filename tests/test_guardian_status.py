import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from appointy_mathnasium_mcp import domain
from appointy_mathnasium_mcp.errors import AppointyApiError
from appointy_mathnasium_mcp.guardian_status import guardian_active_from_students

NOW = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
G = "grp_test"
C = G + "/com_test"
U = C + "/cust_test"
S = C + "/stu_test"


class GuardianUIStatusTests(unittest.TestCase):
    def test_matches_executed_frontend_helper(self):
        fixture = json.loads(
            (Path(__file__).parent / "fixtures/guardian_ui_status.json").read_text()
        )
        for case in fixture["cases"]:
            with self.subTest(case=case["name"]):
                self.assertEqual(
                    guardian_active_from_students(case["students"], now=NOW),
                    case["expectedActive"],
                )

    def test_incomplete_data_is_unknown_not_default_true(self):
        for students in [
            None,
            {},
            [None],
            [{}],
            [{"enrolments": None}],
            [{"enrolments": [{"startDate": "2026-01-01T00:00:00Z"}]}],
        ]:
            with self.subTest(students=students):
                self.assertIsNone(guardian_active_from_students(students, now=NOW))

    def test_timezone_aware_reference_required(self):
        with self.assertRaises(ValueError):
            guardian_active_from_students([], now=datetime(2026, 11, 12))


class GuardianLookupStatusTests(unittest.IsolatedAsyncioTestCase):
    async def lookup(self, detail=None, failure=None):
        client = SimpleNamespace(
            find_guardians_graphql=AsyncMock(
                return_value={
                    "data": {
                        "customers": {
                            "edges": [
                                {
                                    "node": {
                                        "id": U,
                                        "firstName": "Jacob",
                                        "lastName": "Marlow",
                                        "active": True,
                                    }
                                }
                            ]
                        }
                    }
                }
            ),
            get_guardian_students_detail_graphql=AsyncMock(
                return_value=detail, side_effect=failure
            ),
        )
        with (
            patch.object(domain, "MATHNASIUM_GROUP_ID", G),
            patch.object(domain, "appointy", client),
            patch.object(
                domain,
                "_get_group_context_cached",
                new_callable=AsyncMock,
                return_value={"centerIndex": []},
            ),
            patch.object(
                domain,
                "guardian_active_from_students",
                side_effect=lambda students: guardian_active_from_students(
                    students, now=NOW
                ),
            ),
        ):
            return await domain._find_guardians_internal(
                parent_id=C,
                email=None,
                name="Jacob Marlow",
                first_name=None,
                last_name=None,
                phone=None,
                center_id=None,
                limit=10,
            )

    def payload(self, enrolments):
        return {
            "data": {
                "students": {
                    "edges": [
                        {
                            "node": {
                                "id": S,
                                "firstName": "Student",
                                "activeMembership": True,
                                "enrolments": enrolments,
                            }
                        }
                    ]
                },
                "customerLocationLinks": {"locationIds": []},
            }
        }

    async def test_jacob_regression_expired_students_are_inactive(self):
        r = await self.lookup(
            self.payload(
                [
                    {
                        "startDate": "2023-01-01T00:00:00Z",
                        "terminationDate": "2023-12-31T00:00:00Z",
                    }
                ]
            )
        )
        self.assertIs(r["matches"][0]["active"], False)
        self.assertEqual(r["matches"][0]["activeStatus"], "inactive")
        self.assertEqual(
            r["matches"][0]["activeStatusSource"], "admin_ui_enrollment_windows"
        )

    async def test_current_enrollment_is_active(self):
        r = await self.lookup(
            self.payload(
                [
                    {
                        "startDate": "2026-01-01T00:00:00Z",
                        "terminationDate": "2027-01-01T00:00:00Z",
                    }
                ]
            )
        )
        self.assertIs(r["matches"][0]["active"], True)

    async def test_future_booking_eligible_is_ui_inactive(self):
        r = await self.lookup(
            self.payload(
                [
                    {
                        "startDate": "2027-01-01T00:00:00Z",
                        "terminationDate": "2028-01-01T00:00:00Z",
                    }
                ]
            )
        )
        self.assertIs(r["matches"][0]["active"], False)
        self.assertTrue(r["matches"][0]["students"][0]["canScheduleSessions"])

    async def test_no_linked_students_is_inactive(self):
        r = await self.lookup({"data": {"students": {"edges": []}}})
        self.assertIs(r["matches"][0]["active"], False)

    async def test_failure_and_partial_data_stay_unknown(self):
        for detail, failure in [
            (None, AppointyApiError("read failed")),
            (None, None),
            ([], None),
            ({"data": {}}, None),
            (
                {
                    "data": {"students": {"edges": []}},
                    "errors": [{"message": "denied"}],
                },
                None,
            ),
            (self.payload(None), None),
        ]:
            with self.subTest(detail=detail):
                r = await self.lookup(detail, failure)
                self.assertIsNone(r["matches"][0]["active"])
                self.assertEqual(r["matches"][0]["activeStatus"], "unknown")
                self.assertTrue(r["warnings"])

    async def test_foreign_group_student_does_not_set_status(self):
        p = self.payload([])
        p["data"]["students"]["edges"][0]["node"]["id"] = "grp_other/com_x/stu_x"
        r = await self.lookup(p)
        self.assertIsNone(r["matches"][0]["active"])
        self.assertFalse(r["matches"][0]["students"])


if __name__ == "__main__":
    unittest.main()
