"""Explicit read contracts over API-key-verified Appointy operations."""

import base64
import hashlib
import json
from datetime import datetime, timedelta

from .clients import appointy
from .config import MATHNASIUM_GROUP_ID
from .errors import AppointyApiError
from .scopes import company_id, full_id
from . import support_queries as q

READ_TYPES = {
    "booking_rules",
    "portal_settings",
    "availability_rules",
    "availability_window",
    "bookable_slots",
    "bookable_durations",
    "enrollment_balance",
    "recurring_series",
    "attendance_statuses",
    "activity_logs",
    "guardian_profile",
    "student_audit",
    "record_metadata",
    "instructor_services",
    "consumer_appointment_count",
    "radius_student",
}


def window(start, end, max_days=62):
    if not start or not end:
        raise ValueError("Both startFrom and startTo are required.")
    dates = [datetime.fromisoformat(v.replace("Z", "+00:00")) for v in (start, end)]
    if any(d.tzinfo is None for d in dates):
        raise ValueError("Date-times must contain a timezone offset.")
    if not timedelta(0) < dates[1] - dates[0] <= timedelta(days=max_days):
        raise ValueError(f"Date window must be positive and at most {max_days} days.")
    return {"startTime": start, "endTime": end}


def fingerprint(filters):
    return hashlib.sha256(json.dumps(filters, sort_keys=True).encode()).hexdigest()


def encode_cursor(token, filters):
    return base64.urlsafe_b64encode(
        json.dumps({"token": token, "filters": fingerprint(filters)}).encode()
    ).decode()


def decode_cursor(cursor, filters):
    if not cursor:
        return None
    try:
        value = json.loads(base64.urlsafe_b64decode(cursor))
        if value["filters"] != fingerprint(filters):
            raise ValueError()
        return value["token"]
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise ValueError(
            "Invalid cursor or cursor belongs to different filters."
        ) from exc


async def graphql(query, variables, *, company=None, location=None):
    payload = await appointy._graphql(
        query_id="SupportRead",
        query=query,
        variables=variables,
        company_id=company,
        location_id=location,
    )
    if payload.get("errors"):
        raise AppointyApiError("Appointy read failed", payload=payload["errors"])
    if not isinstance(payload.get("data"), dict):
        raise AppointyApiError("Appointy read returned no data")
    return payload["data"]


