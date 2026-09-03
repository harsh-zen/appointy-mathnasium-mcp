import asyncio
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from .clients import gcp_logging
from .config import (
    GCP_CLUSTER_NAME,
    GCP_LOG_CHUNK_HOURS,
    GCP_LOG_DEFAULT_LOOKBACK_HOURS,
    GCP_LOG_LOCATION,
    GCP_LOG_MAX_ATTEMPTS,
    GCP_LOG_MAX_LIMIT,
    GCP_LOG_QUERY_TIMEOUT_SECONDS,
    GCP_LOG_RETRY_BACKOFF_SECONDS,
    GCP_LOG_TOTAL_TIMEOUT_SECONDS,
    GCP_NAMESPACE,
    GCP_POD_APP_LABEL,
    GCP_PROJECT_ID,
)
from .errors import GcpLoggingError
from .utils import (
    _compact_payload,
    _gcp_filter_string,
    _normalize_log_timestamp,
    _normalize_space,
    _safe_json_dumps,
    _to_text,
)

_TRANSIENT_GCP_ERROR_MARKERS = (
    "429",
    "500",
    "502",
    "503",
    "504",
    "connection",
    "deadline",
    "internal",
    "remoteprotocolerror",
    "temporarily unavailable",
    "timeout",
    "unavailable",
)


def _timestamp_to_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _split_time_range(start: str, end: str, *, chunk_hours: int) -> List[Tuple[str, str]]:
    start_at = _timestamp_to_datetime(start)
    end_at = _timestamp_to_datetime(end)
    if start_at > end_at:
        raise ValueError("startTime must be earlier than or equal to endTime.")

    chunk_size = timedelta(hours=max(1, chunk_hours))
    chunks: List[Tuple[str, str]] = []
    cursor_end = end_at
    while cursor_end > start_at:
        cursor_start = max(start_at, cursor_end - chunk_size)
        chunks.append((_format_timestamp(cursor_start), _format_timestamp(cursor_end)))
        cursor_end = cursor_start
    if not chunks:
        chunks.append((start, end))
    return chunks


def _is_transient_gcp_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in _TRANSIENT_GCP_ERROR_MARKERS)


async def _list_entries_with_retry(*, query: str, limit: int, deadline: float) -> Tuple[List[Any], int]:
    attempts = max(1, GCP_LOG_MAX_ATTEMPTS)
    for attempt in range(1, attempts + 1):
        remaining_budget = deadline - time.monotonic()
        if remaining_budget <= 0:
            raise GcpLoggingError("Log search reached its total execution-time budget.")
        try:
            entries = await asyncio.wait_for(
                gcp_logging.list_entries(filter_=query, limit=limit),
                timeout=min(max(1, GCP_LOG_QUERY_TIMEOUT_SECONDS), remaining_budget),
            )
            return entries, attempt
        except asyncio.TimeoutError as exc:
            raise GcpLoggingError(
                f"A log-search chunk timed out after {max(1, GCP_LOG_QUERY_TIMEOUT_SECONDS)} seconds."
            ) from exc
        except GcpLoggingError as exc:
            if attempt >= attempts or not _is_transient_gcp_error(exc):
                raise
            backoff = max(0, GCP_LOG_RETRY_BACKOFF_SECONDS) * attempt
            if backoff:
                await asyncio.sleep(min(backoff, max(0, deadline - time.monotonic())))
    raise GcpLoggingError("Log search failed after retry attempts.")

def _or_text_filter(values: List[str]) -> str:
    cleaned = [value for value in [_normalize_space(_to_text(v)) for v in values] if value]
    if not cleaned:
        return ""
    return " OR ".join([f'"{_gcp_filter_string(value)}"' for value in cleaned])


def _or_json_field_equals_filter(field_name: str, values: List[str]) -> str:
    cleaned = [value for value in [_normalize_space(_to_text(v)) for v in values] if value]
    if not cleaned:
        return ""
    safe_field = re.sub(r"[^A-Za-z0-9_.]", "", field_name)
    if not safe_field:
        return ""
    return " OR ".join([f'jsonPayload.{safe_field}="{_gcp_filter_string(value)}"' for value in cleaned])


