"""Bounded, read-only report contracts; raw report counters remain authoritative."""

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import support_queries as q
from .errors import AppointyApiError
from .scopes import full_id, company_id

REPORT_TYPES = {"monthly_utilization", "overbooking_report", "notification_history"}


async def read_report(
    *,
    entity_type,
    parent_id,
    company=None,
    location=None,
    report_month=None,
    notification_address=None,
    start=None,
    end=None,
    timezone="UTC",
    limit=25,
    cursor=None,
):
    from .support_reads import graphql, window, decode_cursor, encode_cursor

    if not 1 <= limit <= 50:
        raise ValueError("Report limit must be between 1 and 50.")
    if not parent_id:
        raise ValueError("Reports require parentId of a company or location.")
    co = company_id(company) if company else None
    scope = await full_id(parent_id, company=co)
    if scope.count("/") not in (1, 2) or not scope.split("/")[-1].startswith(
        ("com_", "loc_")
    ):
        raise ValueError("Report parentId must identify a company or location.")
    if co and company_id(scope) != co:
        raise ValueError("Report parentId conflicts with companyId.")
    co = company_id(scope)
    loc = scope if "/loc_" in scope else None
    if location and await full_id(location, company=co) != loc:
        raise ValueError("Report locationId must match a location-level parentId.")
    if entity_type != "monthly_utilization" and timezone != "UTC":
        raise ValueError(
            "timezone applies only to monthly_utilization; other reports use UTC date anchors or explicit timestamp offsets."
        )
    filters = dict(
        entityType=entity_type,
        parentId=scope,
        companyId=co,
        locationId=loc,
        reportMonth=report_month,
        notificationAddress=notification_address,
        startFrom=start,
        startTo=end,
        timezone=timezone,
        limit=limit,
    )
    warnings = []
    if entity_type == "notification_history":
        if report_month is not None:
            raise ValueError(
                "notification_history uses startFrom/startTo, not reportMonth."
            )
        if notification_address is not None and not notification_address.strip():
            raise ValueError("notificationAddress must not be blank.")
        period = window(start, end, 1)
        variables = dict(
            p=scope,
            start=period["startTime"],
            end=period["endTime"],
            address=notification_address,
            n=limit,
        )
        query, field = q.NOTIFICATION_HISTORY, "notificationReport"
        warnings.append(
            "EMAIL send events only; sent does not prove delivery. Bounce, suppression and password-reset success are not exposed."
        )
    else:
        if start is not None or end is not None or notification_address is not None:
            raise ValueError(
                "Monthly reports use reportMonth, not dates or notificationAddress."
            )
        try:
            if not isinstance(report_month, str) or len(report_month) != 7:
                raise ValueError()
            month = datetime.strptime(report_month, "%Y-%m")
            if month.strftime("%Y-%m") != report_month:
                raise ValueError()
            ZoneInfo(timezone)
        except (ValueError, ZoneInfoNotFoundError, TypeError) as exc:
            raise ValueError(
                "Provide reportMonth as YYYY-MM and a valid timezone."
            ) from exc
        # Match the verified frontend/report request: UTC first-of-month anchor.
        date = month.strftime("%Y-%m-01T00:00:00Z")
        variables = dict(p=scope, date=date)
        if entity_type == "monthly_utilization":
            variables.update(tz=timezone, n=limit)
            query, field = q.MONTHLY_UTILIZATION, "enrollmentUnderUtilizationReport"
            warnings.append(
                "reportMonth is the upstream start month; bookedSessions can include subsequent months. Raw allowance/max/count fields are not an attendance breakdown or Radius balance."
            )
        else:
            query, field = q.OVERBOOKING_REPORT, "mathnasiumOverBookingReport"
            warnings.append(
                "Upstream has no timezone or pagination argument; reportMonth is a UTC month anchor. Local continuation re-reads the returned report and can shift if data changes."
            )
    token = decode_cursor(cursor, filters)
    offset = 0 if token is None else token
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("Invalid report cursor.")
    if entity_type != "overbooking_report":
        variables["o"] = offset
    data = await graphql(query, variables, company=co, location=loc)
    result = data.get(field)
    if not isinstance(result, dict):
        raise AppointyApiError("Report response is missing its result object.")
    source_truncated = False
    if entity_type == "overbooking_report":
        rows = result.get("nodes")
        if not isinstance(rows, list) or not isinstance(result.get("total"), int):
            raise AppointyApiError("Overbooking report has invalid rows or total.")
        source_truncated = result["total"] > len(rows)
        items = rows[offset : offset + limit]
        more, next_offset = offset + limit < len(rows), offset + limit
    else:
        edges, page = result.get("edges"), result.get("pageInfo")
        if (
            not isinstance(edges, list)
            or not isinstance(page, dict)
            or not isinstance(page.get("hasNextPage"), bool)
        ):
            raise AppointyApiError("Report pagination is missing or invalid.")
        key = "data" if entity_type == "monthly_utilization" else "node"
        if any(
            not isinstance(e, dict) or not isinstance(e.get(key), dict) for e in edges
        ):
            raise AppointyApiError("Report contains invalid rows.")
        items = [e[key] for e in edges]
        more, next_offset = page["hasNextPage"], page.get("nextOffset")
        if more and (
            isinstance(next_offset, bool)
            or not isinstance(next_offset, int)
            or next_offset <= offset
        ):
            raise AppointyApiError(
                "Report indicated more rows without a progressing offset."
            )
    if source_truncated:
        warnings.append(
            "Upstream returned fewer rows than total; local pagination cannot recover omitted source rows."
        )
    return dict(
        status="partial" if source_truncated else "success",
        entityType=entity_type,
        filters=filters,
        data=dict(
            items=items,
            total=result.get("total"),
            downloadLimit=result.get("downloadLimit"),
        ),
        has_more=more,
        next_cursor=encode_cursor(next_offset, filters) if more else None,
        source_truncated=source_truncated,
        warnings=warnings,
    )