async def read_entity(
    *,
    entity_type,
    parent_id=None,
    entity_id=None,
    company=None,
    location=None,
    student_id=None,
    guardian_id=None,
    enrollment_id=None,
    service_id=None,
    instructor_id=None,
    start=None,
    end=None,
    timezone="UTC",
    duration=None,
    cursor=None,
    limit=25,
    event_ids=None,
):
    """No natural-language dispatch, arbitrary GraphQL, or mutations."""
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100.")
    co = company_id(company) if company else None
    scope = await full_id(parent_id, company=co) if parent_id else None
    loc = await full_id(location, company=co) if location else None
    if scope and "/loc_" in scope:
        loc = scope.split("/srv_")[0]
    if co and (scope or loc) and company_id(scope or loc) != co:
        raise ValueError("parentId/locationId conflicts with companyId.")
    co = co or (company_id(scope or loc) if scope or loc else None)
    identity = student_id or guardian_id or entity_id or instructor_id
    if not co and identity and "/" in identity:
        co = company_id(identity)
    if (
        not loc
        and entity_type == "recurring_series"
        and entity_id
        and "/apt_" in entity_id
    ):
        loc = entity_id.split("/apt_")[0]
    filters = dict(
        entityType=entity_type,
        parentId=scope,
        entityId=entity_id,
        companyId=co,
        locationId=loc,
        studentId=student_id,
        guardianId=guardian_id,
        enrollmentId=enrollment_id,
        serviceId=service_id,
        instructorId=instructor_id,
        startFrom=start,
        startTo=end,
        timezone=timezone,
        durationSeconds=duration,
        eventIds=event_ids or [],
    )
    token = decode_cursor(cursor, filters)
    variables = {}
    connection = None
    warnings = []
    if (
        entity_type
        in {
            "booking_rules",
            "portal_settings",
            "availability_rules",
            "availability_window",
            "bookable_slots",
            "bookable_durations",
            "attendance_statuses",
            "instructor_services",
            "consumer_appointment_count",
        }
        and not loc
    ):
        raise ValueError(f"{entity_type} requires a location parentId or locationId.")
    if entity_type == "booking_rules":
        target = await full_id(service_id, parent=loc) if service_id else loc
        query, variables = q.BOOKING_RULES, {"p": target}
        warnings.append(
            "Interpret policyType before interval: AllowUpdate means any time. Location and service are separate scopes; no company default is inferred."
        )
    elif entity_type == "portal_settings":
        query, variables = q.PORTAL_SETTINGS, {"p": loc}
    elif entity_type == "availability_rules":
        query = q.AVAILABILITY_RULES
        variables, connection = {"p": loc, "n": limit, "a": token}, "openHourRules"
        warnings.append(
            "Current/expired rules only; deletion history is separate and may not retain complete before-state."
        )
    elif entity_type == "availability_window":
        slot = window(start, end, 31)
        query, variables = q.AVAILABILITY_WINDOW, {
            "p": [loc],
            "start": slot["startTime"],
            "end": slot["endTime"],
        }
    elif entity_type == "bookable_slots":
        slot = window(start, end, 7)
        if (
            not student_id
            or not enrollment_id
            or not service_id
            or not duration
            or duration <= 0
        ):
            raise ValueError(
                "bookable_slots requires studentId, enrollmentId, serviceId and positive durationSeconds."
            )
        sid = await full_id(student_id, company=co)
        eid = enrollment_id if "/" in enrollment_id else f"{sid}/{enrollment_id}"
        await full_id(eid)
        f = {
            "parent": loc,
            "consumerId": sid,
            "enrolmentId": eid,
            "services": [await full_id(service_id, parent=loc)],
            "duration": duration,
            "timeSlot": slot,
        }
        if instructor_id:
            f["employees"] = [await full_id(instructor_id, company=co)]
        query, variables = q.BOOKABLE_SLOTS, {"f": [f], "tz": timezone}
        warnings.append(
            "Empty matches do not establish a complete root cause. Capacity is returned as supplied by Appointy, not a separately verified free-seat count."
        )
    elif entity_type == "bookable_durations":
        if not student_id or not service_id:
            raise ValueError("bookable_durations requires studentId and serviceId.")
        query, variables = q.BOOKABLE_DURATIONS, {
            "p": loc,
            "s": await full_id(student_id, company=co),
            "v": await full_id(service_id, parent=loc),
            "slot": window(start, end, 7),
        }
    elif entity_type == "enrollment_balance":
        if not student_id or not guardian_id:
            raise ValueError("enrollment_balance requires studentId and guardianId.")
        query, variables = q.ENROLLMENT_BALANCE, {
            "s": await full_id(student_id, company=co),
            "g": await full_id(guardian_id, company=co),
            "tz": timezone,
        }
        warnings.append(
            "Remaining bookable buckets are not booked/attended counts or a Radius sync history. Bucket coverage is controlled by Appointy."
        )
    elif entity_type == "recurring_series":
        if not entity_id:
            raise ValueError(
                "recurring_series requires entityId of a seed appointment, not a rec_ ID."
            )
        query, variables = q.RECURRING_SERIES, {
            "a": await full_id(entity_id, parent=loc)
        }
    elif entity_type == "attendance_statuses":
        query, variables = q.ATTENDANCE_STATUSES, {"p": loc}
    elif entity_type == "guardian_profile":
        query, variables = q.GUARDIAN_PROFILE, {
            "g": await full_id(entity_id or guardian_id, company=co)
        }
    elif entity_type == "student_audit":
        query = q.STUDENT_AUDIT
        variables = {"id": await full_id(entity_id or student_id, company=co)}
    elif entity_type == "record_metadata":
        if not co:
            raise ValueError("record_metadata requires companyId.")
        query = q.RECORD_METADATA if loc else q.COMPANY_METADATA
        variables = {"c": co, "l": loc} if loc else {"c": co}
    elif entity_type == "instructor_services":
        if not instructor_id:
            raise ValueError("instructor_services requires instructorId.")
        query = q.INSTRUCTOR_SERVICES
        variables, connection = {
            "e": await full_id(instructor_id, company=co),
            "l": loc,
            "n": limit,
            "a": token,
        }, "listServicesOfEmployee"
    elif entity_type == "consumer_appointment_count":
        query, variables = q.CONSUMER_COUNT, {
            "p": loc,
            "s": await full_id(student_id or guardian_id, company=co),
        }
        warnings.append(
            "This count has no date-range argument. Use filtered appointments for date-specific counts."
        )
    elif entity_type == "radius_student":
        if not entity_id or "/" in entity_id:
            raise ValueError(
                "radius_student requires the exact Radius student ID in entityId."
            )
        query, variables = q.RADIUS_STUDENT, {"g": MATHNASIUM_GROUP_ID, "s": entity_id}
        warnings.append(
            "Current Appointy wrapper projection, not the last received Radius payload or historical sync journal."
        )
    elif entity_type == "activity_logs":
        if not scope:
            raise ValueError("activity_logs requires parentId.")
        slot = window(start, end, 90)
        if token is not None and (not isinstance(token, int) or token < 0):
            raise ValueError("Invalid activity cursor.")
        query = q.ACTIVITY_LOGS
        variables, connection = {
            "p": [scope],
            "n": limit,
            "o": token or 0,
            "range": slot,
            "events": event_ids or None,
        }, "activityLogs"
        warnings.append(
            "Audit events can have missing activity IDs or incomplete snapshots; do not reconstruct unknown deleted records."
        )
    else:
        raise ValueError("Unsupported verified read type.")
    data = await graphql(query, variables, company=co, location=loc)
    has_more, next_token = False, None
    if connection:
        conn = data.get(connection) or {}
        items = [
            e["node"] for e in conn.get("edges", []) if isinstance(e.get("node"), dict)
        ]
        page = conn.get("pageInfo") or {}
        has_more = bool(page.get("hasNextPage"))
        next_token = page.get(
            "nextOffset" if entity_type == "activity_logs" else "endCursor"
        )
        data = {"items": items}
    elif entity_type in {"availability_window", "bookable_slots"}:
        # Appointy has no cursor for these reads; bound the response with filter-bound local continuation.
        field = (
            "listOpenHourRulesForAvailability"
            if entity_type == "availability_window"
            else "mathnasiumAvailability"
        )
        result = data.get(field) or {}
        if entity_type == "availability_window":
            rows = result.get("openHours") or []
        else:
            nodes = result.get("nodes") or []
            rows = [
                {"studentId": n.get("studentId"), **slot}
                for n in nodes
                for slot in n.get("slots") or []
            ]
            data["slotErrors"] = [
                {"studentId": n.get("studentId"), "errorMessage": n.get("errorMessage")}
                for n in nodes
            ]
        offset = token or 0
        if not isinstance(offset, int) or offset < 0:
            raise ValueError("Invalid list cursor.")
        data[field] = {"items": rows[offset : offset + limit], "total": len(rows)}
        next_token = offset + limit
        has_more = next_token < len(rows)
        warnings.append(
            "Local continuation re-reads the bounded window; data changes between calls can shift results."
        )
    elif cursor:
        raise ValueError("This entity type does not support pagination.")
    if has_more and next_token is None:
        raise AppointyApiError(
            "Upstream indicated another page without a continuation token."
        )
    if entity_type == "record_metadata":
        from .domain import _parse_metadata

        for value in data.values():
            if isinstance(value, dict):
                value["decodedMetadata"] = _parse_metadata(value.get("metadata"))
    return {
        "status": "success",
        "entityType": entity_type,
        "filters": filters,
        "data": data,
        "has_more": has_more,
        "next_cursor": encode_cursor(next_token, filters) if has_more else None,
        "warnings": warnings,
    }