def _build_custom_logs_filter(
    *,
    source: str,
    text_terms: List[str],
    identifiers: List[str],
    messages: List[str],
    query_ids: List[str],
    paths: List[str],
    endpoint_names: List[str],
    status_codes: List[str],
    start_time: Optional[str],
    end_time: Optional[str],
    severity_min: str,
    match_all_terms: bool,
) -> Tuple[str, str, str, List[str]]:
    now = datetime.now(timezone.utc)
    start_default = datetime.fromtimestamp(now.timestamp() - (GCP_LOG_DEFAULT_LOOKBACK_HOURS * 3600), tz=timezone.utc)
    start = _normalize_log_timestamp(start_time, default=start_default)
    end = _normalize_log_timestamp(end_time, default=now)

    filter_parts = [
        'resource.type="k8s_container"',
        f'resource.labels.project_id="{_gcp_filter_string(GCP_PROJECT_ID)}"',
        f'resource.labels.location="{_gcp_filter_string(GCP_LOG_LOCATION)}"',
        f'resource.labels.cluster_name="{_gcp_filter_string(GCP_CLUSTER_NAME)}"',
        f'resource.labels.namespace_name="{_gcp_filter_string(GCP_NAMESPACE)}"',
        f'labels."k8s-pod/app"="{_gcp_filter_string(GCP_POD_APP_LABEL)}"',
        f"severity>={_gcp_filter_string(severity_min or 'DEFAULT')}",
        f'timestamp>="{start}"',
        f'timestamp<="{end}"',
    ]

    source_value = (source or "all").strip().lower()
    if source_value == "admin_requests":
        filter_parts.append('jsonPayload.authority="mathnasium-admin.appointy.com"')
    elif source_value == "graphql":
        filter_parts.append("(jsonPayload.graphql=true OR jsonPayload.message=\"Finished request\" OR jsonPayload.message=\"Error while processing request\")")
    elif source_value == "radius_wrappers":
        filter_parts.append("(jsonPayload.message=\"Successful\" OR jsonPayload.message=\"Failed\")")
    elif source_value != "all":
        filter_parts.append(f'("{_gcp_filter_string(source_value)}")')

    message_filter = _or_json_field_equals_filter("message", messages)
    if message_filter:
        filter_parts.append(f"({message_filter})")

    query_filter = _or_json_field_equals_filter("name", query_ids)
    if query_filter:
        filter_parts.append(f"({query_filter})")

    status_filter = _or_json_field_equals_filter("status", status_codes)
    if status_filter:
        filter_parts.append(f"({status_filter})")

    term_values = [
        value
        for value in [*text_terms, *identifiers]
        if _normalize_space(_to_text(value))
    ]
    if term_values:
        if match_all_terms:
            for term in term_values:
                filter_parts.append(f'("{_gcp_filter_string(term)}")')
        else:
            filter_parts.append(f"({_or_text_filter(term_values)})")

    path_values = [value for value in paths if _normalize_space(_to_text(value))]
    if path_values:
        filter_parts.append(f"({_or_text_filter(path_values)})")

    endpoint_values = [value for value in endpoint_names if _normalize_space(_to_text(value))]
    if endpoint_values:
        filter_parts.append(f"({_or_text_filter(endpoint_values)})")

    return "\n".join(filter_parts), start, end, [*term_values, *path_values, *endpoint_values, *query_ids]


def _extract_payload_field(payload: Any, *names: str) -> str:
    if not isinstance(payload, dict):
        return ""
    candidates: List[Any] = []
    lower_payload = {str(key).lower(): value for key, value in payload.items()}
    for name in names:
        candidates.append(payload.get(name))
        candidates.append(payload.get(name.upper()))
        candidates.append(lower_payload.get(name.lower()))
    for nested_key in ["request", "response", "data", "payload", "metadata", "error"]:
        nested = payload.get(nested_key)
        if isinstance(nested, dict):
            lower_nested = {str(key).lower(): value for key, value in nested.items()}
            for name in names:
                candidates.append(nested.get(name))
                candidates.append(nested.get(name.upper()))
                candidates.append(lower_nested.get(name.lower()))
    for value in candidates:
        text = _to_text(value)
        if text:
            return text
    return ""


