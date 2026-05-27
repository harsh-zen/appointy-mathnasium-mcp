import argparse
import base64
import json
import logging
import os
import re
import time
import uuid
from typing import Any, Dict, Iterable, List, Literal, Optional, Set, Tuple
from urllib.parse import urljoin

import httpx
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

TransportType = Literal["stdio", "sse", "streamable-http"]


def _bool_from_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_mcp_port(default: int = 8010) -> int:
    mcp_port = os.getenv("MCP_PORT")
    if mcp_port:
        try:
            return int(mcp_port)
        except ValueError:
            pass

    render_port = os.getenv("PORT")
    if render_port:
        try:
            return int(render_port)
        except ValueError:
            pass

    return default


def _safe_int_from_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


DEFAULT_TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio").strip().lower()
if DEFAULT_TRANSPORT == "http":
    DEFAULT_TRANSPORT = "streamable-http"
if DEFAULT_TRANSPORT not in {"stdio", "sse", "streamable-http"}:
    DEFAULT_TRANSPORT = "stdio"

MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
MCP_PORT = _resolve_mcp_port(8010)
MCP_STREAMABLE_HTTP_PATH = os.getenv("MCP_STREAMABLE_HTTP_PATH", "/mcp")
MCP_SSE_PATH = os.getenv("MCP_SSE_PATH", "/sse")
MCP_JSON_RESPONSE = _bool_from_env("MCP_JSON_RESPONSE", False)
MCP_STATELESS_HTTP = _bool_from_env("MCP_STATELESS_HTTP", False)
MCP_LOG_LEVEL = os.getenv("MCP_LOG_LEVEL", "INFO").upper()

APPOINTY_API_BASE_URL = os.getenv("APPOINTY_API_BASE_URL", "").rstrip("/")
APPOINTY_API_KEY = os.getenv("APPOINTY_API_KEY")
MATHNASIUM_GROUP_ID = os.getenv("MATHNASIUM_GROUP_ID")
MATHNASIUM_COMPANY_ID_OPTIONAL = os.getenv("MATHNASIUM_COMPANY_ID_OPTIONAL")
DEFAULT_SUPPORT_USER_ID = os.getenv("DEFAULT_SUPPORT_USER_ID")
DEFAULT_FIRST = _safe_int_from_env("DEFAULT_FIRST", 25)
GROUP_CONTEXT_CACHE_TTL_SECONDS = _safe_int_from_env("GROUP_CONTEXT_CACHE_TTL_SECONDS", 900)
APPOINTY_TIMEOUT_SECONDS = _safe_int_from_env("APPOINTY_TIMEOUT_SECONDS", 20)
ENABLE_PII_MASKING = _bool_from_env("ENABLE_PII_MASKING", False)
APPOINTY_BOOKING_URL_TEMPLATE = os.getenv("APPOINTY_BOOKING_URL_TEMPLATE", "https://www.appointy.com/{locationSlug}")


GRAPHQL_APP_QUERY = """
query AppQuery {
  viewer {
    id
    groups {
      id
      name
      companies {
        id
        title
        displayName
        active
        customCompanyId
        slugObject {
          slugValue
        }
        companySettings {
          aliases(locale: "en-US")
        }
        apps {
          id
          appTypeId
          name
          active
          serviceModules
        }
        locations(first: 500) {
          edges {
            node {
              id
              name
              customLocationId
              active
              preference {
                timezone
              }
              slugObject {
                slugValue
              }
            }
          }
        }
      }
    }
  }
}
""".strip()

GRAPHQL_FIND_GUARDIANS_QUERY = """
query FindGuardianQuery(
  $parent: String!
  $first: Int!
  $firstName: String
  $email: String
  $phone: String
  $locationIds: [String!]
) {
  customers(
    parent: $parent
    first: $first
    firstName: $firstName
    email: $email
    phoneNumber: $phone
    locationIds: $locationIds
    accessContact: true
  ) {
    edges {
      node {
        id
        firstName
        lastName
        email
        phoneNumber
        customCustomerId
        metadata
      }
    }
  }
}
""".strip()

