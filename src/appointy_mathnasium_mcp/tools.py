from typing import Annotated, Dict, List, Literal, Optional, Any

from pydantic import Field
from mcp.types import ToolAnnotations

from .app import mcp
from .appointment_search import find_appointments
from .clients import require_gcp_logging_config
from .config import GROUP_CONTEXT_CACHE_TTL_SECONDS, require_config
from .domain import (
    _find_centers_internal,
    _find_guardians_internal,
    _find_students_internal,
    _get_context_entity_internal,
    _get_graphql_entity_internal,
    _get_group_context_cached,
)
from .support_reads import READ_TYPES, read_entity
from .errors import AppointyApiError, GcpLoggingError
from .log_search import _search_custom_logs_internal


@mcp.tool()
async def mathnasium_get_group_context(
    refresh: Annotated[bool, Field(description="Force-refresh cached Mathnasium group/company/location context instead of using the short-lived cache.")] = False,
) -> Dict[str, Any]:
    """Return normalized Mathnasium group/company/location context and aliases."""
    config_error = require_config()
    if config_error:
        return config_error
    try:
        context = await _get_group_context_cached(refresh=refresh)
        return {
            "status": "success",
            "groupId": context.get("groupId", ""),
            "groupName": context.get("groupName", ""),
            "companies": context.get("companies", []),
            "aliases": context.get("aliases", {}),
            "cacheTtlSeconds": GROUP_CONTEXT_CACHE_TTL_SECONDS,
        }
    except AppointyApiError as exc:
        return {"status": "failed", "error": str(exc), "details": exc.payload}


@mcp.tool()
async def mathnasium_find_guardian(
    parentId: Annotated[str, Field(description="Required Appointy parent scope for guardian lookup. Must be a company/location id or full scoped id, e.g. com_..., loc_..., or grp_.../com_.../loc_.... Resolve this with mathnasium_find_center first; never call guardian lookup globally.")],
    email: Annotated[Optional[str], Field(description="Guardian email to search within the supplied parentId scope. Exact and normalized email variants are checked.")] = None,
    name: Annotated[Optional[str], Field(description="Guardian full or partial name. Appointy search is first-name scoped, then results are locally filtered against this full value.")] = None,
    firstName: Annotated[Optional[str], Field(description="Optional explicit guardian first name. Use when the requester provides first/last separately or the full name parsing is uncertain.")] = None,
    lastName: Annotated[Optional[str], Field(description="Optional explicit guardian last name. Used for local result validation with firstName/name; Appointy itself is still searched by first name.")] = None,
    phone: Annotated[Optional[str], Field(description="Guardian phone number to search within the supplied parentId scope.")] = None,
    centerId: Annotated[Optional[str], Field(description="Optional location id to further narrow the parent scope. Usually this is the locationId returned by mathnasium_find_center.")] = None,
    limit: Annotated[int, Field(description="Maximum guardian matches to return, capped at 50.", ge=1, le=50)] = 10,
) -> Dict[str, Any]:
    """Find guardian records within a provided parent scope (company or location id)."""
    config_error = require_config()
    if config_error:
        return config_error
    try:
        return await _find_guardians_internal(
            parent_id=parentId,
            email=email,
            name=name,
            first_name=firstName,
            last_name=lastName,
            phone=phone,
            center_id=centerId,
            limit=max(1, min(limit, 50)),
        )
    except Exception as exc:
        return {"matches": [], "warnings": [f"Unexpected error in guardian lookup: {exc}"]}


@mcp.tool()
async def mathnasium_find_student(
    studentName: Annotated[Optional[str], Field(description="Student full or partial name. Student lookup is group-scoped and does not require company/location first.")] = None,
    guardianEmail: Annotated[Optional[str], Field(description="Weak hint only. Appointy group student search cannot reliably filter by guardian email without guardianId, so prefer guardianId.")] = None,
    guardianId: Annotated[Optional[str], Field(description="Appointy guardian/customer id to filter linked students.")] = None,
    centerId: Annotated[Optional[str], Field(description="Optional center/location id to narrow returned students by center linkage.")] = None,
    limit: Annotated[int, Field(description="Maximum student matches to return, capped at 50.", ge=1, le=50)] = 10,
) -> Dict[str, Any]:
    """Find students and enrollment state by student/guardian/center hints."""
    config_error = require_config()
    if config_error:
        return config_error
    try:
        return await _find_students_internal(
            student_name=studentName,
            guardian_email=guardianEmail,
            guardian_id=guardianId,
            center_id=centerId,
            limit=max(1, min(limit, 50)),
        )
    except Exception as exc:
        return {"matches": [], "warnings": [f"Unexpected error in student lookup: {exc}"]}