def _entry_to_dict(entry: Any, *, identifiers: List[str], include_payload: bool) -> Dict[str, Any]:
    payload = getattr(entry, "payload", None)
    timestamp = getattr(entry, "timestamp", None)
    if isinstance(timestamp, datetime):
        timestamp_text = timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    else:
        timestamp_text = _to_text(timestamp)
    payload_text = _safe_json_dumps(payload).lower()
    identifier_matches = [
        identifier
        for identifier in identifiers
        if identifier and identifier.lower() in payload_text
    ]
    resource = getattr(entry, "resource", None)
    resource_labels = getattr(resource, "labels", {}) if resource is not None else {}
    labels = getattr(entry, "labels", {}) or {}
    message = _extract_payload_field(payload, "message", "status")
    error_message = _extract_payload_field(payload, "errorMessage", "error", "reason", "message")
    endpoint = _extract_payload_field(payload, "endpoint", "path", "url", "route", "operation", "method")
    http_method = _extract_payload_field(payload, "httpMethod", "method")

    return {
        "timestamp": timestamp_text,
        "severity": _to_text(getattr(entry, "severity", "")),
        "message": message,
        "endpoint": endpoint,
        "httpMethod": http_method,
        "identifierMatches": identifier_matches,
        "errorMessage": error_message if message.lower() != error_message.lower() else "",
        "insertId": _to_text(getattr(entry, "insert_id", "")),
        "logName": _to_text(getattr(entry, "log_name", "")),
        "resourceLabels": dict(resource_labels) if isinstance(resource_labels, dict) else {},
        "labels": dict(labels) if isinstance(labels, dict) else {},
        "payload": _compact_payload(payload, include_payload=include_payload),
    }