GRAPHQL_GUARDIAN_DETAIL_QUERY = """
query CustomerDetailQuery($customerId: String) {
  students(guardianId: { guardianId: $customerId }, first: 100) {
    edges {
      node {
        id
        firstName
        lastName
        email
        grade
        customStudentId
        activeMembership
        metadata
        primaryGuardianId
        studentLocationsLink {
          locationIds
          studentId
        }
        enrolments {
          id
          customEnrolmentId
          customStudentId
          enrolmentBaseType
          gradeRangeId
          maxSessions
          remainingSessions
          membershipTypeId
          sessionLengths
          startDate
          terminationDate
          studentId
          deliveryMethods {
            deliveryMethod
            timeSlot {
              startTime
              endTime
            }
          }
          holds {
            id
            customHoldId
            deleteScheduledSessions
            startDate
            endDate
          }
        }
      }
    }
  }
  customerLocationLinks(customerId: $customerId) {
    locationIds
  }
}
""".strip()

GRAPHQL_FIND_STUDENTS_QUERY = """
query FindStudentQuery(
  $parent: String!
  $first: Int!
  $query: String
  $guardianId: String
) {
  students(
    parent: { parent: $parent }
    first: $first
    query: $query
    guardianId: { guardianId: $guardianId }
  ) {
    edges {
      node {
        id
        firstName
        lastName
        email
        grade
        customStudentId
        activeMembership
        metadata
        primaryGuardianId
        studentLocationsLink {
          locationIds
          studentId
        }
        enrolments {
          id
          customEnrolmentId
          customStudentId
          enrolmentBaseType
          gradeRangeId
          maxSessions
          remainingSessions
          membershipTypeId
          sessionLengths
          startDate
          terminationDate
          studentId
          deliveryMethods {
            deliveryMethod
            timeSlot {
              startTime
              endTime
            }
          }
          holds {
            id
            customHoldId
            deleteScheduledSessions
            startDate
            endDate
          }
        }
      }
    }
  }
}
""".strip()

GRAPHQL_FIND_STUDENTS_QUERY_NO_GUARDIAN = """
query FindStudentQuery(
  $parent: String!
  $first: Int!
  $query: String
) {
  students(
    parent: { parent: $parent }
    first: $first
    query: $query
  ) {
    edges {
      node {
        id
        firstName
        lastName
        email
        grade
        customStudentId
        activeMembership
        metadata
        primaryGuardianId
        studentLocationsLink {
          locationIds
          studentId
        }
        enrolments {
          id
          customEnrolmentId
          customStudentId
          enrolmentBaseType
          gradeRangeId
          maxSessions
          remainingSessions
          membershipTypeId
          sessionLengths
          startDate
          terminationDate
          studentId
          deliveryMethods {
            deliveryMethod
            timeSlot {
              startTime
              endTime
            }
          }
          holds {
            id
            customHoldId
            deleteScheduledSessions
            startDate
            endDate
          }
        }
      }
    }
  }
}
""".strip()

GRAPHQL_STUDENT_DETAIL_QUERY = """
query StudentDetailQuery($id: ID!) {
  student(id: $id) {
    id
    firstName
    lastName
    email
    grade
    customStudentId
    activeMembership
    metadata
    primaryGuardianId
    studentLocationsLink {
      locationIds
      studentId
    }
    enrolments {
      id
      customEnrolmentId
      customStudentId
      enrolmentBaseType
      gradeRangeId
      maxSessions
      remainingSessions
      membershipTypeId
      sessionLengths
      startDate
      terminationDate
      studentId
      deliveryMethods {
        deliveryMethod
        timeSlot {
          startTime
          endTime
        }
      }
      holds {
        id
        customHoldId
        deleteScheduledSessions
        startDate
        endDate
      }
    }
  }
}
""".strip()

logging.basicConfig(level=logging.INFO)

mcp = FastMCP(
    "appointy-mathnasium-mcp",
    host=MCP_HOST,
    port=MCP_PORT,
    streamable_http_path=MCP_STREAMABLE_HTTP_PATH,
    sse_path=MCP_SSE_PATH,
    json_response=MCP_JSON_RESPONSE,
    stateless_http=MCP_STATELESS_HTTP,
    log_level=MCP_LOG_LEVEL,
)


