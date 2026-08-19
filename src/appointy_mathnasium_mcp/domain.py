from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import time

from .clients import appointy
from .config import DEFAULT_FIRST, GROUP_CONTEXT_CACHE_TTL_SECONDS, MATHNASIUM_GROUP_ID
from .errors import AppointyApiError
from .queries import GRAPHQL_OTHER_ENTITY_QUERIES
from .utils import (
    _build_booking_url_info,
    _coalesce,
    _decode_base64_json,
    _email_variants,
    _iter_dict_nodes,
    _is_scalar,
    _listify,
    _mask_email,
    _normalize_email,
    _normalize_phone,
    _normalize_space,
    _to_text,
    _unique_by_key,
)

_group_context_cache: Dict[str, Any] = {
    "expires_at": 0.0,
    "raw": None,
    "normalized": None,
}


def _parse_location_node(location: Dict[str, Any], company: Dict[str, Any]) -> Dict[str, Any]:
    location_id = _coalesce(location.get("id"), location.get("locationId"), location.get("location_id"))
    slug_object = location.get("slugObject") if isinstance(location.get("slugObject"), dict) else {}
    company_slug_object = company.get("slugObject") if isinstance(company.get("slugObject"), dict) else {}
    preference = location.get("preference") if isinstance(location.get("preference"), dict) else {}
    location_slug = _to_text(_coalesce(slug_object.get("slugValue"), location.get("slug"), location.get("slugValue")))
    company_slug = _to_text(_coalesce(company_slug_object.get("slugValue"), company.get("slug"), company.get("slugValue")))
    booking_info = _build_booking_url_info(location_slug, company_slug)
    return {
        "locationId": _to_text(location_id),
        "companyId": _to_text(_coalesce(company.get("id"), company.get("companyId"), company.get("company_id"))),
        "companyDisplayName": _to_text(_coalesce(company.get("displayName"), company.get("title"))),
        "name": _to_text(_coalesce(location.get("name"), location.get("displayName"))),
        "customLocationId": _to_text(_coalesce(location.get("customLocationId"), location.get("custom_location_id"))),
        "slug": location_slug,
        "companySlug": company_slug,
        "timezone": _to_text(_coalesce(preference.get("timezone"), location.get("timezone"))),
        "active": bool(_coalesce(location.get("active"), True)),
        **booking_info,
    }


def _normalize_group_context_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    viewer = (((raw or {}).get("data") or {}).get("viewer") or {}) if isinstance(raw, dict) else {}
    groups = viewer.get("groups") if isinstance(viewer.get("groups"), list) else []

    selected_group: Dict[str, Any] = {}
    if MATHNASIUM_GROUP_ID:
        for group in groups:
            if _to_text(group.get("id")) == MATHNASIUM_GROUP_ID:
                selected_group = group
                break
    if not selected_group and groups:
        selected_group = groups[0]

    companies = selected_group.get("companies") if isinstance(selected_group.get("companies"), list) else []
    normalized_companies = []
    center_index = []
    aliases: Dict[str, Any] = {}

    for company in companies:
        company_id = _to_text(_coalesce(company.get("id"), company.get("companyId"), company.get("company_id")))
        company_slug_object = company.get("slugObject") if isinstance(company.get("slugObject"), dict) else {}
        company_slug = _to_text(_coalesce(company_slug_object.get("slugValue"), company.get("slug")))
        company_settings = company.get("companySettings") if isinstance(company.get("companySettings"), dict) else {}
        alias_raw = company_settings.get("aliases")
        alias_dict = _decode_base64_json(alias_raw) if isinstance(alias_raw, str) else {}
        if alias_dict:
            aliases = alias_dict

        locations_connection = company.get("locations")
        location_edges: List[Dict[str, Any]] = []
        if isinstance(locations_connection, dict):
            edges = locations_connection.get("edges")
            if isinstance(edges, list):
                location_edges = [edge for edge in edges if isinstance(edge, dict)]

        normalized_locations = []
        for edge in location_edges:
            node = edge.get("node") if isinstance(edge.get("node"), dict) else {}
            if not node:
                continue
            location = _parse_location_node(node, company)
            center_index.append(location)
            normalized_locations.append(
                {
                    "locationId": location["locationId"],
                    "name": location["name"],
                    "customLocationId": location["customLocationId"],
                    "slug": location["slug"],
                    "timezone": location["timezone"],
                    "active": location["active"],
                    "bookingUrl": location["bookingUrl"],
                    "bookingUrls": location["bookingUrls"],
                    "bookingUrlLevel": location["bookingUrlLevel"],
                    "companyBookingUrl": location["companyBookingUrl"],
                    "locationBookingUrl": location["locationBookingUrl"],
                }
            )

        app_modules = []
        for app in _listify(company.get("apps")):
            if not isinstance(app, dict):
                continue
            app_modules.append(
                {
                    "id": _to_text(app.get("id")),
                    "name": _to_text(app.get("name")),
                    "appTypeId": _to_text(app.get("appTypeId")),
                    "active": bool(_coalesce(app.get("active"), True)),
                    "serviceModules": [str(module) for module in _listify(app.get("serviceModules")) if _is_scalar(module)],
                }
            )

        normalized_companies.append(
            {
                "companyId": company_id,
                "displayName": _to_text(_coalesce(company.get("displayName"), company.get("title"))),
                "customCompanyId": _to_text(
                    _coalesce(company.get("customCompanyId"), company.get("custom_company_id"))
                ),
                "companySlug": company_slug,
                "active": bool(_coalesce(company.get("active"), True)),
                "locations": normalized_locations,
                "apps": app_modules,
            }
        )

    return {
        "groupId": _to_text(_coalesce(selected_group.get("id"), MATHNASIUM_GROUP_ID)),
        "groupName": _to_text(_coalesce(selected_group.get("name"), "Mathnasium Group")),
        "companies": normalized_companies,
        "aliases": aliases,
        "centerIndex": center_index,
    }