async def _search_custom_logs_internal(
    *,
    source: str,
    text_terms: List[str],
    identifiers: List[str],
    messages: List[str],
    query_ids: List[str],
    paths: List[str],
    endpoint_names: List[str],
    status_codes: List[str],
    start_time: Optional[str],
    end_time: Optional[str],
    severity_min: str,
    match_all_terms: bool,
    limit: int,
    include_payload: bool,
) -> Dict[str, Any]:
    if not any([text_terms, identifiers, messages, query_ids, paths, endpoint_names, status_codes]):
        return {
            "status": "failed",
            "error": "Provide at least one filter: textTerms, identifiers, messages, queryIds, paths, endpointNames, or statusCodes.",
            "matches": [],
        }

    limit = max(1, min(limit, GCP_LOG_MAX_LIMIT))
    logical_query, resolved_start, resolved_end, match_terms = _build_custom_logs_filter(
        source=source,
        text_terms=text_terms,
        identifiers=identifiers,
        messages=messages,
        query_ids=query_ids,
        paths=paths,
        endpoint_names=endpoint_names,
        status_codes=status_codes,
        start_time=start_time,
        end_time=end_time,
        severity_min=severity_min or "DEFAULT",
        match_all_terms=match_all_terms,
    )
    chunks = _split_time_range(
        resolved_start,
        resolved_end,
        chunk_hours=max(1, GCP_LOG_CHUNK_HOURS),
    )
    is_chunked = len(chunks) > 1
    effective_include_payload = include_payload and not is_chunked
    deadline = time.monotonic() + max(1, GCP_LOG_TOTAL_TIMEOUT_SECONDS)
    matches: List[Dict[str, Any]] = []
    seen_matches = set()
    chunk_results: List[Dict[str, Any]] = []
    warnings: List[str] = []
    successful_chunks = 0
    last_chunk_error: Optional[GcpLoggingError] = None
    stop_reason = ""

    if include_payload and is_chunked:
        warnings.append(
            "Raw payloads were omitted for this long-range search to keep the MCP response reliable. "
            f"Rerun a relevant {max(1, GCP_LOG_CHUNK_HOURS)}-hour-or-shorter window with "
            "includePayload=true for full payloads."
        )

    for chunk_start, chunk_end in chunks:
        if len(matches) >= limit:
            stop_reason = "result_limit"
            warnings.append("Stopped searching older chunks after reaching the requested global result limit.")
            break
        if time.monotonic() >= deadline:
            stop_reason = "time_budget"
            warnings.append("Stopped searching older chunks after reaching the MCP execution-time budget.")
            break

        chunk_query, _, _, _ = _build_custom_logs_filter(
            source=source,
            text_terms=text_terms,
            identifiers=identifiers,
            messages=messages,
            query_ids=query_ids,
            paths=paths,
            endpoint_names=endpoint_names,
            status_codes=status_codes,
            start_time=chunk_start,
            end_time=chunk_end,
            severity_min=severity_min or "DEFAULT",
            match_all_terms=match_all_terms,
        )
        try:
            entries, attempts = await _list_entries_with_retry(
                query=chunk_query,
                limit=limit - len(matches),
                deadline=deadline,
            )
        except GcpLoggingError as exc:
            last_chunk_error = exc
            chunk_results.append(
                {
                    "startTime": chunk_start,
                    "endTime": chunk_end,
                    "status": "failed",
                    "count": 0,
                    "error": str(exc),
                }
            )
            warnings.append(f"Log chunk {chunk_start} to {chunk_end} failed: {exc}")
            if not _is_transient_gcp_error(exc):
                if not successful_chunks:
                    raise
                break
            continue

        successful_chunks += 1
        added = 0
        for entry in entries:
            row = _entry_to_dict(entry, identifiers=match_terms, include_payload=effective_include_payload)
            dedupe_key = (
                row.get("insertId")
                or "|".join(
                    [
                        _to_text(row.get("timestamp")),
                        _to_text(row.get("logName")),
                        _to_text(row.get("message")),
                        _to_text(row.get("endpoint")),
                        _to_text(row.get("errorMessage")),
                    ]
                )
            )
            if dedupe_key in seen_matches:
                continue
            seen_matches.add(dedupe_key)
            matches.append(row)
            added += 1
            if len(matches) >= limit:
                break
        chunk_results.append(
            {
                "startTime": chunk_start,
                "endTime": chunk_end,
                "status": "success",
                "count": added,
                "attempts": attempts,
            }
        )

    if not successful_chunks and last_chunk_error is not None:
        raise last_chunk_error

    matches.sort(key=lambda row: _to_text(row.get("timestamp")), reverse=True)
    matches = matches[:limit]
    timestamps = [row.get("timestamp") for row in matches if row.get("timestamp")]
    messages_summary: Dict[str, int] = {}
    severities_summary: Dict[str, int] = {}
    for row in matches:
        message = _to_text(row.get("message")) or "unknown"
        severity = _to_text(row.get("severity")) or "unknown"
        messages_summary[message] = messages_summary.get(message, 0) + 1
        severities_summary[severity] = severities_summary.get(severity, 0) + 1
    range_complete = len(chunk_results) == len(chunks) and all(
        chunk.get("status") == "success" for chunk in chunk_results
    )
    return {
        "status": "success" if range_complete or stop_reason == "result_limit" else "partial",
        "source": source or "all",
        "queryUsed": logical_query,
        "timeRange": {
            "startTime": resolved_start,
            "endTime": resolved_end,
        },
        "chunking": {
            "enabled": is_chunked,
            "chunkHours": max(1, GCP_LOG_CHUNK_HOURS),
            "planned": len(chunks),
            "attempted": len(chunk_results),
            "successful": successful_chunks,
            "complete": range_complete,
            "stopReason": stop_reason,
            "payloadIncluded": effective_include_payload,
            "chunks": chunk_results,
        },
        "matches": matches,
        "summary": {
            "total": len(matches),
            "messages": messages_summary,
            "severities": severities_summary,
            "earliest": min(timestamps) if timestamps else "",
            "latest": max(timestamps) if timestamps else "",
            "limit": limit,
        },
        "warnings": warnings,
    }
