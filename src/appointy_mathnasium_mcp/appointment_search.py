"""Bounded, read-only appointment calendar lookup for support."""

import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .clients import appointy
from .config import MATHNASIUM_GROUP_ID
from .domain import _get_group_context_cached
from .queries import GRAPHQL_APPOINTMENT_CALENDAR_QUERY


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Date-times must include a timezone offset")
    return parsed.astimezone(timezone.utc)


def _matches_id(candidate: Any, wanted: Optional[str]) -> bool:
    return bool(candidate and wanted and str(candidate).split("/")[-1] == wanted.split("/")[-1])


def _encode_cursor(offset: int, fingerprint: str, start: datetime, end: datetime) -> str:
    data = {"offset": offset, "filter": fingerprint, "start": start.isoformat(), "end": end.isoformat()}
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")


async def find_appointments(
    *, student_id: Optional[str], customer_id: Optional[str], location_id: Optional[str],
    start_from: Optional[str], start_to: Optional[str], status: Optional[List[str]],
    recurring_id: Optional[str], order: Optional[str], cursor: Optional[str], page_size: int,
) -> Dict[str, Any]:
    if not (student_id or customer_id or recurring_id or (start_from and start_to)):
        return {"status": "failed", "error": "Provide student_id, customer_id, recurring_id, or a date window of at most 62 days. location_id alone is insufficient."}
    if bool(start_from) != bool(start_to):
        return {"status": "failed", "error": "Provide both start_from and start_to."}
    now = datetime.now(timezone.utc)
    cursor_data = None
    if cursor:
        try:
            cursor_data = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        except (ValueError, TypeError):
            return {"status": "failed", "error": "Invalid cursor."}
    try:
        start = _instant(start_from) if start_from else _instant(cursor_data["start"]) if cursor_data else now - timedelta(days=31)
        end = _instant(start_to) if start_to else _instant(cursor_data["end"]) if cursor_data else now + timedelta(days=31)
    except (ValueError, KeyError, TypeError) as exc:
        return {"status": "failed", "error": f"Invalid ISO 8601 date-time: {exc}"}
    if end <= start or end - start > timedelta(days=62):
        return {"status": "failed", "error": "Date window must be positive and at most 62 days."}

    scope = MATHNASIUM_GROUP_ID
    company_id = None
    resolved_location = None
    center_timezone = None
    if location_id:
        context = await _get_group_context_cached()
        centers = [row for row in context.get("centerIndex", []) if _matches_id(row.get("locationId"), location_id)]
        if len(centers) != 1:
            return {"status": "failed", "error": "location_id did not uniquely resolve to a Mathnasium center."}
        center = centers[0]
        scope = resolved_location = center["locationId"]
        company_id = center["companyId"]
        center_timezone = center.get("timezone")

    filters = {"student_id": student_id, "customer_id": customer_id, "location_id": location_id,
               "start_from": start.isoformat(), "start_to": end.isoformat(), "status": status or [],
               "recurring_id": recurring_id, "order": order or "nearest"}
    fingerprint = hashlib.sha256(json.dumps(filters, sort_keys=True).encode()).hexdigest()[:16]
    offset = 0
    if cursor:
        try:
            payload = cursor_data
            if payload["filter"] != fingerprint or not isinstance(payload["offset"], int) or payload["offset"] < 0:
                raise ValueError()
            offset = payload["offset"]
        except (ValueError, KeyError, TypeError):
            return {"status": "failed", "error": "Invalid cursor for these filters."}

    raw = await appointy._graphql(
        query_id="MathnasiumSupportAppointmentCalendar",
        query=GRAPHQL_APPOINTMENT_CALENDAR_QUERY,
        variables={"startTime": start.isoformat(), "endTime": end.isoformat(), "parents": [scope]},
        company_id=company_id,
        location_id=resolved_location,
    )
    if raw.get("errors"):
        return {"status": "failed", "error": "Appointment GraphQL query failed", "details": raw["errors"]}
    calendar = (raw.get("data") or {}).get("appointmentCalendar") or {}
    appointments = calendar.get("appointments")
    if not isinstance(appointments, list):
        return {"status": "failed", "error": "Appointment calendar response did not contain an appointments list."}

    selected = []
    for item in appointments:
        slot = item.get("timeSlot") or {}
        try:
            instant = _instant(slot.get("startTime", ""))
        except ValueError:
            continue
        if not start <= instant <= end:
            continue
        if status and str(item.get("status", "")).upper() not in {s.upper() for s in status}:
            continue
        if recurring_id and not _matches_id(item.get("recurringId"), recurring_id):
            continue
        consumers = item.get("consumers") or []
        students = [c for c in consumers if (c.get("original") or {}).get("__typename") == "Student"]
        customers = [c for c in consumers if (c.get("original") or {}).get("__typename") == "Customer"]
        if student_id and not any(_matches_id((c.get("original") or {}).get("id") or c.get("_id"), student_id) for c in students):
            continue
        guardian_ids = [((c.get("original") or {}).get("primaryGuardian") or {}).get("id") for c in students]
        guardian_ids += [(c.get("original") or {}).get("id") or c.get("_id") for c in customers]
        if customer_id and not any(_matches_id(value, customer_id) for value in guardian_ids):
            continue
        result = {
            "id": item.get("id"), "start": slot.get("startTime"), "end": slot.get("endTime"),
            "timezone": center_timezone or next((c.get("timezone") for c in consumers if c.get("timezone")), None),
            "status": item.get("status"),
            "student_id": next(((c.get("original") or {}).get("id") or c.get("_id") for c in students), None),
            "customer_id": next((value for value in guardian_ids if value), None),
            "service_id": (item.get("service") or {}).get("_id"),
            "location_id": resolved_location,
            "recurring_id": item.get("recurringId"), "created_at": item.get("booked_on"),
            "created_by": item.get("emailOfBookedBy") or item.get("source"),
        }
        selected.append((instant, result))
    if order == "asc":
        selected.sort(key=lambda pair: (pair[0], pair[1]["id"] or ""))
    elif order == "desc":
        selected.sort(key=lambda pair: (pair[0], pair[1]["id"] or ""), reverse=True)
    else:
        selected.sort(key=lambda pair: (abs((pair[0] - now).total_seconds()), pair[0], pair[1]["id"] or ""))
    page = [result for _, result in selected[offset:offset + page_size]]
    next_offset = offset + len(page)
    return {"status": "success", "filters": filters, "window_applied": {"start": start.isoformat(), "end": end.isoformat(), "defaulted": not bool(start_from)},
            "appointments": page, "total": len(selected), "has_more": next_offset < len(selected),
            "next_cursor": _encode_cursor(next_offset, fingerprint, start, end) if next_offset < len(selected) else None}