@mcp.tool()
async def mathnasium_find_center(
    query: Annotated[Optional[str], Field(description="Free-text center/company/location hint: center name, city, booking URL, slug, or custom location id.")] = None,
    includeInactive: Annotated[bool, Field(description="Whether inactive centers should be included in results.")] = False,
    limit: Annotated[int, Field(description="Maximum center matches to return, capped at 100.", ge=1, le=100)] = 10,
) -> Dict[str, Any]:
    """Find Mathnasium center/company/location by free text, slug, or customLocationId."""
    config_error = require_config()
    if config_error:
        return config_error
    try:
        return await _find_centers_internal(
            query=query,
            include_inactive=includeInactive,
            limit=max(1, min(limit, 100)),
        )
    except AppointyApiError as exc:
        return {"matches": [], "warnings": [str(exc)]}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
async def mathnasium_get_entity(
    entityType: Annotated[
        Literal[
            "appointments",
            "services",
            "employees",
            "resources",
            "group_settings",
            "company_settings",
            "location_settings",
            "apps",
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
        ],
        Field(
            description="Exact entity type to fetch. For services, results include session-type membership links, grade-range links, durations, active status, and booking-rule metadata. Use dedicated tools for centers, guardians, and students."
        ),
    ],
    parentId: Annotated[
        Optional[str],
        Field(
            description="Required for appointments/services/resources (location-level parentId) and employees (company-level parentId). Not used for settings/apps context reads."
        ),
    ] = None,
    entityId: Annotated[
        Optional[str],
        Field(
            description="Exact entity ID for profile/audit reads, a seed apt_ ID for recurring_series, or exact Radius student ID for radius_student. Optional exact filter for legacy list reads; not fuzzy search."
        ),
    ] = None,
    companyId: Annotated[
        Optional[str],
        Field(
            description="Required for company_settings/apps and useful for GraphQL scoping. Use the companyId returned by mathnasium_find_center."
        ),
    ] = None,
    locationId: Annotated[
        Optional[str],
        Field(
            description="Required for location_settings and useful for location-scoped GraphQL calls. Use the locationId returned by mathnasium_find_center."
        ),
    ] = None,
    limit: Annotated[
        int,
        Field(description="Maximum list items to return, capped at 100.", ge=1, le=100),
    ] = 25,
    refreshContext: Annotated[
        bool,
        Field(
            description="Force-refresh cached group context for context-backed entity types."
        ),
    ] = False,
    studentId: Annotated[
        Optional[str],
        Field(
            description="Confirmed student ID; use full scoped ID unless companyId is supplied."
        ),
    ] = None,
    guardianId: Annotated[
        Optional[str],
        Field(
            description="Confirmed guardian ID, required with studentId for enrollment_balance."
        ),
    ] = None,
    enrollmentId: Annotated[
        Optional[str],
        Field(description="Confirmed enrollment ID, required for bookable_slots."),
    ] = None,
    serviceId: Annotated[
        Optional[str],
        Field(
            description="Session-type ID; optional service override for booking_rules; required for slots/durations."
        ),
    ] = None,
    instructorId: Annotated[
        Optional[str],
        Field(
            description="Instructor ID for instructor_services or optional slot filter."
        ),
    ] = None,
    startFrom: Annotated[
        Optional[str],
        Field(
            description="ISO date-time with offset. Required with startTo for dated availability and activity reads."
        ),
    ] = None,
    startTo: Annotated[
        Optional[str],
        Field(
            description="ISO upper bound; maximum 7 days for slots/durations, 31 for availability_window, 90 for activity_logs."
        ),
    ] = None,
    timezone: Annotated[
        str,
        Field(
            description="Timezone used for remaining-bookable and slot calculations; do not guess the center timezone."
        ),
    ] = "UTC",
    durationSeconds: Annotated[
        Optional[int],
        Field(
            description="Positive slot duration in seconds, required for bookable_slots.",
            ge=1,
        ),
    ] = None,
    cursor: Annotated[
        Optional[str],
        Field(
            description="next_cursor from the same entity type and identical filters. Supported for employees, services, rules, activity, and bounded slot/window reads."
        ),
    ] = None,
    eventIds: Annotated[
        Optional[List[str]],
        Field(
            description="Exact activity event IDs, e.g. ale_223/ale_224 for deleted availability evidence."
        ),
    ] = None,
) -> Dict[str, Any]:
    """Read exact scoped entities and verified support configuration. booking_rules: location/service policies; portal_settings: booking toggles; availability_rules/window: configured hours; bookable_slots/durations: student/enrollment/service date checks; enrollment_balance: remaining-bookable buckets (not usage history); recurring_series: seed appointment entityId; attendance_statuses: configured no-show etc; activity_logs: bounded audit evidence; guardian_profile/student_audit: timezone/timestamps; record_metadata: company/location AutoInvites; instructor_services: assignments; consumer_appointment_count: undated count; radius_student: current wrapper projection, not sync history. No writes or authoritative full-reason diagnosis."""
    config_error = require_config()
    if config_error:
        return config_error
    try:
        if entityType == "appointments":
            return await find_appointments(
                student_id=studentId,
                customer_id=guardianId,
                location_id=locationId or parentId,
                start_from=startFrom,
                start_to=startTo,
                status=None,
                recurring_id=None,
                order="desc",
                cursor=cursor,
                page_size=min(limit, 50),
            )
        if entityType in READ_TYPES:
            return await read_entity(
                entity_type=entityType,
                parent_id=parentId,
                entity_id=entityId,
                company=companyId,
                location=locationId,
                student_id=studentId,
                guardian_id=guardianId,
                enrollment_id=enrollmentId,
                service_id=serviceId,
                instructor_id=instructorId,
                start=startFrom,
                end=startTo,
                timezone=timezone,
                duration=durationSeconds,
                cursor=cursor,
                limit=limit,
                event_ids=eventIds,
            )
        if entityType in {
            "group_settings",
            "company_settings",
            "location_settings",
            "apps",
        }:
            return await _get_context_entity_internal(
                entity_type=entityType,
                company_id=companyId,
                location_id=locationId,
                refresh=refreshContext,
            )
        return await _get_graphql_entity_internal(
            entity_type=entityType,
            parent_id=parentId or "",
            company_id=companyId,
            location_id=locationId,
            entity_id=entityId,
            limit=max(1, min(limit, 100)),
            cursor=cursor,
        )
    except (ValueError, AppointyApiError) as exc:
        return {
            "status": "failed",
            "error": str(exc),
            "details": getattr(exc, "payload", None),
        }
    except Exception as exc:
        return {
            "status": "failed",
            "error": f"Unexpected error in entity lookup: {exc}",
        }


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
async def mathnasium_find_appointments(
    student_id: Annotated[
        Optional[str],
        Field(
            description="Student ID. Server-side student filter. Use a full scoped ID or supply location_id."
        ),
    ] = None,
    customer_id: Annotated[
        Optional[str],
        Field(
            description="Guardian/customer ID. Server-side booking customer filter, not every linked guardian."
        ),
    ] = None,
    location_id: Annotated[
        Optional[str],
        Field(
            description="Center location ID. Combine with an entity ID or a date window; location alone is rejected."
        ),
    ] = None,
    start_from: Annotated[
        Optional[str],
        Field(
            description="Inclusive ISO 8601 appointment-start lower bound. Supply together with start_to; maximum window 62 days."
        ),
    ] = None,
    start_to: Annotated[
        Optional[str],
        Field(
            description="Inclusive ISO 8601 appointment-start upper bound. Supply together with start_from; maximum window 62 days."
        ),
    ] = None,
    status: Annotated[
        Optional[List[str]],
        Field(
            description="One or more appointment status values, such as CONFIRMED or CANCELLED. Combined with other filters using AND."
        ),
    ] = None,
    recurring_id: Annotated[
        Optional[str],
        Field(
            description="Reserved for compatibility; direct rec_ ID reads are blocked upstream. Use get_entity recurring_series with a seed appointment entityId."
        ),
    ] = None,
    order: Annotated[
        Optional[Literal["asc", "desc"]],
        Field(
            description="Sort by appointment start ascending or descending. Omit for newest first (desc)."
        ),
    ] = None,
    cursor: Annotated[
        Optional[str],
        Field(
            description="next_cursor from the previous page using identical filters."
        ),
    ] = None,
    page_size: Annotated[
        int, Field(description="Results per page; default 25, maximum 50.", ge=1, le=50)
    ] = 25,
    custom_status_ids: Annotated[
        Optional[List[str]],
        Field(
            description="Exact attendance status IDs from get_entity attendance_statuses; e.g. No-show. Separate from overall status."
        ),
    ] = None,
) -> Dict[str, Any]:
    """Search appointments with server-side student/customer/date/status filters and native cursor pagination. Defaults to newest first and a bounded 62-day window. Attendance/no-show is a separate custom status, not overall appointment status. Direct recurring-ID reads are blocked upstream; use get_entity recurring_series with a seed appointment instead."""
    config_error = require_config()
    if config_error:
        return config_error
    try:
        return await find_appointments(
            student_id=student_id,
            customer_id=customer_id,
            location_id=location_id,
            start_from=start_from,
            start_to=start_to,
            status=status,
            recurring_id=recurring_id,
            order=order,
            cursor=cursor,
            page_size=page_size,
            custom_status_ids=custom_status_ids,
        )
    except AppointyApiError as exc:
        return {"status": "failed", "error": str(exc), "details": exc.payload}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
