import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from appointy_mathnasium_mcp.enrollment_sync import PATH, balance, project_event, read_enrollment_sync


def event(body, response=None, outcome="Successful", method="PUT"):
    return {"timestamp": "2026-11-17T00:01:00Z", "insertId": "entry-1", "payload": {
        "PATH": PATH, "METHOD": method, "message": outcome, "REQUEST_BODY": body,
        "RESPONSE": response, "EnrolmentUpdated_0": "Enrolment Id: 42",
        "error": "write failed" if outcome == "Failed" else "",
    }}


BODY = 'student:<enrolments:<enrolment_id:"420" remaining_sessions:9 > enrolments:<enrolment_id:"42" holds:<remaining_sessions:99 note:">"> remaining_sessions:0 > >'


class EnrollmentSyncTests(unittest.IsolatedAsyncioTestCase):
    def test_exact_id_and_direct_fields(self):
        self.assertEqual(balance(BODY, "42"), (0, True))
        self.assertEqual(balance(BODY, "420"), (9, True))
        self.assertEqual(balance(BODY, "4"), (None, False))
        self.assertEqual(balance('enrolments:<enrolment_id:"42" >', "42"), (None, True))
        self.assertEqual(balance('enrolments:<enrolment_id:"42" remaining_sessions:4', "42"), (None, False))

    def test_success_and_failure_do_not_conflate_balances(self):
        response = 'enrolments:<enrolment_id:"42" remaining_sessions:3 >'
        successful = project_event(event(BODY, response), "42")
        self.assertEqual(successful["receivedBalance"], 0)
        self.assertEqual(successful["successfulResponseBalance"], 3)
        self.assertTrue(successful["enrollmentUpdateReported"])
        self.assertIsNone(successful["requestId"])
        failed = project_event(event(BODY, response, "Failed"), "42")
        self.assertEqual(failed["receivedBalance"], 0)
        self.assertIsNone(failed["successfulResponseBalance"])
        self.assertFalse(failed["enrollmentUpdateReported"])
        self.assertEqual(failed["error"], "write failed")
        self.assertIsNone(project_event(event(BODY, method="POST"), "42"))

    async def test_exact_query_and_cursor(self):
        end = datetime.now(timezone.utc)
        args = ("42", (end - timedelta(minutes=10)).isoformat(), end.isoformat(), 5)
        with patch("appointy_mathnasium_mcp.enrollment_sync._list_entries_with_retry", new_callable=AsyncMock, return_value=([], "token", 1)) as call:
            result = await read_enrollment_sync(*args, None)
            query = call.call_args.kwargs["query"]
            self.assertIn(f'jsonPayload.PATH="{PATH}"', query)
            self.assertIn('jsonPayload.METHOD="PUT"', query)
            self.assertIn("timestamp<", query)
            self.assertNotIn("timestamp<=", query)
            self.assertTrue(result["has_more"])
            await read_enrollment_sync(*args, result["next_cursor"])
            self.assertEqual(call.call_args.kwargs["page_token"], "token")
            with self.assertRaisesRegex(ValueError, "different filters"):
                await read_enrollment_sync("420", *args[1:], result["next_cursor"])

    async def test_bad_id_and_long_window_rejected(self):
        end = datetime.now(timezone.utc)
        with patch("appointy_mathnasium_mcp.enrollment_sync._list_entries_with_retry", new_callable=AsyncMock) as call:
            for ident, start in [("grp_x/enr_42", end - timedelta(minutes=5)), ("42", end - timedelta(hours=2)), ("42", end - timedelta(days=31))]:
                with self.assertRaises(ValueError):
                    await read_enrollment_sync(ident, start.isoformat(), end.isoformat(), 5, None)
            call.assert_not_called()
