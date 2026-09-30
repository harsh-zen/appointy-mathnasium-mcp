import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from appointy_mathnasium_mcp.appointment_search import find_appointments


def search(**changes):
    arguments = dict(student_id="stu_123", customer_id=None, location_id=None,
                     start_from="2026-09-29T00:00:00Z", start_to="2026-10-01T00:00:00Z",
                     status=None, recurring_id=None, order="asc", cursor=None, page_size=25)
    arguments.update(changes)
    return asyncio.run(find_appointments(**arguments))


def appointment(student="stu_123", status="CONFIRMED", start="2026-09-30T15:45:00Z"):
    return {"id": "apt_1", "status": status, "recurringId": "rec_1",
            "timeSlot": {"startTime": start, "endTime": "2026-09-30T16:45:00Z"},
            "service": {"_id": "srv_1"}, "consumers": [{"_id": student, "timezone": "Europe/London",
                         "original": {"__typename": "Student", "id": student,
                                      "primaryGuardian": {"id": "cust_1"}}}],
            "booked_on": "2026-09-28T12:00:00Z", "source": "ADMIN"}


class AppointmentSearchTests(unittest.TestCase):
    def test_rejects_location_only(self):
        result = search(student_id=None, location_id="loc_123", start_from=None, start_to=None)
        self.assertEqual(result["status"], "failed")
        self.assertIn("location_id alone", result["error"])

    def test_rejects_oversized_window(self):
        result = search(start_to="2026-12-01T00:00:00Z")
        self.assertEqual(result["status"], "failed")

    def test_filters_and_pages(self):
        payload = {"data": {"appointmentCalendar": {"appointments": [
            appointment(), appointment(student="stu_other"),
            dict(appointment(status="CANCELLED"), id="apt_2"),
        ]}}}
        with patch("appointy_mathnasium_mcp.appointment_search.appointy._graphql", new_callable=AsyncMock) as graphql:
            graphql.return_value = payload
            first = search(status=["CONFIRMED", "CANCELLED"], customer_id="cust_1", page_size=1)
            self.assertEqual(first["total"], 2)
            self.assertEqual(first["appointments"][0]["id"], "apt_1")
            self.assertTrue(first["has_more"])
            second = search(status=["CONFIRMED", "CANCELLED"], customer_id="cust_1", page_size=1,
                            cursor=first["next_cursor"])
            self.assertEqual(second["appointments"][0]["id"], "apt_2")
            self.assertEqual(graphql.call_args.kwargs["variables"]["startTime"], "2026-09-29T00:00:00+00:00")

    def test_status_filter_and_compact_size(self):
        payload = {"data": {"appointmentCalendar": {"appointments": [dict(appointment(), id=f"apt_{n}") for n in range(25)]}}}
        with patch("appointy_mathnasium_mcp.appointment_search.appointy._graphql", new_callable=AsyncMock) as graphql:
            graphql.return_value = payload
            result = search()
        import json
        self.assertLess(len(json.dumps(result).encode()), 10_000)
        self.assertEqual(len(result["appointments"]), 25)

    def test_default_window_cursor_remains_valid(self):
        payload = {"data": {"appointmentCalendar": {"appointments": [
            dict(appointment(start="2026-09-30T15:45:00Z"), id="apt_1"),
            dict(appointment(start="2026-09-30T16:45:00Z"), id="apt_2"),
        ]}}}
        with patch("appointy_mathnasium_mcp.appointment_search.appointy._graphql", new_callable=AsyncMock) as graphql, \
             patch("appointy_mathnasium_mcp.appointment_search.datetime") as clock:
            from datetime import datetime, timezone
            clock.now.return_value = datetime(2026, 9, 30, tzinfo=timezone.utc)
            clock.fromisoformat.side_effect = datetime.fromisoformat
            graphql.return_value = payload
            first = search(start_from=None, start_to=None, page_size=1)
            second = search(start_from=None, start_to=None, page_size=1, cursor=first["next_cursor"])
        self.assertEqual(second["status"], "success")
        self.assertEqual(second["appointments"][0]["id"], "apt_2")


if __name__ == "__main__":
    unittest.main()
