"""Filtered Appointy appointment reads using native cursor pagination."""

from datetime import datetime, timedelta, timezone
from typing import Optional, List

from . import support_queries
from .config import MATHNASIUM_GROUP_ID
from .scopes import company_id, full_id
from .support_reads import decode_cursor, encode_cursor, graphql, window

QUERY = support_queries.APPOINTMENTS


async def find_appointments(
    *,
    student_id: Optional[str],
    customer_id: Optional[str],
    location_id: Optional[str],
    start_from: Optional[str],
    start_to: Optional[str],
    status: Optional[List[str]],
    recurring_id: Optional[str],
    order: Optional[str],
    cursor: Optional[str],
    page_size: int,
    custom_status_ids=None,
):
    try:
        if not 1 <= page_size <= 50:
            raise ValueError("page_size must be between 1 and 50.")
        if recurring_id:
            raise ValueError(
                "Direct recurring-ID lookup is not API-key accessible. Use get_entity entityType=recurring_series with a seed appointment entityId."
            )
        if not (student_id or customer_id or (start_from and start_to)):
            raise ValueError(
                "Provide student_id, customer_id, or a date window of at most 62 days. location_id alone is insufficient."
            )
        if bool(start_from) != bool(start_to):
            raise ValueError("Provide both start_from and start_to.")
        now = datetime.now(timezone.utc)
        # Keep omitted default windows stable in the opaque cursor.
        base = {
            "student_id": student_id,
            "customer_id": customer_id,
            "location_id": location_id,
            "start_from": start_from,
            "start_to": start_to,
            "status": status or [],
            "custom_status_ids": custom_status_ids or [],
            "order": order or "desc",
        }
        continuation = decode_cursor(cursor, base)
        if continuation is not None and not isinstance(continuation, dict):
            raise ValueError("Invalid appointment cursor.")
        start = (
            start_from
            or (continuation or {}).get("start")
            or (now - timedelta(days=31)).isoformat()
        )
        end = (
            start_to
            or (continuation or {}).get("end")
            or (now + timedelta(days=31)).isoformat()
        )
        slot = window(start, end)
        if order not in {None, "asc", "desc"}:
            raise ValueError("order must be asc or desc.")
        loc = await full_id(location_id) if location_id else None
        seed = student_id or customer_id
        co = company_id(loc or seed) if loc or seed and "/" in seed else None
        student = await full_id(student_id, company=co) if student_id else None
        guardian = await full_id(customer_id, company=co) if customer_id else None
        statuses = []
        for value in status or []:
            value = value.upper()
            statuses.append(
                value if value.startswith("APPOINTMENT_") else f"APPOINTMENT_{value}"
            )
        variables = {
            "p": loc or co or MATHNASIUM_GROUP_ID,
            "c": {"consumerId": student} if student else None,
            "g": guardian,
            "slot": slot,
            "after": (continuation or {}).get("after"),
            "n": page_size,
            "status": (
                {
                    "statuses": statuses or None,
                    "customStatus": custom_status_ids or None,
                }
                if statuses or custom_status_ids
                else None
            ),
            "order": "Ascending" if order == "asc" else "Descending",
        }
        data = await graphql(QUERY, variables, company=co, location=loc)
        conn = data.get("appointments")
        if not isinstance(conn, dict) or not isinstance(conn.get("edges"), list):
            raise ValueError("Appointment response did not contain a connection.")
        items = []
        for edge in conn["edges"]:
            item = edge["node"]
            consumers = item.get("consumers") or []
            students = [
                c
                for c in consumers
                if "/stu_" in c.get("_id", "") or c.get("_id", "").startswith("stu_")
            ]
            selected = next(
                (c for c in students if c.get("_id") == student), None
            ) or next(iter(students), {})
            slot_value = item.get("timeSlot") or {}
            items.append(
                {
                    "id": item.get("id"),
                    "start": slot_value.get("startTime"),
                    "end": slot_value.get("endTime"),
                    "timezone": selected.get("timezone")
                    or next(
                        (c.get("timezone") for c in consumers if c.get("timezone")),
                        None,
                    ),
                    "status": item.get("status"),
                    "student_id": selected.get("_id"),
                    "customer_id": selected.get("bookingCustomerId"),
                    "service_id": (item.get("service") or {}).get("_id"),
                    "instructor_id": (item.get("employee") or {}).get("_id"),
                    "location_id": loc or item.get("id", "").split("/apt_")[0],
                    "recurring_id": item.get("recurringId"),
                    "repeat_rule": item.get("recurrenceSet"),
                    "created_at": item.get("booked_on"),
                    "created_by": item.get("booked_by"),
                    "created_by_admin": item.get("isBookedByAdmin"),
                    "updated_at": item.get("updatedOn"),
                    "updated_by": item.get("updatedBy"),
                    "last_status_updated_at": item.get("lastStatusUpdatedOn"),
                    "last_status_updated_by": item.get("lastStatusUpdatedBy"),
                    "attendance": [
                        {
                            "consumer_id": c.get("_id"),
                            "status": c.get("status"),
                            "custom_status": c.get("customStatus"),
                            "changed_at": c.get("customStatusLastChangedOn"),
                            "cancellation_reason": c.get("cancelationReason"),
                        }
                        for c in consumers
                    ],
                    "history": item.get("historicalData") or [],
                }
            )
        page = conn.get("pageInfo") or {}
        has_more = bool(page.get("hasNextPage"))
        if has_more and not page.get("endCursor"):
            raise ValueError("Upstream omitted the next cursor.")
        return {
            "status": "success",
            "filters": base,
            "window_applied": {
                "start": start,
                "end": end,
                "defaulted": not bool(start_from),
            },
            "appointments": items,
            "has_more": has_more,
            "next_cursor": (
                encode_cursor(
                    {"after": page["endCursor"], "start": start, "end": end}, base
                )
                if has_more
                else None
            ),
        }
    except ValueError as exc:
        return {"status": "failed", "error": str(exc)}
