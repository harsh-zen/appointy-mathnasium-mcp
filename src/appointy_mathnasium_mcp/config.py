import os
from typing import Literal

TransportType = Literal["stdio", "sse", "streamable-http"]


def bool_from_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def resolve_mcp_port(default: int = 8010) -> int:
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


def safe_int_from_env(name: str, default: int) -> int:
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
MCP_PORT = resolve_mcp_port(8010)
MCP_STREAMABLE_HTTP_PATH = os.getenv("MCP_STREAMABLE_HTTP_PATH", "/mcp")
MCP_SSE_PATH = os.getenv("MCP_SSE_PATH", "/sse")
MCP_JSON_RESPONSE = bool_from_env("MCP_JSON_RESPONSE", False)
MCP_STATELESS_HTTP = bool_from_env("MCP_STATELESS_HTTP", False)
MCP_LOG_LEVEL = os.getenv("MCP_LOG_LEVEL", "INFO").upper()

APPOINTY_API_BASE_URL = os.getenv("APPOINTY_API_BASE_URL", "").rstrip("/")
APPOINTY_API_KEY = os.getenv("APPOINTY_API_KEY")
MATHNASIUM_GROUP_ID = os.getenv("MATHNASIUM_GROUP_ID")
DEFAULT_SUPPORT_USER_ID = os.getenv("DEFAULT_SUPPORT_USER_ID")
DEFAULT_FIRST = safe_int_from_env("DEFAULT_FIRST", 25)
GROUP_CONTEXT_CACHE_TTL_SECONDS = safe_int_from_env("GROUP_CONTEXT_CACHE_TTL_SECONDS", 900)
APPOINTY_TIMEOUT_SECONDS = safe_int_from_env("APPOINTY_TIMEOUT_SECONDS", 20)
ENABLE_PII_MASKING = bool_from_env("ENABLE_PII_MASKING", False)
APPOINTY_BOOKING_URL_TEMPLATE = os.getenv("APPOINTY_BOOKING_URL_TEMPLATE", "https://mathnasium-booking.appointy.com/{locationSlug}")
GOOGLE_APPLICATION_CREDENTIALS_JSON = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "waqt-prod")
GCP_LOG_LOCATION = os.getenv("GCP_LOG_LOCATION", "europe-west1-c")
GCP_CLUSTER_NAME = os.getenv("GCP_CLUSTER_NAME", "mathphase2-prod-gke")
GCP_NAMESPACE = os.getenv("GCP_NAMESPACE", "prod")
GCP_POD_APP_LABEL = os.getenv("GCP_POD_APP_LABEL", "deployment")
GCP_LOG_DEFAULT_LOOKBACK_HOURS = safe_int_from_env("GCP_LOG_DEFAULT_LOOKBACK_HOURS", 48)
GCP_LOG_MAX_LIMIT = safe_int_from_env("GCP_LOG_MAX_LIMIT", 200)


def require_config():
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
