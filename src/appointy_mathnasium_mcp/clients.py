import os
import tempfile
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import asyncio
import httpx

from .config import (
    APPOINTY_API_BASE_URL,
    APPOINTY_API_KEY,
    APPOINTY_TIMEOUT_SECONDS,
    DEFAULT_SUPPORT_USER_ID,
    GCP_CLUSTER_NAME,
    GCP_LOG_LOCATION,
    GCP_LOG_MAX_LIMIT,
    GCP_NAMESPACE,
    GCP_POD_APP_LABEL,
    GCP_PROJECT_ID,
    GOOGLE_APPLICATION_CREDENTIALS_JSON,
    MATHNASIUM_GROUP_ID,
    require_config,
)
from .errors import AppointyApiError, GcpLoggingError
from .queries import (
    GRAPHQL_APP_QUERY,
    GRAPHQL_FIND_GUARDIANS_QUERY,
    GRAPHQL_FIND_STUDENTS_QUERY,
    GRAPHQL_FIND_STUDENTS_QUERY_NO_GUARDIAN,
    GRAPHQL_STUDENT_DETAIL_QUERY,
    GRAPHQL_GUARDIAN_DETAIL_QUERY,
)

logging_v2 = None
logging_v2_import_error: Optional[Exception] = None


def _ensure_google_credentials_file() -> Optional[str]:
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        return os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not GOOGLE_APPLICATION_CREDENTIALS_JSON:
        return None

    credentials_path = os.path.join(tempfile.gettempdir(), "appointy_mathnasium_gcp_credentials.json")
    if not os.path.exists(credentials_path):
        with open(credentials_path, "w", encoding="utf-8") as handle:
            handle.write(GOOGLE_APPLICATION_CREDENTIALS_JSON)
        os.chmod(credentials_path, 0o600)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
    return credentials_path


def _load_google_logging_client_module() -> Any:
    global logging_v2, logging_v2_import_error
    if logging_v2 is not None or logging_v2_import_error is not None:
        return logging_v2
    try:
        from google.cloud import logging_v2 as loaded_logging_v2

        logging_v2 = loaded_logging_v2
    except Exception as exc:  # pragma: no cover - dependency/config surfaced at tool runtime
        logging_v2_import_error = exc
        logging_v2 = None
    return logging_v2


def require_gcp_logging_config():
    missing = []
    _load_google_logging_client_module()
    if logging_v2 is None:
        if logging_v2_import_error:
            missing.append(f"google-cloud-logging dependency: {logging_v2_import_error}")
        else:
            missing.append("google-cloud-logging dependency")
    if not GCP_PROJECT_ID:
        missing.append("GCP_PROJECT_ID")
    if not GCP_LOG_LOCATION:
        missing.append("GCP_LOG_LOCATION")
    if not GCP_CLUSTER_NAME:
        missing.append("GCP_CLUSTER_NAME")
    if not GCP_NAMESPACE:
        missing.append("GCP_NAMESPACE")
    if not GCP_POD_APP_LABEL:
        missing.append("GCP_POD_APP_LABEL")
    if missing:
        return {
            "status": "failed",
            "error": "Missing required Google Cloud Logging configuration",
            "missing": missing,
        }
    return None

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
    ) -> Any:
        resolved_company_id = company_id
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
            company_id=None,
            location_id=None,
        )


appointy = AppointyClient()


class GcpLoggingClient:
    def __init__(self) -> None:
        self.project_id = GCP_PROJECT_ID

    def _list_entries_sync(self, *, filter_: str, limit: int) -> List[Any]:
        _ensure_google_credentials_file()
        error = _require_gcp_logging_config()
        if error:
            raise GcpLoggingError(error["error"], payload=error)
        client = logging_v2.Client(project=self.project_id)  # type: ignore[union-attr]
        return list(
            client.list_entries(
                resource_names=[f"projects/{self.project_id}"],
                filter_=filter_,
                order_by=logging_v2.DESCENDING,  # type: ignore[union-attr]
                page_size=max(1, min(limit, GCP_LOG_MAX_LIMIT)),
                max_results=max(1, min(limit, GCP_LOG_MAX_LIMIT)),
            )
        )

    async def list_entries(self, *, filter_: str, limit: int) -> List[Any]:
        try:
            return await asyncio.to_thread(self._list_entries_sync, filter_=filter_, limit=limit)
        except GcpLoggingError:
            raise
        except Exception as exc:
            raise GcpLoggingError(f"Google Cloud Logging query failed: {exc}") from exc


gcp_logging = GcpLoggingClient()