def _require_config() -> Optional[Dict[str, Any]]:
    missing = []
    if not APPOINTY_API_BASE_URL:
        missing.append("APPOINTY_API_BASE_URL")
    if not APPOINTY_API_KEY:
        missing.append("APPOINTY_API_KEY")
    if not MATHNASIUM_GROUP_ID:
        missing.append("MATHNASIUM_GROUP_ID")
    if missing:
        return {
            "status": "failed",
            "error": "Missing required environment variables",
            "missing": missing,
        }
    return None


def _normalize_text(value: Optional[str]) -> str:
    return (value or "").strip()


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _normalize_phone(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"[^0-9+]", "", value)


def _split_email(email: str) -> Tuple[str, str]:
    parts = email.split("@", 1)
    if len(parts) != 2:
        return "", ""
    return parts[0], parts[1]


def _normalize_email(email: Optional[str]) -> str:
    if not email:
        return ""
    return email.strip().lower()


def _email_variants(email: Optional[str]) -> List[str]:
    normalized = _normalize_email(email)
    if not normalized or "@" not in normalized:
        return []
    local, domain = _split_email(normalized)
    if not local or not domain:
        return [normalized]

    local_no_plus = local.split("+", 1)[0]
    variants = [f"{local_no_plus}@{domain}"]
    if domain in {"gmail.com", "googlemail.com"}:
        variants.append(f"{local_no_plus.replace('.', '')}@{domain}")
    if normalized not in variants:
        variants.insert(0, normalized)

    # Keep order but remove duplicates.
    seen: Set[str] = set()
    deduped = []
    for variant in variants:
        if variant not in seen:
            seen.add(variant)
            deduped.append(variant)
    return deduped


def _mask_email(email: Optional[str]) -> str:
    if not email:
        return ""
    normalized = _normalize_email(email)
    if not ENABLE_PII_MASKING:
        return normalized
    if "@" not in normalized:
        return normalized
    local, domain = _split_email(normalized)
    if len(local) <= 2:
        return f"{local[:1]}***@{domain}"
    return f"{local[:1]}***{local[-1:]}@{domain}"


def _listify(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _is_dict(value: Any) -> bool:
    return isinstance(value, dict)


def _is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) or value is None


def _iter_dict_nodes(value: Any, max_depth: int = 7, depth: int = 0) -> Iterable[Dict[str, Any]]:
    if depth > max_depth:
        return
    if isinstance(value, dict):
        yield value
        for child in value.values():
            if isinstance(child, (dict, list)):
                yield from _iter_dict_nodes(child, max_depth=max_depth, depth=depth + 1)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)):
                yield from _iter_dict_nodes(item, max_depth=max_depth, depth=depth + 1)


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _safe_json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=True)
    except Exception:
        return _to_text(value)


def _decode_base64_json(value: Optional[str]) -> Dict[str, Any]:
    if not value:
        return {}
    try:
        decoded = base64.b64decode(value).decode("utf-8")
        parsed = json.loads(decoded)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return {}
    return {}


def _build_booking_urls(location_slug: str, company_slug: str = "") -> List[str]:
    urls: List[str] = []
    template = APPOINTY_BOOKING_URL_TEMPLATE.strip()
    if template and "{locationSlug}" in template:
        try:
            built = template.format(
                locationSlug=location_slug,
                companySlug=company_slug,
                slug=location_slug,
            )
            if built:
                urls.append(built)
        except Exception:
            pass

    # Safe fallback candidates when template is not supplied or mismatched.
    if location_slug:
        urls.append(f"https://www.appointy.com/{location_slug}")
    if company_slug:
        urls.append(f"https://www.appointy.com/{company_slug}")

    deduped = []
    seen = set()
    for url in urls:
        cleaned = url.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)
    return deduped