async def _get_group_context_cached(refresh: bool = False) -> Dict[str, Any]:
    now = time.time()
    if not refresh and _group_context_cache.get("normalized") and now < _group_context_cache.get("expires_at", 0.0):
        return _group_context_cache["normalized"]

    raw = await appointy.get_group_context()
    normalized = _normalize_group_context_payload(raw if isinstance(raw, dict) else {})
    _group_context_cache["raw"] = raw
    _group_context_cache["normalized"] = normalized
    _group_context_cache["expires_at"] = now + max(60, GROUP_CONTEXT_CACHE_TTL_SECONDS)
    return normalized


async def _get_group_context_raw_cached(refresh: bool = False) -> Dict[str, Any]:
    now = time.time()
    if not refresh and _group_context_cache.get("raw") and now < _group_context_cache.get("expires_at", 0.0):
        raw = _group_context_cache.get("raw")
        return raw if isinstance(raw, dict) else {}
    await _get_group_context_cached(refresh=refresh)
    raw = _group_context_cache.get("raw")
    return raw if isinstance(raw, dict) else {}


def _raw_mathnasium_group(raw: Dict[str, Any]) -> Dict[str, Any]:
    viewer = (((raw or {}).get("data") or {}).get("viewer") or {}) if isinstance(raw, dict) else {}
    groups = viewer.get("groups") if isinstance(viewer.get("groups"), list) else []
    for group in groups:
        if _to_text(group.get("id")) == MATHNASIUM_GROUP_ID:
            return group if isinstance(group, dict) else {}
    return groups[0] if groups and isinstance(groups[0], dict) else {}


def _raw_company_by_id(group: Dict[str, Any], company_id: str) -> Dict[str, Any]:
    target = _to_text(company_id)
    for company in _listify(group.get("companies")):
        if isinstance(company, dict) and _to_text(company.get("id")) == target:
            return company
    return {}


def _raw_location_by_id(company: Dict[str, Any], location_id: str) -> Dict[str, Any]:
    target = _to_text(location_id)
    locations_connection = company.get("locations") if isinstance(company, dict) else {}
    for edge in _listify((locations_connection or {}).get("edges") if isinstance(locations_connection, dict) else []):
        node = edge.get("node") if isinstance(edge, dict) else {}
        if isinstance(node, dict) and _to_text(node.get("id")) == target:
            return node
    return {}


def _is_in_mathnasium_group(entity_id: str) -> bool:
    if not entity_id or not MATHNASIUM_GROUP_ID:
        return False
    return entity_id.startswith(f"{MATHNASIUM_GROUP_ID}/")


def _company_prefix_from_entity_id(entity_id: str) -> str:
    parts = entity_id.split("/")
    if len(parts) < 2:
        return ""
    return "/".join(parts[:2])


def _resolve_full_location_id(location_id: str, context: Dict[str, Any]) -> str:
    value = _to_text(location_id).strip()
    if not value:
        return ""
    if "/loc_" in value and value.startswith(f"{MATHNASIUM_GROUP_ID}/"):
        return value
    if not value.startswith("loc_"):
        return value
    for center in _listify(context.get("centerIndex")):
        if not isinstance(center, dict):
            continue
        candidate = _to_text(center.get("locationId"))
        if not candidate:
            continue
        if candidate == value or candidate.endswith(f"/{value}"):
            return candidate
    return value


def _resolve_guardian_parent_scope(parent_id: str, context: Dict[str, Any]) -> Tuple[str, str]:
    parent_value = _to_text(parent_id).strip()
    if not parent_value:
        return "", ""

    if parent_value.startswith(f"{MATHNASIUM_GROUP_ID}/") and "/loc_" in parent_value:
        return parent_value, _company_prefix_from_entity_id(parent_value)
    if parent_value.startswith(f"{MATHNASIUM_GROUP_ID}/") and "/com_" in parent_value:
        company_prefix = _company_prefix_from_entity_id(parent_value)
        return company_prefix, company_prefix

    if parent_value.startswith("loc_"):
        for center in _listify(context.get("centerIndex")):
            if not isinstance(center, dict):
                continue
            location_id = _to_text(center.get("locationId"))
            company_id = _to_text(center.get("companyId"))
            if not location_id or not company_id:
                continue
            if location_id == parent_value or location_id.endswith(f"/{parent_value}"):
                return location_id, company_id
        return parent_value, ""

    if parent_value.startswith("com_"):
        for company in _listify(context.get("companies")):
            if not isinstance(company, dict):
                continue
            company_id = _to_text(company.get("companyId"))
            if not company_id:
                continue
            if company_id == parent_value or company_id.endswith(f"/{parent_value}"):
                return company_id, company_id
        return parent_value, parent_value

    return parent_value, _company_prefix_from_entity_id(parent_value)


