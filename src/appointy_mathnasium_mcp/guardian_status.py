"""Guardian detail badge parity with the QA admin's enrollment-window helper.

QA release 3ffc4d0, 98.2ff17b35.chunk.js: allStudentsInactive and its
CustomerDetail caller. This is intentionally NOT booking eligibility.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_UI_INFINITE_ENDS = {"0001-01-01T00:00:00Z", "1970-01-01T00:00:00Z"}


def _instant(value: Any) -> Optional[datetime]:
    # Explicit null/invalid dates are invalid moments in the UI: neither before
    # nor after now. GraphQL timestamps normally contain an offset.
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _student_inactive(enrolments: List[Dict[str, Any]], now: datetime) -> bool:
    if not enrolments:
        return True
    infinite = [e for e in enrolments if e["terminationDate"] in _UI_INFINITE_ENDS]
    finite = [e for e in enrolments if e["terminationDate"] not in _UI_INFINITE_ENDS]

    def future(e: Dict[str, Any]) -> bool:
        start = _instant(e["startDate"])
        return start is not None and start > now

    def outside(e: Dict[str, Any]) -> bool:
        start, end = _instant(e["startDate"]), _instant(e["terminationDate"])
        return bool(
            start
            and end
            and ((start < now and end < now) or (start > now and end > now))
        )

    if not infinite:
        return all(outside(e) for e in finite)
    if not finite:
        return all(future(e) for e in infinite)
    # The frontend uses OR here, not AND. Preserve its observable badge behavior
    # even for an expired finite enrollment beside a started open-ended one.
    return all(outside(e) for e in finite) or all(future(e) for e in infinite)


def guardian_active_from_students(
    students: Any, *, now: Optional[datetime] = None
) -> Optional[bool]:
    """Return the UI's active state, or None when the selected data is incomplete."""
    if not isinstance(students, list):
        return None
    for student in students:
        if not isinstance(student, dict) or not isinstance(
            student.get("enrolments"), list
        ):
            return None
        if any(
            not isinstance(e, dict)
            or not {"startDate", "terminationDate"} <= e.keys()
            or any(
                e[k] is not None and not isinstance(e[k], str)
                for k in ("startDate", "terminationDate")
            )
            for e in student["enrolments"]
        ):
            return None
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        raise ValueError("Guardian status reference time must be timezone-aware.")
    reference = reference.astimezone(timezone.utc)
    return any(not _student_inactive(s["enrolments"], reference) for s in students)