def _unique_by_key(rows: List[Dict[str, Any]], key_fields: List[str]) -> List[Dict[str, Any]]:
    seen = set()
    deduped = []
    for row in rows:
        key = tuple(_to_text(row.get(field, "")).lower() for field in key_fields)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _status_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned in {"active", "enabled", "true", "yes"}:
            return True
        if cleaned in {"inactive", "disabled", "false", "no"}:
            return False
    return None


class AppointyApiError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None, payload: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class AppointyClient:
    def __init__(self) -> None:
        self.base_url = APPOINTY_API_BASE_URL
        self.api_key = APPOINTY_API_KEY
        self.timeout = APPOINTY_TIMEOUT_SECONDS

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Any:
        error = _require_config()
        if error:
            raise AppointyApiError(error["error"], payload=error)

        url = urljoin(f"{self.base_url}/", path.lstrip("/"))
        headers = {
            "x-api-key": self.api_key or "",
            "x-request-id": str(uuid.uuid4()),
            "accept": "application/json",
        }
        if json_body is not None:
            headers["content-type"] = "application/json"

        filtered_params = {}
        for key, value in (params or {}).items():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            filtered_params[key] = value

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.request(
                method,
                url,
                headers=headers,
                params=filtered_params or None,
                json=json_body,
            )

        content_type = response.headers.get("content-type", "").lower()
        parsed_payload: Any
        if "application/json" in content_type:
            try:
                parsed_payload = response.json()
            except Exception:
                parsed_payload = {"raw": response.text}
        else:
            parsed_payload = {"raw": response.text}

        if response.is_error:
            raise AppointyApiError(
                f"Appointy API error {response.status_code}",
                status_code=response.status_code,
                payload=parsed_payload,
            )
        return parsed_payload

    async def _graphql(
        self,
        *,
        query_id: str,
        query: str,
        variables: Dict[str, Any],
        company_id: Optional[str] = None,
        location_id: Optional[str] = None,
        user_id: Optional[str] = None,
        use_default_company_scope: bool = True,
    ) -> Any:
        resolved_company_id = company_id
        if not resolved_company_id and use_default_company_scope:
            resolved_company_id = MATHNASIUM_COMPANY_ID_OPTIONAL or None

        params: Dict[str, Any] = {
            "groupId": MATHNASIUM_GROUP_ID,
            "companyId": resolved_company_id,
            "locationId": location_id or None,
            "queryId": query_id,
            "userId": user_id or DEFAULT_SUPPORT_USER_ID or None,
        }
        body = {
            "id": query_id,
            "query": query,
            "variables": variables,
        }
        return await self._request("POST", "/graphql", params=params, json_body=body)

    async def find_guardians_graphql(
        self,
        *,
        parent_id: str,
        company_scope_id: str,
        first_name: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        location_ids: Optional[List[str]] = None,
        limit: int = 10,
    ) -> Any:
        return await self._graphql(
            query_id="FindGuardianQuery",
            query=GRAPHQL_FIND_GUARDIANS_QUERY,
            variables={
                "parent": parent_id,
                "first": max(1, min(limit, 100)),
                "firstName": first_name or None,
                "email": email or None,
                "phone": phone or None,
                "locationIds": location_ids or None,
            },
            company_id=company_scope_id,
            location_id=location_ids[0] if location_ids else None,
            use_default_company_scope=False,
        )

    async def get_guardian_students_detail_graphql(
        self,
        *,
        company_id: str,
        guardian_id: str,
        location_id: Optional[str] = None,
    ) -> Any:
        return await self._graphql(
            query_id="CustomerDetailQuery",
            query=GRAPHQL_GUARDIAN_DETAIL_QUERY,
            variables={"customerId": guardian_id},
            company_id=company_id,
            location_id=location_id,
        )

    async def find_students_graphql(
        self,
        *,
        parent_id: str,
        student_name: Optional[str] = None,
        guardian_id: Optional[str] = None,
        limit: int = 10,
        company_scope_id: Optional[str] = None,
        location_id: Optional[str] = None,
    ) -> Any:
        if guardian_id:
            query = GRAPHQL_FIND_STUDENTS_QUERY
            variables = {
                "parent": parent_id,
                "first": max(1, min(limit, 100)),
                "query": student_name or None,
                "guardianId": guardian_id,
            }
        else:
            query = GRAPHQL_FIND_STUDENTS_QUERY_NO_GUARDIAN
            variables = {
                "parent": parent_id,
                "first": max(1, min(limit, 100)),
                "query": student_name or None,
            }
        return await self._graphql(
            query_id="FindStudentQuery",
            query=query,
            variables=variables,
            company_id=company_scope_id,
            location_id=location_id,
            use_default_company_scope=False,
        )

    async def get_student_detail_graphql(
        self,
        *,
        company_id: str,
        student_id: str,
        location_id: Optional[str] = None,
    ) -> Any:
        return await self._graphql(
            query_id="StudentDetailQuery",
            query=GRAPHQL_STUDENT_DETAIL_QUERY,
            variables={"id": student_id},
            company_id=company_id,
            location_id=location_id,
        )

    async def get_companies(self, *, query: Optional[str] = None, limit: int = 50) -> Any:
        params: Dict[str, Any] = {
            "parent": MATHNASIUM_GROUP_ID,
            "view_mask": "default",
            "first": max(1, min(limit, 200)),
            "query": query or None,
        }
        return await self._request("GET", "/api/v1/companies", params=params)

    async def get_locations(self, *, query: Optional[str] = None, limit: int = 100) -> Any:
        params: Dict[str, Any] = {
            "parent": MATHNASIUM_GROUP_ID,
            "view_mask": "default",
            "first": max(1, min(limit, 300)),
            "query": query or None,
        }
        return await self._request("GET", "/api/v1/locations", params=params)

    async def get_group_context(self) -> Any:
        return await self._graphql(
            query_id="AppQuery",
            query=GRAPHQL_APP_QUERY,
            variables={},
            company_id=MATHNASIUM_COMPANY_ID_OPTIONAL or None,
            location_id=None,
        )