async def mathnasium_search_custom_logs(
    source: Annotated[
        Literal["all", "admin_requests", "graphql", "radius_wrappers"],
        Field(
            description="Log source preset. Use radius_wrappers for Radius sync wrapper logs, graphql for GraphQL/queryId logs, admin_requests for admin request logs, all only with strong filters."
        ),
    ] = "all",
    textTerms: Annotated[
        Optional[List[str]],
        Field(
            description="Exact text snippets, error messages, or payload clues to search in log entries."
        ),
    ] = None,
    identifiers: Annotated[
        Optional[List[str]],
        Field(
            description="Emails, Appointy IDs, Radius IDs, custom IDs, names, center/company IDs, or other exact identifiers."
        ),
    ] = None,
    messages: Annotated[
        Optional[List[str]],
        Field(
            description="Exact jsonPayload.message values, for example Successful, Failed, Finished request, or Error while processing request."
        ),
    ] = None,
    queryIds: Annotated[
        Optional[List[str]],
        Field(
            description="GraphQL operation/query ids, for example CompanyAppointmentReportQuery."
        ),
    ] = None,
    paths: Annotated[
        Optional[List[str]],
        Field(
            description="Request path fragments, for example /graphql or /api/v1/wrappers/mathnasium/customer-account."
        ),
    ] = None,
    endpointNames: Annotated[
        Optional[List[str]],
        Field(
            description="Endpoint fragments such as customer-account, student, physical-center, virtual-center, or appointment/status."
        ),
    ] = None,
    statusCodes: Annotated[
        Optional[List[str]],
        Field(
            description="Status codes or status values when present in log payloads."
        ),
    ] = None,
    startTime: Annotated[
        Optional[str],
        Field(
            description="Inclusive ISO timestamp lower bound. If omitted, uses the configured default lookback window."
        ),
    ] = None,
    endTime: Annotated[
        Optional[str],
        Field(
            description="Inclusive ISO timestamp upper bound. If omitted, uses current time."
        ),
    ] = None,
    severityMin: Annotated[
        str, Field(description="Minimum Cloud Logging severity, default DEFAULT.")
    ] = "DEFAULT",
    matchAllTerms: Annotated[
        bool,
        Field(
            description="When true, all textTerms/identifiers must match instead of any one matching."
        ),
    ] = False,
    limit: Annotated[
        int,
        Field(
            description="Maximum log entries per response, capped at 50. Follow next_cursor for more.",
            ge=1,
        ),
    ] = 100,
    cursor: Annotated[
        Optional[str],
        Field(
            description="Continuation token from this log search. Repeat the identical filters to continue without rescanning completed pages."
        ),
    ] = None,
    summaryOnly: Annotated[
        bool,
        Field(
            description="Return page-level counts and latest error without individual rows; not a full-window aggregate."
        ),
    ] = False,
    includePayload: Annotated[
        bool,
        Field(
            description="Include raw log payloads in returned matches. For ranges longer than the configured chunk size, payloads are automatically omitted; rerun the relevant narrow window to retrieve them."
        ),
    ] = True,
) -> Dict[str, Any]:
    """Search Mathnasium production GKE logs with a maximum 25-second application budget, native page continuation and explicit partial coverage. Names use text search, not inferred entity IDs. Follow next_cursor before concluding no matching request exists. Infrastructure errors outside the application cannot be guaranteed absent."""
    config_error = require_gcp_logging_config()
    if config_error:
        return config_error
    try:
        return await _search_custom_logs_internal(
            source=source,
            text_terms=textTerms or [],
            identifiers=identifiers or [],
            messages=messages or [],
            query_ids=queryIds or [],
            paths=paths or [],
            endpoint_names=endpointNames or [],
            status_codes=statusCodes or [],
            start_time=startTime,
            end_time=endTime,
            severity_min=severityMin,
            match_all_terms=matchAllTerms,
            limit=limit,
            include_payload=includePayload,
            cursor=cursor,
            summary_only=summaryOnly,
        )
    except GcpLoggingError as exc:
        return {
            "status": "failed",
            "error": str(exc),
            "details": exc.payload,
            "matches": [],
        }
    except Exception as exc:
        return {
            "status": "failed",
            "error": f"Unexpected error in custom log search: {exc}",
            "matches": [],
        }
