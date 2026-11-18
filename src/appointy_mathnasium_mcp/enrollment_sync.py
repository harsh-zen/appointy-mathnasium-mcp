"""Read observed enrollment sync outcomes without changing general log search."""

import json
import re
import time
from datetime import datetime, timedelta, timezone

from .log_search import _build_custom_logs_filter, _entry_to_dict, _list_entries_with_retry
from .support_reads import decode_cursor, encode_cursor, window

PATH = "api/v1/wrappers/mathnasium/student"
TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|[<>\{\}:]|[^\s"<>\{\}:]+')


def balance(body, enrollment_id):
    """Select a direct balance field within the exact enrollment block."""
    if not isinstance(body, str):
        return None, False
    tokens = TOKEN.findall(body)
    candidates = []
    for i in range(len(tokens) - 2):
        if tokens[i:i + 2] != ["enrolments", ":"] or tokens[i + 2] not in ("<", "{"):
            continue
        stack = [tokens[i + 2]]
        fields = {}
        for j in range(i + 3, len(tokens)):
            token = tokens[j]
            if token in ("<", "{"):
                stack.append(token)
            elif token in (">", "}"):
                if stack[-1] != {">": "<", "}": "{"}[token]:
                    break
                stack.pop()
                if not stack:
                    if fields.get("enrolment_id") == json.dumps(enrollment_id):
                        candidates.append(fields.get("remaining_sessions"))
                    break
            elif len(stack) == 1 and token in ("enrolment_id", "remaining_sessions"):
                if tokens[j + 1:j + 2] == [":"] and j + 2 < len(tokens):
                    fields[token] = tokens[j + 2]
    if not candidates:
        return None, False
    v = candidates[0]
    return (int(v) if len(candidates) == 1 and v and re.fullmatch(r"-?[0-9]{1,18}", v) else None), True


def project_event(row, enrollment_id):
    p = row.get("payload")
    if not isinstance(p, dict) or p.get("PATH") != PATH or p.get("METHOD") != "PUT":
        return None
    incoming, in_request = balance(p.get("REQUEST_BODY"), enrollment_id)
    response, in_response = balance(p.get("RESPONSE"), enrollment_id)
    if not (in_request or in_response):
        return None
    status = p.get("message")
    if status not in ("Successful", "Failed"):
        return None
    marker = any(
        k.startswith("EnrolmentUpdated_") and v == f"Enrolment Id: {enrollment_id}"
        for k, v in p.items()
    )
    request_id = p.get("request_id") or p.get("REQUEST_ID") or p.get("requestId")
    return {
        "observedAt": row.get("timestamp"),
        "logInsertId": row.get("insertId"),
        "requestId": request_id if isinstance(request_id, str) else None,
        "outcome": "successful_response" if status == "Successful" else "failed",
        "receivedBalance": incoming,
        "successfulResponseBalance": response if status == "Successful" else None,
        "enrollmentUpdateReported": marker and status == "Successful",
        "error": str(p.get("error") or "")[:500] or None if status == "Failed" else None,
    }


async def read_enrollment_sync(enrollment_id, start, end, limit, cursor):
    if not re.fullmatch(r"[A-Za-z0-9_#-]{1,128}", enrollment_id):
        raise ValueError("Use the Radius enrollment ID (customEnrolmentId), not a full Appointy path.")
    bounds = window(start, end, 1)
    t0, t1 = (datetime.fromisoformat(bounds[k].replace("Z", "+00:00")) for k in ("startTime", "endTime"))
    if t1 - t0 > timedelta(hours=1):
        raise ValueError("Enrollment log windows must be at most one hour.")
    if t0 < datetime.now(timezone.utc) - timedelta(days=30):
        raise ValueError("Enrollment log windows must start within the last 30 days.")
    filters = dict(radiusEnrollmentId=enrollment_id, startTime=start, endTime=end, limit=limit)
    token = decode_cursor(cursor, filters)
    if token is not None and not isinstance(token, str):
        raise ValueError("Invalid enrollment log cursor.")
    query, _, upper, _ = _build_custom_logs_filter(
        source="radius_wrappers", text_terms=[], identifiers=[], messages=[],
        query_ids=[], paths=[], endpoint_names=[], status_codes=[], start_time=start,
        end_time=end, severity_min="DEFAULT", match_all_terms=False,
    )
    query = query.replace(f'timestamp<="{upper}"', f'timestamp<"{upper}"')
    query += f'\njsonPayload.PATH="{PATH}"\njsonPayload.METHOD="PUT"'
    exact = f'enrolment_id:"{enrollment_id}"'
    query += f'\n(jsonPayload.REQUEST_BODY:{json.dumps(exact)} OR jsonPayload.RESPONSE:{json.dumps(exact)})'
    entries, next_token, _ = await _list_entries_with_retry(
        query=query, limit=limit, deadline=time.monotonic() + 15, page_token=token,
    )
    events = []
    for entry in entries:
        row = _entry_to_dict(entry, identifiers=[], include_payload=True)
        event = project_event(row, enrollment_id)
        if event is not None:
            events.append(event)
    return dict(
        status="partial" if next_token or len(events) != len(entries) else "success",
        filters=filters, events=events, has_more=bool(next_token),
        next_cursor=encode_cursor(next_token, filters) if next_token else None,
        scannedRows=len(entries), unparsedRows=len(entries) - len(events),
        coverage="Observed PUT outcome logs only; no guarantee of complete history.",
        warnings=[
            "observedAt is the log time, not separate receipt or commit time.",
            "Successful response balance is not independent proof of database commit.",
            "Missing balances and request IDs are unknown. logInsertId is not a request ID.",
        ],
    )