appointy = AppointyClient()

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
        "bookingUrls": _build_booking_urls(location_slug, company_slug),
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
                    "bookingUrls": location["bookingUrls"],
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


def _normalize_enrolments(value: Any) -> Tuple[List[Dict[str, Any]], str]:
    enrolments: List[Dict[str, Any]] = []
    if not isinstance(value, list):
        return enrolments, "unknown"

    has_active = False
    for row in value:
        if not isinstance(row, dict):
            continue
        termination = _to_text(row.get("terminationDate"))
        status = "active" if not termination or termination.startswith("0001-01-01") else "inactive"
        if status == "active":
            has_active = True
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
    return enrolments, ("active" if has_active else ("inactive" if enrolments else "unknown"))


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
                    "activeMembership": bool(row.get("activeMembership", False)),
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
                    "enrollmentStatus": "unknown",
                    "enrollments": [],
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
                "bookingUrl": booking_urls[0] if booking_urls else "",
            }
        )
    return hydrated


async def _find_guardians_internal(
    *,
    parent_id: str,
    email: Optional[str],
    name: Optional[str],
    phone: Optional[str],
    center_id: Optional[str],
    limit: int,
) -> Dict[str, Any]:
    if not parent_id:
        return {"matches": [], "warnings": ["parentId is required (company or location id)."]}
    if not any([email, name, phone]):
        return {"matches": [], "warnings": ["At least one of email, name, or phone is required."]}

    context = await _get_group_context_cached(refresh=False)
    warnings = []
    raw_candidates: List[Dict[str, Any]] = []
    lookup_name = None
    if name:
        lookup_name = _normalize_space(name).split(" ")[0]
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
        if name and _score_text_match(name, guardian_name) <= 0:
            continue

        derived_centers = list(guardian.get("centerIds", []))
        derived_centers.extend(
            _map_center_custom_ids_to_location_ids(_listify(guardian.get("centerCustomIds")), context)
        )
        derived_centers = list(dict.fromkeys([center for center in derived_centers if center]))
        if resolved_center_id and resolved_center_id not in derived_centers:
            continue

        confidence, reason = _guardian_confidence(guardian, email=email, name=name, phone=phone)
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
                "bookingUrl": (_listify(row.get("bookingUrls"))[0] if _listify(row.get("bookingUrls")) else ""),
                "confidence": round(score, 3),
            }
        )

    matches = _unique_by_key(matches, ["locationId"])
    matches.sort(key=lambda row: row.get("confidence", 0.0), reverse=True)
    matches = matches[: max(1, min(limit, 100))]
    return {"matches": matches}


