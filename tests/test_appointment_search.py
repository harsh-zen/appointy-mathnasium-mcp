import asyncio
import unittest
from unittest.mock import AsyncMock, patch
from appointy_mathnasium_mcp.appointment_search import find_appointments

G = "grp_test"
C = G + "/com_1"
L = C + "/loc_1"
S = C + "/stu_1"
U = C + "/cust_1"


def search(**changes):
    args = dict(
        student_id=S,
        customer_id=None,
        location_id=L,
        start_from="2026-09-01T00:00:00Z",
        start_to="2026-10-01T00:00:00Z",
        status=None,
        recurring_id=None,
        order="desc",
        cursor=None,
        page_size=25,
    )
    args.update(changes)
    with patch("appointy_mathnasium_mcp.scopes.MATHNASIUM_GROUP_ID", G):
        return asyncio.run(find_appointments(**args))


def connection(more=False):
    return {
        "appointments": {
            "edges": [
                {
                    "node": {
                        "id": L + "/apt_1",
                        "status": "APPOINTMENT_CONFIRMED",
                        "timeSlot": {
                            "startTime": "2026-09-30T15:45:00Z",
                            "endTime": "2026-09-30T16:15:00Z",
                        },
                        "consumers": [
                            {
                                "_id": S,
                                "bookingCustomerId": U,
                                "timezone": "Europe/London",
                                "customStatus": {"customStatusName": "No-show"},
                            }
                        ],
                    }
                }
            ],
            "pageInfo": {"hasNextPage": more, "endCursor": "native-token"},
        }
    }


class AppointmentSearchTests(unittest.TestCase):
    def test_location_only_rejected(self):
        self.assertIn(
            "location_id alone",
            search(student_id=None, start_from=None, start_to=None)["error"],
        )

    def test_oversized_window_rejected(self):
        self.assertEqual(search(start_to="2026-12-01T00:00:00Z")["status"], "failed")

    def test_native_filters_and_cursor(self):
        with patch(
            "appointy_mathnasium_mcp.appointment_search.graphql", new_callable=AsyncMock
        ) as gql:
            gql.return_value = connection(True)
            first = search(customer_id=U, status=["CANCELLED"], page_size=1)
            self.assertTrue(first["has_more"])
            v = gql.call_args.args[1]
            self.assertEqual(v["c"], {"consumerId": S})
            self.assertEqual(v["g"], U)
            self.assertEqual(v["status"]["statuses"], ["APPOINTMENT_CANCELLED"])
            second = search(
                customer_id=U,
                status=["CANCELLED"],
                page_size=1,
                cursor=first["next_cursor"],
            )
            self.assertEqual(second["status"], "success")
            self.assertEqual(gql.call_args.args[1]["after"], "native-token")
            self.assertEqual(search(cursor=first["next_cursor"])["status"], "failed")

    def test_attendance_is_separate(self):
        with patch(
            "appointy_mathnasium_mcp.appointment_search.graphql",
            new_callable=AsyncMock,
            return_value=connection(),
        ) as gql:
            result = search(custom_status_ids=["cst_1"])
            self.assertEqual(gql.call_args.args[1]["status"]["customStatus"], ["cst_1"])
            self.assertEqual(
                result["appointments"][0]["attendance"][0]["custom_status"][
                    "customStatusName"
                ],
                "No-show",
            )

    def test_default_window_stable(self):
        with patch(
            "appointy_mathnasium_mcp.appointment_search.graphql",
            new_callable=AsyncMock,
            return_value=connection(True),
        ):
            first = search(start_from=None, start_to=None)
            second = search(start_from=None, start_to=None, cursor=first["next_cursor"])
            self.assertEqual(first["window_applied"], second["window_applied"])

    def test_foreign_group_and_bad_cursor(self):
        self.assertEqual(
            search(student_id="grp_foreign/com_1/stu_1")["status"], "failed"
        )
        self.assertEqual(search(cursor="nope")["status"], "failed")

    def test_direct_series_read_is_not_claimed(self):
        self.assertIn("seed appointment", search(recurring_id="rec_1")["error"])
