from typing import Annotated, Dict, List, Literal, Optional, Any

from pydantic import Field

from .app import mcp
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


@mcp.tool()
async def mathnasium_get_entity(
    entityType: Annotated[Literal["appointments", "services", "employees", "resources", "group_settings", "company_settings", "location_settings", "apps"], Field(description="Exact entity type to fetch. Use dedicated tools for centers, guardians, and students; this tool is for appointments/services/employees/resources/settings/apps only.")],
    parentId: Annotated[Optional[str], Field(description="Required for appointments/services/resources (location-level parentId) and employees (company-level parentId). Not used for settings/apps context reads.")] = None,
    entityId: Annotated[Optional[str], Field(description="Optional exact entity id filter applied to list-like results. This is not fuzzy search.")] = None,
    companyId: Annotated[Optional[str], Field(description="Required for company_settings/apps and useful for GraphQL scoping. Use the companyId returned by mathnasium_find_center.")] = None,
    locationId: Annotated[Optional[str], Field(description="Required for location_settings and useful for location-scoped GraphQL calls. Use the locationId returned by mathnasium_find_center.")] = None,
    limit: Annotated[int, Field(description="Maximum list items to return, capped at 100.", ge=1, le=100)] = 25,
    refreshContext: Annotated[bool, Field(description="Force-refresh cached group context for context-backed entity types.")] = False,
) -> Dict[str, Any]:
    """Get exact scoped Mathnasium entities not covered by center/guardian/student tools, such as appointments, services, employees, resources, settings, and apps."""
    config_error = require_config()
    if config_error:
        return config_error
    try:
        if entityType in {"group_settings", "company_settings", "location_settings", "apps"}:
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
        )
    except AppointyApiError as exc:
        return {"status": "failed", "error": str(exc), "details": exc.payload}
    except Exception as exc:
        return {"status": "failed", "error": f"Unexpected error in entity lookup: {exc}"}


@mcp.tool()
async def mathnasium_search_custom_logs(
    source: Annotated[Literal["all", "admin_requests", "graphql", "radius_wrappers"], Field(description="Log source preset. Use radius_wrappers for Radius sync wrapper logs, graphql for GraphQL/queryId logs, admin_requests for admin request logs, all only with strong filters.")] = "all",
    textTerms: Annotated[Optional[List[str]], Field(description="Exact text snippets, error messages, or payload clues to search in log entries.")] = None,
    identifiers: Annotated[Optional[List[str]], Field(description="Emails, Appointy IDs, Radius IDs, custom IDs, names, center/company IDs, or other exact identifiers.")] = None,
    messages: Annotated[Optional[List[str]], Field(description="Exact jsonPayload.message values, for example Successful, Failed, Finished request, or Error while processing request.")] = None,
    queryIds: Annotated[Optional[List[str]], Field(description="GraphQL operation/query ids, for example CompanyAppointmentReportQuery.")] = None,
    paths: Annotated[Optional[List[str]], Field(description="Request path fragments, for example /graphql or /api/v1/wrappers/mathnasium/customer-account.")] = None,
    endpointNames: Annotated[Optional[List[str]], Field(description="Endpoint fragments such as customer-account, student, physical-center, virtual-center, or appointment/status.")] = None,
    statusCodes: Annotated[Optional[List[str]], Field(description="Status codes or status values when present in log payloads.")] = None,
    startTime: Annotated[Optional[str], Field(description="Inclusive ISO timestamp lower bound. If omitted, uses the configured default lookback window.")] = None,
    endTime: Annotated[Optional[str], Field(description="Inclusive ISO timestamp upper bound. If omitted, uses current time.")] = None,
    severityMin: Annotated[str, Field(description="Minimum Cloud Logging severity, default DEFAULT.")] = "DEFAULT",
    matchAllTerms: Annotated[bool, Field(description="When true, all textTerms/identifiers must match instead of any one matching.")] = False,
    limit: Annotated[int, Field(description="Maximum log entries to return, capped by GCP_LOG_MAX_LIMIT.", ge=1)] = 100,
    includePayload: Annotated[bool, Field(description="Include raw log payloads in returned matches. Useful for deep investigation, but may expose sensitive production payload data.")] = True,
) -> Dict[str, Any]:
    """Search Mathnasium production GKE logs with custom text/queryId/path/message filters without exposing raw Cloud Logging syntax."""
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