@mcp.custom_route("/health", methods=["GET"], include_in_schema=False)
async def health_check(_: Request) -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "service": "appointy-mathnasium-mcp",
            "transport": "mcp",
        }
    )


@mcp.tool()
async def mathnasium_get_group_context(refresh: bool = False) -> Dict[str, Any]:
    """Return normalized Mathnasium group/company/location context and aliases."""
    config_error = _require_config()
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
    parentId: str,
    email: Optional[str] = None,
    name: Optional[str] = None,
    phone: Optional[str] = None,
    centerId: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """Find guardian records within a provided parent scope (company or location id)."""
    config_error = _require_config()
    if config_error:
        return config_error
    try:
        return await _find_guardians_internal(
            parent_id=parentId,
            email=email,
            name=name,
            phone=phone,
            center_id=centerId,
            limit=max(1, min(limit, 50)),
        )
    except Exception as exc:
        return {"matches": [], "warnings": [f"Unexpected error in guardian lookup: {exc}"]}


@mcp.tool()
async def mathnasium_find_student(
    studentName: Optional[str] = None,
    guardianEmail: Optional[str] = None,
    guardianId: Optional[str] = None,
    centerId: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """Find students and enrollment state by student/guardian/center hints."""
    config_error = _require_config()
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
    query: Optional[str] = None,
    includeInactive: bool = False,
    limit: int = 10,
) -> Dict[str, Any]:
    """Find Mathnasium center/company/location by free text, slug, or customLocationId."""
    config_error = _require_config()
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


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Appointy Mathnasium MCP server")
    parser.add_argument(
        "--transport",
        default=DEFAULT_TRANSPORT,
        choices=["stdio", "sse", "streamable-http", "http"],
        help="Transport to run (http is an alias for streamable-http).",
    )
    parser.add_argument("--host", default=MCP_HOST, help="Host for HTTP/SSE transports.")
    parser.add_argument("--port", type=int, default=MCP_PORT, help="Port for HTTP/SSE transports.")
    parser.add_argument(
        "--streamable-http-path",
        default=MCP_STREAMABLE_HTTP_PATH,
        help="Path for streamable HTTP endpoint.",
    )
    parser.add_argument(
        "--sse-path",
        default=MCP_SSE_PATH,
        help="Path for SSE endpoint.",
    )
    parser.add_argument(
        "--json-response",
        action="store_true",
        default=MCP_JSON_RESPONSE,
        help="Enable JSON responses for streamable HTTP transport.",
    )
    parser.add_argument(
        "--stateless-http",
        action="store_true",
        default=MCP_STATELESS_HTTP,
        help="Enable stateless streamable HTTP mode for horizontal scalability.",
    )
    parser.add_argument(
        "--log-level",
        default=MCP_LOG_LEVEL,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level.",
    )
    return parser


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()
    transport: TransportType = "streamable-http" if args.transport == "http" else args.transport

    mcp.settings.host = args.host
    mcp.settings.port = args.port
    mcp.settings.streamable_http_path = args.streamable_http_path
    mcp.settings.sse_path = args.sse_path
    mcp.settings.json_response = args.json_response
    mcp.settings.stateless_http = args.stateless_http
    mcp.settings.log_level = args.log_level

    logging.info(
        "Starting Appointy Mathnasium MCP server transport=%s host=%s port=%s",
        transport,
        args.host,
        args.port,
    )
    if transport == "streamable-http":
        logging.info("Streamable HTTP endpoint: http://%s:%s%s", args.host, args.port, args.streamable_http_path)
    elif transport == "sse":
        logging.info("SSE endpoint: http://%s:%s%s", args.host, args.port, args.sse_path)

    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