def _extract_name(row: Dict[str, Any]) -> str:
    first = _to_text(_coalesce(row.get("firstName"), row.get("first_name")))
    last = _to_text(_coalesce(row.get("lastName"), row.get("last_name")))
    name = _to_text(_coalesce(row.get("name"), row.get("displayName"), row.get("fullName")))
    if name:
        return _normalize_space(name)
    combined = _normalize_space(f"{first} {last}".strip())
    return combined


def _extract_id(row: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    generic = row.get("id")
    if isinstance(generic, str) and generic.strip():
        return generic.strip()
    return ""


def _extract_ids_from_object(value: Any) -> List[str]:
    ids = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                ids.append(item)
            elif isinstance(item, dict):
                item_id = _extract_id(item, "id", "studentId", "guardianId", "locationId")
                if item_id:
                    ids.append(item_id)
    elif isinstance(value, dict):
        item_id = _extract_id(value, "id", "studentId", "guardianId", "locationId")
        if item_id:
            ids.append(item_id)
    elif isinstance(value, str):
        ids.append(value)
    return [i for i in ids if i]


def _parse_metadata(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return _decode_base64_json(value)
    return {}


def _parse_datetime(value: Any) -> Optional[datetime]:
    text = _to_text(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.year <= 1:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_open_ended_date(value: Any) -> bool:
    text = _to_text(value).strip()
    return not text or text.startswith("0001-01-01")


def _enrolment_booking_status(row: Dict[str, Any], now: datetime) -> str:
    start = _parse_datetime(row.get("startDate"))
    termination = _parse_datetime(row.get("terminationDate"))
    has_open_end = _is_open_ended_date(row.get("terminationDate"))

    if start and start > now:
        return "active"
    if start and start <= now and (has_open_end or (termination and termination >= now)):
        return "active"
    if not start and (has_open_end or (termination and termination >= now)):
        return "active"
    return "inactive"


def _normalize_enrolments(value: Any) -> Tuple[List[Dict[str, Any]], str]:
    enrolments: List[Dict[str, Any]] = []
    if not isinstance(value, list):
        return enrolments, "inactive"

    now = datetime.now(timezone.utc)
    can_schedule_sessions = False
    for row in value:
        if not isinstance(row, dict):
            continue
        termination = _to_text(row.get("terminationDate"))
        status = _enrolment_booking_status(row, now)
        if status == "active":
            can_schedule_sessions = True
        enrolments.append(
            {
                "enrolmentId": _to_text(row.get("id")),
                "customEnrolmentId": _to_text(row.get("customEnrolmentId")),
                "customStudentId": _to_text(row.get("customStudentId")),
                "studentId": _to_text(row.get("studentId")),
                "status": status,
                "enrolmentBaseType": _to_text(row.get("enrolmentBaseType")),
                "gradeRangeId": _to_text(row.get("gradeRangeId")),
                "membershipTypeId": _to_text(row.get("membershipTypeId")),
                "maxSessions": row.get("maxSessions"),
                "remainingSessions": row.get("remainingSessions"),
                "sessionLengths": _listify(row.get("sessionLengths")),
                "startDate": _to_text(row.get("startDate")),
                "terminationDate": termination,
                "deliveryMethods": _listify(row.get("deliveryMethods")),
                "holds": _listify(row.get("holds")),
            }
        )
    return enrolments, ("active" if can_schedule_sessions else "inactive")


def _parse_guardian_candidates(payload: Any) -> List[Dict[str, Any]]:
    candidates = []
    edges = []
    if isinstance(payload, dict):
        if isinstance(payload.get("edges"), list):
            edges = payload.get("edges", [])
        elif isinstance(((payload.get("data") or {}).get("customers") or {}).get("edges"), list):
            edges = ((payload.get("data") or {}).get("customers") or {}).get("edges", [])

    if isinstance(edges, list):
        for edge in edges:
            row = {}
            if isinstance(edge, dict):
                if isinstance(edge.get("data"), dict):
                    row = edge.get("data")
                elif isinstance(edge.get("node"), dict):
                    row = edge.get("node")
            if not row:
                continue
            email = _normalize_email(_to_text(row.get("email")))
            name = _extract_name(row)
            guardian_id = _extract_id(row, "id", "customerId", "guardianId")
            phone = _normalize_phone(_to_text(_coalesce(row.get("phoneNumber"), row.get("phone"))))
            metadata = _parse_metadata(row.get("metadata"))
            center_ids = _extract_ids_from_object(
                _coalesce(
                    row.get("locationIds"),
                    row.get("locations"),
                    metadata.get("physicalCenterId"),
                    metadata.get("virtualCenterId"),
                )
            )
            center_custom_ids = [
                _to_text(metadata.get("physicalCenterCustomId")),
                _to_text(metadata.get("virtualCenterCustomId")),
            ]
            candidates.append(
                {
                    "guardianId": guardian_id or f"guardian:{email or name}",
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "centerIds": list(dict.fromkeys([value for value in center_ids if value])),
                    "centerCustomIds": list(dict.fromkeys([value for value in center_custom_ids if value])),
                    "studentIds": [],
                    "active": True,
                    "_raw": row,
                }
            )
    else:
        for row in _iter_dict_nodes(payload):
            email = _normalize_email(
                _to_text(
                    _coalesce(
                        row.get("email"),
                        row.get("access_contact"),
                        row.get("accessContact"),
                        row.get("primaryEmail"),
                    )
                )
            )
            name = _extract_name(row)
            guardian_id = _extract_id(row, "guardianId", "parentId", "customerId", "id")
            if not email and not name and not guardian_id:
                continue
            phone = _normalize_phone(_to_text(_coalesce(row.get("phone"), row.get("telephone"), row.get("mobile"))))
            candidates.append(
                {
                    "guardianId": guardian_id or f"guardian:{email or name}",
                    "name": name,
                    "email": email,
                    "phone": phone,
                    "centerIds": [],
                    "centerCustomIds": [],
                    "studentIds": [],
                    "active": True,
                    "_raw": row,
                }
            )
    return _unique_by_key(candidates, ["guardianId", "email", "name"])


def _parse_student_candidates(payload: Any) -> List[Dict[str, Any]]:
    candidates = []
    edges = []
    direct_student = None
    if isinstance(payload, dict):
        if isinstance(((payload.get("data") or {}).get("students") or {}).get("edges"), list):
            edges = ((payload.get("data") or {}).get("students") or {}).get("edges", [])
        elif isinstance((payload.get("students") or {}).get("edges"), list):
            edges = (payload.get("students") or {}).get("edges", [])
        elif isinstance(payload.get("nodes"), list):
            edges = payload.get("nodes", [])
        if isinstance((payload.get("data") or {}).get("student"), dict):
            direct_student = (payload.get("data") or {}).get("student")
        elif isinstance(payload.get("student"), dict):
            direct_student = payload.get("student")

    if direct_student:
        edges = [{"node": direct_student}]

    if isinstance(edges, list):
        for item in edges:
            row = item.get("node") if isinstance(item, dict) and isinstance(item.get("node"), dict) else {}
            if not row and isinstance(item, dict):
                row = item
            if not row:
                continue
            student_id = _extract_id(row, "id", "studentId")
            name = _extract_name(row)
            metadata = _parse_metadata(row.get("metadata"))
            center_custom_ids = [
                _to_text(metadata.get("physicalCenterCustomId")),
                _to_text(metadata.get("virtualCenterCustomId")),
            ]
            location_link = row.get("studentLocationsLink") if isinstance(row.get("studentLocationsLink"), dict) else {}
            location_ids = _listify(location_link.get("locationIds"))
            enrolments, enrolment_status = _normalize_enrolments(row.get("enrolments"))
            can_schedule_sessions = enrolment_status == "active"
            candidates.append(
                {
                    "studentId": student_id or f"student:{name}",
                    "name": name,
                    "guardianIds": [_to_text(row.get("primaryGuardianId"))] if _to_text(row.get("primaryGuardianId")) else [],
                    "centerIds": [cid for cid in location_ids if isinstance(cid, str) and cid],
                    "centerCustomIds": list(dict.fromkeys([value for value in center_custom_ids if value])),
                    "enrollmentStatus": enrolment_status,
                    "enrollments": enrolments,
                    "grade": _to_text(row.get("grade")),
                    "customStudentId": _to_text(row.get("customStudentId")),
                    "activeMembership": can_schedule_sessions,
                    "canScheduleSessions": can_schedule_sessions,
                    "_raw": row,
                }
            )
    else:
        for row in _iter_dict_nodes(payload):
            student_id = _extract_id(row, "studentId", "id")
            name = _extract_name(row)
            has_student_shape = any(key in row for key in ["studentId", "firstName", "lastName"])
            if not has_student_shape and not (student_id and name):
                continue
            candidates.append(
                {
                    "studentId": student_id or f"student:{name}",
                    "name": name,
                    "guardianIds": [],
                    "centerIds": [],
                    "centerCustomIds": [],
                    "enrollmentStatus": "inactive",
                    "enrollments": [],
                    "activeMembership": False,
                    "canScheduleSessions": False,
                    "_raw": row,
                }
            )
    return _unique_by_key(candidates, ["studentId", "name"])


def _score_text_match(query: str, value: str) -> float:
    q = _normalize_space(query).lower()
    v = _normalize_space(value).lower()
    if not q or not v:
        return 0.0
    if q == v:
        return 1.0
    if q in v:
        return 0.85
    q_tokens = set(q.split(" "))
    v_tokens = set(v.split(" "))
    if not q_tokens:
        return 0.0
    overlap = len(q_tokens.intersection(v_tokens))
    return min(0.75, overlap / max(1, len(q_tokens)))


def _guardian_confidence(
    guardian: Dict[str, Any],
    *,
    email: Optional[str],
    name: Optional[str],
    phone: Optional[str],
) -> Tuple[float, str]:
    reasons = []
    score = 0.35

    if email:
        input_variants = set(_email_variants(email))
        matched_email = _normalize_email(guardian.get("email"))
        if matched_email and matched_email in input_variants:
            if matched_email == _normalize_email(email):
                score += 0.5
                reasons.append("exact_email")
            else:
                score += 0.35
                reasons.append("normalized_email")

    if name:
        name_score = _score_text_match(name, _to_text(guardian.get("name")))
        if name_score >= 0.99:
            score += 0.35
            reasons.append("exact_name")
        elif name_score > 0:
            score += 0.2
            reasons.append("partial_name")

    if phone:
        input_phone = _normalize_phone(phone)
        guardian_phone = _normalize_phone(_to_text(guardian.get("phone")))
        if input_phone and guardian_phone and input_phone == guardian_phone:
            score += 0.25
            reasons.append("exact_phone")

    return min(score, 0.99), (reasons[0] if reasons else "candidate")


def _student_confidence(
    student: Dict[str, Any],
    *,
    student_name: Optional[str],
    guardian_id: Optional[str],
    center_id: Optional[str],
) -> Tuple[float, str]:
    score = 0.3
    reasons = []
    if student_name:
        name_score = _score_text_match(student_name, _to_text(student.get("name")))
        if name_score >= 0.99:
            score += 0.45
            reasons.append("exact_student_name")
        elif name_score > 0:
            score += 0.25
            reasons.append("partial_student_name")
    if guardian_id and guardian_id in _listify(student.get("guardianIds")):
        score += 0.2
        reasons.append("guardian_link")
    if center_id and center_id in _listify(student.get("centerIds")):
        score += 0.2
        reasons.append("center_link")
    return min(score, 0.99), (reasons[0] if reasons else "candidate")


def _center_confidence(center: Dict[str, Any], query: str) -> float:
    values = [
        _to_text(center.get("name")),
        _to_text(center.get("customLocationId")),
        _to_text(center.get("slug")),
        _to_text(center.get("companyDisplayName")),
    ]
    score = 0.0
    for value in values:
        score = max(score, _score_text_match(query, value))
    if query and _to_text(center.get("customLocationId")).lower() == query.lower():
        score = max(score, 1.0)
    return min(score, 1.0)


def _map_center_custom_ids_to_location_ids(center_custom_ids: List[str], context: Dict[str, Any]) -> List[str]:
    if not center_custom_ids:
        return []
    wanted = {value.strip().lower() for value in center_custom_ids if value and value.strip()}
    mapped = []
    for center in _listify(context.get("centerIndex")):
        if not isinstance(center, dict):
            continue
        custom_location_id = _to_text(center.get("customLocationId")).strip().lower()
        if custom_location_id and custom_location_id in wanted:
            mapped.append(_to_text(center.get("locationId")))
    return list(dict.fromkeys([value for value in mapped if value]))


def _build_center_details_from_ids(center_ids: List[str], context: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not center_ids:
        return []

    unique_ids = []
    seen = set()
    for center_id in center_ids:
        value = _to_text(center_id).strip()
        if not value:
            continue
        resolved = _resolve_full_location_id(value, context) or value
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_ids.append(resolved)

    center_index = [row for row in _listify(context.get("centerIndex")) if isinstance(row, dict)]
    hydrated = []
    for wanted_id in unique_ids:
        match = None
        for row in center_index:
            location_id = _to_text(row.get("locationId"))
            if not location_id:
                continue
            if location_id == wanted_id or location_id.endswith(f"/{wanted_id}") or wanted_id.endswith(f"/{location_id}"):
                match = row
                break
        if not match:
            continue
        booking_urls = _listify(match.get("bookingUrls"))
        hydrated.append(
            {
                "companyId": _to_text(match.get("companyId")),
                "locationId": _to_text(match.get("locationId")),
                "centerName": _to_text(match.get("name")),
                "companyDisplayName": _to_text(match.get("companyDisplayName")),
                "customLocationId": _to_text(match.get("customLocationId")),
                "slug": _to_text(match.get("slug")),
                "companySlug": _to_text(match.get("companySlug")),
                "timezone": _to_text(match.get("timezone")),
                "active": bool(match.get("active", True)),
                "bookingUrls": booking_urls,
                "bookingUrl": _to_text(match.get("bookingUrl")) or (booking_urls[0] if booking_urls else ""),
                "bookingUrlLevel": _to_text(match.get("bookingUrlLevel")),
                "companyBookingUrl": _to_text(match.get("companyBookingUrl")),
                "locationBookingUrl": _to_text(match.get("locationBookingUrl")),
            }
        )
    return hydrated


async def _find_guardians_internal(
    *,
    parent_id: str,
    email: Optional[str],
    name: Optional[str],
    first_name: Optional[str],
    last_name: Optional[str],
    phone: Optional[str],
    center_id: Optional[str],
    limit: int,
) -> Dict[str, Any]:
    if not parent_id:
        return {"matches": [], "warnings": ["parentId is required (company or location id)."]}
    if not any([email, name, first_name, last_name, phone]):
        return {"matches": [], "warnings": ["At least one of email, name, firstName, lastName, or phone is required."]}

    context = await _get_group_context_cached(refresh=False)
    warnings = []
    raw_candidates: List[Dict[str, Any]] = []
    normalized_name = _normalize_space(name or "")
    explicit_name = _normalize_space(f"{first_name or ''} {last_name or ''}")
    local_name_query = normalized_name or explicit_name
    lookup_name = _normalize_space(first_name or "") or (normalized_name.split(" ")[0] if normalized_name else None)
    resolved_parent_id, company_scope = _resolve_guardian_parent_scope(parent_id, context)
    if not resolved_parent_id:
        return {"matches": [], "warnings": ["parentId could not be resolved to a company/location scope."]}
    if not company_scope:
        return {"matches": [], "warnings": ["Could not resolve company scope from parentId."]}

    resolved_center_id = _resolve_full_location_id(center_id, context) if center_id else None
    location_ids = [resolved_center_id] if resolved_center_id else None

    try:
        payload = await appointy.find_guardians_graphql(
            parent_id=resolved_parent_id,
            company_scope_id=company_scope,
            first_name=lookup_name,
            email=_normalize_email(email) if email else None,
            phone=_normalize_phone(phone) if phone else None,
            location_ids=location_ids,
            limit=max(limit, DEFAULT_FIRST),
        )
        raw_candidates.extend(_parse_guardian_candidates(payload))
    except AppointyApiError as exc:
        warnings.append(f"Guardian query failed for parent {resolved_parent_id}: {exc}")

    deduped = _unique_by_key(raw_candidates, ["guardianId", "email", "name"])
    input_email_variants = set(_email_variants(email))
    input_phone = _normalize_phone(phone)

    results = []
    for guardian in deduped:
        if not _is_in_mathnasium_group(_to_text(guardian.get("guardianId"))):
            continue

        guardian_email = _normalize_email(_to_text(guardian.get("email")))
        guardian_phone = _normalize_phone(_to_text(guardian.get("phone")))
        guardian_name = _to_text(guardian.get("name"))

        if email and guardian_email not in input_email_variants:
            continue
        if phone and input_phone and guardian_phone != input_phone:
            continue
        if local_name_query and _score_text_match(local_name_query, guardian_name) <= 0:
            continue

        derived_centers = list(guardian.get("centerIds", []))
        derived_centers.extend(
            _map_center_custom_ids_to_location_ids(_listify(guardian.get("centerCustomIds")), context)
        )
        derived_centers = list(dict.fromkeys([center for center in derived_centers if center]))
        if resolved_center_id and resolved_center_id not in derived_centers:
            continue

        confidence, reason = _guardian_confidence(guardian, email=email, name=local_name_query, phone=phone)
        company_prefix = _company_prefix_from_entity_id(_to_text(guardian.get("guardianId")))
        enrichment_students = []
        try:
            detail_payload = await appointy.get_guardian_students_detail_graphql(
                company_id=company_prefix,
                guardian_id=_to_text(guardian.get("guardianId")),
                location_id=(derived_centers[0] if derived_centers else resolved_center_id),
            )
            location_links = (
                (((detail_payload or {}).get("data") or {}).get("customerLocationLinks") or {})
                if isinstance(detail_payload, dict)
                else {}
            )
            derived_centers.extend([loc for loc in _listify(location_links.get("locationIds")) if isinstance(loc, str)])
            derived_centers = list(dict.fromkeys([center for center in derived_centers if center]))
            detail_students = _parse_student_candidates(detail_payload)
            for detail_student in detail_students:
                if not _is_in_mathnasium_group(_to_text(detail_student.get("studentId"))):
                    continue
                enrichment_students.append(
                    {
                        "studentId": _to_text(detail_student.get("studentId")),
                        "name": _to_text(detail_student.get("name")),
                        "customStudentId": _to_text(detail_student.get("customStudentId")),
                        "enrollmentStatus": _to_text(detail_student.get("enrollmentStatus")),
                        "activeMembership": bool(detail_student.get("activeMembership", False)),
                        "canScheduleSessions": bool(detail_student.get("canScheduleSessions", False)),
                        "enrollments": _listify(detail_student.get("enrollments")),
                    }
                )
            enrichment_students = _unique_by_key(enrichment_students, ["studentId"])
        except AppointyApiError as exc:
            warnings.append(f"Guardian detail enrichment failed for {_to_text(guardian.get('guardianId'))}: {exc}")

        center_details = _build_center_details_from_ids(derived_centers, context)
        results.append(
            {
                "guardianId": guardian["guardianId"],
                "name": guardian_name,
                "email": _mask_email(guardian_email),
                "phone": guardian_phone,
                "centerIds": derived_centers,
                "centers": center_details,
                "studentIds": [s.get("studentId", "") for s in enrichment_students if isinstance(s, dict)],
                "students": enrichment_students,
                "active": bool(guardian.get("active", True)),
                "confidence": round(confidence, 3),
                "matchReason": reason,
            }
        )

    results.sort(key=lambda row: row.get("confidence", 0.0), reverse=True)
    results = results[: max(1, min(limit, 50))]

    if email and len(input_email_variants) > 1:
        warnings.append("Checked normalized email variants (including dotted/plus variants).")
    if len(results) > 1:
        warnings.append("Multiple guardian matches found; verify center and student linkage before replying.")
    if not results and not warnings:
        warnings.append("No guardian match found in provided parent scope.")

    return {"matches": results, "warnings": warnings}


async def _find_students_internal(
    *,
    student_name: Optional[str],
    guardian_email: Optional[str],
    guardian_id: Optional[str],
    center_id: Optional[str],
    limit: int,
) -> Dict[str, Any]:
    if not any([student_name, guardian_email, guardian_id]):
        return {"matches": [], "warnings": ["At least one of studentName, guardianEmail, or guardianId is required."]}

    context = await _get_group_context_cached(refresh=False)
    warnings = []
    if guardian_email and not guardian_id:
        warnings.append("guardianEmail filter is ignored without guardianId in group-level student search.")

    results: List[Dict[str, Any]] = []
    center_hint = center_id
    if not center_hint and student_name:
        # no-op, keeping explicit for readability and future extension.
        center_hint = center_id

    try:
        payload = await appointy.find_students_graphql(
            parent_id=MATHNASIUM_GROUP_ID or "",
            student_name=student_name,
            guardian_id=guardian_id,
            limit=max(limit, DEFAULT_FIRST),
            company_scope_id=None,
            location_id=None,
        )
    except AppointyApiError as exc:
        return {"matches": [], "warnings": [f"Student query failed for group scope: {exc}"]}

    parsed = _parse_student_candidates(payload)
    for student in parsed:
        student_id = _to_text(student.get("studentId"))
        if not _is_in_mathnasium_group(student_id):
            continue
        if student_name and _score_text_match(student_name, _to_text(student.get("name"))) <= 0:
            continue

        derived_center_ids = list(_listify(student.get("centerIds")))
        derived_center_ids.extend(
            _map_center_custom_ids_to_location_ids(_listify(student.get("centerCustomIds")), context)
        )
        derived_center_ids = list(dict.fromkeys([value for value in derived_center_ids if value]))
        if center_hint and center_hint not in derived_center_ids:
            continue

        student_guardian_ids = list(_listify(student.get("guardianIds")))
        if guardian_id and guardian_id not in student_guardian_ids:
            student_guardian_ids.append(guardian_id)

        company_scope = _company_prefix_from_entity_id(student_id)
        detail_student = student
        try:
            detail_payload = await appointy.get_student_detail_graphql(
                company_id=company_scope,
                student_id=student_id,
                location_id=(center_hint if center_hint else None),
            )
            parsed_detail = _parse_student_candidates(detail_payload)
            if parsed_detail:
                detail_student = parsed_detail[0]
        except AppointyApiError as exc:
            warnings.append(f"Student detail enrichment failed for {student_id}: {exc}")

        confidence, reason = _student_confidence(
            {
                **detail_student,
                "guardianIds": student_guardian_ids,
                "centerIds": derived_center_ids,
            },
            student_name=student_name,
            guardian_id=guardian_id,
            center_id=center_hint,
        )
        results.append(
            {
                "studentId": student_id,
                "name": student.get("name", ""),
                "guardianIds": student_guardian_ids,
                "centerIds": derived_center_ids,
                "enrollmentStatus": detail_student.get("enrollmentStatus", "unknown"),
                "enrollments": _listify(detail_student.get("enrollments")),
                "customStudentId": _to_text(detail_student.get("customStudentId")),
                "activeMembership": bool(detail_student.get("activeMembership", False)),
                "canScheduleSessions": bool(detail_student.get("canScheduleSessions", False)),
                "confidence": round(confidence, 3),
                "matchReason": reason,
            }
        )
        if len(results) >= max(limit * 2, DEFAULT_FIRST * 2):
            break

    results = _unique_by_key(results, ["studentId", "name"])
    results.sort(key=lambda row: row.get("confidence", 0.0), reverse=True)
    results = results[: max(1, min(limit, 50))]

    if len(results) > 1:
        warnings.append("Multiple student candidates found; verify guardian and center before action.")
    if not results and not warnings:
        warnings.append("No student match found in Mathnasium group scope.")

    return {"matches": results, "warnings": warnings}


async def _find_centers_internal(*, query: Optional[str], include_inactive: bool, limit: int) -> Dict[str, Any]:
    context = await _get_group_context_cached(refresh=False)
    center_index = _listify(context.get("centerIndex"))
    query_value = _normalize_space(_to_text(query))

    matches = []
    for row in center_index:
        if not isinstance(row, dict):
            continue
        if not include_inactive and not bool(row.get("active", True)):
            continue
        if query_value:
            score = _center_confidence(row, query_value)
            if score <= 0:
                continue
        else:
            score = 0.6
        center_type = "virtual"
        name_lower = _to_text(row.get("name")).lower()
        if "virtual" not in name_lower and "online" not in name_lower and "@home" not in name_lower:
            center_type = "physical"
        matches.append(
            {
                "companyId": _to_text(row.get("companyId")),
                "locationId": _to_text(row.get("locationId")),
                "centerName": _to_text(row.get("name")),
                "displayName": _to_text(row.get("name")),
                "customLocationId": _to_text(row.get("customLocationId")),
                "slug": _to_text(row.get("slug")),
                "companySlug": _to_text(row.get("companySlug")),
                "timezone": _to_text(row.get("timezone")),
                "active": bool(row.get("active", True)),
                "centerType": center_type,
                "bookingUrls": _listify(row.get("bookingUrls")),
                "bookingUrl": _to_text(row.get("bookingUrl")) or (_listify(row.get("bookingUrls"))[0] if _listify(row.get("bookingUrls")) else ""),
                "bookingUrlLevel": _to_text(row.get("bookingUrlLevel")),
                "companyBookingUrl": _to_text(row.get("companyBookingUrl")),
                "locationBookingUrl": _to_text(row.get("locationBookingUrl")),
                "confidence": round(score, 3),
            }
        )

    matches = _unique_by_key(matches, ["locationId"])
    matches.sort(key=lambda row: row.get("confidence", 0.0), reverse=True)
    matches = matches[: max(1, min(limit, 100))]
    return {"matches": matches}


async def _get_context_entity_internal(
    *,
    entity_type: str,
    company_id: Optional[str],
    location_id: Optional[str],
    refresh: bool,
) -> Dict[str, Any]:
    raw = await _get_group_context_raw_cached(refresh=refresh)
    group = _raw_mathnasium_group(raw)
    if not group:
        return {"status": "failed", "error": "Mathnasium group context was not found."}

    if entity_type == "group_settings":
        return {
            "status": "success",
            "entityType": entity_type,
            "source": "graphql:AppQuery",
            "data": {
                "groupId": _to_text(group.get("id")),
                "groupName": _to_text(group.get("name")),
                "groupSettings": group.get("groupSettings") or {},
            },
        }

    if not company_id:
        return {"status": "failed", "error": f"{entity_type} requires companyId."}

    company = _raw_company_by_id(group, company_id)
    if not company:
        return {"status": "failed", "error": f"Company not found for companyId={company_id}."}

    if entity_type == "company_settings":
        company_settings = company.get("companySettings") if isinstance(company.get("companySettings"), dict) else {}
        return {
            "status": "success",
            "entityType": entity_type,
            "source": "graphql:AppQuery",
            "data": {
                "companyId": _to_text(company.get("id")),
                "displayName": _to_text(_coalesce(company.get("displayName"), company.get("title"))),
                "customCompanyId": _to_text(company.get("customCompanyId")),
                "active": bool(_coalesce(company.get("active"), True)),
                "preference": company.get("preference") or {},
                "companySettings": company_settings,
                "aliases": _decode_base64_json(company_settings.get("aliases")) if isinstance(company_settings.get("aliases"), str) else {},
                "roleLevelCustomization": company.get("roleLevelCustomization"),
                "apps": _listify(company.get("apps")),
                "metadata": company.get("metadata"),
            },
        }

    if entity_type == "apps":
        return {
            "status": "success",
            "entityType": entity_type,
            "source": "graphql:AppQuery",
            "data": {
                "companyId": _to_text(company.get("id")),
                "apps": _listify(company.get("apps")),
            },
        }

    if entity_type == "location_settings":
        if not location_id:
            return {"status": "failed", "error": "location_settings requires locationId."}
        location = _raw_location_by_id(company, location_id)
        if not location:
            return {"status": "failed", "error": f"Location not found for locationId={location_id}."}
        return {
            "status": "success",
            "entityType": entity_type,
            "source": "graphql:AppQuery",
            "data": {
                "companyId": _to_text(company.get("id")),
                "locationId": _to_text(location.get("id")),
                "name": _to_text(location.get("name")),
                "customLocationId": _to_text(location.get("customLocationId")),
                "active": bool(_coalesce(location.get("active"), True)),
                "preference": location.get("preference") or {},
                "slugObject": location.get("slugObject") or {},
                "address": location.get("address") or {},
                "telephones": _listify(location.get("telephones")),
                "metadata": location.get("metadata"),
            },
        }

    return {"status": "failed", "error": f"Unsupported context entity type: {entity_type}"}


async def _get_graphql_entity_internal(
    *,
    entity_type: str,
    parent_id: str,
    company_id: Optional[str],
    location_id: Optional[str],
    entity_id: Optional[str],
    limit: int,
) -> Dict[str, Any]:
    query_spec = GRAPHQL_OTHER_ENTITY_QUERIES.get(entity_type)
    if not query_spec:
        return {"status": "failed", "error": f"Unsupported GraphQL entity type: {entity_type}"}
    if not parent_id:
        return {"status": "failed", "error": f"{entity_type} requires parentId."}

    query_id, connection_name, query = query_spec
    payload = await appointy._graphql(
        query_id=query_id,
        query=query,
        variables={"parent": parent_id, "first": max(1, min(limit, 100))},
        company_id=company_id or _company_prefix_from_entity_id(parent_id),
        location_id=location_id if location_id else (parent_id if "/loc_" in parent_id else None),
    )
    errors = payload.get("errors") if isinstance(payload, dict) else None
    data = payload.get("data") if isinstance(payload, dict) else {}
    connection = data.get(connection_name) if isinstance(data, dict) else {}
    edges = connection.get("edges") if isinstance(connection, dict) else []
    items = []
    for edge in _listify(edges):
        node = edge.get("node") if isinstance(edge, dict) else {}
        if not isinstance(node, dict):
            continue
        if entity_id and _to_text(node.get("id")) != _to_text(entity_id):
            continue
        items.append(_normalize_service_entity(node) if entity_type == "services" else node)

    return {
        "status": "success" if not errors else "partial",
        "entityType": entity_type,
        "source": f"graphql:{query_id}",
        "parentId": parent_id,
        "entityId": entity_id or "",
        "items": items,
        "rawErrors": errors,
        "warnings": [
            "This common lookup does exact entity-type/parent/id based reads only; it does not fuzzy-search names or infer missing scope."
        ],
    }


def _normalize_service_entity(node: Dict[str, Any]) -> Dict[str, Any]:
    service_link = node.get("mathnasiumServiceLinks")
    if not isinstance(service_link, dict):
        service_link = {}

    memberships = [item for item in _listify(service_link.get("memberships")) if isinstance(item, dict)]
    grade_ranges = [item for item in _listify(service_link.get("grades")) if isinstance(item, dict)]
    durations = [value for value in _listify(node.get("durations")) if isinstance(value, (int, float))]

    return {
        **node,
        "mathnasiumServiceLinkId": _to_text(service_link.get("id")),
        "membershipTypes": memberships,
        "membershipTypeIds": [_to_text(item.get("id")) for item in memberships if _to_text(item.get("id"))],
        "gradeRanges": grade_ranges,
        "gradeRangeIds": [_to_text(item.get("id")) for item in grade_ranges if _to_text(item.get("id"))],
        "durationsSeconds": durations,
        "durationsMinutes": [value / 60 for value in durations],
        "hasMembershipLinks": bool(memberships),
        "hasGradeRangeLinks": bool(grade_ranges),
    }
